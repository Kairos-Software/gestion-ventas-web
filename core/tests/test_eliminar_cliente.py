import os
import shutil
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from caja.models import CuentaPorCobrar
from core.models import Cliente

MEDIA_TEST = os.path.join(settings.BASE_DIR, '_media_test_eliminar_cliente')


@override_settings(MEDIA_ROOT=MEDIA_TEST)
class EliminarClienteTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='admin_t', password='x12345678')
        self.client.force_login(self.admin)
        self.cliente = Cliente.objects.create(nombre='Laura', apellido='Fernández')
        self.carpeta = os.path.join(MEDIA_TEST, 'clientes', self.cliente.codigo or str(self.cliente.pk))
        os.makedirs(self.carpeta, exist_ok=True)
        with open(os.path.join(self.carpeta, 'pagare.jpg'), 'wb') as f:
            f.write(b'x')

    def tearDown(self):
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)

    def _eliminar(self):
        return self.client.post(reverse('core:cliente_eliminar'), {'pk': self.cliente.pk})

    def test_con_cuenta_por_cobrar_avisa_y_no_borra_nada(self):
        CuentaPorCobrar.objects.create(
            cliente=self.cliente, monto_original=Decimal('30000'),
            cantidad_cuotas=3, fecha_inicio=date(2026, 10, 10))
        resp = self._eliminar()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cuenta', resp.json()['error'].lower())
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())
        # Sus archivos (pagaré escaneado, fotos) siguen ahí.
        self.assertTrue(os.path.exists(os.path.join(self.carpeta, 'pagare.jpg')))

    def test_sin_deudas_lo_elimina_con_sus_archivos(self):
        resp = self._eliminar()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertFalse(Cliente.objects.filter(pk=self.cliente.pk).exists())
        self.assertFalse(os.path.exists(self.carpeta))
