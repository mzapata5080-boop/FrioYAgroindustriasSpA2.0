import json
from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import Group
from django.test import TestCase
from django.utils import timezone
from openpyxl import load_workbook

from finanzas.models import Cliente, DocumentoVenta, FacturaCompra, Proveedor
from inventario.models import CategoriaRepuesto, MovimientoBodega, Repuesto
from obras.models import Obra, SolicitudMaterial
from reportes.excel import _cell_value
from usuarios.models import Trabajador


class ReportsDashboardAndAlertsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = cls.user_with_role('manager-reports', 'Gerencia')
        cls.finance = cls.user_with_role('finance-reports', 'Finanzas')
        cls.warehouse = cls.user_with_role('warehouse-reports', 'Bodega')
        cls.supervisor = cls.user_with_role('supervisor-reports', 'Supervisor de Obra')

        cls.client_record = Cliente.objects.create(
            rut='76.123.456-7',
            razon_social='Cliente Reportes',
            telefono='123',
            correo='reportes@cliente.cl',
            direccion='Santiago',
        )
        cls.provider = Proveedor.objects.create(
            rut='77.222.333-4',
            razon_social='Proveedor Reportes',
            giro='Insumos',
            telefono='123',
            email='ventas@proveedor.cl',
            direccion='Santiago',
            banco='Banco Central',
        )
        category = CategoriaRepuesto.objects.create(nombre='Categoría Reportes')
        cls.article = Repuesto.objects.create(
            codigo_parte='REP-REPORTES',
            descripcion='Artículo reportes',
            ubicacion_bodega='A-1',
            unidad_medida='unidad',
            categoria=category,
            stock_actual=1,
            stock_minimo=2,
        )
        cls.work = Obra.objects.create(
            codigo_ot='OT-REPORTES',
            nombre='Obra próxima',
            cliente=cls.client_record,
            estado='EN_EJECUCION',
            fecha_termino_estimada=timezone.localdate() + timedelta(days=5),
            supervisor=cls.supervisor,
        )
        cls.request_record = SolicitudMaterial.objects.create(
            obra=cls.work,
            articulo=cls.article,
            cantidad_solicitada=1,
            solicitado_por=cls.supervisor,
        )
        cls.document = DocumentoVenta.objects.create(
            numero_documento='DV-REPORTES',
            cliente=cls.client_record,
            fecha=timezone.localdate(),
            vencimiento=timezone.localdate() + timedelta(days=10),
            total=1000,
        )
        cls.invoice = FacturaCompra.objects.create(
            proveedor=cls.provider,
            fecha=timezone.localdate(),
            numero_documento='FC-REPORTES',
            tipo_documento='Factura',
            monto=1000,
        )
        for movement_type in ('INGRESO', 'SALIDA'):
            MovimientoBodega.objects.create(
                tipo=movement_type,
                cantidad=1,
                repuesto=cls.article,
                responsable=cls.manager,
            )

    @staticmethod
    def user_with_role(username, role):
        user = Trabajador.objects.create_user(username=username, password='test-safe-password')
        group, _ = Group.objects.get_or_create(name=role)
        user.groups.add(group)
        return user

    def test_client_filter_is_shared_by_table_and_excel_report(self):
        self.client.force_login(self.finance)
        response = self.client.get('/api/clientes/?razon_social=Reportes')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['razon_social'] for row in response.json()['items']], [
            'Cliente Reportes'
        ])

        columns = json.dumps([
            {'key': 'razon_social', 'label': 'Razón social'},
            {'key': 'correo', 'label': 'Correo'},
        ])
        report = self.client.get(
            '/api/reportes/clientes/xlsx/',
            {'razon_social': 'Reportes', 'columns': columns},
        )
        self.assertEqual(report.status_code, 200)
        workbook = load_workbook(BytesIO(report.content), read_only=True)
        values = list(workbook.active.values)
        self.assertEqual(values[0], ('Razón social', 'Correo'))
        self.assertEqual(values[1], ('Cliente Reportes', 'reportes@cliente.cl'))

    def test_pdf_report_and_invalid_filter_response(self):
        self.client.force_login(self.finance)
        pdf = self.client.get('/api/reportes/proveedores/pdf/')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))

        invalid = self.client.get('/api/facturas/?fecha_inicio=no-es-fecha')
        self.assertEqual(invalid.status_code, 400)

    def test_advanced_filters_cover_invoice_inventory_kardex_works_and_requests(self):
        today = timezone.localdate().isoformat()
        self.client.force_login(self.finance)
        invoices = self.client.get(
            '/api/facturas/',
            {'fecha_inicio': today, 'fecha_termino': today, 'proveedor': 'Reportes'},
        )
        self.assertEqual(invoices.status_code, 200)
        self.assertEqual([item['numero_documento'] for item in invoices.json()['items']], [
            'FC-REPORTES'
        ])

        self.client.force_login(self.warehouse)
        articles = self.client.get(
            '/api/articulos/?categoria=Reportes&stock_bajo=1&activo=1'
        )
        self.assertEqual([item['codigo_parte'] for item in articles.json()['items']], [
            'REP-REPORTES'
        ])
        requests = self.client.get(
            '/api/solicitudes/?estado=PENDIENTE&obra=OT-REPORTES'
        )
        self.assertEqual(len(requests.json()['items']), 1)

        self.client.force_login(self.supervisor)
        works = self.client.get(
            '/api/obras/?estado=EN_EJECUCION&supervisor=supervisor-reports'
        )
        self.assertEqual([item['codigo_ot'] for item in works.json()['items']], [
            'OT-REPORTES'
        ])

        self.client.force_login(self.manager)
        kardex = self.client.get(
            '/api/kardex/',
            {'tipo': 'SALIDA', 'fecha_inicio': today, 'fecha_termino': today},
        )
        self.assertEqual([item['clase_movimiento'] for item in kardex.json()['items']], [
            'SALIDA'
        ])

    def test_dashboard_is_manager_only_and_has_thirty_days_of_movement_data(self):
        self.client.force_login(self.manager)
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['movimientos_30_dias']), 30)
        self.assertGreaterEqual(payload['kpis']['stock_critico'], 1)
        self.assertEqual(payload['kpis']['ingresos_mes'], 1)
        self.assertEqual(payload['kpis']['salidas_mes'], 1)
        self.assertTrue(payload['actividades_kardex'])
        self.assertNotIn('saldo', payload['kpis'])

        self.client.force_login(self.finance)
        denied = self.client.get('/api/dashboard/')
        self.assertEqual(denied.status_code, 403)

    def test_alerts_are_scoped_by_role_and_do_not_expose_pending_sales_to_warehouse(self):
        self.client.force_login(self.supervisor)
        response = self.client.get('/api/alertas/')
        self.assertEqual(response.status_code, 200)
        groups = {item['tipo']: item for item in response.json()['groups']}
        self.assertIn('stock', groups)
        self.assertIn('solicitud', groups)
        self.assertIn('obra', groups)
        self.assertNotIn('documento', groups)

        self.client.force_login(self.warehouse)
        warehouse_groups = {
            item['tipo'] for item in self.client.get('/api/alertas/').json()['groups']
        }
        self.assertIn('solicitud', warehouse_groups)
        self.assertNotIn('documento', warehouse_groups)

        self.client.force_login(self.finance)
        finance_groups = {
            item['tipo'] for item in self.client.get('/api/alertas/').json()['groups']
        }
        self.assertIn('documento', finance_groups)
        self.assertNotIn('solicitud', finance_groups)

    def test_report_permissions_match_existing_resource_access(self):
        self.client.force_login(self.warehouse)
        denied = self.client.get('/api/reportes/proveedores/pdf/')
        self.assertEqual(denied.status_code, 403)
        allowed = self.client.get('/api/reportes/articulos/xlsx/')
        self.assertEqual(allowed.status_code, 200)

    def test_excel_cells_neutralize_formula_like_text(self):
        self.assertEqual(_cell_value('=1+1'), "'=1+1")
        self.assertEqual(_cell_value('  @SUM(A1:A2)'), "'  @SUM(A1:A2)")
