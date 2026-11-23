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