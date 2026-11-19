"""FIFO con redondeo acumulado por lote para conservar el subtotal recibido."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from django.core.exceptions import ValidationError
from inventario.models import RecepcionIngreso

CENTAVO = Decimal('0.01')


def costo_parcial_lote(cantidad_inicial, disponible, tomar, precio, subtotal):
    """Asigna solo el aumento del costo acumulado ya redondeado.

    Al agotar el lote, la suma de todas sus asignaciones coincide con subtotal.
    Una asignación puede costar cero por distribución de centavos.
    """
    with localcontext() as context:
        context.prec = 50
        if not (cantidad_inicial > 0 and 0 <= disponible <= cantidad_inicial and 0 < tomar <= disponible and precio >= 0):
            raise ValidationError('El lote tiene cantidades o precios inconsistentes.')
        esperado = (cantidad_inicial * precio).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if subtotal != esperado:
            raise ValidationError('El subtotal del lote no coincide con su cantidad y precio. Revisa el ingreso.')
        consumido = cantidad_inicial - disponible
        antes = (consumido * precio).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        despues = subtotal if tomar == disponible else ((consumido + tomar) * precio).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        return despues - antes


def consumir_fifo(repuesto, cantidad):
    """El llamador mantiene transacción y artículo bloqueado; no guarda parciales."""
    pendiente = cantidad
    costo = Decimal('0.00')
    cambios = []
    lotes = (RecepcionIngreso.objects.select_for_update(of=('self',))
             .select_related('movimiento')
             .filter(movimiento__repuesto=repuesto, cantidad_disponible__gt=0)
             .order_by('movimiento__fecha_registro', 'movimiento_id'))
    for lote in lotes:
        if pendiente == 0:
            break
        tomar = min(lote.cantidad_disponible, pendiente)
        costo += costo_parcial_lote(lote.movimiento.cantidad, lote.cantidad_disponible,
                                     tomar, lote.precio_unitario_neto, lote.subtotal_neto)
        lote.cantidad_disponible -= tomar
        cambios.append(lote)
        pendiente -= tomar
    if pendiente:
        raise ValidationError('Los lotes disponibles no cubren la salida. Revisa los saldos históricos.')
    for lote in cambios:
        lote.save(update_fields=['cantidad_disponible'])
    return costo
