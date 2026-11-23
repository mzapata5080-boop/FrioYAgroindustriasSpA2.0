from decimal import Decimal
from uuid import uuid5
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from inventario.models import (Repuesto, MovimientoBodega, RecepcionIngreso, DetalleConsumoFIFO,OperacionInventario, MovimientoOperacion, MermaConsumoObra,)
from inventario.fifo import (consumir_fifo, costo_consumo_lote, registrar_salida_fifo, ConflictoSolicitudFIFO,)
from inventario.devoluciones import registrar_devolucion_fifo
from frio_agroindustria.common import registrar_cambio

CERO = Decimal('0')


def devueltos_vigentes(consumo):
    return consumo.devoluciones.exclude( movimiento__detalle_operacion__operacion__anulada_por__isnull=False)

def cantidad_mermada(consumo):
    return MermaConsumoObra.objects.filter(consumo=consumo,operacion__anulada_por__isnull=True).aggregate(total=Sum('cantidad'))['total'] or CERO

def pendiente(consumo):
    devuelto = devueltos_vigentes(consumo).aggregate(total=Sum('cantidad'))['total'] or CERO
    valor = consumo.cantidad - devuelto - cantidad_mermada(consumo)
    if valor < 0:
        raise ValidationError('El historial del consumo es inconsistente.')
    return valor

def salida_de_obra(salida, exigir_obra=False):
    if salida.tipo != 'SALIDA' or (exigir_obra and salida.obra_id is None):
        raise ValidationError('Selecciona una salida válida' + (' asociada a una Obra.' if exigir_obra else '.'))
    if OperacionInventario.objects.filter(movimiento_anulado=salida).exists():
        raise ValidationError('La salida está anulada.')
    enlace = MovimientoOperacion.objects.select_related('operacion').filter(movimiento=salida).first()
    if enlace and (
        enlace.funcion != 'SALIDA_CAMBIO'
        or OperacionInventario.objects.filter(anula_a=enlace.operacion).exists()
        ):
        raise ValidationError('Ese movimiento no es una entrega vigente a una Obra.')
    return salida


def identificar_solicitud(datos):
    resultado = {}
    for key, value in datos.items():
        if key == 'solicitud_id':
            continue
        if hasattr(value, 'pk'):
            value = str(value.pk)
        elif isinstance(value, Decimal):
            value = format(value.quantize(Decimal('.01')), 'f')
        resultado[key] = value
    return resultado


def vincular_movimiento(operacion, movimiento, funcion):
    MovimientoOperacion.objects.create(operacion=operacion, movimiento=movimiento, funcion=funcion)


def descontar_bodega(operacion, articulo, cantidad, *, lote=None, costo_exacto=None, funcion='SALIDA'):
    articulo.refresh_from_db()
    if articulo.unidad_medida == 'unidad' and cantidad != cantidad.to_integral_value():
        raise ValidationError('La cantidad debe ser entera para artículos por unidad.')
    if cantidad > articulo.stock_disponible:
        raise ValidationError('No alcanza el stock disponible; no se pueden consumir reservas.')
    if lote is None:
        if not articulo.activo:
            raise ValidationError('El artículo está inactivo.')
        resultado = consumir_fifo(articulo, cantidad)
        costo = resultado.costo_total
        detalles = [(c.lote_id, c.cantidad, c.precio_unitario, c.costo_asignado) for c in resultado.consumos]
    else:
        lote = RecepcionIngreso.objects.select_for_update().get(pk=lote.pk)
        if lote.movimiento.repuesto_id != articulo.pk or cantidad > lote.cantidad_disponible:
            raise ValidationError('El lote original no tiene cantidad suficiente.')
        if costo_exacto is not None:
            valor = costo_consumo_lote(lote, lote.cantidad_disponible)
            if costo_exacto > valor:
                raise ValidationError('El lote no conserva el valor necesario para compensar la devolución.')
            costo = costo_exacto
        else:
            costo = costo_consumo_lote(lote, cantidad)
        detalles = [(lote.pk, cantidad, lote.precio_unitario_neto, costo)]
        lote.cantidad_disponible -= cantidad
        lote.save(update_fields=['cantidad_disponible'])
    movimiento = MovimientoBodega.objects.create(
        tipo='SALIDA', repuesto=articulo, cantidad=cantidad, costo_total_fifo=costo,
        responsable=operacion.responsable, obra_id=operacion.obra_id,
        cliente_id=operacion.obra.cliente_id if operacion.obra_id else None,
        numero_ot=operacion.obra.codigo_ot if operacion.obra_id else '',
        observaciones=f'{operacion.get_tipo_display()}: {operacion.motivo}'[:1500],
    )
    
    DetalleConsumoFIFO.objects.bulk_create([
        DetalleConsumoFIFO(salida=movimiento, lote_id=l, orden=i, cantidad=q,
                           precio_unitario=p, costo_asignado=c)
        for i, (l, q, p, c) in enumerate(detalles, 1)
        ])
    
    articulo.stock_actual -= cantidad
    articulo.save(update_fields=['stock_actual'])
    vincular_movimiento(operacion, movimiento, funcion)
    return movimiento


def reintegrar_lotes(operacion, salida, cantidad, *, compensacion=False):
    consumos = list(DetalleConsumoFIFO.objects.select_for_update().filter(
        salida=salida).order_by('orden'))
    if not consumos or cantidad > sum((pendiente(c) for c in consumos), CERO):
        raise ValidationError('La devolución supera lo entregado pendiente o falta el detalle FIFO original.')
    por_devolver = cantidad
    for consumo in consumos:
        tomar = min(por_devolver, pendiente(consumo))
        if tomar <= 0:
            continue
        resultado = registrar_devolucion_fifo(
            consumo_id=consumo.pk, cantidad=tomar, responsable_id=operacion.responsable_id,
            solicitud_id=uuid5(operacion.pk, f'devolucion:{salida.pk}:{consumo.pk}'),
            compensacion=compensacion,
        )
        vincular_movimiento(operacion, resultado.devolucion.movimiento, 'REINTEGRO')
        por_devolver -= tomar
        if not por_devolver:
            break


def compensar_salida(operacion, salida):
    consumos = list(DetalleConsumoFIFO.objects.filter(salida=salida))
    if not consumos or sum((c.cantidad for c in consumos), CERO) != salida.cantidad:
        raise ValidationError('No se puede anular: falta la trazabilidad FIFO completa.')
    if any(pendiente(c) != c.cantidad for c in consumos):
        raise ValidationError('No se puede anular: la salida tiene devoluciones o mermas posteriores vigentes.')
    reintegrar_lotes(operacion, salida, salida.cantidad, compensacion=True)


def anular(operacion, original, movimiento):
    if original:
        if original.tipo == 'ANULAR':
            raise ValidationError('No se permite anular una anulación.')
        if OperacionInventario.objects.filter(anula_a=original).exists():
            raise ValidationError('La operación ya está anulada.')
        if original.tipo == 'MERMA_OBRA':
            return
        relaciones = list(original.movimientos.select_related(
            'movimiento__repuesto', 'movimiento__devolucion_fifo__consumo__lote').order_by('pk'))
        for relacion in relaciones:
            if relacion.movimiento.tipo == 'SALIDA':
                compensar_salida(operacion, relacion.movimiento)
        for relacion in relaciones:
            if relacion.movimiento.tipo != 'DEVOLUCION':
                continue
            dev = relacion.movimiento.devolucion_fifo
            descontar_bodega(operacion, dev.consumo.salida.repuesto, dev.cantidad,
                lote=dev.consumo.lote, costo_exacto=dev.costo_reintegrado,
                funcion='REVERSO_REINTEGRO')
    else:
        if movimiento.tipo != 'SALIDA' or MovimientoOperacion.objects.filter(movimiento=movimiento).exists():
            raise ValidationError('Selecciona una salida original de BC2 o anula la operación completa que la generó.')
        if OperacionInventario.objects.filter(movimiento_anulado=movimiento).exclude(pk=operacion.pk).exists():
            raise ValidationError('La salida ya está anulada.')
        compensar_salida(operacion, movimiento)


def ejecutar_operacion(operacion, datos):
    articulo = operacion.articulo
    origen = operacion.origen
    lote = operacion.lote
    obra = operacion.obra
    articulo_nuevo = operacion.articulo_nuevo
    cantidad = operacion.cantidad
    actor = operacion.responsable
    objetivo = datos.get('anula_a')
    movimiento = datos.get('movimiento_anulado')
    if operacion.tipo in ('MERMA_BODEGA', 'USO_INTERNO'):
        descontar_bodega(operacion, articulo, cantidad)
    elif operacion.tipo == 'DEV_PROVEEDOR':
        descontar_bodega(operacion, articulo, cantidad, lote=lote)
    elif operacion.tipo in ('DEV_BODEGA', 'CAMBIO'):
        reintegrar_lotes(operacion, origen, cantidad)
        if operacion.tipo == 'CAMBIO':
            if articulo_nuevo.pk == articulo.pk:
                raise ValidationError('El artículo de reemplazo debe ser distinto del original.')
            resultado = registrar_salida_fifo(
                articulo_id=articulo_nuevo.pk, cantidad=datos['cantidad_nueva'],
                responsable_id=actor.pk, solicitud_id=uuid5(operacion.pk, 'salida-cambio'),
                obra_id=obra.pk, observaciones='Cambio de artículo: ' + operacion.motivo,)
            vincular_movimiento(operacion, resultado.movimiento, 'SALIDA_CAMBIO')
    elif operacion.tipo == 'MERMA_OBRA':
        restante = cantidad
        for consumo in DetalleConsumoFIFO.objects.select_for_update().filter(salida=origen).order_by('orden'):
            tomar = min(restante, pendiente(consumo))
            if tomar > 0:
                MermaConsumoObra.objects.create(operacion=operacion, consumo=consumo, cantidad=tomar)
                restante -= tomar
        if restante:
            raise ValidationError('La merma supera la cantidad entregada pendiente.')
    elif operacion.tipo == 'ANULAR':
        anular(operacion, objetivo, movimiento)
        if objetivo:
            operacion.anula_a = objetivo
            operacion.save(update_fields=['anula_a'])


def registrar_operacion(datos, actor):
    huella = identificar_solicitud(datos)
    origen = datos.get('origen')
    lote = datos.get('lote')
    objetivo = datos.get('anula_a')
    movimiento = datos.get('movimiento_anulado')
    if objetivo:
        articulo, obra = objetivo.articulo, objetivo.obra
        articulo_nuevo = objetivo.articulo_nuevo
    elif movimiento:
        articulo, obra = movimiento.repuesto, movimiento.obra
        articulo_nuevo = None
    elif origen:
        articulo, obra = origen.repuesto, origen.obra
        articulo_nuevo = datos.get('articulo_nuevo')
    elif lote:
        articulo, obra = lote.movimiento.repuesto, None
        articulo_nuevo = None
    else:
        articulo, obra = datos.get('articulo'), datos.get('obra')
        articulo_nuevo = None
    if articulo is None:
        raise ValidationError('Falta identificar el artículo.')
    ids = {articulo.pk}
    if articulo_nuevo:
        ids.add(articulo_nuevo.pk)
    try:
        with transaction.atomic():
            bloqueados = {a.pk: a for a in Repuesto.objects.select_for_update().filter(pk__in=ids).order_by('pk')}
            anterior = OperacionInventario.objects.filter(pk=datos['solicitud_id']).first()
            if anterior:
                if anterior.responsable_id != actor.pk or anterior.datos_solicitud != huella:
                    raise ConflictoSolicitudFIFO('Esta solicitud ya se utilizó con otros datos o trabajador.')
                return anterior, True
            articulo = bloqueados[articulo.pk]
            if origen:
                origen = MovimientoBodega.objects.select_for_update().get(pk=origen.pk)
                salida_de_obra(origen, exigir_obra=datos['tipo'] in ('MERMA_OBRA', 'CAMBIO'))
            if datos['tipo'] == 'ANULAR':
                if not actor.is_superuser and actor.rol != 'gerencia':
                    raise ValidationError('Solo Gerencia puede autorizar anulaciones.')
                if objetivo:
                    objetivo = OperacionInventario.objects.select_for_update().get(pk=objetivo.pk)
                    if OperacionInventario.objects.filter(anula_a=objetivo).exists():
                        raise ValidationError('La operación ya está anulada.')
                elif OperacionInventario.objects.filter(movimiento_anulado=movimiento).exists():
                    raise ValidationError('La salida ya está anulada.')
            cantidad = (objetivo.cantidad if objetivo else movimiento.cantidad) if datos['tipo'] == 'ANULAR' else datos['cantidad']
            if articulo.unidad_medida == 'unidad' and cantidad != cantidad.to_integral_value():
                raise ValidationError('El artículo requiere cantidad entera.')
            operacion = OperacionInventario.objects.create(
                solicitud_id=datos['solicitud_id'], tipo=datos['tipo'], articulo=articulo,
                articulo_nuevo=articulo_nuevo, origen=origen, lote=lote, obra=obra,
                cantidad=cantidad, cantidad_nueva=datos.get('cantidad_nueva'),
                motivo=datos['motivo'], destino=datos.get('destino', ''), responsable=actor,
                datos_solicitud=huella,
                movimiento_anulado=movimiento,
                )
            ejecutar_operacion(operacion, datos)
            registrar_cambio(actor, 'CREAR', operacion)
            for relacion in operacion.movimientos.select_related('movimiento'):
                registrar_cambio(actor, 'CREAR', relacion.movimiento)
            return operacion, False
    except IntegrityError:
        anterior = OperacionInventario.objects.filter(pk=datos['solicitud_id']).first()
        if anterior and anterior.responsable_id == actor.pk and anterior.datos_solicitud == huella:
            return anterior, True
        raise ConflictoSolicitudFIFO('Otra solicitud modificó esta operación. Recarga antes de continuar.')