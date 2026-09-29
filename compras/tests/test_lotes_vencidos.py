from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from compras.models import LoteCompra, MotivoPerdida, Perdida, procesar_lotes_vencidos
from core.models import ConfiguracionVentas
from productos.models import Producto
from ventas.models import ItemVenta, Venta, _descontar_stock_venta_item


class LotesVencidosTests(TestCase):
    """Baja automática con tolerancia, venta de vencidos y recupero de la pérdida."""

    def setUp(self):
        self.hoy = timezone.localtime().date()
        self.user = get_user_model().objects.create_user('cajero', password='x')
        self.producto = Producto.objects.create(
            nombre='Yogur', es_perecedero=True, gestiona_stock=True,
            precio_venta=Decimal('1000'), stock_actual=Decimal('10'),
        )
        self.config = ConfiguracionVentas.get_solo()

    def _lote(self, cantidad, vence_hace_dias, costo='400'):
        return LoteCompra.objects.create(
            producto=self.producto, cantidad_inicial=cantidad, cantidad_actual=cantidad,
            costo_unitario=Decimal(costo), fecha_compra=self.hoy - timedelta(days=30),
            fecha_vencimiento=self.hoy - timedelta(days=vence_hace_dias),
        )

    def _configurar(self, baja=True, dias=0):
        self.config.vencidos_baja_automatica = baja
        self.config.vencidos_dias_tolerancia = dias
        self.config.save()

    def _vender(self, cantidad):
        venta = Venta.objects.create(fecha=self.hoy, creado_por=self.user)
        item = ItemVenta.objects.create(
            venta=venta, producto=self.producto, cantidad=Decimal(cantidad),
            precio_unitario=Decimal('1000'),
        )
        return _descontar_stock_venta_item(item)

    def test_baja_automatica_apagada_no_da_de_baja(self):
        self._configurar(baja=False)
        self._lote(10, vence_hace_dias=20)
        self.assertEqual(procesar_lotes_vencidos(), [])
        self.assertFalse(Perdida.objects.exists())

    def test_tolerancia_y_fecha_de_la_perdida(self):
        self._configurar(dias=3)
        dentro = self._lote(4, vence_hace_dias=2)   # todavía vendible
        fuera = self._lote(6, vence_hace_dias=5)    # pasó la tolerancia
        procesar_lotes_vencidos()
        dentro.refresh_from_db()
        fuera.refresh_from_db()
        self.assertEqual(dentro.cantidad_actual, 4)
        self.assertEqual(fuera.cantidad_actual, 0)
        perdida = Perdida.objects.get()
        self.assertEqual(perdida.motivo, MotivoPerdida.VENCIMIENTO)
        # Fechada el primer día no vendible: vencimiento + 3 + 1.
        self.assertEqual(perdida.fecha, fuera.fecha_vencimiento + timedelta(days=4))

    def test_vender_dentro_de_la_tolerancia_avisa(self):
        self._configurar(dias=5)
        self._lote(10, vence_hace_dias=2)
        consumos, avisos = self._vender(3)
        self.assertEqual(sum(c.cantidad for c in consumos), 3)
        self.assertTrue(any('vencido el' in a for a in avisos))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 7)

    def test_vender_lo_dado_de_baja_lo_descuenta_de_la_perdida(self):
        self._configurar(dias=0)
        lote = self._lote(10, vence_hace_dias=3, costo='400')
        # La venta procesa el vencido antes de elegir lotes: pérdida de 10.
        consumos, avisos = self._vender(4)
        perdida = Perdida.objects.get()
        self.assertEqual(perdida.cantidad, 6)
        self.assertEqual(perdida.cantidad_recuperada, 4)
        self.assertEqual(sum(c.cantidad for c in consumos), 4)
        self.assertEqual(consumos[0].costo_unitario_snapshot, Decimal('400'))
        self.assertTrue(any('dado de baja por vencimiento' in a for a in avisos))
        lote.refresh_from_db()
        self.producto.refresh_from_db()
        self.assertEqual(lote.cantidad_actual, 0)
        self.assertEqual(self.producto.stock_actual, 0)

    def test_sin_perdida_recuperable_sigue_bloqueando(self):
        self._configurar(dias=0)
        with self.assertRaises(ValueError):
            self._vender(1)

    def test_pierde_lo_manual_no_se_recupera(self):
        from compras.models import registrar_perdida
        self._configurar(dias=0)
        lote = self._lote(10, vence_hace_dias=-30)   # vence en 30 días
        registrar_perdida(lote, 10, MotivoPerdida.VENCIMIENTO, usuario=self.user)
        with self.assertRaises(ValueError):
            self._vender(1)

    def test_estadisticas_cuentan_la_perdida_neta_y_separan_vencidos(self):
        from compras.models import registrar_perdida
        from core.services_estadisticas.productos import perdidas_del_periodo
        self._configurar(dias=0)
        self._lote(10, vence_hace_dias=3, costo='400')
        self._vender(4)                                   # 6 perdidas netas × $400
        roto = self._lote(5, vence_hace_dias=-60, costo='100')
        Producto.objects.filter(pk=self.producto.pk).update(stock_actual=5)
        registrar_perdida(roto, 2, MotivoPerdida.ROTURA)  # 2 × $100
        r = perdidas_del_periodo(self.hoy - timedelta(days=30), self.hoy)
        self.assertEqual(r['total_vencido_periodo'], Decimal('2400.00'))
        self.assertEqual(r['total_mermas_periodo'], Decimal('200.00'))
        self.assertEqual(r['total_perdidas_periodo'], Decimal('2600.00'))
