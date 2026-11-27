"""Pruebas unitarias de funciones comunes: archivos privados y auditoría transversal."""
import tempfile
from pathlib import Path
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from frio_agroindustria.api import internal_error
from frio_agroindustria.common import (
    open_private_file,
    registrar_cambio,
    save_private_file,
    snapshot_instance,
)
from frio_agroindustria.models import RegistroAuditoria
from inventario.models import CategoriaRepuesto
from usuarios.models import Trabajador


class CommonUtilitiesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = Trabajador.objects.create_user('benjamin', first_name='Benjamín', last_name='Canales')

    def test_save_and_open_private_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(PRIVATE_MEDIA_ROOT=Path(tmpdir)):
                sample = SimpleUploadedFile('factura_101.pdf', b'%PDF-1.4 contenido', content_type='application/pdf')
                meta = save_private_file(sample, 'finanzas')
                self.assertTrue(meta['ruta_privada'].startswith('finanzas/'))
                self.assertEqual(meta['nombre_original'], 'factura_101.pdf')
                with open_private_file(meta['ruta_privada']) as fh:
                    self.assertEqual(fh.read(), b'%PDF-1.4 contenido')

    def test_rejects_disallowed_extension_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(PRIVATE_MEDIA_ROOT=Path(tmpdir)):
                bad = SimpleUploadedFile('script.exe', b'MZ', content_type='application/octet-stream')
                with self.assertRaises(ValidationError):
                    save_private_file(bad, 'obras')
                with self.assertRaises(FileNotFoundError):
                    open_private_file('../settings.py')

    def test_internal_error_handler_uses_required_api_message(self):
        response = internal_error(RequestFactory().get('/api/session/'))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {'error': 'Ha ocurrido un error, intente nuevamente'},
        )

    def test_audit_records_create_edit_and_delete(self):
        cat = CategoriaRepuesto.objects.create(nombre='Refrigeración')
        log_create = registrar_cambio(self.user, 'CREAR', cat)
        self.assertIsNotNone(log_create)
        self.assertEqual(log_create.usuario_id, self.user.pk)
        self.assertIn('Refrigeración', log_create.cambios_json)

        antes = snapshot_instance(cat)
        cat.nombre = 'Refrigeración Industrial'
        cat.save()
        log_edit = registrar_cambio(self.user, 'EDITAR', cat, antes=antes)
        self.assertIsNotNone(log_edit)
        self.assertIn('Refrigeración Industrial', log_edit.cambios_json)

        # Sin cambios reales no genera ruido en auditoría
        self.assertIsNone(registrar_cambio(self.user, 'EDITAR', cat, antes=snapshot_instance(cat)))

        antes_del = snapshot_instance(cat)
        cat_pk = cat.pk
        cat.delete()
        cat.pk = cat_pk
        log_del = registrar_cambio(self.user, 'ELIMINAR', cat, antes=antes_del)
        self.assertEqual(log_del.accion, 'ELIMINAR')
        self.assertEqual(RegistroAuditoria.objects.count(), 3)