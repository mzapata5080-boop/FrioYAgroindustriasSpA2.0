"""Auditoría de solo lectura: estructura, sin mostrar filas ni credenciales."""
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Comprueba las tablas y relaciones necesarias sin modificar la base.'

    def handle(self, *args, **options):
        expected = {
            'inventario_categoriarepuesto': {'id', 'nombre'},
            'inventario_repuesto': {'id', 'codigo_parte', 'descripcion', 'ubicacion_bodega',
                'unidad_medida', 'stock_actual', 'stock_minimo', 'categoria_id'},
            'inventario_movimientobodega': {'id', 'tipo', 'cantidad', 'fecha_registro', 'numero_ot', 'repuesto_id', 'costo_total_fifo', 'responsable_id', 'solicitud_salida'},
            'recepciones_ingreso': {'solicitud_id', 'factura_id', 'movimiento_id', 'responsable_id',
                'unidad_medida', 'precio_unitario_neto', 'subtotal_neto', 'cantidad_disponible'},
        }
        problems = []
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            for table, required in expected.items():
                if table not in tables:
                    problems.append(f'Falta la tabla {table}')
                    continue
                columns = {c.name for c in connection.introspection.get_table_description(cursor, table)}
                missing = required - columns
                if missing:
                    problems.append(f'{table}: faltan {sorted(missing)}')
                else:
                    self.stdout.write(f'Columnas OK: {table}')
            if 'recepciones_ingreso' in tables:
                constraints = connection.introspection.get_constraints(cursor, 'recepciones_ingreso')
                primary = [c['columns'] for c in constraints.values() if c.get('primary_key')]
                if ['solicitud_id'] not in primary:
                    problems.append('La clave primaria de recepciones_ingreso debe ser solicitud_id')
                targets = {tuple(c['columns']): c.get('foreign_key') for c in constraints.values() if c.get('foreign_key')}
                for field, target in {'factura_id': ('finanzas_facturacompra', 'id'),
                    'movimiento_id': ('inventario_movimientobodega', 'id'),
                    'responsable_id': ('usuarios_trabajador', 'id')}.items():
                    if targets.get((field,)) != target:
                        problems.append(f'Revisar relación de {field}')
            if connection.vendor == 'postgresql':
                cursor.execute("""SELECT table_name, column_name, data_type, numeric_precision, numeric_scale
                    FROM information_schema.columns WHERE table_schema = 'public'
                    AND ((table_name = 'inventario_repuesto' AND column_name IN ('stock_actual', 'stock_minimo'))
                    OR (table_name = 'inventario_movimientobodega' AND column_name = 'cantidad'))""")
                for table, column, kind, precision, scale in cursor.fetchall():
                    if kind != 'numeric' or precision != 15 or scale != 2:
                        problems.append(f'{table}.{column}: se esperaba numeric(15,2)')
        if problems:
            raise CommandError('\n'.join(problems))
        self.stdout.write(self.style.SUCCESS('Estructura revisada. No se modificó ningún dato.'))
        self.stdout.write('Esto no sustituye recuperar el historial de migraciones ni probar el rol de conexión y los triggers de Supabase.')
