"""Servicio interno de devolución: permisos y autorización pertenecen al llamador."""
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum

from inventario.fifo import CENTAVO, ConflictoSolicitudFIFO, costo_repartido
from inventario.models import DetalleConsumoFIFO, DevolucionFIFO, MovimientoBodega, RecepcionIngreso, Repuesto


@dataclass(frozen=True)
class ResultadoDevolucionFIFO:
    devolucion: DevolucionFIFO
    repetida: bool


def _repetida(registro, consumo_id, cantidad, responsable_id):
    if (registro.consumo_id != consumo_id or registro.cantidad != cantidad
            or registro.movimiento.responsable_id != responsable_id):
        raise ConflictoSolicitudFIFO('La clave de devolución ya fue usada con otros datos.')
    return ResultadoDevolucionFIFO(registro, True)


def registrar_devolucion_fifo(*, consumo_id, cantidad, responsable_id, solicitud_id):
    """Devuelve una cantidad de un detalle original a su lote y acredita su costo.

    Una devolución de varios lotes se invoca por cada detalle, con claves propias,
    dentro de una transacción del llamador si requiere atomicidad del conjunto.
    No acepta precio ni un lote elegido por el cliente. Requiere permisos previos.
    """
    if type(consumo_id) is not int or consumo_id <= 0 or type(responsable_id) is not int or responsable_id <= 0:
        raise ValidationError('Indica identificadores válidos de consumo y responsable.')
    if (not isinstance(cantidad, Decimal) or not cantidad.is_finite() or cantidad <= 0
            or cantidad > Decimal('9999999999999.99') or cantidad.quantize(CENTAVO) != cantidad):
        raise ValidationError('La cantidad debe ser Decimal positiva con hasta dos decimales.')
    try:
        solicitud_id = UUID(str(solicitud_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError('La clave de devolución debe ser un UUID válido.') from exc
    try:
        with transaction.atomic():
            origen = DetalleConsumoFIFO.objects.select_related('salida').get(pk=consumo_id)
            articulo = Repuesto.objects.select_for_update().get(pk=origen.salida.repuesto_id)
            anterior = DevolucionFIFO.objects.select_related('movimiento').filter(pk=solicitud_id).first()
            if anterior:
                return _repetida(anterior, consumo_id, cantidad, responsable_id)
            consumo = DetalleConsumoFIFO.objects.select_for_update(of=('self',)).select_related('salida').get(pk=consumo_id)
            lote = RecepcionIngreso.objects.select_for_update(of=('self',)).select_related('movimiento').get(pk=consumo.lote_id)
            if consumo.salida.tipo != 'SALIDA' or lote.movimiento.repuesto_id != articulo.pk:
                raise ValidationError('El detalle no corresponde a una salida y un lote del mismo artículo.')
            if articulo.unidad_medida == 'unidad' and cantidad != cantidad.to_integral_value():
                raise ValidationError('La cantidad debe ser entera para artículos por unidad.')
            devuelto = consumo.devoluciones.aggregate(cantidad=Sum('cantidad'), costo=Sum('costo_reintegrado'))
            acumulado = devuelto['cantidad'] or Decimal('0')
            costo_previo = (costo_repartido(consumo.cantidad, consumo.costo_asignado, Decimal('0'), acumulado)
                if acumulado else Decimal('0.00'))
            if (devuelto['costo'] or Decimal('0')) != costo_previo:
                raise ValidationError('El historial de costos devueltos de este consumo es inconsistente.')
            if cantidad > consumo.cantidad - acumulado:
                raise ValidationError('La devolución supera la cantidad pendiente de este consumo.')
            if (lote.cantidad_disponible + cantidad > lote.movimiento.cantidad
                    or articulo.stock_actual + cantidad > Decimal('9999999999999.99')):
                raise ValidationError('La devolución excede el saldo permitido del lote o artículo.')
            costo = costo_repartido(consumo.cantidad, consumo.costo_asignado, acumulado, cantidad)
            movimiento = MovimientoBodega.objects.create(tipo='DEVOLUCION', cantidad=cantidad,
                repuesto=articulo, numero_ot=consumo.salida.numero_ot,
                responsable_id=responsable_id, costo_total_fifo=costo)
            registro = DevolucionFIFO.objects.create(solicitud_id=solicitud_id, consumo=consumo,
                movimiento=movimiento, cantidad=cantidad, costo_reintegrado=costo)
            lote.cantidad_disponible += cantidad
            lote.save(update_fields=['cantidad_disponible'])
            articulo.stock_actual += cantidad
            articulo.save(update_fields=['stock_actual'])
            return ResultadoDevolucionFIFO(registro, False)
    except IntegrityError:
        anterior = DevolucionFIFO.objects.select_related('movimiento').filter(pk=solicitud_id).first()
        if anterior:
            return _repetida(anterior, consumo_id, cantidad, responsable_id)
        raise
