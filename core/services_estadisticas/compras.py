"""
core/services_estadisticas/compras.py

Todo lo relacionado a mercadería comprada: total del período,
ranking de proveedores, desglose por medio de pago y evolución
mensual del gasto. Análogo a services_estadisticas/ventas.py, pero
del lado de la compra — acá no hay "ganancia", es simplemente lo que
salió a reponer stock.
"""

from decimal import Decimal

from django.db.models import F, Sum, Count, ExpressionWrapper
from django.db.models.functions import TruncMonth

from compras.models import ItemCompra, Compra, EstadoCompra, PagoCompra, MedioPagoCompra

from . import MONEY, _periodo_anterior


# subtotal de un ItemCompra calculado en la DB (replica la property
# `subtotal` del modelo: cantidad*costo_unitario*(1-descuento_pct/100))
SUBTOTAL_EXPR = ExpressionWrapper(
    F('cantidad') * F('costo_unitario') * (1 - F('descuento_pct') / 100),
    output_field=MONEY,
)


def _items_confirmados(desde, hasta):
    return (
        ItemCompra.objects
        .filter(compra__estado=EstadoCompra.CONFIRMADA, compra__fecha__range=(desde, hasta))
        .annotate(subtotal_calc=SUBTOTAL_EXPR)
    )


# ══════════════════════════════════════════════════════════════════
#  RESUMEN + COMPARACIÓN DE PERÍODO
# ══════════════════════════════════════════════════════════════════

def resumen_compras(desde, hasta):
    items = _items_confirmados(desde, hasta)
    total_comprado = items.aggregate(total=Sum('subtotal_calc'))['total'] or Decimal('0')

    return {
        'total_comprado': total_comprado,
        'cantidad_compras': Compra.objects.filter(
            estado=EstadoCompra.CONFIRMADA, fecha__range=(desde, hasta)).count(),
    }


def comparacion_periodo(desde, hasta):
    """Compara el total comprado del período contra el inmediatamente
    anterior (misma duración), igual que ventas.comparacion_periodo."""
    actual = resumen_compras(desde, hasta)
    desde_ant, hasta_ant = _periodo_anterior(desde, hasta)
    anterior = resumen_compras(desde_ant, hasta_ant)

    variacion = None
    if anterior['total_comprado']:
        variacion = round(
            ((actual['total_comprado'] - anterior['total_comprado']) / anterior['total_comprado']) * 100, 2
        )

    return {
        'actual': actual,
        'anterior': anterior,
        'anterior_desde': desde_ant,
        'anterior_hasta': hasta_ant,
        'variacion_total_comprado': variacion,
    }


def serie_mensual(hoy, meses=12):
    """Total comprado por mes, últimos N meses — misma forma que
    ventas.serie_mensual, para el gráfico de tendencia de gasto."""
    from datetime import timedelta
    primer_mes = (hoy.replace(day=1) - timedelta(days=30 * (meses - 1))).replace(day=1)

    compras_por_mes = (
        ItemCompra.objects
        .filter(compra__estado=EstadoCompra.CONFIRMADA, compra__fecha__gte=primer_mes)
        .annotate(subtotal_calc=SUBTOTAL_EXPR, mes=TruncMonth('compra__fecha'))
        .values('mes')
        .annotate(total=Sum('subtotal_calc'))
    )
    totales_dict = {f['mes']: f['total'] or Decimal('0') for f in compras_por_mes}

    serie = []
    cursor = primer_mes
    for _ in range(meses):
        serie.append({'mes': cursor, 'total': totales_dict.get(cursor, Decimal('0'))})
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return serie


# ══════════════════════════════════════════════════════════════════
#  RANKING DE PROVEEDORES
# ══════════════════════════════════════════════════════════════════

def ranking_proveedores(desde, hasta, top=10):
    """
    A quién le compraste más en el período. Usa el snapshot
    `proveedor_nombre` (no el FK vivo) para que el ranking siga
    mostrando el nombre aunque el proveedor se haya eliminado
    después — mismo criterio que el resto del historial de compras.
    """
    items = _items_confirmados(desde, hasta).exclude(proveedor_nombre='')

    ranking = (
        items.values('proveedor__id', 'proveedor_nombre')
        .annotate(
            total=Sum('subtotal_calc'),
            cant_compras=Count('compra', distinct=True),
        )
        .order_by('-total')[:top]
    )
    return [
        {
            'id': fila['proveedor__id'],
            'nombre': fila['proveedor_nombre'],
            'total': fila['total'] or Decimal('0'),
            'cant_compras': fila['cant_compras'],
        }
        for fila in ranking
    ]


# ══════════════════════════════════════════════════════════════════
#  COMPRAS POR MEDIO DE PAGO
#  Se agrupa también por moneda de la cuenta: PagoCompra.monto está
#  en la moneda de `cuenta`, no siempre en pesos (a diferencia de
#  Ventas), así que sumar todo junto mezclaría monedas.
# ══════════════════════════════════════════════════════════════════

def por_medio_pago(desde, hasta):
    labels = dict(MedioPagoCompra.choices)
    pagos = (
        PagoCompra.objects
        .filter(compra__estado=EstadoCompra.CONFIRMADA, compra__fecha__range=(desde, hasta))
        .values('medio', 'cuenta__moneda')
        .annotate(total=Sum('monto'))
        .order_by('-total')
    )
    return [
        {
            'medio': fila['medio'],
            'medio_label': labels.get(fila['medio'], fila['medio']),
            'moneda': fila['cuenta__moneda'] or 'ARS',
            'total': fila['total'] or Decimal('0'),
        }
        for fila in pagos
    ]
