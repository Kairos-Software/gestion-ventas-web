import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import PaqueteComponente, Producto, generar_codigo_barras_paquete


class PaqueteSinCodigoDeBarrasTests(TestCase):
    """Los paquetes creados antes de que existiera el código de barras
    propio quedaban sin código para siempre: al editarlos se "conservaba"
    el que tenían (ninguno), y "Imprimir código" nunca andaba."""

    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser('admin', 'a@a.com', 'x'))
        self.componente = Producto.objects.create(nombre='Cerveza', precio_venta=Decimal('900'))
        self.paquete = Producto.objects.create(nombre='Combo', es_paquete=True, precio_venta=Decimal('5000'))
        PaqueteComponente.objects.create(paquete=self.paquete, producto=self.componente, cantidad=Decimal('6'))

    def _guardar(self):
        return self.client.post(reverse('productos:paquete_acciones'), json.dumps({
            'pk': self.paquete.pk, 'nombre': 'Combo', 'precio_venta': '5000', 'modo_precio': 'manual',
            'componentes': [{'producto_pk': self.componente.pk, 'cantidad': '6'}],
        }), content_type='application/json')

    def test_editar_un_paquete_sin_codigo_le_genera_uno(self):
        self.assertFalse(self.paquete.codigo_barras)
        self.assertEqual(self._guardar().status_code, 200)
        self.paquete.refresh_from_db()
        self.assertTrue(self.paquete.codigo_barras.startswith('PAQ-'))

    def test_el_codigo_nuevo_no_repite_el_de_un_paquete_mas_nuevo(self):
        # Un paquete creado después (id más alto) ya tiene el 00001; el
        # viejo, al editarlo, tiene que recibir el 00002 — no otra vez el 00001.
        otro = Producto.objects.create(nombre='Otro', es_paquete=True, precio_venta=Decimal('1'))
        Producto.objects.filter(pk=otro.pk).update(codigo_barras=generar_codigo_barras_paquete())
        Producto.objects.filter(pk=self.paquete.pk).update(codigo_barras=generar_codigo_barras_paquete())
        tercero = generar_codigo_barras_paquete()
        codigos = list(Producto.objects.filter(es_paquete=True).values_list('codigo_barras', flat=True))
        self.assertEqual(len(set(codigos)), 2)
        self.assertNotIn(tercero, codigos)

    def test_editar_un_paquete_con_codigo_lo_conserva(self):
        Producto.objects.filter(pk=self.paquete.pk).update(codigo_barras='PAQ-2025-00007')
        self._guardar()
        self.paquete.refresh_from_db()
        self.assertEqual(self.paquete.codigo_barras, 'PAQ-2025-00007')
