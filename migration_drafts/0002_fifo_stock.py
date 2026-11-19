"""BORRADOR aditivo de saldos FIFO; requiere reconciliar la inicial histórica.
NO crea descuentos monetarios ni cambia precios de recepciones.
"""
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def inicializar_lotes(apps, schema_editor):
    alias = schema_editor.connection.alias
    Movement = apps.get_model('inventario', 'MovimientoBodega')
    Receipt = apps.get_model('inventario', 'RecepcionIngreso')
    Article = apps.get_model('inventario', 'Repuesto')
    if Movement.objects.using(alias).exclude(tipo='INGRESO').exists():
        raise RuntimeError('Hay movimientos históricos distintos de INGRESO: reconciliar saldos por lote antes de migrar.')
    totals = {}
    for receipt in Receipt.objects.using(alias).select_related('movimiento').iterator():
        movement = receipt.movimiento
        if movement.tipo != 'INGRESO' or movement.cantidad < 0 or receipt.precio_unitario_neto < 0:
            raise RuntimeError('Recepción histórica incompatible con la inicialización FIFO.')
        totals[movement.repuesto_id] = totals.get(movement.repuesto_id, Decimal('0')) + movement.cantidad
        Receipt.objects.using(alias).filter(pk=receipt.pk).update(cantidad_disponible=movement.cantidad)
        Movement.objects.using(alias).filter(pk=movement.pk).update(responsable_id=receipt.responsable_id)
    for article in Article.objects.using(alias).all().iterator():
        if article.stock_actual != totals.get(article.pk, Decimal('0')):
            raise RuntimeError('Stock histórico sin recepciones suficientes: reconciliar por artículo antes de migrar.')
    if Movement.objects.using(alias).filter(recepcioningreso__isnull=True).exists():
        raise RuntimeError('Hay ingresos históricos sin recepción/precio: se requiere conciliación.')


class Migration(migrations.Migration):
    atomic = True
    dependencies = [('inventario', '0001_initial'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name='recepcioningreso', name='cantidad_disponible',
            field=models.DecimalField(max_digits=15, decimal_places=2, null=True)),
        migrations.AddField(model_name='movimientobodega', name='costo_total_fifo',
            field=models.DecimalField(max_digits=25, decimal_places=2, null=True, blank=True)),
        migrations.AddField(model_name='movimientobodega', name='responsable',
            field=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT, null=True, blank=True)),
        migrations.AddField(model_name='movimientobodega', name='solicitud_salida',
            field=models.UUIDField(null=True, blank=True, unique=True)),
        migrations.RunPython(inicializar_lotes),
        migrations.AlterField(model_name='recepcioningreso', name='cantidad_disponible',
            field=models.DecimalField(max_digits=15, decimal_places=2)),
        migrations.AddConstraint(model_name='recepcioningreso', constraint=models.CheckConstraint(
            condition=models.Q(cantidad_disponible__gte=0), name='fyag_lote_saldo_no_negativo')),
    ]
