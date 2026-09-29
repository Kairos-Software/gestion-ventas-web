from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from productos import services_historial as sh
from productos.models import Producto


def _ev(cantidad, es_entrada, activo=True, dia=1):
    return sh._evento(
        fecha_orden=(date(2026, 9, dia), datetime(2026, 9, dia)), fecha_display=date(2026, 9, dia),
        categoria='compra' if es_entrada else 'venta', tipo_label='x', es_entrada=es_entrada,
        cantidad=Decimal(cantidad), combinacion_desc='', origen_label='x', origen_url='',
        usuario='', detalle='', activo=activo,
    )


class ConciliacionIgnoraAnuladosTests(TestCase):
    """Anular una venta devuelve el stock al lote sin crear un evento de
    reverso (el consumo queda, marcado como anulado); anular una compra
    desactiva su lote. Si la conciliación los sumaba igual, todo producto
    con una anulación mostraba una "diferencia" que no existía."""

    def test_venta_y_compra_anuladas_no_generan_diferencia(self):
        producto = Producto.objects.create(nombre='Yerba 1 kg', precio_venta=Decimal('4000'))
        # Compró 10, vendió 3 (una venta de 1 anulada), compra de 5 anulada → hay 8.
        Producto.objects.filter(pk=producto.pk).update(stock_actual=Decimal('8'))
        producto.refresh_from_db()
        eventos = [_ev(10, True, dia=1), _ev(2, False, dia=2), _ev(1, False, activo=False, dia=3),
                   _ev(5, True, activo=False, dia=4)]
        vacio = lambda *a: []
        with patch.object(sh, '_eventos_compras', lambda *a: eventos), \
             patch.object(sh, '_eventos_ajustes', vacio), patch.object(sh, '_eventos_mermas', vacio), \
             patch.object(sh, '_eventos_fraccionamientos', vacio), \
             patch.object(sh, '_eventos_ventas', vacio), patch.object(sh, '_eventos_devoluciones', vacio):
            r = sh.construir_historial_stock(producto)
        self.assertEqual(r['stock_reconstruido'], Decimal('8'))
        self.assertEqual(r['diferencia'], Decimal('0'))
