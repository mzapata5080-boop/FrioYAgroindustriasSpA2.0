"""Consulta del historial y registro transaccional e idempotente de ingresos y salidas."""
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.db import IntegrityError, transaction
from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from frio_agroindustria.api_common import allowed, error, data, schema, serialize as base_serialize
from inventario.api_forms import IngresoForm, SalidaForm
from inventario.fifo import registrar_salida_fifo, ConflictoSolicitudFIFO
from inventario.models import MovimientoBodega, RecepcionIngreso, Repuesto
from finanzas.forms import RecepcionDetalleForm
from finanzas.models import (
    FacturaCompra,
    FacturaCompraDetalle,
    RecepcionCompra,
    RecepcionDetalle,
)
from obras.models import Obra, SolicitudMaterial


def serialize(movement):
    row = base_serialize(movement)
    if movement.responsable_id:
        worker = movement.responsable
        row.update(responsable_id=worker.pk, responsable=worker.get_full_name().strip() or worker.username)
    if movement.obra_id:
        row.update(obra_id=movement.obra_id, obra_codigo=movement.obra.codigo_ot, obra_nombre=movement.obra.nombre)
    if movement.cliente_id:
        row.update(cliente_id=movement.cliente_id, cliente_nombre=str(movement.cliente))
    if movement.receptor_id:
        rec = movement.receptor
        row.update(receptor_id=rec.pk, receptor=rec.get_full_name().strip() or rec.username)
    elif movement.receptor_nombre:
        row.update(receptor_id=None, receptor=movement.receptor_nombre)
    if movement.observaciones:
        row['observaciones'] = movement.observaciones

    if movement.tipo == 'INGRESO':
        try:
            receipt = movement.recepcioningreso
            row.update({name: getattr(receipt, name) for name in ('cantidad_disponible',)})
        except RecepcionIngreso.DoesNotExist:
            pass
        try:
            detail = movement.detalle_recepcion_compra
            row.update(
                recepcion_id=str(detail.recepcion_id),
                detalle_factura_id=detail.detalle_factura_id,
            )
        except RecepcionDetalle.DoesNotExist:
            pass
    if movement.tipo == 'SALIDA':
        detalles = list(movement.detalles_fifo.all())
        row['detalles_fifo'] = [
            {
                'id': detalle.pk,
                'orden': detalle.orden,
                'lote_id': detalle.lote_id,
                'ingreso_id': detalle.lote.movimiento_id,
                'cantidad': detalle.cantidad,
                'precio_unitario': detalle.precio_unitario,
                'costo_asignado': detalle.costo_asignado,
            }
            for detalle in detalles
        ]
        row['detalle_fifo_estado'] = 'registrado' if detalles else 'historico_sin_detalle'
    if movement.tipo == 'DEVOLUCION':
        registro = movement.devolucion_fifo
        row.update(
            consumo_origen_id=registro.consumo_id,
            salida_origen_id=registro.consumo.salida_id,
            lote_origen_id=registro.consumo.lote_id,
            costo_reintegrado_fifo=registro.costo_reintegrado,
            consumo_original_id=registro.consumo_id,
            salida_original_id=registro.consumo.salida_id,
            lote_original_id=registro.consumo.lote_id,
            costo_reintegrado=registro.costo_reintegrado,
        )
    return row


def pending_invoice_details():
    details = (
        FacturaCompraDetalle.objects.select_related('factura__proveedor', 'articulo')
        .annotate(
            recibido=Coalesce(
                Sum('recepciones__cantidad'),
                Decimal('0.00'),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            )
        )
        .order_by('-factura__fecha', '-factura_id', 'pk')
    )
    items = []
    for detail in details:
        legacy_received = (
            RecepcionIngreso.objects.filter(
                factura_id=detail.factura_id,
                movimiento__repuesto_id=detail.articulo_id,
                movimiento__detalle_recepcion_compra__isnull=True,
            ).aggregate(
                total=Coalesce(
                    Sum('movimiento__cantidad'),
                    Decimal('0.00'),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                )
            )['total']
        )
        pending = detail.cantidad - detail.recibido - legacy_received
        total_recibido = detail.recibido + legacy_received
        pending = detail.cantidad - total_recibido
        if pending <= 0:
            continue
        items.append({
            'id': detail.pk,
            'factura_id': detail.factura_id,
            'factura_numero': detail.factura.numero_documento,
            'proveedor_nombre': detail.factura.proveedor.razon_social,
            'articulo_id': detail.articulo_id,
            'codigo_parte': detail.articulo.codigo_parte,
            'articulo_nombre': detail.articulo.descripcion,
            'unidad_medida': detail.articulo.unidad_medida,
            'cantidad_facturada': str(detail.cantidad),
            'cantidad_recibida': str(total_recibido),
            'pendiente': str(pending),
            'precio_unitario': str(detail.precio_unitario),
        })
    return items

def validate_receipt_details(raw_details, factura_id):
    if not isinstance(raw_details, list) or not raw_details:
        return None, {'recepcion_detalles': ['Debes indicar al menos un artículo recibido de la factura.']}
    quantities = {}
    errors = []
    for index, raw in enumerate(raw_details, start=1):
        if not isinstance(raw, dict):
            errors.append(f'Línea {index}: formato inválido.')
            continue
        form = RecepcionDetalleForm(raw)
        if not form.is_valid():
            msg = '; '.join(m for errs in form.errors.values() for m in errs)
            errors.append(f'Línea {index}: {msg}')
            continue
        detail = form.cleaned_data['detalle_factura']
        if detail.factura_id != factura_id:
            errors.append(f'Línea {index}: el detalle no pertenece a la factura seleccionada.')
            continue
        quantities[detail.pk] = quantities.get(detail.pk, Decimal('0.00')) + form.cleaned_data['cantidad']
    if errors:
        return None, {'recepcion_detalles': errors}

    details_map = {
        d.pk: d
        for d in FacturaCompraDetalle.objects.select_related('articulo')
        .filter(pk__in=quantities.keys())
        .annotate(
            recibido=Coalesce(
                Sum('recepciones__cantidad'),
                Decimal('0.00'),
                output_field=DecimalField(max_digits=15, decimal_places=2),
            )
        )
    }
    for detail_id, qty in quantities.items():
        detail = details_map.get(detail_id)
        if not detail:
            errors.append('Uno de los artículos de la factura ya no existe.')
            continue
        if detail.articulo.unidad_medida == 'unidad' and qty != qty.to_integral_value():
            errors.append(f'{detail.articulo.descripcion}: requiere cantidad entera por unidad.')
            continue
        legacy_received = (
            RecepcionIngreso.objects.filter(
                factura_id=factura_id,
                movimiento__repuesto_id=detail.articulo_id,
                movimiento__detalle_recepcion_compra__isnull=True,
            ).aggregate(
                total=Coalesce(
                    Sum('movimiento__cantidad'),
                    Decimal('0.00'),
                    output_field=DecimalField(max_digits=15, decimal_places=2),
                )
            )['total']
        )
        pending = detail.cantidad - detail.recibido - legacy_received
        if qty > pending:
            errors.append(
                f'{detail.articulo.descripcion}: excede la cantidad pendiente ({pending}).'
            )
    if errors:
        return None, {'recepcion_detalles': errors}
    return quantities, None


def repeated_receipt_response(receipt_compra, quantities, user):
    if receipt_compra.responsable_id != user.pk:
        return error('La solicitud ya fue usada por otro trabajador.', 409)
    existing_map = {
        d.detalle_factura_id: d.cantidad
        for d in receipt_compra.detalles.all()
    }
    if existing_map != quantities:
        return error('La solicitud ya fue usada con otros datos. Abre un ingreso nuevo.', 409)
    first_detail = receipt_compra.detalles.select_related('movimiento').first()
    item = serialize(first_detail.movimiento) if first_detail else {'recepcion_id': str(receipt_compra.pk)}
    return JsonResponse({'ok': True, 'repeated': True, 'item': item})


def repeated_response(receipt, values, user):
    """Compatibilidad con payload legado de 1 artículo."""
    same = (
        receipt.responsable_id == user.pk
        and receipt.factura_id == values['factura'].pk
        and receipt.movimiento.repuesto_id == values['articulo'].pk
        and receipt.movimiento.cantidad == values['cantidad']
        and receipt.precio_unitario_neto == values['precio']
    )
    if not same:
        return error('La solicitud ya fue usada con otros datos. Abre un ingreso nuevo.', 409)
    return JsonResponse({'ok': True, 'repeated': True, 'item': serialize(receipt.movimiento)})


def movements(request, resource):
    roles = ('gerencia',) if resource == 'kardex' else ('bodega', 'gerencia')
    if not allowed(request.user, roles):
        return error('No tienes permisos.', 403)
    if request.method == 'GET':
        qs = (
            MovimientoBodega.objects.select_related(
                'repuesto',
                'responsable',
                'receptor',
                'obra',
                'cliente',
                'recepcioningreso__responsable',
                'devolucion_fifo__consumo',
                'detalle_recepcion_compra__recepcion',
            )
            .prefetch_related('detalles_fifo__lote')
            .order_by('-fecha_registro', '-pk')
        )
        if resource != 'kardex':
            qs = qs.filter(tipo='INGRESO' if resource == 'ingresos' else 'SALIDA')
        fields = schema(IngresoForm() if resource == 'ingresos' else SalidaForm()) if resource != 'kardex' else []
        result = {
            'items': [serialize(x) for x in qs],
            'fields': fields,
            'can_write': resource in ('ingresos', 'salidas'),
            'can_delete': False,
        }
        if resource in ('ingresos', 'salidas'):
            result['articles'] = list(
                Repuesto.objects.filter(activo=True).values(
                    'id', 'codigo_parte', 'descripcion', 'unidad_medida', 'stock_actual', 'stock_reservado'
                )
            )
        if resource == 'salidas':
            result['works'] = list(
                Obra.objects.exclude(estado='CERRADA').values('id', 'cliente_id', 'codigo_ot')
            )
            result['materialRequests'] = [
                {
                    'id': solicitud.pk,
                    'obra_id': solicitud.obra_id,
                    'articulo_id': solicitud.articulo_id,
                    'cantidad_pendiente': str(solicitud.cantidad_pendiente),
                }
                for solicitud in SolicitudMaterial.objects.filter(
                    estado__in=('APROBADA', 'PARCIAL')
                ).only(
                    'id', 'obra_id', 'articulo_id', 'cantidad_reservada', 'cantidad_entregada'
                )
            ]
        if resource == 'ingresos':
            invoice_details = pending_invoice_details()
            pending_invoice_ids = {str(detail['factura_id']) for detail in invoice_details}
            for field in fields:
                if field['name'] == 'factura':
                    field['choices'] = [
                        choice
                        for choice in field['choices']
                        if choice[0] == '' or choice[0] in pending_invoice_ids
                    ]
            fields.append({
                'name': 'recepcion_detalles',
                'label': 'Artículos recibidos',
                'type': 'receipt_details',
                'required': True,
            })
            result['invoiceDetails'] = invoice_details
        if resource == 'kardex':
            from inventario.operaciones_api import enriquecer_kardex
            enriquecer_kardex(result['items'])

        return JsonResponse(result)

    if resource == 'salidas':
        return registrar_salida(request)
    if resource != 'ingresos':
        return error('Solo se permite registrar ingresos.', 405)

    payload = data(request)
    if any(name in payload for name in ('descuento_1', 'descuento_2', 'descuento_3', 'costo_unitario_final')):
        return error('Este ingreso no admite descuentos porcentuales. Recarga el formulario actualizado.')

    raw_details = payload.pop('recepcion_detalles', None)
    form = IngresoForm(payload)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    values = form.cleaned_data

    quantities, detail_errors = validate_receipt_details(raw_details, values['factura'].pk)
    if detail_errors:
        return JsonResponse({'errors': detail_errors}, status=400)

    try:
        with transaction.atomic():
            previous_compra = RecepcionCompra.objects.filter(solicitud_id=values['solicitud_id']).first()
            if previous_compra:
                return repeated_receipt_response(previous_compra, quantities, request.user)
            
            previous_legacy = RecepcionIngreso.objects.filter(solicitud_id=values['solicitud_id']).first()
            if previous_legacy:
                return error('La solicitud ya fue usada con otros datos. Abre un ingreso nuevo.', 409)

            recepcion_compra = RecepcionCompra.objects.create(
                solicitud_id=values['solicitud_id'],
                factura=values['factura'],
                responsable=request.user,
            )
            created_movements = []
            for idx, (detail_id, qty) in enumerate(quantities.items()):
                detail_line = FacturaCompraDetalle.objects.select_for_update().select_related('articulo').get(pk=detail_id)
                article = Repuesto.objects.select_for_update().get(pk=detail_line.articulo_id)
                already_received = (
                    RecepcionDetalle.objects.filter(detalle_factura=detail_line).aggregate(
                        total=Coalesce(Sum('cantidad'), Decimal('0.00'))
                    )['total']
                )
                if already_received + qty > detail_line.cantidad:
                    return error(f'La cantidad recibida de {article.codigo_parte} supera lo facturado.', 400)
                if article.unidad_medida == 'unidad' and qty != qty.to_integral_value():
                    return error(f'Debe ser una cantidad entera para {article.codigo_parte}.', 400)
                new_stock = article.stock_actual + qty
                if new_stock > Decimal('9999999999999.99'):
                    return error('El stock excede el máximo permitido.', 400)

                movement = MovimientoBodega.objects.create(
                    tipo='INGRESO',
                    cantidad=qty,
                    repuesto=article,
                    responsable=request.user,
                )
                lote_uuid = values['solicitud_id'] if idx == 0 else uuid.uuid4()
                RecepcionIngreso.objects.create(
                    solicitud_id=lote_uuid,
                    factura=values['factura'],
                    movimiento=movement,
                    responsable=request.user,
                    unidad_medida=article.unidad_medida,
                    precio_unitario_neto=detail_line.precio_unitario,
                    cantidad_disponible=qty,
                    subtotal_neto=(qty * detail_line.precio_unitario).quantize(
                        Decimal('.01'), rounding=ROUND_HALF_UP
                    ),
                )
                RecepcionDetalle.objects.create(
                    recepcion=recepcion_compra,
                    detalle_factura=detail_line,
                    movimiento=movement,
                    cantidad=qty,
                )
                article.stock_actual = new_stock
                article.save(update_fields=['stock_actual'])
                created_movements.append(movement)
    except IntegrityError:
        previous_compra = RecepcionCompra.objects.filter(solicitud_id=values['solicitud_id']).first()
        if previous_compra:
            return repeated_receipt_response(previous_compra, quantities, request.user)
        return error('No se pudo registrar: datos inválidos. Actualiza la lista.')

    return JsonResponse(
        {
            'item': serialize(created_movements[0]),
            'items': [serialize(m) for m in created_movements],
            'recepcion_id': str(recepcion_compra.pk),
        },
        status=201,
    )


def registrar_salida(request):
    form = SalidaForm(data(request))
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    values = form.cleaned_data
    try:
        resultado = registrar_salida_fifo(
            articulo_id=values['articulo'].pk,
            cantidad=values['cantidad'],
            numero_ot=values['numero_ot'],
            responsable_id=request.user.pk,
            solicitud_id=values['solicitud_id'],
            obra_id=values['obra'].pk if values.get('obra') else None,
            cliente_id=values['cliente'].pk if values.get('cliente') else None,
            solicitud_material_id=values['solicitud_material'].pk if values.get('solicitud_material') else None,
            receptor_id=values['receptor'].pk if values.get('receptor') else None,
            receptor_nombre=values.get('receptor_nombre', ''),
            observaciones=values.get('observaciones', ''),
        )
    except ConflictoSolicitudFIFO as exc:
        return error(' '.join(exc.messages), 409)
    except ValidationError as exc:
        return error(' '.join(exc.messages))
    except Repuesto.DoesNotExist:
        return error('El artículo ya no existe. Actualiza la lista.')
    except IntegrityError:
        return error('No se pudo registrar la salida. Revisa los datos.')
    payload = {'item': serialize(resultado.movimiento)}
    if resultado.repetida:
        payload.update(ok=True, repeated=True)
    return JsonResponse(payload, status=200 if resultado.repetida else 201)