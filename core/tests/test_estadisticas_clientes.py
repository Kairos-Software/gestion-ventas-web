from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.services_estadisticas import clientes as stats
from core.services_estadisticas import cliente_perfil as stats_perfil


class EstadisticasClientesTests(SimpleTestCase):
    def test_ranking_agrupa_por_cliente_y_muestra_nombre_actual(self):
        items = MagicMock()
        items.filter.return_value = items
        ranking = [{
            'cliente__id': 7,
            'total_comprado': Decimal('150'),
            'cant_ventas': 2,
        }]
        items.values.return_value.annotate.return_value.order_by.return_value.__getitem__.return_value = ranking
        cliente = SimpleNamespace(id=7, get_nombre_display=lambda: 'Nombre actual')

        with (
            patch.object(stats, '_items_confirmados_con_cliente', return_value=items),
            patch.object(stats.Cliente.objects, 'filter', return_value=[cliente]),
        ):
            resultado = stats.mejores_clientes(date(2026, 9, 1), date(2026, 9, 30))

        items.values.assert_called_once_with('cliente__id')
        items.filter.assert_called_once_with(moneda='ARS')
        self.assertEqual(resultado[0]['nombre'], 'Nombre actual')
        self.assertEqual(resultado[0]['total_comprado'], Decimal('150'))

    def test_sin_compras_revisa_mas_de_200_clientes(self):
        hoy = date(2026, 9, 22)
        clientes = [
            SimpleNamespace(id=i, nombre=f'Cliente {i}', razon_social='', codigo=f'C{i}')
            for i in range(1, 202)
        ]
        ventas = MagicMock()
        ventas.exclude.return_value.values.return_value.annotate.return_value = [
            {'cliente__id': i, 'ultima': hoy} for i in range(1, 201)
        ]
        activos = MagicMock()
        activos.iterator.return_value = iter(clientes)

        with (
            patch.object(stats.ItemVenta.objects, 'filter', return_value=ventas),
            patch.object(stats.Cliente.objects, 'filter', return_value=activos),
            patch.object(
                stats.timezone, 'localtime',
                return_value=datetime(2026, 9, 22, tzinfo=ZoneInfo('America/Argentina/Buenos_Aires')),
            ),
        ):
            resultado = stats.clientes_inactivos()

        self.assertEqual([c['id'] for c in resultado], [201])

    def test_historial_muestra_solo_la_parte_del_cliente_en_venta_compartida(self):
        cliente = SimpleNamespace(id=7)
        venta = SimpleNamespace(
            pk=12, fecha=date(2026, 9, 20), numero='V-12', total=Decimal('100'),
            pagos=SimpleNamespace(all=lambda: []),
            get_medio_pago_display=lambda: 'Efectivo',
        )
        items = MagicMock()
        items.annotate.return_value.values.return_value.annotate.return_value = [
            {'venta_id': 12, 'moneda': 'ARS', 'monto_cliente': Decimal('40')},
            {'venta_id': 12, 'moneda': 'USD', 'monto_cliente': Decimal('20')},
        ]
        ventas = MagicMock()
        ventas.prefetch_related.return_value = [venta]
        cuentas = MagicMock()
        cuentas.prefetch_related.return_value = []
        cuotas = MagicMock()
        cuotas.select_related.return_value = []

        with (
            patch.object(stats_perfil.ItemVenta.objects, 'filter', return_value=items),
            patch.object(stats_perfil.Venta.objects, 'filter', return_value=ventas),
            patch.object(stats_perfil.CuentaPorCobrar.objects, 'filter', return_value=cuentas),
            patch.object(stats_perfil.CuotaCobro.objects, 'filter', return_value=cuotas),
        ):
            historial = stats_perfil.historial_cliente(cliente)

        self.assertEqual([fila['monto'] for fila in historial], ['40', '20'])
        self.assertEqual(historial[0]['fecha'], date(2026, 9, 20))
        self.assertEqual([fila['moneda'] for fila in historial], ['ARS', 'USD'])

    def test_cuentas_por_cobrar_no_suma_monedas_distintas(self):
        pendientes = MagicMock()
        vencidas = MagicMock()
        proximas = MagicMock()
        pendientes.filter.side_effect = [vencidas, proximas]

        def consulta(filas):
            valores = MagicMock()
            valores.annotate.return_value = filas
            return valores

        pendientes.values.side_effect = [
            consulta([
                {'cuenta_por_cobrar__moneda': 'ARS', 'total': Decimal('100'), 'cantidad': 1},
                {'cuenta_por_cobrar__moneda': 'USD', 'total': Decimal('50'), 'cantidad': 1},
            ]),
            consulta([
                {'cuenta_por_cobrar__cliente__id': 7, 'cuenta_por_cobrar__moneda': 'ARS', 'total': Decimal('100'), 'cantidad': 1},
                {'cuenta_por_cobrar__cliente__id': 7, 'cuenta_por_cobrar__moneda': 'USD', 'total': Decimal('50'), 'cantidad': 1},
            ]),
        ]
        vencidas.values.return_value.annotate.return_value = [
            {'cuenta_por_cobrar__moneda': 'USD', 'total': Decimal('10'), 'cantidad': 1},
        ]
        proximas.values.return_value.annotate.return_value = []
        cobradas = MagicMock()
        cobradas.values.return_value.annotate.return_value = [
            {'cuenta_por_cobrar__moneda': 'ARS', 'total': Decimal('20')},
            {'cuenta_por_cobrar__moneda': 'USD', 'total': Decimal('5')},
        ]
        cliente = SimpleNamespace(id=7, get_nombre_display=lambda: 'Cliente')

        with (
            patch.object(stats.CuotaCobro.objects, 'filter', side_effect=[pendientes, cobradas]),
            patch.object(stats.CuentaPorCobrar.objects, 'filter', return_value=[]),
            patch.object(stats.Cliente.objects, 'filter', return_value=[cliente]),
            patch.object(
                stats.timezone, 'localtime',
                return_value=datetime(2026, 9, 22, tzinfo=ZoneInfo('America/Argentina/Buenos_Aires')),
            ),
        ):
            resultado = stats.cuentas_por_cobrar(date(2026, 9, 1), date(2026, 9, 22))

        self.assertEqual(resultado['total_pendiente'], Decimal('100'))
        self.assertEqual(resultado['cobrado_periodo'], Decimal('20'))
        self.assertEqual(resultado['ranking_deudores'][0]['total'], Decimal('100'))
        dolares = resultado['otras_monedas'][0]
        self.assertEqual(dolares['moneda'], 'USD')
        self.assertEqual(dolares['total_pendiente'], Decimal('50'))
        self.assertEqual(dolares['total_vencido'], Decimal('10'))
        self.assertEqual(dolares['ranking_deudores'][0]['total'], Decimal('50'))

    def test_perfil_separa_saldos_y_mora_por_moneda(self):
        cliente = SimpleNamespace(id=7)
        confirmadas = MagicMock()
        confirmadas.exclude.return_value = []
        mora = MagicMock()
        mora.values.return_value.annotate.return_value = [{
            'cuenta_por_cobrar__moneda': 'USD',
            'total': Decimal('10'),
            'cantidad': 1,
        }]
        cuentas = [
            SimpleNamespace(moneda='ARS', saldo_pendiente=Decimal('100'), monto_total=Decimal('200')),
            SimpleNamespace(moneda='USD', saldo_pendiente=Decimal('50'), monto_total=Decimal('80')),
        ]

        with (
            patch.object(stats_perfil.CuotaCobro.objects, 'filter', side_effect=[confirmadas, mora]),
            patch.object(stats_perfil.CuentaPorCobrar.objects, 'filter', return_value=cuentas),
            patch.object(
                stats_perfil.timezone, 'localtime',
                return_value=datetime(2026, 9, 22, tzinfo=ZoneInfo('America/Argentina/Buenos_Aires')),
            ),
        ):
            resultado = stats_perfil.comportamiento_pago(cliente)

        self.assertEqual(resultado['saldo_actual'], Decimal('100'))
        self.assertEqual(resultado['mora_total'], Decimal('0'))
        self.assertEqual(resultado['cantidad_cuentas_ars'], 1)
        self.assertEqual(resultado['otras_monedas'][0]['saldo_actual'], Decimal('50'))
        self.assertEqual(resultado['otras_monedas'][0]['mora_total'], Decimal('10'))

    def test_historial_mantiene_saldo_independiente_por_moneda(self):
        cliente = SimpleNamespace(id=7)
        cuenta = SimpleNamespace(
            pk=2, moneda='USD', descripcion='Cuenta en dolares', numero_comprobante='',
            fecha_inicio=date(2026, 9, 1), monto_total=Decimal('100'),
            cantidad_cuotas=1, cuotas=SimpleNamespace(all=lambda: []),
        )
        cuota = SimpleNamespace(
            cuenta_por_cobrar=cuenta, fecha_confirmacion=datetime(
                2026, 9, 10, tzinfo=ZoneInfo('America/Argentina/Buenos_Aires')
            ), fecha_vencimiento=date(2026, 9, 10),
            cobro_cuenta_corriente_id=None, numero=1, monto=Decimal('40'),
        )
        items = MagicMock()
        items.annotate.return_value.values.return_value.annotate.return_value = []
        ventas = MagicMock()
        ventas.prefetch_related.return_value = []
        cuentas = MagicMock()
        cuentas.prefetch_related.return_value = [cuenta]
        cuotas = MagicMock()
        cuotas.select_related.return_value = [cuota]

        with (
            patch.object(stats_perfil.ItemVenta.objects, 'filter', return_value=items),
            patch.object(stats_perfil.Venta.objects, 'filter', return_value=ventas),
            patch.object(stats_perfil.CuentaPorCobrar.objects, 'filter', return_value=cuentas),
            patch.object(stats_perfil.CuotaCobro.objects, 'filter', return_value=cuotas),
        ):
            historial = stats_perfil.historial_cliente(cliente)

        self.assertEqual([fila['moneda'] for fila in historial], ['USD', 'USD'])
        self.assertEqual([fila['saldo'] for fila in historial], ['100', '60'])

    def test_perfil_no_resta_costos_en_ars_a_ventas_en_usd(self):
        todos = MagicMock()
        todos.annotate.return_value = todos
        todos.aggregate.return_value = {'ultima': date(2026, 9, 22)}
        pesos = MagicMock()
        pesos.aggregate.return_value = {'total': Decimal('100')}
        pesos.values.return_value.distinct.return_value.count.return_value = 2
        todos.filter.return_value = pesos
        todos.exclude.return_value.values.return_value.annotate.return_value = [{
            'moneda': 'USD', 'ingresos': Decimal('50'), 'cant_ventas': 1,
        }]

        with (
            patch.object(stats_perfil.ItemVenta.objects, 'filter', return_value=todos),
            patch.object(stats_perfil, '_costo_de_items', return_value=Decimal('40')),
        ):
            resultado = stats_perfil.perfil_valor(SimpleNamespace(id=7))

        todos.filter.assert_called_once_with(moneda='ARS')
        self.assertEqual(resultado['ingresos'], Decimal('100'))
        self.assertEqual(resultado['ganancia'], Decimal('60'))
        self.assertEqual(resultado['ventas_otras_monedas'][0]['ingresos'], Decimal('50'))
