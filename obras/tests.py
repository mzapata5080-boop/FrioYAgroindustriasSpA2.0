"""Pruebas de Obras, Solicitudes/Reservas, Salidas FIFO y aislamiento por Supervisor."""
import json
import tempfile
import uuid
from decimal import Decimal
from pathlib import Path
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from finanzas.models import Cliente, FacturaCompra, FacturaCompraDetalle, Proveedor
from inventario.models import CategoriaRepuesto, Repuesto
from obras.forms import ObraForm, PresupuestoForm
from obras.models import Obra, SolicitudMaterial
from usuarios.models import Trabajador


class ObrasSolicitudesSalidasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gerente = Trabajador.objects.create_user('gerente_obra', first_name='Carlos', last_name='Gerente')
        cls.bodega = Trabajador.objects.create_user('bodega_obra', first_name='Ana', last_name='Bodega')
        cls.sup1 = Trabajador.objects.create_user('sup1', first_name='Luis', last_name='Supervisor')
        cls.sup2 = Trabajador.objects.create_user('sup2', first_name='Pedro', last_name='OtroSup')
        cls.tecnico = Trabajador.objects.create_user('tec1', first_name='Mario', last_name='Técnico')

        for user, role in (
            (cls.gerente, 'Gerencia'),
            (cls.bodega, 'Bodega'),
            (cls.sup1, 'Supervisor de Obra'),
            (cls.sup2, 'Supervisor de Obra'),
        ):
            grp, _ = Group.objects.get_or_create(name=role)
            user.groups.add(grp)

        cls.cliente = Cliente.objects.create(
            rut='76.111.222-3',
            razon_social='Agrofrío Sur SpA',
            telefono='+56911111111',
            correo='contacto@agrofrio.cl',
            direccion='Ruta 5 Sur Km 120',
        )
        cls.cat = CategoriaRepuesto.objects.create(nombre='Tuberías y Válvulas')
        cls.art = Repuesto.objects.create(
            codigo_parte='VAL-10',
            descripcion='Válvula solenoide 1/2',
            ubicacion_bodega='Estante B2',
            unidad_medida='unidad',
            categoria=cls.cat,
        )
        cls.prov = Proveedor.objects.create(
            rut='77.222.333-4',
            razon_social='Importadora Frío',
            giro='Insumos',
            telefono='2222222',
            email='ventas@impfrio.cl',
            direccion='Santiago',
        )
        cls.factura = FacturaCompra.objects.create(
            proveedor=cls.prov,
            fecha='2026-11-20',
            numero_documento='F-900',
            tipo_documento='Factura',
            monto='50000.00',
        )

    def post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type='application/json')

    def ingresar_lote(self, cantidad, precio):
        linea = FacturaCompraDetalle.objects.create(
            factura=self.factura,
            articulo=self.art,
            cantidad=Decimal(str(cantidad)),
            precio_unitario=Decimal(str(precio)),
        )
        self.client.force_login(self.bodega)
        resp = self.post_json('/api/ingresos/', {
            'solicitud_id': str(uuid.uuid4()),
            'factura': self.factura.pk,
            'recepcion_detalles': [
                {'detalle_factura': linea.pk, 'cantidad': str(cantidad)},
            ],
        })
        self.assertEqual(resp.status_code, 201, resp.content)

    def crear_obra_sup1(self):
        self.client.force_login(self.sup1)
        resp = self.post_json('/api/obras/', {
            'codigo_ot': 'OT-2026-01',
            'nombre': 'Cámara Frigorífica Planta 1',
            'cliente': self.cliente.pk,
            'tipo_servicio': 'INSTALACION',
            'presupuesto_estimado': '2500000.00',
            'direccion': 'Curicó',
            'estado': 'EN_EJECUCION',
            'fecha_inicio': '2026-11-21',
            'fecha_termino_estimada': '2026-12-15',
            'supervisor': self.sup1.pk,
            'tecnicos': [self.tecnico.pk],
        })
        self.assertEqual(resp.status_code, 201, resp.content)
        return Obra.objects.get(codigo_ot='OT-2026-01')

    def test_obra_form_marks_tecnicos_as_multiple_select(self):
        self.client.force_login(self.sup1)
        response = self.client.get('/api/obras/')

        self.assertEqual(response.status_code, 200)
        fields = {field['name']: field for field in response.json()['fields']}
        self.assertTrue(fields['tecnicos']['multiple'])
        self.assertEqual(fields['presupuesto_estimado']['step'], '1')

    def test_obra_and_presupuesto_reject_new_fractional_amounts(self):
        obra_form = ObraForm(data={
            'codigo_ot': 'OT-PRECIO-01',
            'nombre': 'Obra con presupuesto decimal',
            'cliente': self.cliente.pk,
            'tipo_servicio': 'INSTALACION',
            'presupuesto_estimado': '1000.50',
            'direccion': 'Curicó',
            'estado': 'EN_EJECUCION',
            'fecha_inicio': '2026-11-21',
            'fecha_termino_estimada': '2026-12-15',
            'supervisor': self.sup1.pk,
            'tecnicos': [],
        })
        self.assertFalse(obra_form.is_valid())
        self.assertIn('presupuesto_estimado', obra_form.errors)

        obra = Obra.objects.create(
            codigo_ot='OT-PRECIO-02',
            nombre='Obra para presupuesto',
            cliente=self.cliente,
            supervisor=self.sup1,
        )
        presupuesto_form = PresupuestoForm(data={
            'obra': obra.pk,
            'version': '1',
            'estado': 'BORRADOR',
            'monto_materiales_estimado': '1000.50',
            'monto_mano_obra_estimado': '0',
            'monto_otros_estimado': '0',
            'observaciones': '',
        })
        self.assertFalse(presupuesto_form.is_valid())
        self.assertIn('monto_materiales_estimado', presupuesto_form.errors)

        historical_obra = Obra.objects.create(
            codigo_ot='OT-PRECIO-03',
            nombre='Obra con valor histórico',
            cliente=self.cliente,
            supervisor=self.sup1,
            presupuesto_estimado='1000.50',
        )
        historical_obra_form = ObraForm(instance=historical_obra, data={
            'codigo_ot': historical_obra.codigo_ot,
            'nombre': 'Obra con valor histórico editada',
            'cliente': self.cliente.pk,
            'tipo_servicio': 'INSTALACION',
            'presupuesto_estimado': '1000.50',
            'direccion': '',
            'estado': 'PLANIFICADA',
            'fecha_inicio': '',
            'fecha_termino_estimada': '',
            'supervisor': self.sup1.pk,
            'tecnicos': [],
        })
        self.assertTrue(historical_obra_form.is_valid(), historical_obra_form.errors)
        self.assertEqual(
            historical_obra_form.fields['presupuesto_estimado'].widget.attrs['step'],
            '0.01'
        )

        historical_budget = Obra.objects.get(pk=obra.pk).presupuestos.create(
            version=1,
            monto_materiales_estimado='1000.50',
        )
        historical_budget_form = PresupuestoForm(instance=historical_budget, data={
            'obra': obra.pk,
            'version': '1',
            'estado': 'BORRADOR',
            'monto_materiales_estimado': '1000.50',
            'monto_mano_obra_estimado': '0',
            'monto_otros_estimado': '0',
            'observaciones': 'Ajuste de descripción',
        })
        self.assertTrue(historical_budget_form.is_valid(), historical_budget_form.errors)
        self.assertEqual(
            historical_budget_form.fields['monto_materiales_estimado'].widget.attrs['step'],
            '0.01'
        )

    def test_salida_form_includes_obra_cliente_mapping(self):
        obra = Obra.objects.create(
            codigo_ot='OT-SALIDA-01',
            nombre='Obra para salida',
            cliente=self.cliente,
            supervisor=self.sup1,
        )
        self.client.force_login(self.bodega)

        response = self.client.get('/api/salidas/')

        self.assertEqual(response.status_code, 200)
        self.assertIn({
            'id': obra.pk,
            'cliente_id': self.cliente.pk,
            'codigo_ot': obra.codigo_ot,
        }, response.json()['works'])

    def test_salida_form_includes_approved_request_article_and_pending_quantity(self):
        obra = Obra.objects.create(
            codigo_ot='OT-SALIDA-02',
            nombre='Obra con solicitud',
            cliente=self.cliente,
            supervisor=self.sup1,
        )
        solicitud = SolicitudMaterial.objects.create(
            obra=obra,
            articulo=self.art,
            cantidad_solicitada='5',
            cantidad_reservada='5',
            cantidad_entregada='2',
            estado='PARCIAL',
            solicitado_por=self.sup1,
        )
        self.client.force_login(self.bodega)

        response = self.client.get('/api/salidas/')

        self.assertEqual(response.status_code, 200)
        self.assertIn({
            'id': solicitud.pk,
            'obra_id': obra.pk,
            'articulo_id': self.art.pk,
            'cantidad_pendiente': '3.00',
        }, response.json()['materialRequests'])

    def test_supervisor_solo_ve_su_obra_y_sus_documentos(self):
        obra1 = self.crear_obra_sup1()
        self.client.force_login(self.sup2)
        self.assertEqual(self.client.get('/api/obras/').json()['items'], [])

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            with self.settings(ARCHIVOS_PRIVADOS_LOCAL_DIR=tmpdir):
                self.client.force_login(self.sup1)
                pdf = SimpleUploadedFile('plano.pdf', b'%PDF-1.4\n%test\n', content_type='application/pdf')
                res_subida = self.client.post(f'/api/obras/{obra1.id}/documentos/', {'archivo': pdf})
                self.assertEqual(res_subida.status_code, 201)
                archivo_id = res_subida.json()['item']['id']

                res_descarga = self.client.get(f'/api/archivos/{archivo_id}/descargar/')
                self.assertEqual(res_descarga.status_code, 200)
                res_descarga.close()

                self.client.force_login(self.sup2)
                self.assertEqual(self.client.get('/api/obras/').json()['items'], [])
                self.assertEqual(self.client.get(f'/api/archivos/{archivo_id}/descargar/').status_code, 403)

    def test_solicitud_aprobar_reservar_y_cancelar_libera_sin_doble_descuento(self):
        self.ingresar_lote(10, 1000)
        obra = self.crear_obra_sup1()

        self.client.force_login(self.sup1)
        res_sol = self.post_json('/api/solicitudes/', {
            'obra': obra.pk,
            'articulo': self.art.pk,
            'cantidad_solicitada': '4',
            'motivo': 'Montaje línea de succión',
        })
        self.assertEqual(res_sol.status_code, 201, res_sol.content)
        sol_id = res_sol.json()['item']['id']

        self.client.force_login(self.sup2)
        self.assertEqual(self.client.get('/api/solicitudes/').json()['items'], [])
        self.assertEqual(self.post_json(f'/api/solicitudes/{sol_id}/', {'accion': 'cancelar'}).status_code, 403)

        self.client.force_login(self.bodega)
        apr = self.post_json(f'/api/solicitudes/{sol_id}/', {'accion': 'aprobar'})
        self.assertEqual(apr.status_code, 200, apr.content)
        self.art.refresh_from_db()
        self.assertEqual(self.art.stock_actual, Decimal('10.00'))
        self.assertEqual(self.art.stock_reservado, Decimal('4.00'))
        self.assertEqual(self.art.stock_disponible, Decimal('6.00'))

        self.client.force_login(self.sup1)
        sol2_id = self.post_json('/api/solicitudes/', {
            'obra': obra.pk,
            'articulo': self.art.pk,
            'cantidad_solicitada': '7',
        }).json()['item']['id']
        self.client.force_login(self.bodega)
        self.assertEqual(self.post_json(f'/api/solicitudes/{sol2_id}/', {'accion': 'aprobar'}).status_code, 400)

        canc = self.post_json(f'/api/solicitudes/{sol_id}/', {'accion': 'cancelar'})
        self.assertEqual(canc.status_code, 200)
        self.art.refresh_from_db()
        self.assertEqual(self.art.stock_actual, Decimal('10.00'))
        self.assertEqual(self.art.stock_reservado, Decimal('0.00'))
        self.assertEqual(self.art.stock_disponible, Decimal('10.00'))

    def test_salida_usa_fifo_libera_reserva_y_registra_trabajador_real_en_kardex(self):
        self.ingresar_lote(3, 1000)
        self.ingresar_lote(5, 2000)
        obra = self.crear_obra_sup1()

        self.client.force_login(self.sup1)
        sol_id = self.post_json('/api/solicitudes/', {
            'obra': obra.pk,
            'articulo': self.art.pk,
            'cantidad_solicitada': '4',
        }).json()['item']['id']

        self.client.force_login(self.bodega)
        self.post_json(f'/api/solicitudes/{sol_id}/', {'accion': 'aprobar'})

        bad_out = self.post_json('/api/salidas/', {
            'solicitud_id': str(uuid.uuid4()),
            'solicitud_material': sol_id,
            'obra': obra.pk,
            'articulo': self.art.pk,
            'cantidad': '5',
            'receptor': self.tecnico.pk,
        })
        self.assertEqual(bad_out.status_code, 400)

        ok_out = self.post_json('/api/salidas/', {
            'solicitud_id': str(uuid.uuid4()),
            'solicitud_material': sol_id,
            'obra': obra.pk,
            'cliente': self.cliente.pk,
            'articulo': self.art.pk,
            'cantidad': '4',
            'receptor': self.tecnico.pk,
            'observaciones': 'Entrega completa a técnico en terreno',
        })
        self.assertEqual(ok_out.status_code, 201, ok_out.content)

        self.art.refresh_from_db()
        self.assertEqual(self.art.stock_actual, Decimal('4.00'))
        self.assertEqual(self.art.stock_reservado, Decimal('0.00'))

        self.client.force_login(self.gerente)
        kardex = self.client.get('/api/kardex/').json()['items']
        salida_kardex = kardex[0]
        self.assertEqual(salida_kardex['tipo'], 'SALIDA')
        self.assertEqual(salida_kardex['costo_total_fifo'], '5000.00')
        self.assertEqual(salida_kardex['responsable_id'], self.bodega.pk)
        self.assertEqual(salida_kardex['responsable'], 'Ana Bodega')
        self.assertEqual(salida_kardex['receptor_id'], self.tecnico.pk)
        self.assertEqual(salida_kardex['obra_codigo'], 'OT-2026-01')
        self.assertEqual(SolicitudMaterial.objects.get(pk=sol_id).estado, 'ENTREGADA')