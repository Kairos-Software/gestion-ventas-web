"""
core/services_estadisticas/

Capa de queries para las páginas de Estadísticas. Es SOLO LECTURA: no
crea ni modifica nada, se apoya en los modelos ya existentes de
productos, compras, ventas y caja.

Un módulo por dominio (ventas, compras, productos, clientes, caja),
cada uno con las funciones que alimentan su página. Este __init__
solo tiene lo genérico que varios módulos necesitan: el manejo de
rangos de fecha y el tipo de campo Money para los annotate().

Convenciones:
- Las funciones reciben `desde`/`hasta` como date (inclusive).
- Los importes se devuelven como Decimal.
"""

from datetime import timedelta

from django.db.models import DecimalField

MONEY = DecimalField(max_digits=14, decimal_places=2)


# ══════════════════════════════════════════════════════════════════
#  RANGOS DE FECHA
# ══════════════════════════════════════════════════════════════════

def rango_por_preset(preset, hoy):
    """Devuelve (desde, hasta) según un preset de filtro rápido."""
    if preset == 'hoy':
        return hoy, hoy
    if preset == 'semana':
        return hoy - timedelta(days=6), hoy
    if preset == 'mes_anterior':
        primero_mes_actual = hoy.replace(day=1)
        ultimo_mes_anterior = primero_mes_actual - timedelta(days=1)
        return ultimo_mes_anterior.replace(day=1), ultimo_mes_anterior
    if preset == 'anio':
        return hoy.replace(month=1, day=1), hoy
    # default: mes_actual
    return hoy.replace(day=1), hoy


def _periodo_anterior(desde, hasta):
    """Período inmediatamente anterior, de la misma duración (en días)."""
    dias = (hasta - desde).days + 1
    hasta_anterior = desde - timedelta(days=1)
    desde_anterior = hasta_anterior - timedelta(days=dias - 1)
    return desde_anterior, hasta_anterior
