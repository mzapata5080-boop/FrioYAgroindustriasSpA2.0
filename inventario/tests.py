import json
import uuid
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import Group
from django.db import IntegrityError
from inventario.models import CategoriaRepuesto, Repuesto, MovimientoBodega, RecepcionIngreso
from usuarios.models import Trabajador
from finanzas.models import (
    Proveedor,
    FacturaCompra,
    FacturaCompraDetalle,
    RecepcionCompra,
    RecepcionDetalle,
)
from finanzas.forms import FacturaCompraDetalleForm


class InventoryApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.warehouse = Trabajador.objects.create_user('bodega', first_name='Ana', last_name='Pérez')
        cls.manager = Trabajador.objects.create_user('gerente')
        cls.finance = Trabajador.objects.create_user('finanzas')
        for user, role in ((cls.warehouse, 'Bodega'), (cls.manager, 'Gerencia'), (cls.finance, 'Finanzas')):
            user.groups.add(Group.objects.create(name=role))
        cls.category = CategoriaRepuesto.objects.create(nombre='Materiales')
        cls.article = Repuesto.objects.create(
            codigo_parte='CL-01',
            descripcion='Clavos',
            ubicacion_bodega='A',
            unidad_medida='kg',
            categoria=cls.category,
        )
        cls.article_unit = Repuesto.objects.create(
            codigo_parte='TOR-01',
            descripcion='Tornillos',
            ubicacion_bodega='B',
            unidad_medida='unidad',
            categoria=cls.category,
        )
        cls.provider = Proveedor.objects.create(rut='11111111-1', razon_social='Proveedor')
        cls.invoice = FacturaCompra.objects.create(
            proveedor=cls.provider,
            fecha='2026-11-18',
            numero_documento='777',
            tipo_documento='Factura',
            monto='19900',
        )
        cls.invoice_line = FacturaCompraDetalle.objects.create(
            factura=cls.invoice,
            articulo=cls.article,
            cantidad='5',
            precio_unitario='1990',
        )
        cls.invoice_line_unit = FacturaCompraDetalle.objects.create(
            factura=cls.invoice,
            articulo=cls.article_unit,
            cantidad='3',
            precio_unitario='100',
        )

    def setUp(self):
        self.client.force_login(self.warehouse)
        self.payload = {
            'solicitud_id': str(uuid.uuid4()),
            'factura': self.invoice.pk,
            'recepcion_detalles': [
                {'detalle_factura': self.invoice_line.pk, 'cantidad': '1.50'},
            ],
        }

    def post(self, path='/api/ingresos/', payload=None):
        return self.client.post(
            path,
            data=json.dumps(self.payload if payload is None else payload),
            content_type='application/json',
        )

    def test_receipt_updates_stock_and_links_everything(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock_actual, Decimal('1.50'))
        receipt = RecepcionIngreso.objects.get()
        self.assertEqual(receipt.factura_id, self.invoice.pk)
        self.assertEqual(receipt.responsable_id, self.warehouse.pk)
        self.assertEqual(receipt.subtotal_neto, Decimal('2985.00'))
        self.assertEqual(RecepcionCompra.objects.count(), 1)
        detail = RecepcionDetalle.objects.get()
        self.assertEqual(detail.detalle_factura_id, self.invoice_line.pk)
        self.assertEqual(detail.movimiento_id, receipt.movimiento_id)
        self.assertEqual(self.client.get('/api/ingresos/').json()['items'][0]['id'], receipt.movimiento_id)
        self.client.force_login(self.manager)
        row = self.client.get('/api/kardex/').json()['items'][0]
        self.assertEqual(row['responsable_id'], self.warehouse.pk)
        self.assertEqual(row['responsable'], 'Ana Pérez')
        self.assertEqual(row['unidad_medida'], 'kg')

    def test_identical_retry_does_not_duplicate(self):
        self.assertEqual(self.post().status_code, 201)
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['repeated'])
        self.assertEqual(RecepcionCompra.objects.count(), 1)
        self.assertEqual(MovimientoBodega.objects.count(), 1)
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock_actual, Decimal('1.50'))

    def test_uuid_cannot_be_reused_for_other_values(self):
        self.post()
        self.payload['recepcion_detalles'][0]['cantidad'] = '2.00'
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(MovimientoBodega.objects.count(), 1)

    def test_uuid_cannot_be_reused_by_other_worker(self):
        self.post()
        self.client.force_login(self.manager)
        self.assertEqual(self.post().status_code, 409)

    def test_unknown_article_and_invoice_rejected(self):
        for key in ('detalle_factura', 'factura'):
            if key == 'detalle_factura':
                payload = dict(
                    self.payload,
                    recepcion_detalles=[{'detalle_factura': 999999, 'cantidad': '1'}],
                )
            else:
                payload = dict(self.payload, factura=999999)
            self.assertEqual(self.post(payload=payload).status_code, 400)
        self.assertFalse(MovimientoBodega.objects.exists())

    def test_quantity_validation(self):
        for quantity in ('0', '-1', '1.001', 'NaN', 'Infinity'):
            self.assertEqual(
                self.post(
                    payload=dict(
                        self.payload,
                        recepcion_detalles=[
                            {'detalle_factura': self.invoice_line.pk, 'cantidad': quantity}
                        ],
                    )
                ).status_code,
                400,
            )

    def test_fractional_units_rejected(self):
        self.article.unidad_medida = 'unidad'
        self.article.save()
        self.assertEqual(self.post().status_code, 400)

    def test_negative_invoice_line_price_rejected(self):
        form = FacturaCompraDetalleForm(
            data={
                'articulo': self.article.pk,
                'cantidad': '1',
                'precio_unitario': '-1',
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn('precio_unitario', form.errors)

    def test_overflow_rejected_without_movement(self):
        self.article.stock_actual = Decimal('9999999999999.99')
        self.article.save()
        self.assertEqual(self.post().status_code, 400)
        self.assertFalse(MovimientoBodega.objects.exists())

    def test_receipt_failure_rolls_back_movement_and_stock(self):
        with patch('inventario.api.RecepcionIngreso.objects.create', side_effect=IntegrityError):
            self.assertEqual(self.post().status_code, 400)
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock_actual, 0)
        self.assertFalse(RecepcionCompra.objects.exists())
        self.assertFalse(RecepcionDetalle.objects.exists())
        self.assertFalse(MovimientoBodega.objects.exists())

    def test_partial_receipts_create_separate_headers_and_never_exceed_ordered_quantity(self):
        self.assertEqual(self.post().status_code, 201)
        second = dict(
            self.payload,
            solicitud_id=str(uuid.uuid4()),
            recepcion_detalles=[{'detalle_factura': self.invoice_line.pk, 'cantidad': '2'}],
        )
        self.assertEqual(self.post(payload=second).status_code, 201)
        self.assertEqual(RecepcionCompra.objects.filter(factura=self.invoice).count(), 2)
        third = dict(
            self.payload,
            solicitud_id=str(uuid.uuid4()),
            recepcion_detalles=[{'detalle_factura': self.invoice_line.pk, 'cantidad': '2'}],
        )
        self.assertEqual(self.post(payload=third).status_code, 400)
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock_actual, Decimal('3.50'))

    def test_one_receipt_can_receive_multiple_invoice_lines(self):
        payload = dict(
            self.payload,
            recepcion_detalles=[
                {'detalle_factura': self.invoice_line.pk, 'cantidad': '1.50'},
                {'detalle_factura': self.invoice_line_unit.pk, 'cantidad': '2'},
            ],
        )
        response = self.post(payload=payload)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(RecepcionCompra.objects.count(), 1)
        self.assertEqual(RecepcionDetalle.objects.count(), 2)
        self.article.refresh_from_db()
        self.article_unit.refresh_from_db()
        self.assertEqual(self.article.stock_actual, Decimal('1.50'))
        self.assertEqual(self.article_unit.stock_actual, Decimal('2'))

    def test_legacy_invoice_receipts_reduce_the_pending_quantity(self):
        legacy_request_id = uuid.UUID(self.payload['solicitud_id'])
        movement = MovimientoBodega.objects.create(
            tipo='INGRESO',
            cantidad='2',
            repuesto=self.article,
            responsable=self.warehouse,
        )
        RecepcionIngreso.objects.create(
            solicitud_id=legacy_request_id,
            factura=self.invoice,
            movimiento=movement,
            responsable=self.warehouse,
            unidad_medida='kg',
            precio_unitario_neto='1990',
            subtotal_neto='3980',
            cantidad_disponible='2',
        )
        self.article.stock_actual = Decimal('2')
        self.article.save(update_fields=['stock_actual'])
        metadata = self.client.get('/api/ingresos/').json()
        line = next(item for item in metadata['invoiceDetails'] if item['id'] == self.invoice_line.pk)
        self.assertEqual(line['pendiente'], '3.00')
        stale_retry = dict(
            self.payload,
            recepcion_detalles=[{'detalle_factura': self.invoice_line.pk, 'cantidad': '1'}],
        )
        self.assertEqual(self.post(payload=stale_retry).status_code, 409)
        overreceipt = dict(
            self.payload,
            solicitud_id=str(uuid.uuid4()),
            recepcion_detalles=[{'detalle_factura': self.invoice_line.pk, 'cantidad': '4'}],
        )
        self.assertEqual(self.post(payload=overreceipt).status_code, 400)
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock_actual, Decimal('2'))

    def test_saving_invoice_and_lines_does_not_change_stock(self):
        self.client.force_login(self.finance)
        response = self.post(
            '/api/facturas/',
            {
                'proveedor': self.provider.pk,
                'fecha': '2026-11-20',
                'numero_documento': '778',
                'tipo_documento': 'Factura',
                'monto': '9950',
                'observaciones': '',
                'detalles': [
                    {
                        'articulo': self.article.pk,
                        'cantidad': '5',
                        'precio_unitario': '1990',
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock_actual, 0)

    def test_invoice_lines_cannot_change_after_a_reception(self):
        self.assertEqual(self.post().status_code, 201)
        self.client.force_login(self.finance)
        response = self.post(
            f'/api/facturas/{self.invoice.pk}/',
            {
                'detalles': [
                    {
                        'articulo': self.article.pk,
                        'cantidad': '6',
                        'precio_unitario': '1990',
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 400)
        self.invoice_line.refresh_from_db()
        self.assertEqual(self.invoice_line.cantidad, Decimal('5'))

    def edit_unit(self, unit):
        return self.post(
            f'/api/articulos/{self.article.pk}/',
            {
                'codigo_parte': 'CL-01',
                'descripcion': 'Clavos',
                'ubicacion_bodega': 'A',
                'unidad_medida': unit,
                'categoria': self.category.pk,
                'stock_minimo': '0',
            },
        )

    def test_unit_change_blocked_with_stock(self):
        self.article.stock_actual = 10
        self.article.save()
        self.assertEqual(self.edit_unit('m').status_code, 400)
        self.article.refresh_from_db()
        self.assertEqual(self.article.unidad_medida, 'kg')

    def test_unit_change_blocked_with_history_even_if_stock_zero(self):
        MovimientoBodega.objects.create(tipo='INGRESO', cantidad=1, repuesto=self.article)
        self.assertEqual(self.edit_unit('m').status_code, 400)

    def test_unit_change_allowed_before_use(self):
        self.assertEqual(self.edit_unit('m').status_code, 200)

    def test_same_unit_allows_other_edits(self):
        self.post()
        self.assertEqual(self.edit_unit('kg').status_code, 200)

    def test_permissions_enforced_by_api(self):
        self.assertEqual(self.client.get('/api/kardex/').status_code, 403)
        self.assertEqual(self.client.get('/api/trabajadores/').status_code, 403)
        self.assertEqual(self.client.get('/api/facturas/').status_code, 403)
        self.client.force_login(self.finance)
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.client.get('/api/kardex/').status_code, 403)
        self.assertEqual(self.client.get('/api/articulos/').status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get('/api/ingresos/').status_code, 401)

    def test_receipt_metadata_includes_unit_and_search_labels(self):
        body = self.client.get('/api/ingresos/').json()
        self.assertEqual(body['articles'][0]['unidad_medida'], 'kg')
        fields = {field['name']: field for field in body['fields']}
        self.assertIn('777 — Proveedor', fields['factura']['choices'][1][1])
        self.assertEqual(fields['recepcion_detalles']['type'], 'receipt_details')
        self.assertEqual(body['invoiceDetails'][0]['unidad_medida'], 'kg')

    def test_old_movement_does_not_invent_responsible(self):
        MovimientoBodega.objects.create(tipo='INGRESO', cantidad=1, repuesto=self.article)
        self.client.force_login(self.manager)
        row = self.client.get('/api/kardex/').json()['items'][0]
        self.assertIsNone(row['responsable_id'])
        self.assertEqual(row['responsable'], 'Sin registro')

    def test_csrf_required_for_authenticated_writes(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.warehouse)
        self.assertEqual(
            client.post('/api/ingresos/', data=json.dumps(self.payload), content_type='application/json').status_code,
            403,
        )
        token = client.get('/api/session/').json()['csrfToken']
        self.assertEqual(
            client.post(
                '/api/ingresos/',
                data=json.dumps(self.payload),
                content_type='application/json',
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            201,
        )

    def test_schema_audit_is_read_only(self):
        from io import StringIO
        from django.core.management import call_command

        before = (Repuesto.objects.count(), MovimientoBodega.objects.count(), RecepcionIngreso.objects.count())
        output = StringIO()
        call_command('auditar_inventario', stdout=output)
        self.assertIn('Estructura revisada', output.getvalue())
        self.assertEqual(
            before,
            (Repuesto.objects.count(), MovimientoBodega.objects.count(), RecepcionIngreso.objects.count()),
        )

    def test_article_creation_defaults_to_zero_stock_and_active(self):
        payload = {
            'codigo_parte': 'VAL-01',
            'descripcion': 'Válvula de bola',
            'ubicacion_bodega': 'Estante 4',
            'unidad_medida': 'unidad',
            'categoria': self.category.pk,
            'stock_minimo': '2',
        }
        response = self.client.post('/api/articulos/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        created = Repuesto.objects.get(codigo_parte='VAL-01')
        self.assertEqual(created.stock_actual, 0)
        self.assertTrue(created.activo)
        self.assertEqual(created.stock_minimo, Decimal('2'))

        ingresos_res = self.client.get('/api/ingresos/').json()
        article_ids = [a['id'] for a in ingresos_res['articles']]
        self.assertIn(created.pk, article_ids)

    def test_duplicate_article_code_rejected(self):
        payload = {
            'codigo_parte': self.article.codigo_parte,
            'descripcion': 'Otro clavo',
            'ubicacion_bodega': 'B',
            'unidad_medida': 'kg',
            'categoria': self.category.pk,
            'stock_minimo': '0',
        }
        response = self.client.post('/api/articulos/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('codigo_parte', response.json().get('errors', {}))

    def test_unauthorized_role_cannot_modify_catalog(self):
        self.client.force_login(self.finance)
        payload = {
            'codigo_parte': 'FIN-01',
            'descripcion': 'Intento no autorizado',
            'ubicacion_bodega': 'X',
            'unidad_medida': 'unidad',
            'categoria': self.category.pk,
            'stock_minimo': '0',
        }
        res_article = self.client.post('/api/articulos/', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res_article.status_code, 403)

        res_cat = self.client.post('/api/categorias/', data=json.dumps({'nombre': 'Nueva Cat'}), content_type='application/json')
        self.assertEqual(res_cat.status_code, 403)

    def test_article_activation_and_deactivation(self):
        response = self.client.post(
            f'/api/articulos/{self.article.pk}/',
            data=json.dumps({'activo': False}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.article.refresh_from_db()
        self.assertFalse(self.article.activo)

        response = self.client.post(
            f'/api/articulos/{self.article.pk}/',
            data=json.dumps({'activo': True}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.article.refresh_from_db()
        self.assertTrue(self.article.activo)

    def test_category_activation_and_deactivation(self):
        response = self.client.post(
            f'/api/categorias/{self.category.pk}/',
            data=json.dumps({'activo': False}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.category.refresh_from_db()
        self.assertFalse(self.category.activo)

    def test_new_category_is_active_by_default_and_form_advertises_default(self):
        fields = self.client.get('/api/categorias/').json()['fields']
        active = next(field for field in fields if field['name'] == 'activo')
        self.assertTrue(active['initial'])
        response = self.client.post(
            '/api/categorias/',
            data=json.dumps({'nombre': 'Refrigeración', 'activo': active['initial']}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(CategoriaRepuesto.objects.get(nombre='Refrigeración').activo)

    def test_article_list_includes_category_name_and_unit_display(self):
        res = self.client.get('/api/articulos/').json()
        items = res['items']
        self.assertTrue(len(items) > 0)
        art = next(x for x in items if x['id'] == self.article.pk)
        self.assertEqual(art['categoria_nombre'], self.category.nombre)
        self.assertEqual(art['unidad_medida_display'], 'Kilogramos')
        self.assertEqual(art['codigo_parte'], 'CL-01')