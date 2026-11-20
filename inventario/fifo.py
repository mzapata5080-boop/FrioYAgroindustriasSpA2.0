"""FIFO con redondeo acumulado por lote para conservar el subtotal recibido."""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from dataclasses import dataclass
from uuid import UUID
from django.db import transaction, connection, IntegrityError
from django.core.exceptions import ValidationError
from django.db.models import Sum
from inventario.models import RecepcionIngreso, Repuesto, MovimientoBodega, DetalleConsumoFIFO, DevolucionFIFO

CENTAVO = Decimal('0.01')


def costo_repartido(cantidad_total, costo_total, acumulado, tomar):
    """Reparte un costo ya asignado conservando sus centavos, también al devolver."""
    with localcontext() as context:
        context.prec = 50
        if not (cantidad_total > 0 and costo_total >= 0 and 0 <= acumulado < cantidad_total
                and 0 < tomar <= cantidad_total - acumulado):
            raise ValidationError('La distribución de cantidad y costo es inconsistente.')
        antes = (costo_total * acumulado / cantidad_total).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        despues = costo_total if acumulado + tomar == cantidad_total else (
            costo_total * (acumulado + tomar) / cantidad_total).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        return despues - antes


def costo_consumo_lote(lote, tomar):
    """Sin devoluciones conserva el algoritmo original; después usa el valor neto."""
    devoluciones = DevolucionFIFO.objects.filter(consumo__lote_id=lote.pk).aggregate(
        cantidad=Sum('cantidad'), costo=Sum('costo_reintegrado'))
    # Comprueba también la coherencia del importe original del ingreso.
    original = costo_parcial_lote(lote.movimiento.cantidad, lote.cantidad_disponible,
        tomar, lote.precio_unitario_neto, lote.subtotal_neto)
    if devoluciones['cantidad'] is None:
        return original
    consumos = lote.consumos_fifo.aggregate(cantidad=Sum('cantidad'), costo=Sum('costo_asignado'))
    historica = (lote.movimiento.cantidad - lote.cantidad_disponible
        - (consumos['cantidad'] or Decimal('0')) + devoluciones['cantidad'])
    if not 0 <= historica <= lote.movimiento.cantidad:
        raise ValidationError('El historial de cantidades del lote es inconsistente.')
    costo_historico = costo_parcial_lote(lote.movimiento.cantidad, lote.movimiento.cantidad,
        historica, lote.precio_unitario_neto, lote.subtotal_neto) if historica else Decimal('0.00')
    disponible = lote.subtotal_neto - costo_historico - (consumos['costo'] or Decimal('0')) + devoluciones['costo']
    if not 0 <= disponible <= lote.subtotal_neto:
        raise ValidationError('El valor disponible del lote es inconsistente.')
    return costo_repartido(lote.cantidad_disponible, disponible, Decimal('0'), tomar)


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


@dataclass(frozen=True)
class ConsumoLoteFIFO:
    lote_id: UUID
    cantidad: Decimal
    precio_unitario: Decimal
    costo_asignado: Decimal


@dataclass(frozen=True)
class ResultadoFIFO:
    costo_total: Decimal
    consumos: tuple[ConsumoLoteFIFO, ...]


@dataclass(frozen=True)
class ResultadoSalidaFIFO:
    movimiento: MovimientoBodega
    repetida: bool


class ConflictoSolicitudFIFO(ValidationError):
    pass


def consumir_fifo(repuesto, cantidad):
    """Primitiva interna: requiere transacción y artículo bloqueado.

    Devuelve costo y asignaciones inmutables. Los módulos externos deben usar
    registrar_salida_fifo para persistir salida, detalles y stock atómicamente.
    """
    if not connection.in_atomic_block:
        raise RuntimeError('El consumo FIFO requiere una transacción y el artículo bloqueado.')
    pendiente = cantidad
    costo = Decimal('0.00')
    cambios = []
    consumos = []
    lotes = (RecepcionIngreso.objects.select_for_update(of=('self',))
             .select_related('movimiento')
             .filter(movimiento__repuesto=repuesto, cantidad_disponible__gt=0)
             .order_by('movimiento__fecha_registro', 'movimiento_id'))
    for lote in lotes:
        if pendiente == 0:
            break
        tomar = min(lote.cantidad_disponible, pendiente)
        asignado = costo_consumo_lote(lote, tomar)
        consumos.append(ConsumoLoteFIFO(lote.pk, tomar, lote.precio_unitario_neto, asignado))
        costo += asignado
        lote.cantidad_disponible -= tomar
        cambios.append(lote)
        pendiente -= tomar
    if pendiente:
        raise ValidationError('Los lotes disponibles no cubren la salida. Revisa los saldos históricos.')
    for lote in cambios:
        lote.save(update_fields=['cantidad_disponible'])
    return ResultadoFIFO(costo, tuple(consumos))


def _salida_existente(movimiento, articulo_id, cantidad, numero_ot, responsable_id):
    if not (movimiento.tipo == 'SALIDA' and movimiento.responsable_id == responsable_id
            and movimiento.repuesto_id == articulo_id and movimiento.cantidad == cantidad
            and movimiento.numero_ot == numero_ot):
        raise ConflictoSolicitudFIFO('La solicitud ya fue usada con otros datos. Abre una salida nueva.')
    return ResultadoSalidaFIFO(movimiento, True)


def registrar_salida_fifo(*, articulo_id, cantidad, numero_ot, responsable_id, solicitud_id):
    """Servicio sin HTTP: guarda salida, lotes y detalles en una transacción.

    cantidad debe ser Decimal. El llamador valida identidad y permisos antes
    de invocarlo. El servicio vuelve a comprobar stock, unidad y estado activo.
    """
    if type(articulo_id) is not int or articulo_id <= 0 or type(responsable_id) is not int or responsable_id <= 0:
        raise ValidationError('Indica identificadores válidos de artículo y responsable.')
    if (not isinstance(cantidad, Decimal) or not cantidad.is_finite() or cantidad <= 0
            or cantidad > Decimal('9999999999999.99') or cantidad.quantize(CENTAVO) != cantidad):
        raise ValidationError('La cantidad debe ser Decimal positiva con hasta dos decimales.')
    if not isinstance(numero_ot, str) or not numero_ot.strip() or len(numero_ot.strip()) > 50:
        raise ValidationError('Indica una orden de trabajo válida de hasta 50 caracteres.')
    numero_ot = numero_ot.strip()
    try:
        solicitud_id = UUID(str(solicitud_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError('El identificador de solicitud no es un UUID válido.') from exc
    try:
        with transaction.atomic():
            articulo = Repuesto.objects.select_for_update().get(pk=articulo_id)
            anterior = MovimientoBodega.objects.filter(solicitud_salida=solicitud_id).first()
            if anterior:
                return _salida_existente(anterior, articulo_id, cantidad, numero_ot, responsable_id)
            if not articulo.activo:
                raise ValidationError('El artículo está inactivo.')
            if articulo.unidad_medida == 'unidad' and cantidad != cantidad.to_integral_value():
                raise ValidationError('Debe ser una cantidad entera para artículos por unidad.')
            if articulo.stock_actual < cantidad:
                raise ValidationError('No hay stock suficiente para registrar la salida.')
            resultado = consumir_fifo(articulo, cantidad)
            movimiento = MovimientoBodega.objects.create(
                tipo='SALIDA', cantidad=cantidad, repuesto=articulo, numero_ot=numero_ot,
                costo_total_fifo=resultado.costo_total, responsable_id=responsable_id,
                solicitud_salida=solicitud_id,
            )
            DetalleConsumoFIFO.objects.bulk_create([
                DetalleConsumoFIFO(salida=movimiento, lote_id=consumo.lote_id, orden=orden,
                    cantidad=consumo.cantidad, precio_unitario=consumo.precio_unitario,
                    costo_asignado=consumo.costo_asignado)
                for orden, consumo in enumerate(resultado.consumos, start=1)
            ])
            articulo.stock_actual -= cantidad
            articulo.save(update_fields=['stock_actual'])
            return ResultadoSalidaFIFO(movimiento, False)
    except IntegrityError:
        anterior = MovimientoBodega.objects.filter(solicitud_salida=solicitud_id).first()
        if anterior:
            return _salida_existente(anterior, articulo_id, cantidad, numero_ot, responsable_id)
        raise
