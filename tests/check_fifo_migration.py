"""Prueba el borrador en SQLite temporal; jamás lee .env ni conecta Supabase.
Ejecutar: python tests/check_fifo_migration.py
La inicial reconstruida es una fixture de prueba, no historial de producción.
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ['DJANGO_SETTINGS_MODULE'] = 'frio_agroindustria.test_settings'
os.environ['DATABASE_MODE'] = 'sqlite'
from django.conf import settings

with tempfile.TemporaryDirectory() as temporary:
    package = Path(temporary) / 'fifo_fixture_migrations'
    package.mkdir()
    (package / '__init__.py').write_text('')
    shutil.copyfile(root / 'migration_drafts/0001_current_schema.py', package / '0001_initial.py')
    shutil.copyfile(root / 'migration_drafts/0002_fifo_stock.py', package / '0002_fifo_stock.py')
    sys.path.insert(0, temporary)
    settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
    settings.MIGRATION_MODULES = {'inventario': 'fifo_fixture_migrations'}
    import django
    django.setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    initial = [('inventario', '0001_initial')]
    target = [('inventario', '0002_fifo_stock')]
    executor = MigrationExecutor(connection)
    executor.migrate(initial)
    apps = executor.loader.project_state(initial).apps
    Worker = apps.get_model('usuarios', 'Trabajador')
    Article = apps.get_model('inventario', 'Repuesto')
    Movement = apps.get_model('inventario', 'MovimientoBodega')
    Receipt = apps.get_model('inventario', 'RecepcionIngreso')
    worker = Worker.objects.create(username='migration-fixture', password='not-a-real-account')
    category = apps.get_model('inventario', 'CategoriaRepuesto').objects.create(nombre='Fixture')
    provider = apps.get_model('finanzas', 'Proveedor').objects.create(rut='fixture', razon_social='Fixture')
    invoice = apps.get_model('finanzas', 'FacturaCompra').objects.create(proveedor=provider, fecha='2026-11-19', numero_documento='fixture', tipo_documento='Factura', monto=200)
    article = Article.objects.create(codigo_parte='fixture', descripcion='Fixture', ubicacion_bodega='A', unidad_medida='kg', categoria=category, stock_actual=2)
    movement = Movement.objects.create(tipo='INGRESO', cantidad=2, repuesto=article)
    import uuid
    receipt = Receipt.objects.create(solicitud_id=uuid.uuid4(),factura=invoice,movimiento=movement,responsable=worker,unidad_medida='kg',precio_unitario_neto=100,subtotal_neto=200)

    def fails_without_columns(fragment):
        try:
            MigrationExecutor(connection).migrate(target)
        except RuntimeError as exc:
            assert fragment in str(exc), str(exc)
        else:
            raise AssertionError('La migración debía rechazar datos sin conciliar')
        with connection.cursor() as cursor:
            columns = {c.name for c in connection.introspection.get_table_description(cursor, 'recepciones_ingreso')}
        assert 'cantidad_disponible' not in columns, 'El rollback dejó columnas nuevas'
        print('Rechazo y rollback OK:', fragment)

    outgoing = Movement.objects.create(tipo='SALIDA', cantidad=1, repuesto=article)
    fails_without_columns('movimientos históricos')
    outgoing.delete()
    article.stock_actual = 5; article.save()
    fails_without_columns('Stock histórico')
    article.stock_actual = 2; article.save()
    orphan = Movement.objects.create(tipo='INGRESO',cantidad=1,repuesto=article)
    fails_without_columns('sin recepción')
    orphan.delete()
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    new_apps = executor.loader.project_state(target).apps
    new_receipt = new_apps.get_model('inventario', 'RecepcionIngreso').objects.get(pk=receipt.pk)
    assert new_receipt.cantidad_disponible == 2
    assert new_apps.get_model('inventario', 'MovimientoBodega').objects.get(pk=movement.pk).responsable_id == worker.pk
    assert new_apps.get_model('inventario', 'Repuesto').objects.get(pk=article.pk).stock_actual == 2
    print('Backfill de lotes, auditoría y preservación del stock: OK')
    # Comprobar que el estado final del borrador coincide con los modelos reales.
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.state import ProjectState
    changes = MigrationAutodetector(executor.loader.project_state(target), ProjectState.from_apps(django.apps.apps)).changes(graph=executor.loader.graph)
    assert not changes.get('inventario'), changes.get('inventario')
    print('Estado del borrador coincide con los modelos: OK')
    connection.close()
