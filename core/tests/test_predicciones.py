from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.services_estadisticas import productos


class PrediccionesStockTests(SimpleTestCase):
    def test_los_rangos_no_reiteran_dias_al_cruzar_de_mes(self):
        rangos = productos._rangos_por_cuando(date(2026, 9, 28))

        self.assertEqual(rangos[0][:2], (date(2026, 9, 28), date(2026, 10, 5)))
        self.assertEqual(rangos[1][:2], (date(2026, 10, 6), date(2026, 10, 31)))
        self.assertTrue(all(actual[1] < siguiente[0] for actual, siguiente in zip(rangos, rangos[1:])))

    def _calcular_con_producto(self, costo):
        hoy = date(2026, 9, 28)
        producto = SimpleNamespace(
            id=1, nombre='Producto futuro', codigo='P1', proveedor_id=None,
            stock_actual=Decimal('150'), stock_maximo=None, costo_actual=costo,
            permite_fraccion=False, get_unidad_medida_display=lambda: 'Unidad',
        )
        ventas = MagicMock()
        ventas.values.return_value.annotate.return_value = [{
            'producto_id': 1, 'unidades': Decimal('90'),
            'primera_venta': hoy - timedelta(days=90), 'cant_ventas': 5,
        }]
        recientes = MagicMock()
        recientes.values.return_value.annotate.return_value = [{
            'producto_id': 1, 'unidades': Decimal('30'),
        }]
        stock = MagicMock()
        stock.select_related.return_value = [producto]

        with (
            patch.object(productos.ItemVenta.objects, 'filter', side_effect=[ventas, recientes]),
            patch.object(productos.Producto.objects, 'filter', return_value=stock),
            patch.object(
                productos.timezone, 'localtime',
                return_value=datetime(2026, 9, 28, tzinfo=ZoneInfo('America/Argentina/Buenos_Aires')),
            ),
        ):
            return productos.prediccion_reposicion()

    def test_incluye_reposicion_mas_alla_de_60_dias(self):
        resultado = self._calcular_con_producto(Decimal('100'))

        self.assertEqual(resultado['cantidad_productos'], 1)
        self.assertEqual(resultado['productos'][0]['recomendado_unidades'], Decimal('60'))
        self.assertEqual(resultado['productos'][0]['costo_estimado'], Decimal('6000'))
        self.assertEqual(sum(b['cantidad_productos'] for b in resultado['buckets']), 1)

    def test_costo_faltante_no_aparece_como_compra_gratis(self):
        resultado = self._calcular_con_producto(None)

        self.assertIsNone(resultado['productos'][0]['costo_estimado'])
        self.assertEqual(resultado['sin_costo'], 1)
        self.assertEqual(resultado['total_estimado'], Decimal('0'))
