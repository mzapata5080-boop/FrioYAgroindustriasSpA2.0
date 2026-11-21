"""Consulta del historial y registro transaccional e idempotente de ingresos."""
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
    RecepcionDetalle
)


def serialize(movement):
    row = base_serialize(movement)
    if movement.responsable_id:
        worker = movement.responsable
        row.update(responsable_id=worker.pk, responsable=worker.get_full_name().strip() or worker.username)
    if movement.tipo == 'INGRESO':
        try:
            receipt = movement.recepcioningreso
            row.update({name: getattr(receipt, name) for name in (
                'cantidad_disponible',)})
        except RecepcionIngreso.DoesNotExist:
            pass
        try:
            detail = movement.detalle_recepcion_compra
            row.update(
                recepcion_id=str(detail.recepcion_id),
                detalle_factura_id=detail.detalle_factura_id
            )
        except RecepcionDetalle.DoesNotExist:
            pass
    if movement.tipo == 'SALIDA':
        detalles = list(movement.detalles_fifo.all())
        row['detalles_fifo'] = [
            {'id': detalle.pk, 'orden': detalle.orden, 'lote_id': detalle.lote_id,
             'ingreso_id': detalle.lote.movimiento_id, 'cantidad': detalle.cantidad,
             'precio_unitario': detalle.precio_unitario, 'costo_asignado': detalle.costo_asignado}
            for detalle in detalles
        ]
        row['detalle_fifo_estado'] = 'registrado' if detalles else 'historico_sin_detalle'
    if movement.tipo == 'DEVOLUCION':
        registro = movement.devolucion_fifo
        row.update(consumo_origen_id=registro.consumo_id,
            salida_origen_id=registro.consumo.salida_id,
            lote_origen_id=registro.consumo.lote_id,
            costo_reintegrado_fifo=registro.costo_reintegrado)
    if movement.tipo == 'DEVOLUCION':
        registro = movement.devolucion_fifo
        row.update(consumo_original_id=registro.consumo_id,
            salida_original_id=registro.consumo.salida_id, lote_original_id=registro.consumo.lote_id,
            costo_reintegrado=registro.costo_reintegrado)
    return row


def repeated_response(receipt, values, user):
    """Un UUID solo puede repetir la misma operación del mismo trabajador."""
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
        qs = MovimientoBodega.objects.select_related(
            'repuesto',
            'responsable',
            'recepcioningreso__responsable',
            'devolucion_fifo__consumo',
            'detalle_recepcion_compra__recepcion'
        ).prefetch_related('detalles_fifo__lote').order_by('-fecha_registro', '-pk')
        if resource != 'kardex':
            qs = qs.filter(tipo='INGRESO' if resource == 'ingresos' else 'SALIDA')
        fields = schema(IngresoForm() if resource == 'ingresos' else SalidaForm()) if resource != 'kardex' else []
        result = {
            'items': [serialize(x) for x in qs],
            'fields': fields,
            'can_write': resource in ('ingresos', 'salidas'), 'can_delete': False,
        }
        if resource in ('ingresos', 'salidas'):
            result['articles'] = list(Repuesto.objects.filter(activo=True).values('id', 'codigo_parte', 'descripcion', 'unidad_medida', 'stock_actual'))
        if resource == 'ingresos':
            invoice_details = pending_invoice_details()
            pending_invoice_ids = {
                str(detail['factura_id']) for detail in invoice_details
            }
            for field in fields:
                if field['name'] == 'factura':
                    field['choices'] = [
                        choice for choice in field['choices']
                        if choice[0] == '' or choice[0] in pending_invoice_ids
                    ]
            fields.append({
                'name': 'recepcion_detalles',
                'label': 'Artículos recibidos',
                'type': 'receipt_details',
                'required': True
            })
            result['invoiceDetails'] = invoice_details
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
    quantities, detail_errors = validate_receipt_details(
        raw_details,
        values['factura'].pk
    )
    if detail_errors:
        return JsonResponse({'errors': detail_errors}, status=400)
    try:
        with transaction.atomic():
            article = Repuesto.objects.select_for_update().get(pk=values['articulo'].pk)
            previous = RecepcionIngreso.objects.filter(solicitud_id=values['solicitud_id']).first()
            if previous:
                return repeated_response(previous, values, request.user)
            if article.unidad_medida == 'unidad' and values['cantidad'] != values['cantidad'].to_integral_value():
                return error('Debe ser una cantidad entera para artículos por unidad.')
            new_stock = article.stock_actual + values['cantidad']
            if new_stock > Decimal('9999999999999.99'):
                return error('El stock excede el máximo permitido.')
            movement = MovimientoBodega.objects.create(
                tipo='INGRESO', cantidad=values['cantidad'], repuesto=article, responsable=request.user
            )
            RecepcionIngreso.objects.create(
                solicitud_id=values['solicitud_id'], factura=values['factura'],
                movimiento=movement, responsable=request.user,
                unidad_medida=article.unidad_medida, precio_unitario_neto=values['precio'],
                cantidad_disponible=values['cantidad'],
                subtotal_neto=(values['cantidad'] * values['precio']).quantize(
                    Decimal('.01'), rounding=ROUND_HALF_UP
                ),
            )
            article.stock_actual = new_stock
            article.save(update_fields=['stock_actual'])
    except Repuesto.DoesNotExist:
        return error('El artículo ya no existe. Actualiza la lista.')
    except FacturaCompra.DoesNotExist:
        return error('La factura ya no existe. Actualiza la lista.')
    except IntegrityError:

        previous = RecepcionIngreso.objects.filter(solicitud_id=values['solicitud_id']).first()
        if previous:
            return repeated_response(previous, values, request.user)
        return error('No se pudo registrar: datos inválidos. Actualiza la lista.')
    return JsonResponse({'item': serialize(movement)}, status=201)



def registrar_salida(request):
    form = SalidaForm(data(request))
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    values = form.cleaned_data
    try:
        resultado = registrar_salida_fifo(
            articulo_id=values['articulo'].pk, cantidad=values['cantidad'],
            numero_ot=values['numero_ot'], responsable_id=request.user.pk,
            solicitud_id=values['solicitud_id'],
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
