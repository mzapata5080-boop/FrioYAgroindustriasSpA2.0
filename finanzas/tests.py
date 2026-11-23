from decimal import Decimal
from django.test import TestCase
from frio_agroindustria.api_common import schema, serialize
from frio_agroindustria.api_resources import RESOURCES
from frio_agroindustria.api_crud import _validate_invoice_details
from inventario.models import CategoriaRepuesto, Repuesto
from .forms import (
    ClienteForm,
    ProveedorForm,
    FacturaCompraForm,
    FacturaCompraDetalleForm
)
from .models import Cliente, Proveedor, FacturaCompra, FacturaCompraDetalle


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

    def test_fractional_unit_price_is_rejected(self):
        form = FacturaCompraDetalleForm(data={
            'articulo': self.kg_article.pk,
            'cantidad': '1.25',
            'precio_unitario': '100.50'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('precio_unitario', form.errors)

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
            '1'
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
        self.assertIsNone(details)
        self.assertIn('detalles.0.precio_unitario', errors)
