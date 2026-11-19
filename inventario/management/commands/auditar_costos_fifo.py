"""Reproduce FIFO por fecha/ID y compara costos y saldos sin modificar datos."""
from collections import defaultdict, deque
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from inventario.models import MovimientoBodega, RecepcionIngreso, Repuesto
from inventario.fifo import costo_parcial_lote


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
        movimientos = MovimientoBodega.objects.select_related('recepcioningreso').order_by('fecha_registro', 'pk')
        for movimiento in movimientos:
            if movimiento.cantidad <= 0:
                raise CommandError(f'Movimiento {movimiento.pk}: cantidad no positiva; revisar historia.')
            if movimiento.tipo == 'INGRESO':
                try:
                    recepcion = movimiento.recepcioningreso
                except RecepcionIngreso.DoesNotExist:
                    raise CommandError(f'Ingreso {movimiento.pk}: falta recepción; no se puede reconstruir.')
                lote = {'recepcion': recepcion, 'inicial': movimiento.cantidad, 'saldo': movimiento.cantidad}
                lotes[movimiento.repuesto_id].append(lote)
                todos.append(lote)
            elif movimiento.tipo == 'SALIDA':
                pendiente = movimiento.cantidad
                costo = Decimal('0.00')
                cola = lotes[movimiento.repuesto_id]
                while pendiente and cola:
                    lote = cola[0]
                    tomar = min(pendiente, lote['saldo'])
                    recibo = lote['recepcion']
                    try:
                        costo += costo_parcial_lote(lote['inicial'], lote['saldo'], tomar,
                                                   recibo.precio_unitario_neto, recibo.subtotal_neto)
                    except ValidationError as exc:
                        raise CommandError(f'Lote del ingreso {recibo.movimiento_id}: datos inconsistentes.') from exc
                    lote['saldo'] -= tomar
                    pendiente -= tomar
                    if lote['saldo'] == 0:
                        cola.popleft()
                if pendiente:
                    raise CommandError(f'Salida {movimiento.pk}: faltan ingresos anteriores para reconstruir FIFO.')
                salidas += 1
                if movimiento.costo_total_fifo != costo:
                    problemas.append(f'Salida {movimiento.pk}: guardado={movimiento.costo_total_fifo}; esperado={costo}')
            else:
                raise CommandError(f'Movimiento {movimiento.pk}: tipo {movimiento.tipo} requiere conciliación específica.')
        for lote in todos:
            if lote['recepcion'].cantidad_disponible != lote['saldo']:
                problemas.append(f"Saldo distinto en lote del ingreso {lote['recepcion'].movimiento_id}")
        saldos = {pk: sum((lote['saldo'] for lote in cola), Decimal('0')) for pk, cola in lotes.items()}
        for articulo in Repuesto.objects.all():
            if articulo.stock_actual != saldos.get(articulo.pk, Decimal('0')):
                problemas.append(f'Stock sin conciliar en artículo {articulo.pk}')
        for problema in problemas:
            self.stdout.write(problema)
        if problemas:
            raise CommandError(f'{len(problemas)} diferencia(s). No se modificó ningún movimiento.')
        self.stdout.write(self.style.SUCCESS(f'Costos y saldos FIFO coherentes: {salidas} salida(s) revisada(s). Solo lectura.'))
