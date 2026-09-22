from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.template.loader import render_to_string

from core.services_estadisticas import caja as stats


class EstadisticasCajaTests(SimpleTestCase):
    def test_pantalla_prioriza_saldo_actual_y_separa_periodo(self):
        html = render_to_string('core/estadisticas/caja.html', {
            'desde': date(2026, 9, 1), 'hasta': date(2026, 9, 22), 'preset': 'mes_actual',
            'situacion_financiera': {'por_moneda': [{
                'label': 'Pesos', 'moneda': 'ARS', 'saldo': Decimal('120'),
                'cxc': Decimal('50'), 'cheques_cobrar': Decimal('0'),
                'deudas': Decimal('20'), 'cheques_pagar': Decimal('0'),
                'neto': Decimal('150'),
            }]},
            'obligaciones_periodo': {'por_moneda': []},
            'cobros_periodo': {'por_moneda': []},
            'mov_concepto': {'por_moneda': []},
            'serie_conceptos': {'por_moneda': []},
            'serie_conceptos_data': {'meses': [], 'por_moneda': []},
            'historial_arqueos': {'cantidad_turnos': 0, 'cantidad_con_diferencia': 0,
                                 'total_sobrante': Decimal('0'), 'total_faltante': Decimal('0'), 'detalle': []},
        })
        self.assertLess(html.index('Disponible en cuentas'), html.index('Lo que vence y lo que se movió'))
        self.assertIn('sin mezclar monedas', html)
        self.assertIn('estFinanzasTendencia', html)

    def test_conceptos_separan_monedas_y_porcentajes(self):
        consulta = MagicMock()
        consulta.values.return_value.annotate.return_value = [
            {'moneda': 'ARS', 'tipo': stats.TipoMovimientoCaja.EGRESO,
             'concepto__nombre': 'Alquiler', 'total': Decimal('100'), 'cantidad': 1},
            {'moneda': 'ARS', 'tipo': stats.TipoMovimientoCaja.EGRESO,
             'concepto__nombre': 'Servicios', 'total': Decimal('100'), 'cantidad': 2},
            {'moneda': 'USD', 'tipo': stats.TipoMovimientoCaja.EGRESO,
             'concepto__nombre': 'Alquiler', 'total': Decimal('10'), 'cantidad': 1},
            {'moneda': 'USD', 'tipo': stats.TipoMovimientoCaja.INGRESO,
             'concepto__nombre': 'Reintegro', 'total': Decimal('5'), 'cantidad': 1},
        ]
        with patch.object(stats.Gasto.objects, 'filter', return_value=consulta):
            resultado = stats.movimientos_por_concepto(date(2026, 9, 1), date(2026, 9, 22))

        por_moneda = {fila['moneda']: fila for fila in resultado['por_moneda']}
        self.assertEqual(por_moneda['ARS']['total_egresos'], Decimal('200'))
        self.assertEqual(por_moneda['USD']['total_egresos'], Decimal('10'))
        self.assertEqual(por_moneda['USD']['total_ingresos'], Decimal('5'))
        self.assertEqual([fila['pct'] for fila in por_moneda['ARS']['egresos']], [50, 50])

    def test_serie_mensual_separa_monedas_y_excluye_fechas_futuras(self):
        consulta = MagicMock()
        consulta.annotate.return_value.values.return_value.annotate.return_value = [
            {'mes': date(2026, 9, 1), 'moneda': 'ARS', 'concepto__nombre': 'Alquiler', 'total': Decimal('100')},
            {'mes': date(2026, 9, 1), 'moneda': 'USD', 'concepto__nombre': 'Alquiler', 'total': Decimal('20')},
        ]
        with patch.object(stats.Gasto.objects, 'filter', return_value=consulta) as filtro:
            resultado = stats.serie_mensual_conceptos(date(2026, 9, 22), meses=2)

        filtro.assert_called_once_with(tipo=stats.TipoMovimientoCaja.EGRESO,
                                       fecha__range=(date(2026, 8, 1), date(2026, 9, 22)))
        por_moneda = {fila['moneda']: fila for fila in resultado['por_moneda']}
        self.assertEqual(por_moneda['ARS']['series'][0]['valores'], [Decimal('0'), Decimal('100')])
        self.assertEqual(por_moneda['USD']['series'][0]['valores'], [Decimal('0'), Decimal('20')])
