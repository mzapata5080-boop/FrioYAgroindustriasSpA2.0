from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('inventario', '0003_movimientobodega_obra_movimientobodega_observaciones_and_more'),
        ('obras', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='OperacionInventario',
            fields=[
                ('solicitud_id', models.UUIDField(primary_key=True, serialize=False)),
                ('tipo', models.CharField(max_length=20, choices=[
                    ('MERMA_BODEGA', 'Merma en Bodega'), ('MERMA_OBRA', 'Merma en Obra'),
                    ('DEV_BODEGA', 'Devolución a Bodega'), ('DEV_PROVEEDOR', 'Devolución a proveedor'),
                    ('USO_INTERNO', 'Uso interno'), ('CAMBIO', 'Cambio de artículo'),
                    ('ANULAR', 'Anulación compensatoria')])),
                ('cantidad', models.DecimalField(max_digits=15, decimal_places=2)),
                ('cantidad_nueva', models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)),
                ('motivo', models.CharField(max_length=1000)),
                ('destino', models.CharField(max_length=150, blank=True)),
                ('fecha', models.DateTimeField(auto_now_add=True)),
                ('datos_solicitud', models.JSONField(default=dict)),
                ('articulo', models.ForeignKey(to='inventario.repuesto', related_name='+', on_delete=django.db.models.deletion.PROTECT)),
                ('articulo_nuevo', models.ForeignKey(to='inventario.repuesto', related_name='+', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
                ('origen', models.ForeignKey(to='inventario.movimientobodega', related_name='operaciones_referidas', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
                ('lote', models.ForeignKey(to='inventario.recepcioningreso', related_name='operaciones_referidas', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
                ('obra', models.ForeignKey(to='obras.obra', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
                ('responsable', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
                ('anula_a', models.OneToOneField(to='inventario.operacioninventario', related_name='anulada_por', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
                ('movimiento_anulado', models.OneToOneField(to='inventario.movimientobodega', related_name='anulacion_inventario', null=True, blank=True, on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.CreateModel(
            name='MovimientoOperacion',
            fields=[
                ('id', models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name='ID')),
                ('funcion', models.CharField(max_length=25)),
                ('operacion', models.ForeignKey(to='inventario.operacioninventario', related_name='movimientos', on_delete=django.db.models.deletion.PROTECT)),
                ('movimiento', models.OneToOneField(to='inventario.movimientobodega', related_name='detalle_operacion', on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.CreateModel(
            name='MermaConsumoObra',
            fields=[
                ('id', models.BigAutoField(primary_key=True, auto_created=True, serialize=False, verbose_name='ID')),
                ('cantidad', models.DecimalField(max_digits=15, decimal_places=2)),
                ('operacion', models.ForeignKey(to='inventario.operacioninventario', related_name='mermas', on_delete=django.db.models.deletion.PROTECT)),
                ('consumo', models.ForeignKey(to='inventario.detalleconsumofifo', related_name='mermas_operacion', on_delete=django.db.models.deletion.PROTECT)),
            ],
        ),
        migrations.AddConstraint(model_name='operacioninventario', constraint=models.CheckConstraint(
            condition=models.Q(cantidad__gt=0), name='fyag_op_cantidad_positiva')),
        migrations.AddConstraint(model_name='operacioninventario', constraint=models.CheckConstraint(
            condition=models.Q(cantidad_nueva__isnull=True) | models.Q(cantidad_nueva__gt=0),
            name='fyag_op_nueva_positiva')),
        migrations.AddConstraint(model_name='mermaconsumoobra', constraint=models.UniqueConstraint(
            fields=['operacion', 'consumo'], name='fyag_op_merma_consumo_unico')),
        migrations.AddConstraint(model_name='mermaconsumoobra', constraint=models.CheckConstraint(
            condition=models.Q(cantidad__gt=0), name='fyag_op_merma_positiva')),
    ]
