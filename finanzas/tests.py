from decimal import Decimal
from datetime import date
import json
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from frio_agroindustria.api_common import schema, serialize
from frio_agroindustria.api_resources import RESOURCES
from frio_agroindustria.api_crud import _validate_invoice_details
from inventario.models import CategoriaRepuesto, Repuesto
from obras.models import Obra
from usuarios.models import Trabajador
from .forms import (
    ClienteForm,
    ProveedorForm,
    FacturaCompraForm,
    FacturaCompraDetalleForm,
    PresupuestoDetalleForm,
)
from .models import (
    Cliente,
    Proveedor,
    FacturaCompra,
    FacturaCompraDetalle,
    Presupuesto,
    PresupuestoDetalle,
    DocumentoVenta,
    PagoDocumento,
    NotaCredito,
)


class ContactFieldsTests(TestCase):
    def test_cliente_contact_fields_are_in_form_and_api_schema(self):
        fields = ClienteForm().fields

        self.assertIn('representante', fields)
        self.assertIn('cargo_contacto', fields)
        self.assertFalse(fields['representante'].required)
        self.assertFalse(fields['cargo_contacto'].required)
        self.assertEqual(
            {field['name'] for field in schema(RESOURCES['clientes'][1]())},
            set(fields)
        )
        cliente = Cliente(
            rut='76.123.456-7',
            razon_social='Cliente de prueba',
            telefono='',
            correo='',
            direccion='',
            representante='Representante de prueba',
            cargo_contacto='Gerente'
        )
        serialized = serialize(cliente)
        self.assertEqual(serialized['representante'], 'Representante de prueba')
        self.assertEqual(serialized['cargo_contacto'], 'Gerente')

    def test_proveedor_payment_fields_are_in_form_and_api_schema(self):
        fields = ProveedorForm().fields

        self.assertIn('encargado_pagos', fields)
        self.assertIn('correo_pagos', fields)
        self.assertFalse(fields['encargado_pagos'].required)
        self.assertFalse(fields['correo_pagos'].required)
        self.assertEqual(
            {field['name'] for field in schema(RESOURCES['proveedores'][1]())},
            set(fields)
        )
        proveedor = Proveedor(
            rut='76.123.456-8',
            razon_social='Proveedor de prueba',
            giro='',
            telefono='',
            email='',
            direccion='',
            encargado_pagos='Encargado de prueba',
            correo_pagos='pagos@ejemplo.cl'
        )
        serialized = serialize(proveedor)
        self.assertEqual(serialized['encargado_pagos'], 'Encargado de prueba')
        self.assertEqual(serialized['correo_pagos'], 'pagos@ejemplo.cl')


class FacturaCompraDetailsTests(TestCase):
    def setUp(self):
        category = CategoriaRepuesto.objects.create(nombre='Prueba')
        self.unit_article = Repuesto.objects.create(
            codigo_parte='UNIT-01',
            descripcion='Artículo por unidad',
            ubicacion_bodega='A-1',
            unidad_medida='unidad',
            categoria=category
        )
        self.kg_article = Repuesto.objects.create(
            codigo_parte='KG-01',
            descripcion='Artículo por peso',
            ubicacion_bodega='A-2',
            unidad_medida='kg',
            categoria=category
        )
        self.proveedor = Proveedor.objects.create(
            rut='76.123.456-7',
            razon_social='Proveedor de prueba',
            giro='Giro',
            telefono='123',
            email='proveedor@ejemplo.cl',
            direccion='Dirección'
        )

    def test_quantity_must_be_positive_and_integral_for_unit_articles(self):
        fractional = FacturaCompraDetalleForm(data={
            'articulo': self.unit_article.pk,
            'cantidad': '1.50',
            'precio_unitario': '100'
        })
        self.assertFalse(fractional.is_valid())
        self.assertIn('cantidad', fractional.errors)

        zero = FacturaCompraDetalleForm(data={
            'articulo': self.kg_article.pk,
            'cantidad': '0',
            'precio_unitario': '100'
        })
        self.assertFalse(zero.is_valid())
        self.assertIn('cantidad', zero.errors)

    def test_fractional_quantity_and_zero_price_are_valid_for_weight_articles(self):
        form = FacturaCompraDetalleForm(data={
            'articulo': self.kg_article.pk,
            'cantidad': '1.25',
            'precio_unitario': '0'
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_fractional_unit_price_is_valid_for_decimal_pricing(self):
        form = FacturaCompraDetalleForm(data={
            'articulo': self.kg_article.pk,
            'cantidad': '1.25',
            'precio_unitario': '100.50'
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['precio_unitario'], Decimal('100.50'))

    def test_invoice_amount_must_be_positive(self):
        form = FacturaCompraForm(data={
            'proveedor': self.proveedor.pk,
            'fecha': '2026-11-20',
            'numero_documento': 'F-001',
            'tipo_documento': 'Factura',
            'monto': '0',
            'observaciones': ''
        })
        self.assertFalse(form.is_valid())
        self.assertIn('monto', form.errors)

    def test_fractional_invoice_amount_is_rejected_and_schema_uses_integer_step(self):
        form = FacturaCompraForm(data={
            'proveedor': self.proveedor.pk,
            'fecha': '2026-11-20',
            'numero_documento': 'F-002',
            'tipo_documento': 'Factura',
            'monto': '1000.50',
            'observaciones': ''
        })
        self.assertFalse(form.is_valid())
        self.assertIn('monto', form.errors)

        schema_fields = {
            field['name']: field
            for field in schema(RESOURCES['facturas'][1]())
        }
        self.assertEqual(schema_fields['monto']['step'], '1')
        self.assertEqual(
            FacturaCompraDetalleForm().fields['precio_unitario'].widget.attrs['step'],
            '0.01'
        )

    def test_existing_fractional_invoice_amount_can_be_kept_unchanged(self):
        invoice = FacturaCompra.objects.create(
            proveedor=self.proveedor,
            fecha='2026-11-20',
            numero_documento='F-003',
            tipo_documento='Factura',
            monto='1000.50'
        )
        form = FacturaCompraForm(instance=invoice, data={
            'proveedor': self.proveedor.pk,
            'fecha': '2026-11-20',
            'numero_documento': 'F-003 corregida',
            'tipo_documento': 'Factura',
            'monto': '1000.50',
            'observaciones': ''
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fields['monto'].widget.attrs['step'], '0.01')
        changed_form = FacturaCompraForm(instance=invoice, data={
            'proveedor': self.proveedor.pk,
            'fecha': '2026-11-20',
            'numero_documento': 'F-003 corregida',
            'tipo_documento': 'Factura',
            'monto': '1000.75',
            'observaciones': ''
        })
        self.assertFalse(changed_form.is_valid())
        self.assertIn('monto', changed_form.errors)

    def test_existing_fractional_unit_price_can_be_kept_unchanged(self):
        invoice = FacturaCompra.objects.create(
            proveedor=self.proveedor,
            fecha='2026-11-20',
            numero_documento='F-004',
            tipo_documento='Factura',
            monto='1000'
        )
        detail = FacturaCompraDetalle.objects.create(
            factura=invoice,
            articulo=self.kg_article,
            cantidad='1.25',
            precio_unitario='100.50'
        )
        form = FacturaCompraDetalleForm(instance=detail, data={
            'articulo': self.kg_article.pk,
            'cantidad': '1.25',
            'precio_unitario': '100.50'
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.fields['precio_unitario'].widget.attrs['step'], '0.01')

    def test_api_details_require_at_least_one_valid_line(self):
        details, errors = _validate_invoice_details([{
            'articulo': self.unit_article.pk,
            'cantidad': '1',
            'precio_unitario': '100'
        }])
        self.assertEqual(errors, {})
        self.assertEqual(len(details), 1)

        details, errors = _validate_invoice_details([])
        self.assertIsNone(details)
        self.assertIn('detalles', errors)

        details, errors = _validate_invoice_details([], required=False)
        self.assertEqual(details, [])
        self.assertEqual(errors, {})

    def test_api_accepts_unchanged_historical_fractional_price(self):
        invoice = FacturaCompra.objects.create(
            proveedor=self.proveedor,
            fecha='2026-11-20',
            numero_documento='F-005',
            tipo_documento='Factura',
            monto='1000'
        )
        detail = FacturaCompraDetalle.objects.create(
            factura=invoice,
            articulo=self.kg_article,
            cantidad='1.25',
            precio_unitario='100.50'
        )
        details, errors = _validate_invoice_details([{
            'id': detail.pk,
            'articulo': self.kg_article.pk,
            'cantidad': '1.25',
            'precio_unitario': '100.50'
        }], existing_details=invoice.detalles.all())
        self.assertEqual(errors, {})
        self.assertEqual(details[0].precio_unitario, Decimal('100.50'))

        details, errors = _validate_invoice_details([{
            'id': detail.pk,
            'articulo': self.kg_article.pk,
            'cantidad': '1.25',
            'precio_unitario': '100.75'
        }], existing_details=invoice.detalles.all())
        self.assertEqual(errors, {})
        self.assertEqual(details[0].precio_unitario, Decimal('100.75'))


class NuevasFuncionesFinancierasTests(TestCase):
    def setUp(self):
        self.usuario = Trabajador.objects.create_user(
            username="usuario-finanzas",
            password="prueba-segura-123",
        )
        grupo, _ = Group.objects.get_or_create(name="Finanzas")
        self.usuario.groups.add(grupo)
        self.cliente = Cliente.objects.create(
            rut="76.123.456-7",
            razon_social="Cliente comercial",
            telefono="123",
            correo="cliente@ejemplo.cl",
            direccion="Dirección",
        )
        categoria = CategoriaRepuesto.objects.create(nombre="Venta")
        self.articulo = Repuesto.objects.create(
            codigo_parte="VENTA-01",
            descripcion="Artículo de venta",
            ubicacion_bodega="A-1",
            unidad_medida="unidad",
            categoria=categoria,
            stock_actual=Decimal("12"),
        )
        self.obra = Obra.objects.create(
            codigo_ot="OT-VENTA-01",
            nombre="Obra comercial",
            cliente=self.cliente,
            supervisor=self.usuario,
        )

    def test_budget_has_priced_lines_and_requires_permission_to_approve(self):
        presupuesto = Presupuesto.objects.create(
            numero="PRES-001",
            cliente=self.cliente,
            obra=self.obra,
        )
        fractional_unit = PresupuestoDetalleForm(data={
            "presupuesto": presupuesto.pk,
            "articulo": self.articulo.pk,
            "cantidad": "1.25",
            "precio_unitario": "150.00",
        })
        self.assertFalse(fractional_unit.is_valid())
        self.assertIn("cantidad", fractional_unit.errors)
        detalle = PresupuestoDetalle.objects.create(
            presupuesto=presupuesto,
            articulo=self.articulo,
            cantidad=Decimal("2"),
            precio_unitario=Decimal("150.00"),
        )
        self.assertEqual(detalle.subtotal, Decimal("300.00"))
        self.assertEqual(presupuesto.total, Decimal("300.00"))

        self.client.force_login(self.usuario)
        response = self.client.post(
            f"/api/presupuestos-venta/{presupuesto.pk}/decision/",
            data=json.dumps({"accion": "aprobar"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        permission = Permission.objects.get(
            content_type__app_label="finanzas",
            codename="aprobar_presupuesto",
        )
        self.usuario.user_permissions.add(permission)
        response = self.client.post(
            f"/api/presupuestos-venta/{presupuesto.pk}/decision/",
            data=json.dumps({"accion": "aprobar"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "APROBADO")

    def test_partial_payments_and_credit_notes_update_financial_balance_only(self):
        documento = DocumentoVenta.objects.create(
            numero_documento="VTA-001",
            cliente=self.cliente,
            obra=self.obra,
            fecha=date(2026, 11, 23),
            vencimiento=date(2026, 12, 23),
            total=Decimal("1000.00"),
        )
        PagoDocumento.objects.create(
            documento=documento,
            monto=Decimal("200.00"),
            registrado_por=self.usuario,
        )
        PagoDocumento.objects.create(
            documento=documento,
            monto=Decimal("300.00"),
            registrado_por=self.usuario,
        )
        NotaCredito.objects.create(
            documento=documento,
            numero_documento="NC-001",
            motivo="Ajuste comercial",
            monto=Decimal("100.00"),
            registrado_por=self.usuario,
        )

        documento.refresh_from_db()
        self.articulo.refresh_from_db()
        self.assertEqual(documento.saldo, Decimal("400.00"))
        self.assertEqual(documento.pagos.count(), 2)
        self.assertEqual(documento.notas_credito.count(), 1)
        self.assertEqual(self.articulo.stock_actual, Decimal("12"))

        with self.assertRaises(ValidationError):
            PagoDocumento.objects.create(
                documento=documento,
                monto=Decimal("400.01"),
                registrado_por=self.usuario,
            )

    def test_payment_endpoint_checks_permission(self):
        documento = DocumentoVenta.objects.create(
            numero_documento="VTA-002",
            cliente=self.cliente,
            fecha=date(2026, 11, 23),
            vencimiento=date(2026, 12, 23),
            total=Decimal("500.00"),
        )
        self.client.force_login(self.usuario)
        payload = {
            "monto": "125.00",
            "fecha_pago": "2026-11-23",
            "metodo": "TRANSFERENCIA",
            "referencia": "TRX-001",
        }
        response = self.client.post(
            f"/api/documentos-venta/{documento.pk}/pagos/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        permission = Permission.objects.get(
            content_type__app_label="finanzas",
            codename="registrar_pago_documento",
        )
        self.usuario.user_permissions.add(permission)
        response = self.client.post(
            f"/api/documentos-venta/{documento.pk}/pagos/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        documento.refresh_from_db()
        self.assertEqual(documento.saldo, Decimal("375.00"))

    def test_credit_note_resource_and_document_anulation_permissions(self):
        documento = DocumentoVenta.objects.create(
            numero_documento="VTA-003",
            cliente=self.cliente,
            fecha=date(2026, 11, 23),
            vencimiento=date(2026, 12, 23),
            total=Decimal("800.00"),
        )
        self.client.force_login(self.usuario)
        response = self.client.post(
            "/api/notas-credito/",
            data=json.dumps({
                "documento": documento.pk,
                "numero_documento": "NC-API-001",
                "fecha": "2026-11-23",
                "motivo": "Ajuste solicitado por el cliente",
                "monto": "100.00",
                "observaciones": "",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            NotaCredito.objects.get(numero_documento="NC-API-001").registrado_por,
            self.usuario,
        )

        payload = json.dumps({"motivo": "Documento emitido por error"})
        response = self.client.post(
            f"/api/documentos-venta/{documento.pk}/anular/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        permission = Permission.objects.get(
            content_type__app_label="finanzas",
            codename="anular_documento_venta",
        )
        self.usuario.user_permissions.add(permission)
        response = self.client.post(
            f"/api/documentos-venta/{documento.pk}/anular/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("pagos o notas de crédito", response.json()["errors"]["error"][0])

        documento_sin_movimientos = DocumentoVenta.objects.create(
            numero_documento="VTA-004",
            cliente=self.cliente,
            fecha=date(2026, 11, 23),
            vencimiento=date(2026, 12, 23),
            total=Decimal("500.00"),
        )
        response = self.client.post(
            f"/api/documentos-venta/{documento_sin_movimientos.pk}/anular/",
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        documento_sin_movimientos.refresh_from_db()
        self.assertTrue(documento_sin_movimientos.anulado)
