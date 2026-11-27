import json
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from usuarios.models import Trabajador


class TrabajadorRoleTests(TestCase):
    def test_gerente_group_has_gerencia_permissions(self):
        worker = Trabajador.objects.create_user('gerente')
        worker.groups.add(Group.objects.create(name='Gerente'))

        self.assertEqual(worker.rol, 'gerencia')

        client = Client()
        client.force_login(worker)
        response = client.get('/api/trabajadores/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['can_write'])

    def test_authentication_errors_use_required_messages(self):
        client = Client()
        response = client.post(
            '/api/login/',
            data=json.dumps({'username': 'missing', 'password': 'wrong'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'Usuario o contraseña incorrectos')

        worker = Trabajador.objects.create_user('sin_permisos')
        client.force_login(worker)
        response = client.get('/api/trabajadores/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'No posee permisos para acceder')

        client.logout()
        response = client.get('/api/ingresos/')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'Su sesión ha expirado')