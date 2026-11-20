"""Reproduce FIFO por fecha/ID y compara costos y saldos sin modificar datos."""
from collections import defaultdict, deque
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from inventario.models import MovimientoBodega, RecepcionIngreso, Repuesto, DevolucionFIFO
from inventario.fifo import costo_parcial_lote, costo_repartido


class Command(BaseCommand):
    help = 'Audita costos FIFO por redondeo acumulado. Solo lectura; no corrige el historial.'

    def handle(self, *args, **options):
        with transaction.atomic():
            if connection.vendor == 'postgresql':
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            self.auditar()

    def auditar(self):
        lotes = defaultdict(deque)
        todos = []
        problemas = []
        salidas = 0
        sin_detalle = 0
        por_id = {}
        consumos = {}
        devueltas = defaultdict(lambda: Decimal('0'))
        movimientos = MovimientoBodega.objects.select_related('recepcioningreso', 'devolucion_fifo__consumo').prefetch_related('detalles_fifo').order_by('fecha_registro', 'pk')
        for movimiento in movimientos:
            if movimiento.cantidad <= 0:
                raise CommandError(f'Movimiento {movimiento.pk}: cantidad no positiva; revisar historia.')
            if movimiento.tipo == 'INGRESO':
                try:
                    recepcion = movimiento.recepcioningreso
                except RecepcionIngreso.DoesNotExist:
                    raise CommandError(f'Ingreso {movimiento.pk}: falta recepción; no se puede reconstruir.')
                try:
                    costo_parcial_lote(movimiento.cantidad, movimiento.cantidad, movimiento.cantidad,
                        recepcion.precio_unitario_neto, recepcion.subtotal_neto)
                except ValidationError as exc:
                    raise CommandError(f'Ingreso {movimiento.pk}: cantidad, precio o subtotal inconsistente.') from exc
                lote = {'recepcion': recepcion, 'inicial': movimiento.cantidad, 'saldo': movimiento.cantidad,
                    'valor': recepcion.subtotal_neto, 'devuelto': False, 'articulo': movimiento.repuesto_id}
                por_id[recepcion.pk] = lote
                lotes[movimiento.repuesto_id].append(lote)
                todos.append(lote)
            elif movimiento.tipo == 'SALIDA':
                pendiente = movimiento.cantidad
                costo = Decimal('0.00')
                cola = lotes[movimiento.repuesto_id]
                esperado = []
                while pendiente and cola:
                    lote = cola[0]
                    tomar = min(pendiente, lote['saldo'])
                    recibo = lote['recepcion']
                    try:
                        asignado = (costo_repartido(lote['saldo'], lote['valor'], Decimal('0'), tomar)
                            if lote['devuelto'] else costo_parcial_lote(lote['inicial'], lote['saldo'], tomar,
                                                   recibo.precio_unitario_neto, recibo.subtotal_neto))
                    except ValidationError as exc:
                        raise CommandError(f'Lote del ingreso {recibo.movimiento_id}: datos inconsistentes.') from exc
                    costo += asignado
                    esperado.append((recibo.pk, tomar, recibo.precio_unitario_neto, asignado))
                    lote['saldo'] -= tomar
                    lote['valor'] -= asignado
                    pendiente -= tomar
                    if lote['saldo'] == 0:
                        cola.popleft()
                if pendiente:
                    raise CommandError(f'Salida {movimiento.pk}: faltan ingresos anteriores para reconstruir FIFO.')
                salidas += 1
                if movimiento.costo_total_fifo != costo:
                    problemas.append(f'Salida {movimiento.pk}: guardado={movimiento.costo_total_fifo}; esperado={costo}')
                detalles = list(movimiento.detalles_fifo.all())
                if detalles:
                    consumos.update({d.pk: d for d in detalles})
                    guardado = [(d.lote_id, d.cantidad, d.precio_unitario, d.costo_asignado) for d in detalles]
                    if guardado != esperado or [d.orden for d in detalles] != list(range(1,len(esperado)+1)):
                        problemas.append(f'Salida {movimiento.pk}: detalle por lote distinto del consumo FIFO reconstruido')
                    if sum((d.cantidad for d in detalles), Decimal('0')) != movimiento.cantidad:
                        problemas.append(f'Salida {movimiento.pk}: cantidades del detalle no suman la salida')
                    if sum((d.costo_asignado for d in detalles), Decimal('0.00')) != movimiento.costo_total_fifo:
                        problemas.append(f'Salida {movimiento.pk}: costos del detalle no suman el costo total')
                else:
                    sin_detalle += 1
            elif movimiento.tipo == 'DEVOLUCION':
                try:
                    registro = movimiento.devolucion_fifo
                except DevolucionFIFO.DoesNotExist:
                    raise CommandError(f'Devolución {movimiento.pk}: falta vínculo al consumo original.')
                consumo = consumos.get(registro.consumo_id)
                if consumo is None or consumo.lote_id not in por_id:
                    raise CommandError(f'Devolución {movimiento.pk}: no existe consumo anterior reconstruible.')
                lote = por_id[consumo.lote_id]
                if (registro.cantidad != movimiento.cantidad or movimiento.repuesto_id != lote['articulo']
                        or lote['saldo'] + registro.cantidad > lote['inicial']):
                    raise CommandError(f'Devolución {movimiento.pk}: cantidades o artículo inconsistentes.')
                try:
                    costo = costo_repartido(consumo.cantidad, consumo.costo_asignado,
                        devueltas[consumo.pk], registro.cantidad)
                except ValidationError as exc:
                    raise CommandError(f'Devolución {movimiento.pk}: excede lo consumido.') from exc
                if registro.costo_reintegrado != costo or movimiento.costo_total_fifo != costo:
                    problemas.append(f'Devolución {movimiento.pk}: costo distinto al del consumo original')
                devueltas[consumo.pk] += registro.cantidad
                lote['saldo'] += registro.cantidad
                lote['valor'] += costo
                lote['devuelto'] = True
                # Retorna a su posición original por antigüedad, aunque estuviera agotado.
                lotes[movimiento.repuesto_id] = deque(x for x in todos
                    if x['articulo'] == movimiento.repuesto_id and x['saldo'] > 0)
            else:
                raise CommandError(f'Movimiento {movimiento.pk}: tipo {movimiento.tipo} requiere conciliación específica.')
        for lote in todos:
            if lote['recepcion'].cantidad_disponible != lote['saldo']:
                problemas.append(f"Saldo distinto en lote del ingreso {lote['recepcion'].movimiento_id}")
        saldos = {pk: sum((lote['saldo'] for lote in cola), Decimal('0')) for pk, cola in lotes.items()}
        for articulo in Repuesto.objects.all():
            if articulo.stock_actual != saldos.get(articulo.pk, Decimal('0')):
                problemas.append(f'Stock sin conciliar en artículo {articulo.pk}')
        if sin_detalle:
            self.stdout.write(f'Aviso: {sin_detalle} salida(s) sin detalle persistido; solo se verificó su encabezado e historial.')
        for problema in problemas:
            self.stdout.write(problema)
        if problemas:
            raise CommandError(f'{len(problemas)} diferencia(s). No se modificó ningún movimiento.')
        self.stdout.write(self.style.SUCCESS(f'Costos y saldos FIFO coherentes: {salidas} salida(s) revisada(s). Solo lectura.'))
