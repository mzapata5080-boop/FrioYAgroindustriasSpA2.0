"""Consulta del historial y registro transaccional e idempotente de ingresos."""
from decimal import Decimal, ROUND_HALF_UP
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from frio_agroindustria.api_common import allowed, error, data, schema, serialize
from inventario.api_forms import IngresoForm
from inventario.models import MovimientoBodega, RecepcionIngreso, Repuesto


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
            'repuesto', 'recepcioningreso__responsable'
        ).order_by('-fecha_registro', '-pk')
        if resource != 'kardex':
            qs = qs.filter(tipo='INGRESO' if resource == 'ingresos' else 'SALIDA')
        result = {
            'items': [serialize(x) for x in qs],
            'fields': schema(IngresoForm()) if resource == 'ingresos' else [],
            'can_write': resource == 'ingresos', 'can_delete': False,
        }
        if resource == 'ingresos':
            result['articles'] = list(Repuesto.objects.values('id', 'unidad_medida'))
        return JsonResponse(result)
    if resource != 'ingresos':
        return error('Solo se permite registrar ingresos.', 405)
    form = IngresoForm(data(request))
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
                tipo='INGRESO', cantidad=values['cantidad'], repuesto=article
            )
            RecepcionIngreso.objects.create(
                solicitud_id=values['solicitud_id'], factura=values['factura'],
                movimiento=movement, responsable=request.user,
                unidad_medida=article.unidad_medida, precio_unitario_neto=values['precio'],
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
