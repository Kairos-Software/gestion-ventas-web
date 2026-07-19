"""
core/services_estadisticas/ventas.py

Ganancia, tendencia y rankings del lado de Ventas. "Ganancia" =
ingresos por venta - costo REAL de la mercadería vendida, usando
ConsumoLoteVenta (que registra de qué lote salió cada porción vendida
y a qué costo). Esto es más preciso que "precio_venta - costo de
catálogo", porque respeta el costo real pagado en cada lote (FIFO),
incluso si el costo de compra cambió con el tiempo.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Sum, Count, ExpressionWrapper
from django.db.models.functions import TruncMonth, ExtractWeekDay

from ventas.models import ItemVenta, Venta, EstadoVenta, ConsumoLoteVenta, PagoVenta, MedioPago
from caja.models import Gasto

from . import MONEY, _periodo_anterior


# subtotal de un ItemVenta calculado en la DB (replica la property
# `subtotal` del modelo, que no se puede usar directo en un annotate)
SUBTOTAL_EXPR = ExpressionWrapper(
    F('cantidad') * F('precio_unitario') * (1 - F('descuento_pct') / 100),
    output_field=MONEY,
)

# costo real de un ConsumoLoteVenta (cantidad consumida * costo del lote)
COSTO_CONSUMO_EXPR = ExpressionWrapper(
    F('cantidad') * F('costo_unitario_snapshot'), output_field=MONEY,
)


# ══════════════════════════════════════════════════════════════════
#  BASE — ítems vendidos confirmados en un rango
# ══════════════════════════════════════════════════════════════════

def _items_confirmados(desde, hasta):
    return (
        ItemVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA, venta__fecha__range=(desde, hasta))
        .annotate(subtotal_calc=SUBTOTAL_EXPR)
    )


def _costo_de_items(items_qs):
    """Costo real (vía ConsumoLoteVenta) de un queryset de ItemVenta."""
    total = (
        ConsumoLoteVenta.objects
        .filter(item_venta__in=items_qs)
        .annotate(costo_calc=COSTO_CONSUMO_EXPR)
        .aggregate(total=Sum('costo_calc'))['total']
    )
    return total or Decimal('0')


# ══════════════════════════════════════════════════════════════════
#  RESUMEN DE GANANCIA (bruta y neta) + COMPARACIÓN DE PERÍODO
# ══════════════════════════════════════════════════════════════════

def resumen_ganancia(desde, hasta):
    items = _items_confirmados(desde, hasta)
    ingresos = items.aggregate(total=Sum('subtotal_calc'))['total'] or Decimal('0')
    costo_mercaderia = _costo_de_items(items)
    ganancia_bruta = ingresos - costo_mercaderia

    gastos = Gasto.objects.filter(fecha__range=(desde, hasta)).aggregate(
        total=Sum('monto'))['total'] or Decimal('0')
    ganancia_neta = ganancia_bruta - gastos

    margen_pct = (ganancia_bruta / ingresos * 100) if ingresos else Decimal('0')

    return {
        'ingresos': ingresos,
        'costo_mercaderia': costo_mercaderia,
        'ganancia_bruta': ganancia_bruta,
        'gastos': gastos,
        'ganancia_neta': ganancia_neta,
        'margen_pct': round(margen_pct, 2),
        'cantidad_ventas': Venta.objects.filter(
            estado=EstadoVenta.CONFIRMADA, fecha__range=(desde, hasta)).count(),
    }


def comparacion_periodo(desde, hasta):
    """Compara el período actual contra el inmediatamente anterior
    (misma duración) para mostrar % de crecimiento/decrecimiento."""
    actual = resumen_ganancia(desde, hasta)
    desde_ant, hasta_ant = _periodo_anterior(desde, hasta)
    anterior = resumen_ganancia(desde_ant, hasta_ant)

    def _variacion(a, b):
        if not b:
            return None  # sin base de comparación (período anterior sin ventas)
        return round(((a - b) / b) * 100, 2)

    return {
        'actual': actual,
        'anterior': anterior,
        'anterior_desde': desde_ant,
        'anterior_hasta': hasta_ant,
        'variacion_ingresos': _variacion(actual['ingresos'], anterior['ingresos']),
        'variacion_ganancia': _variacion(actual['ganancia_bruta'], anterior['ganancia_bruta']),
    }


def serie_mensual(hoy, meses=12):
    """
    Ingresos/costo/ganancia agrupados por mes, últimos N meses.
    Para el gráfico de tendencia de crecimiento del negocio.

    Siempre devuelve `meses` filas (una por cada mes del rango), aunque
    algunos tengan $0 en ventas — así la línea del gráfico se ve
    completa y prolija incluso con poca data cargada todavía, en vez
    de mostrar un solo punto suelto.
    """
    primer_mes = (hoy.replace(day=1) - timedelta(days=30 * (meses - 1))).replace(day=1)

    items = (
        ItemVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA, venta__fecha__gte=primer_mes)
        .annotate(subtotal_calc=SUBTOTAL_EXPR, mes=TruncMonth('venta__fecha'))
    )
    ingresos_por_mes = (
        items.values('mes')
        .annotate(ingresos=Sum('subtotal_calc'))
    )
    ingresos_dict = {f['mes']: f['ingresos'] or Decimal('0') for f in ingresos_por_mes}

    costos_por_mes = (
        ConsumoLoteVenta.objects
        .filter(item_venta__venta__estado=EstadoVenta.CONFIRMADA,
                item_venta__venta__fecha__gte=primer_mes)
        .annotate(costo_calc=COSTO_CONSUMO_EXPR, mes=TruncMonth('item_venta__venta__fecha'))
        .values('mes')
        .annotate(costo=Sum('costo_calc'))
    )
    costos_dict = {c['mes']: c['costo'] or Decimal('0') for c in costos_por_mes}

    # Generamos explícitamente los `meses` casilleros del calendario,
    # en orden, completando con $0 los que no tengan ventas.
    serie = []
    cursor = primer_mes
    for _ in range(meses):
        ingresos = ingresos_dict.get(cursor, Decimal('0'))
        costo = costos_dict.get(cursor, Decimal('0'))
        serie.append({
            'mes': cursor,
            'ingresos': ingresos,
            'costo': costo,
            'ganancia': ingresos - costo,
        })
        # avanzar al primer día del mes siguiente
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return serie


# ══════════════════════════════════════════════════════════════════
#  RANKING DE EMPLEADOS MÁS RENTABLES
# ══════════════════════════════════════════════════════════════════

def ranking_empleados(desde, hasta, top=10):
    """
    Ranking por rentabilidad generada. Se toma `confirmado_por` de la
    Venta como "vendedor", ya que es quien efectivamente ejecutó la
    confirmación (y por lo tanto el cobro) de la operación.
    """
    items = _items_confirmados(desde, hasta)

    ingresos_por_empleado = (
        items.exclude(venta__confirmado_por__isnull=True)
        .values('venta__confirmado_por__id', 'venta__confirmado_por__username',
                'venta__confirmado_por__first_name', 'venta__confirmado_por__last_name')
        .annotate(ingresos=Sum('subtotal_calc'), cant_ventas=Count('venta', distinct=True))
        .order_by('-ingresos')
    )

    costos_por_empleado = (
        ConsumoLoteVenta.objects
        .filter(item_venta__venta__estado=EstadoVenta.CONFIRMADA,
                item_venta__venta__fecha__range=(desde, hasta))
        .exclude(item_venta__venta__confirmado_por__isnull=True)
        .annotate(costo_calc=COSTO_CONSUMO_EXPR)
        .values('item_venta__venta__confirmado_por__id')
        .annotate(costo=Sum('costo_calc'))
    )
    costos_dict = {c['item_venta__venta__confirmado_por__id']: c['costo'] or Decimal('0')
                   for c in costos_por_empleado}

    ranking = []
    for fila in ingresos_por_empleado:
        empleado_id = fila['venta__confirmado_por__id']
        ingresos = fila['ingresos'] or Decimal('0')
        costo = costos_dict.get(empleado_id, Decimal('0'))
        ganancia = ingresos - costo
        nombre = (
            f"{fila['venta__confirmado_por__first_name'] or ''} "
            f"{fila['venta__confirmado_por__last_name'] or ''}"
        ).strip()
        cant_ventas = fila['cant_ventas'] or 0
        ranking.append({
            'id': empleado_id,
            'nombre': nombre or fila['venta__confirmado_por__username'],
            'ingresos': ingresos,
            'ganancia': ganancia,
            'cant_ventas': cant_ventas,
            'ticket_promedio': round(ingresos / cant_ventas, 2) if cant_ventas else Decimal('0'),
        })

    ranking.sort(key=lambda r: r['ganancia'], reverse=True)
    return ranking[:top]


# ══════════════════════════════════════════════════════════════════
#  RANKING POR CATEGORÍA DE PRODUCTO
# ══════════════════════════════════════════════════════════════════

def ranking_categorias(desde, hasta, top=10):
    items = _items_confirmados(desde, hasta).exclude(producto__categoria__isnull=True)

    ingresos_por_categoria = (
        items.values('producto__categoria__id', 'producto__categoria__nombre')
        .annotate(ingresos=Sum('subtotal_calc'), unidades=Sum('cantidad'))
        .order_by('-ingresos')
    )

    costos_por_categoria = (
        ConsumoLoteVenta.objects
        .filter(item_venta__venta__estado=EstadoVenta.CONFIRMADA,
                item_venta__venta__fecha__range=(desde, hasta))
        .exclude(item_venta__producto__categoria__isnull=True)
        .annotate(costo_calc=COSTO_CONSUMO_EXPR)
        .values('item_venta__producto__categoria__id')
        .annotate(costo=Sum('costo_calc'))
    )
    costos_dict = {c['item_venta__producto__categoria__id']: c['costo'] or Decimal('0')
                   for c in costos_por_categoria}

    ranking = []
    for fila in ingresos_por_categoria:
        cat_id = fila['producto__categoria__id']
        ingresos = fila['ingresos'] or Decimal('0')
        costo = costos_dict.get(cat_id, Decimal('0'))
        ranking.append({
            'id': cat_id,
            'nombre': fila['producto__categoria__nombre'],
            'ingresos': ingresos,
            'ganancia': ingresos - costo,
            'unidades': fila['unidades'] or 0,
        })

    ranking.sort(key=lambda r: r['ganancia'], reverse=True)
    return ranking[:top]


# ══════════════════════════════════════════════════════════════════
#  VENTAS POR MEDIO DE PAGO
#  Se agrupa también por moneda de la cuenta: PagoVenta.monto está en
#  la moneda de `cuenta`, no siempre en pesos (ver PagoVenta), así
#  que sumar todo junto mezclaría monedas.
# ══════════════════════════════════════════════════════════════════

def por_medio_pago(desde, hasta):
    labels = dict(MedioPago.choices)
    pagos = (
        PagoVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA, venta__fecha__range=(desde, hasta))
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


# ══════════════════════════════════════════════════════════════════
#  VENTAS POR DÍA DE LA SEMANA
#  ExtractWeekDay: 1=domingo … 7=sábado (Django lo normaliza igual
#  sin importar el motor de base de datos).
# ══════════════════════════════════════════════════════════════════

NOMBRES_DIA_SEMANA = {
    1: 'Domingo', 2: 'Lunes', 3: 'Martes', 4: 'Miércoles',
    5: 'Jueves', 6: 'Viernes', 7: 'Sábado',
}


def por_dia_semana(desde, hasta):
    items = (
        _items_confirmados(desde, hasta)
        .annotate(dia_semana=ExtractWeekDay('venta__fecha'))
        .values('dia_semana')
        .annotate(ingresos=Sum('subtotal_calc'), cant_ventas=Count('venta', distinct=True))
    )
    totales = {f['dia_semana']: f for f in items}

    # Siempre devolvemos los 7 días en orden Lunes→Domingo (más
    # natural para leer una semana laboral), completando con $0 los
    # días sin ventas en el período.
    orden = [2, 3, 4, 5, 6, 7, 1]
    return [
        {
            'dia': NOMBRES_DIA_SEMANA[d],
            'ingresos': totales.get(d, {}).get('ingresos') or Decimal('0'),
            'cant_ventas': totales.get(d, {}).get('cant_ventas') or 0,
        }
        for d in orden
    ]


# ══════════════════════════════════════════════════════════════════
#  IMPACTO DE OFERTAS Y LISTAS DE DESCUENTO
#  Cuánto se descontó (precio de lista - lo que realmente se cobró)
#  agrupado por el nombre de la oferta/lista que se aplicó.
# ══════════════════════════════════════════════════════════════════

def impacto_descuentos(desde, hasta, top=8):
    items = _items_confirmados(desde, hasta).annotate(
        precio_lleno=ExpressionWrapper(F('cantidad') * F('precio_unitario'), output_field=MONEY),
    )

    def _agrupar(campo):
        filas = (
            items.exclude(**{campo: ''})
            .values(campo)
            .annotate(
                descuento_total=Sum(F('precio_lleno') - F('subtotal_calc')),
                unidades=Sum('cantidad'),
                cant_items=Count('id'),
            )
            .order_by('-descuento_total')[:top]
        )
        return [
            {
                'nombre': fila[campo],
                'descuento_total': fila['descuento_total'] or Decimal('0'),
                'unidades': fila['unidades'] or 0,
                'cant_items': fila['cant_items'],
            }
            for fila in filas
        ]

    return {
        'ofertas': _agrupar('oferta_aplicada_nombre'),
        'listas_descuento': _agrupar('lista_descuento_nombre'),
    }


# ══════════════════════════════════════════════════════════════════
#  RANKING DE PRODUCTOS (por ganancia generada)
# ══════════════════════════════════════════════════════════════════

def ranking_productos(desde, hasta, top=10):
    items = _items_confirmados(desde, hasta).exclude(producto__isnull=True)

    ingresos_por_producto = (
        items.values('producto__id', 'producto__nombre', 'producto__codigo')
        .annotate(ingresos=Sum('subtotal_calc'), unidades=Sum('cantidad'))
        .order_by('-ingresos')
    )

    costos_por_producto = (
        ConsumoLoteVenta.objects
        .filter(item_venta__venta__estado=EstadoVenta.CONFIRMADA,
                item_venta__venta__fecha__range=(desde, hasta))
        .exclude(item_venta__producto__isnull=True)
        .annotate(costo_calc=COSTO_CONSUMO_EXPR)
        .values('item_venta__producto__id')
        .annotate(costo=Sum('costo_calc'))
    )
    costos_dict = {c['item_venta__producto__id']: c['costo'] or Decimal('0')
                   for c in costos_por_producto}

    ranking = []
    for fila in ingresos_por_producto:
        producto_id = fila['producto__id']
        ingresos = fila['ingresos'] or Decimal('0')
        costo = costos_dict.get(producto_id, Decimal('0'))
        ranking.append({
            'id': producto_id,
            'nombre': fila['producto__nombre'],
            'codigo': fila['producto__codigo'],
            'ingresos': ingresos,
            'ganancia': ingresos - costo,
            'unidades': fila['unidades'] or 0,
        })

    ranking.sort(key=lambda r: r['ganancia'], reverse=True)
    return ranking[:top]
