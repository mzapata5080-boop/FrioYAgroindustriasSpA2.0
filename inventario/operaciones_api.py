from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction, connection
from django.http import JsonResponse, FileResponse
from django.shortcuts import get_object_or_404
from frio_agroindustria.api_common import allowed, data, error, schema, permission_denied
from frio_agroindustria.common import save_private_file, open_private_file, private_storage, registrar_cambio
from frio_agroindustria.models import ArchivoPrivado
from inventario.models import (OperacionInventario, MovimientoOperacion, MovimientoBodega, Repuesto, RecepcionIngreso,)
from inventario.fifo import ConflictoSolicitudFIFO
from inventario.operaciones import registrar_operacion, pendiente, salida_de_obra
from inventario.operaciones_forms import OperacionForm, CAMPOS_POR_TIPO, OPCIONALES
from obras.models import Obra


def permitido(request):
    if not request.user.is_authenticated:
        return error('Inicia sesión.', 401)
    if not allowed(request.user, ('bodega', 'gerencia')):
        return permission_denied()
    return None


def serializar(op):
    return {
        'id': str(op.pk), 'tipo': op.tipo, 'nombre': op.get_tipo_display(),
        'fecha': op.fecha.isoformat(), 'articulo': str(op.articulo),
        'cantidad': str(op.cantidad), 'unidad': op.articulo.unidad_medida,
        'articulo_nuevo': str(op.articulo_nuevo) if op.articulo_nuevo_id else '',
        'cantidad_nueva': str(op.cantidad_nueva) if op.cantidad_nueva is not None else '',
        'obra': op.obra.codigo_ot if op.obra_id else '',
        'origen': op.origen_id, 'lote': str(op.lote_id) if op.lote_id else '',
        'proveedor': str(op.lote.factura.proveedor) if op.lote_id else '',
        'documento_compra': op.lote.factura.numero_documento if op.lote_id else '',
        'destino': op.destino, 'motivo': op.motivo,
        'responsable_id': op.responsable_id,
        'responsable': op.responsable.get_full_name().strip() or op.responsable.username,
        'anulada': OperacionInventario.objects.filter(anula_a=op).exists(),
        'anula_a': str(op.anula_a_id) if op.anula_a_id else None,
        'movimiento_anulado': op.movimiento_anulado_id,
    }


def operaciones(request):
    rechazo = permitido(request)
    if rechazo is not None:
        return rechazo
    tablas = set(connection.introspection.table_names())
    requeridas = {'inventario_operacioninventario', 'inventario_movimientooperacion','inventario_mermaconsumoobra',}
    if not requeridas.issubset(tablas):
        return error('Falta aplicar la migración de operaciones especiales en la base que usa Django.', 503)
    if request.method == 'POST':
        form = OperacionForm(data(request))
        if not form.is_valid():
            return JsonResponse({'errors': form.errors}, status=400)
        if form.cleaned_data['tipo'] == 'ANULAR' and not (request.user.is_superuser or request.user.rol == 'gerencia'):
            return permission_denied()
        try:
            op, repetida = registrar_operacion(form.cleaned_data, request.user)
        except ConflictoSolicitudFIFO as exc:
            return error(' '.join(exc.messages), 409)
        except ValidationError as exc:
            return error(' '.join(exc.messages))
        return JsonResponse({'item': serializar(op), 'repetida': repetida}, status=200 if repetida else 201)
    if request.method != 'GET':
        return error('Método no permitido.', 405)
    salidas, salidas_anulables = [], []
    for salida in MovimientoBodega.objects.filter(tipo='SALIDA').select_related('repuesto', 'obra'):
        enlace = MovimientoOperacion.objects.filter(movimiento=salida).first()
        if not enlace and not OperacionInventario.objects.filter(movimiento_anulado=salida).exists():
            salidas_anulables.append({'id': salida.pk, 'label': f'#{salida.pk} — {salida.repuesto} — {salida.cantidad}'})
        try:
            salida_de_obra(salida, exigir_obra=True)
            saldo = sum((pendiente(c) for c in salida.detalles_fifo.all()), Decimal('0'))
        except ValidationError:
            continue
        if saldo > 0:
            salidas.append({'id': salida.pk, 'obra': salida.obra_id,'label': f'#{salida.pk} — {salida.obra.codigo_ot if salida.obra_id else salida.numero_ot} — {salida.repuesto} — pendiente {saldo} {salida.repuesto.unidad_medida}'})
    queryset = OperacionInventario.objects.select_related('articulo', 'articulo_nuevo', 'obra', 'responsable', 'lote__factura__proveedor'
    ).order_by('-fecha')
    items = [serializar(op) for op in queryset]
    return JsonResponse({
        'items': items,
        'campos': schema(OperacionForm()),
        'campos_por_tipo': CAMPOS_POR_TIPO,
        'opcionales': sorted(OPCIONALES),
        'tipos': [{'id': k, 'label': v} for k, v in OperacionInventario.TIPOS
                  if k != 'ANULAR' or request.user.is_superuser or request.user.rol == 'gerencia'],
        'articulos': [{'id': a.pk, 'label': f'{a} — {a.unidad_medida} — disponible {a.stock_disponible}'}
                      for a in Repuesto.objects.filter(activo=True)],
        'obras': [{'id': o.pk, 'label': f'{o.codigo_ot} — {o.nombre}'} for o in Obra.objects.all()],
        'salidas': salidas, 'salidas_anulables': salidas_anulables,
        'operaciones_anulables': [{'id': x['id'], 'label': f'{x["nombre"]} — {x["articulo"]} — {x["cantidad"]} — {x["id"]}'}
                                 for x in items if not x['anulada'] and x['tipo'] != 'ANULAR'],
        'lotes': [{'id': str(l.pk),
                   'label': f'Ingreso #{l.movimiento_id} — {l.movimiento.repuesto} — proveedor {l.factura.proveedor} — doc. {l.factura.numero_documento} — disponible {l.cantidad_disponible}'}
                  for l in RecepcionIngreso.objects.filter(cantidad_disponible__gt=0).select_related(
                      'movimiento__repuesto', 'factura__proveedor')],
    })


def documentos(request, operacion_id):
    rechazo = permitido(request)
    if rechazo is not None:
        return rechazo
    op = get_object_or_404(OperacionInventario, pk=operacion_id)
    if request.method == 'GET':
        docs = ArchivoPrivado.objects.filter(modulo='inventario_operaciones',
            modelo='inventario.operacioninventario', objeto_id=str(op.pk))
        return JsonResponse({'items': list(docs.values('id', 'nombre_original', 'tamano_bytes', 'creado_el'))})
    if request.method != 'POST':
        return error('Método no permitido.', 405)
    upload = request.FILES.get('archivo')
    meta = None
    try:
        meta = save_private_file(upload, 'inventario_operaciones', allowed_exts={'.pdf', '.png', '.jpg', '.jpeg'})
        with transaction.atomic():
            doc = ArchivoPrivado.objects.create(modulo='inventario_operaciones', modelo='inventario.operacioninventario',objeto_id=str(op.pk), subido_por=request.user, **meta,)
            registrar_cambio(request.user, 'CREAR', doc)
    except ValidationError as exc:
        if meta:
            private_storage().delete(meta['ruta_privada'])
        return error(' '.join(exc.messages))
    except Exception:
        if meta:
            private_storage().delete(meta['ruta_privada'])
        raise
    return JsonResponse({'item': {'id': doc.pk, 'nombre_original': doc.nombre_original}}, status=201)


def descargar_documento(request, operacion_id, archivo_id):
    rechazo = permitido(request)
    if rechazo is not None:
        return rechazo
    if request.method != 'GET':
        return error('Método no permitido.', 405)
    get_object_or_404(OperacionInventario, pk=operacion_id)
    doc = get_object_or_404(ArchivoPrivado, pk=archivo_id, modulo='inventario_operaciones',
        modelo='inventario.operacioninventario', objeto_id=str(operacion_id))
    try:
        archivo = open_private_file(doc.ruta_privada)
    except FileNotFoundError:
        return error('El archivo no está disponible en el almacenamiento privado.', 404)
    return FileResponse(archivo, as_attachment=True, filename=doc.nombre_original)


def enriquecer_kardex(items):
    if 'inventario_operacioninventario' not in connection.introspection.table_names():
        return
    enlaces = {e.movimiento_id: e for e in MovimientoOperacion.objects.select_related('operacion')}
    for row in items:
        enlace = enlaces.get(row.get('id'))
        op = enlace.operacion if enlace else None
        row.update(
            clase_movimiento=op.tipo if op else row['tipo'],
            operacion_id=str(op.pk) if op else '', motivo_operacion=op.motivo if op else '',
            destino=op.destino if op else '',
            referencia_movimiento=(op.origen_id or op.movimiento_anulado_id) if op else None,
            referencia_operacion=str(op.anula_a_id) if op and op.anula_a_id else '',
            referencia_lote=str(op.lote_id) if op and op.lote_id else '',
            variacion_stock_bodega=(-Decimal(str(row['cantidad'])) if row['tipo'] == 'SALIDA'
                else Decimal(str(row['cantidad'])) if row['tipo'] in ('INGRESO', 'DEVOLUCION') else None),
        )
    virtuales = OperacionInventario.objects.filter(tipo='MERMA_OBRA') | OperacionInventario.objects.filter(
        tipo='ANULAR', anula_a__tipo='MERMA_OBRA')
    for op in virtuales.select_related('responsable', 'articulo', 'obra'):
        row = {k: None for k in items[0]} if items else {}
        row.update(id='OP-' + str(op.pk), tipo=op.tipo, clase_movimiento=op.tipo,
            operacion_id=str(op.pk), articulo=str(op.articulo), fecha_registro=op.fecha,
            cantidad=op.cantidad, variacion_stock_bodega=Decimal('0'), costo_total_fifo=None,
            responsable_id=op.responsable_id,
            responsable=op.responsable.get_full_name().strip() or op.responsable.username,
            obra_codigo=op.obra.codigo_ot if op.obra_id else '',
            motivo_operacion=op.motivo, observaciones=op.motivo,
            destino='', referencia_movimiento=op.origen_id or (op.anula_a.origen_id if op.anula_a_id else None),
            referencia_operacion=str(op.anula_a_id) if op.anula_a_id else '', referencia_lote='')
        items.append(row)
    items.sort(key=lambda r: str(r.get('fecha_registro') or ''), reverse=True)