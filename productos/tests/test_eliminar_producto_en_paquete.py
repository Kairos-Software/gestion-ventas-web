import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import PaqueteComponente, Producto


class EliminarProductoUsadoEnPaqueteTests(TestCase):
    """Un producto que forma parte de un paquete no se puede borrar (el
    componente es PROTECT). Antes eso terminaba en un error 500 en vez de
    explicar por qué, y en el borrado masivo dejaba la mitad hecha."""

    def setUp(self):
        admin = get_user_model().objects.create_superuser(username='admin_p', password='x12345678')
        self.client.force_login(admin)
        self.coca = Producto.objects.create(nombre='Coca-Cola 500 ml', precio_venta=Decimal('1500'))
        self.papas = Producto.objects.create(nombre='Papas fritas 100 g', precio_venta=Decimal('1200'))
        self.suelto = Producto.objects.create(nombre='Chicle', precio_venta=Decimal('300'))
        self.combo = Producto.objects.create(nombre='Combo previa', es_paquete=True, precio_venta=Decimal('2500'))
        PaqueteComponente.objects.create(paquete=self.combo, producto=self.coca, cantidad=1)
        PaqueteComponente.objects.create(paquete=self.combo, producto=self.papas, cantidad=1)

    def test_eliminar_uno_avisa_en_que_paquete_esta(self):
        resp = self.client.post(reverse('productos:producto_eliminar'),
                                json.dumps({'pk': self.coca.pk}), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Combo previa', resp.json()['error'])
        self.assertTrue(Producto.objects.filter(pk=self.coca.pk).exists())

    def test_eliminar_varios_borra_los_que_puede_y_explica_el_resto(self):
        resp = self.client.post(reverse('productos:producto_acciones_masivas'),
                                json.dumps({'pks': [self.suelto.pk, self.coca.pk], 'accion': 'eliminar'}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data['eliminados'], [self.suelto.pk])
        self.assertEqual([b['pk'] for b in data['bloqueados']], [self.coca.pk])
        self.assertIn('Combo previa', data['bloqueados'][0]['motivo'])
