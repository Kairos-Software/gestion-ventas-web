from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import UsuarioPermisoOverride

Usuario = get_user_model()


class UsuariosProtegidosTests(TestCase):
    """Quien administra usuarios sin ser superusuario no puede tocar al
    superusuario (ni a sí mismo) aunque arme la petición a mano: la lista no
    los muestra, y cambiarle el email al dueño alcanzaría para quedarse con
    su cuenta vía "¿Olvidaste tu contraseña?"."""

    def setUp(self):
        self.dueno = Usuario.objects.create_superuser(
            username='dueno', password='x12345678', email='dueno@negocio.com')
        self.encargado = Usuario.objects.create_user(
            username='encargado', password='x12345678')
        for codigo in ('ver_usuarios', 'editar_usuarios', 'eliminar_usuarios'):
            UsuarioPermisoOverride.objects.create(
                usuario=self.encargado, permiso=codigo, concedido=True)
        self.empleado = Usuario.objects.create_user(
            username='empleado', password='x12345678')
        self.client.force_login(self.encargado)

    def _editar(self, usuario):
        return self.client.post(reverse('core:usuario_acciones'), {
            'pk': usuario.pk, 'username': usuario.username,
            'email': 'encargado@gmail.com',
        })

    def test_no_puede_editar_al_superusuario(self):
        self.assertEqual(self._editar(self.dueno).status_code, 404)
        resp = self.client.post(
            reverse('core:editar_usuario_detalle', args=[self.dueno.pk]),
            {'username': 'dueno', 'email': 'encargado@gmail.com'})
        self.assertEqual(resp.status_code, 404)
        self.dueno.refresh_from_db()
        self.assertEqual(self.dueno.email, 'dueno@negocio.com')

    def test_no_puede_ver_ni_eliminar_al_superusuario(self):
        resp = self.client.get(
            reverse('core:detalle_usuario', args=[self.dueno.pk]))
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get(
            reverse('core:usuario_acciones'), {'get_pk': self.dueno.pk})
        self.assertEqual(resp.status_code, 404)
        resp = self.client.delete(
            reverse('core:usuario_eliminar') + f'?pk={self.dueno.pk}')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Usuario.objects.filter(pk=self.dueno.pk).exists())

    def test_no_puede_editarse_ni_eliminarse_a_si_mismo(self):
        self.assertEqual(self._editar(self.encargado).status_code, 404)
        resp = self.client.delete(
            reverse('core:usuario_eliminar') + f'?pk={self.encargado.pk}')
        self.assertEqual(resp.status_code, 404)

    def test_a_un_empleado_si_lo_puede_editar(self):
        resp = self._editar(self.empleado)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.email, 'encargado@gmail.com')
