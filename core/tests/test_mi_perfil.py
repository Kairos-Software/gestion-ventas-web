from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CambiarPasswordMiPerfilTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='perfil_test', password='original123')
        self.client.force_login(self.user)
        self.url = reverse('core:mi_perfil')

    def _cambiar(self, actual):
        return self.client.post(self.url, {
            'accion': 'password',
            'password_actual': actual,
            'password_nueva': 'nueva12345',
            'password_confirmar': 'nueva12345',
        })

    def test_con_contrasena_actual_incorrecta_no_la_cambia(self):
        resp = self._cambiar('otracosa')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'La contraseña actual es incorrecta.')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('original123'))

    def test_con_contrasena_actual_correcta_la_cambia(self):
        resp = self._cambiar('original123')
        self.assertRedirects(resp, self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('nueva12345'))
