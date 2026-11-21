from django.test import TestCase
from frio_agroindustria.api_common import schema, serialize
from frio_agroindustria.api_resources import RESOURCES
from .forms import ClienteForm, ProveedorForm
from .models import Cliente, Proveedor


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
