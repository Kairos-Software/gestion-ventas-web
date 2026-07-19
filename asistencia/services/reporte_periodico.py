from decimal import Decimal

from core.services_estadisticas.caja import situacion_financiera
from core.services_estadisticas.productos import perdidas_vencimiento
from core.services_estadisticas.ventas import (
    comparacion_periodo, por_medio_pago, ranking_productos,
)

from .alertas import _fmt


def _con_porcentaje(filas, campo):
    """Agrega 'porcentaje' (relativo al máximo de la lista) para las
    barras del mail, y formatea el campo de valor a moneda ARS."""
    maximo = max((f[campo] for f in filas), default=Decimal('0')) or Decimal('1')
    return [
        {**f, 'porcentaje': round((f[campo] / maximo) * 100), f'{campo}_fmt': _fmt(f[campo])}
        for f in filas
    ]


def construir_contexto(desde, hasta, dias_aviso_vencimiento=14):
    comparacion = comparacion_periodo(desde, hasta)
    resumen = comparacion['actual']

    productos = _con_porcentaje(ranking_productos(desde, hasta, top=5), 'ganancia')
    medios = _con_porcentaje(por_medio_pago(desde, hasta), 'total')

    financiero = situacion_financiera()
    perdidas = perdidas_vencimiento(dias_alerta=dias_aviso_vencimiento)

    saldo_cuentas = [{**f, 'total': _fmt(f['total'])} for f in financiero['saldo_cuentas']]
    deudas_pendientes = [{**f, 'total': _fmt(f['total'])} for f in financiero['deudas_pendientes']]

    return {
        'resumen': {**resumen, 'ingresos': _fmt(resumen['ingresos']),
                    'ganancia_neta': _fmt(resumen['ganancia_neta'])},
        'variacion_ingresos': comparacion['variacion_ingresos'],
        'ranking_productos': productos,
        'por_medio_pago': medios,
        'saldo_cuentas': saldo_cuentas,
        'deudas_pendientes': deudas_pendientes,
        'total_en_riesgo': _fmt(perdidas['total_en_riesgo']) if perdidas['total_en_riesgo'] else None,
    }
