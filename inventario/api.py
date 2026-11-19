"""Consulta del historial y registro transaccional e idempotente de ingresos."""
from decimal import Decimal, ROUND_HALF_UP
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from frio_agroindustria.api_common import allowed, error, data, schema, serialize as base_serialize
from inventario.api_forms import IngresoForm, SalidaForm
from inventario.fifo import consumir_fifo
from inventario.models import MovimientoBodega, RecepcionIngreso, Repuesto


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
            'repuesto', 'responsable', 'recepcioningreso__responsable'
        ).order_by('-fecha_registro', '-pk')
        if resource != 'kardex':
            qs = qs.filter(tipo='INGRESO' if resource == 'ingresos' else 'SALIDA')
        result = {
            'items': [serialize(x) for x in qs],
            'fields': schema(IngresoForm() if resource == 'ingresos' else SalidaForm()) if resource != 'kardex' else [],
            'can_write': resource in ('ingresos', 'salidas'), 'can_delete': False,
        }
        if resource == 'ingresos':
            result['articles'] = list(Repuesto.objects.values('id', 'unidad_medida'))
        return JsonResponse(result)
    if resource == 'salidas':
        return registrar_salida(request)
    if resource != 'ingresos':
        return error('Solo se permite registrar ingresos.', 405)
    payload = data(request)
    if any(name in payload for name in ('descuento_1', 'descuento_2', 'descuento_3', 'costo_unitario_final')):
        return error('Este ingreso no admite descuentos porcentuales. Recarga el formulario actualizado.')
    form = IngresoForm(payload)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    values = form.cleaned_data
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
    except IntegrityError:

        previous = RecepcionIngreso.objects.filter(solicitud_id=values['solicitud_id']).first()
        if previous:
            return repeated_response(previous, values, request.user)
        return error('No se pudo registrar: datos inválidos. Actualiza la lista.')
    return JsonResponse({'item': serialize(movement)}, status=201)


def salida_repetida(movimiento, values, user):
    if not (movimiento.responsable_id == user.pk
            and movimiento.repuesto_id == values['articulo'].pk
            and movimiento.cantidad == values['cantidad']
            and movimiento.numero_ot == values['numero_ot']):
        return error('La solicitud ya fue usada con otros datos. Abre una salida nueva.', 409)
    return JsonResponse({'ok': True, 'repeated': True, 'item': serialize(movimiento)})


def registrar_salida(request):
    form = SalidaForm(data(request))
    if not form.is_valid():
        return JsonResponse({'errors': form.errors}, status=400)
    values = form.cleaned_data
    try:
        with transaction.atomic():
            article = Repuesto.objects.select_for_update().get(pk=values['articulo'].pk)
            previous = MovimientoBodega.objects.filter(solicitud_salida=values['solicitud_id']).first()
            if previous:
                return salida_repetida(previous, values, request.user)
            quantity = values['cantidad']
            if article.unidad_medida == 'unidad' and quantity != quantity.to_integral_value():
                return error('Debe ser una cantidad entera para artículos por unidad.')
            if article.stock_actual < quantity:
                return error('No hay stock suficiente para registrar la salida.')
            cost = consumir_fifo(article, quantity)
            movement = MovimientoBodega.objects.create(
                tipo='SALIDA', cantidad=quantity, repuesto=article,
                numero_ot=values['numero_ot'], costo_total_fifo=cost,
                responsable=request.user, solicitud_salida=values['solicitud_id'],
            )
            article.stock_actual -= quantity
            article.save(update_fields=['stock_actual'])
    except ValidationError as exc:
        return error(' '.join(exc.messages))
    except Repuesto.DoesNotExist:
        return error('El artículo ya no existe. Actualiza la lista.')
    except IntegrityError:
        previous = MovimientoBodega.objects.filter(solicitud_salida=values['solicitud_id']).first()
        if previous:
            return salida_repetida(previous, values, request.user)
        return error('No se pudo registrar la salida. Revisa los datos.')
    return JsonResponse({'item': serialize(movement)}, status=201)
