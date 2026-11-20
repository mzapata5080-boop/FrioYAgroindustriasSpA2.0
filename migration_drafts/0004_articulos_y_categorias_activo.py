"""BORRADOR PARA REVISIÓN (Turno 2 - Luis).
NO aplicar automáticamente en Supabase sin revisión de equipo y respaldo previo.

Agrega campo 'activo' (booleano) a CategoriaRepuesto y Repuesto para permitir
activar y desactivar artículos y categorías sin eliminar datos históricos.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('inventario', '0003_obras_presupuestos_y_comunes'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoriarepuesto',
            name='activo',
            field=models.BooleanField(default=True, verbose_name='Activo'),
        ),
        migrations.AddField(
            model_name='repuesto',
            name='activo',
            field=models.BooleanField(default=True, verbose_name='Activo'),
        ),
    ]
