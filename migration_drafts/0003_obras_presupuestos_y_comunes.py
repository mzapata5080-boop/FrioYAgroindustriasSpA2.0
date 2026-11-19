"""BORRADOR PARA REVISIÓN (Turno 1 - Benjamín).
NO aplicar automáticamente en Supabase sin revisión de equipo y respaldo previo.

Incluye:
1. Tablas transversales fyag_registro_auditoria y fyag_archivo_privado.
2. Modelos mínimos de Obras y Presupuestos conectados a Cliente, Trabajador,
   MovimientoBodega y FacturaCompra (sin duplicar tablas existentes).
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('finanzas', '0004_alter_facturacompra_proveedor'),
        ('inventario', '0002_fifo_stock'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RegistroAuditoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('modelo', models.CharField(db_index=True, max_length=100)),
                ('objeto_id', models.CharField(db_index=True, max_length=64)),
                ('accion', models.CharField(choices=[('CREAR', 'Crear'), ('EDITAR', 'Editar'), ('ELIMINAR', 'Eliminar')], max_length=12)),
                ('cambios_json', models.TextField(default='{}')),
                ('fecha_registro', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='auditorias_realizadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'fyag_registro_auditoria', 'ordering': ['-fecha_registro', '-pk']},
        ),
        migrations.CreateModel(
            name='ArchivoPrivado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('modulo', models.CharField(db_index=True, max_length=50)),
                ('modelo', models.CharField(db_index=True, max_length=100)),
                ('objeto_id', models.CharField(db_index=True, max_length=64)),
                ('nombre_original', models.CharField(max_length=255)),
                ('ruta_privada', models.CharField(max_length=500, unique=True)),
                ('tamano_bytes', models.PositiveBigIntegerField(default=0)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('subido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'fyag_archivo_privado', 'ordering': ['-creado_el', '-pk']},
        ),
        migrations.CreateModel(
            name='Obra',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo_ot', models.CharField(max_length=50, unique=True)),
                ('nombre', models.CharField(max_length=150)),
                ('direccion', models.CharField(blank=True, default='', max_length=200)),
                ('estado', models.CharField(choices=[('PLANIFICADA', 'Planificada'), ('EN_EJECUCION', 'En ejecución'), ('PAUSADA', 'Pausada'), ('CERRADA', 'Cerrada')], default='PLANIFICADA', max_length=20)),
                ('fecha_inicio', models.DateField(blank=True, null=True)),
                ('fecha_termino_estimada', models.DateField(blank=True, null=True)),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='obras', to='finanzas.cliente')),
                ('supervisor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='obras_supervisadas', to=settings.AUTH_USER_MODEL)),
            ],
            options={'db_table': 'obras_obra'},
        ),
        migrations.CreateModel(
            name='Presupuesto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('version', models.PositiveIntegerField(default=1)),
                ('estado', models.CharField(choices=[('BORRADOR', 'Borrador'), ('APROBADO', 'Aprobado'), ('RECHAZADO', 'Rechazado')], default='BORRADOR', max_length=20)),
                ('monto_materiales_estimado', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('monto_mano_obra_estimado', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('monto_otros_estimado', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('observaciones', models.TextField(blank=True, default='')),
                ('creado_el', models.DateTimeField(auto_now_add=True)),
                ('aprobado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='presupuestos_aprobados', to=settings.AUTH_USER_MODEL)),
                ('obra', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='presupuestos', to='obras.obra')),
            ],
            options={'db_table': 'obras_presupuesto', 'unique_together': {('obra', 'version')}},
        ),
        migrations.AddField(
            model_name='movimientobodega',
            name='obra',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movimientos_bodega', to='obras.obra'),
        ),
        migrations.AddField(
            model_name='facturacompra',
            name='obra',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='facturas_compra', to='obras.obra'),
        ),
    ]