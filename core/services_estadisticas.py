"""
core/services_estadisticas.py

Capa de queries para el dashboard de Estadísticas. Es SOLO LECTURA:
no crea ni modifica nada, se apoya en los modelos ya existentes de
productos, compras, ventas y caja.

Convenciones:
- Todas las funciones reciben `desde`/`hasta` como date (inclusive).
- Los importes se devuelven como Decimal.
- "Ganancia" = ingresos por venta - costo REAL de la mercadería vendida,
  usando ConsumoLoteVenta (que registra de qué lote salió cada porción
  vendida y a qué costo). Esto es más preciso que "precio_venta - costo
  de catálogo", porque respeta el costo real pagado en cada lote (FIFO),
  incluso si el costo de compra cambió con el tiempo.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Q, Sum, Count, Avg, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncMonth
from django.utils import timezone

from ventas.models import ItemVenta, Venta, EstadoVenta, ConsumoLoteVenta
from compras.models import LoteCompra
from productos.models import MovimientoStock, TipoMovimiento, Moneda
from caja.models import (
    Gasto, MovimientoCaja, TipoCaja, TipoMovimientoCaja,
    CuotaDeuda, EstadoCuota, EstadoDeuda,
    Cheque, TipoCheque, EstadoCheque,
)


MONEY = DecimalField(max_digits=14, decimal_places=2)

# subtotal de un ItemVenta calculado en la DB (replica la property
# `subtotal` del modelo, que no se puede usar directo en un annotate)
SUBTOTAL_EXPR = ExpressionWrapper(
    F('cantidad') * F('precio_unitario') * (1 - F('descuento_pct') / 100),
    output_field=MONEY,
)

# costo real de un ConsumoLoteVenta (cantidad consumida * costo del lote)
COSTO_CONSUMO_EXPR = ExpressionWrapper(
    F('cantidad') * F('costo_unitario_snapshot'),
    output_field=MONEY,
)


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


# ══════════════════════════════════════════════════════════════════
#  PÉRDIDAS POR VENCIMIENTO / MERMA
# ══════════════════════════════════════════════════════════════════

def perdidas_vencimiento(dias_alerta=30):
    """
    - lotes_vencidos: lotes activos con stock, ya vencidos → pérdida
      "consumada" (siguen en el depósito pero ya no son vendibles).
    - lotes_por_vencer: lotes activos con stock que vencen dentro de
      `dias_alerta` días → alerta preventiva para liquidar/descartar.
    - mermas: histórico de MovimientoStock tipo=MERMA, valuado al costo
      promedio de los lotes de cada producto (aproximado: el movimiento
      de stock no guarda a qué lote específico correspondía).
      Si todavía no registrás mermas por ese modelo, esto queda vacío.
    """
    hoy = timezone.now().date()
    limite_alerta = hoy + timedelta(days=dias_alerta)

    lotes_vencidos = (
        LoteCompra.objects
        .filter(activo=True, cantidad_actual__gt=0, fecha_vencimiento__lt=hoy)
        .select_related('producto')
        .annotate(valor_perdido=ExpressionWrapper(
            F('cantidad_actual') * F('costo_unitario'), output_field=MONEY))
        .order_by('fecha_vencimiento')
    )
    total_vencido = sum((l.valor_perdido for l in lotes_vencidos), Decimal('0'))

    lotes_por_vencer = (
        LoteCompra.objects
        .filter(activo=True, cantidad_actual__gt=0,
                fecha_vencimiento__gte=hoy, fecha_vencimiento__lte=limite_alerta)
        .select_related('producto')
        .annotate(valor_en_riesgo=ExpressionWrapper(
            F('cantidad_actual') * F('costo_unitario'), output_field=MONEY))
        .order_by('fecha_vencimiento')
    )
    total_en_riesgo = sum((l.valor_en_riesgo for l in lotes_por_vencer), Decimal('0'))

    # — Mermas históricas (cualquier pérdida de stock, no solo vencimiento) —
    costo_promedio_por_producto = {
        row['producto']: row['costo_prom'] or Decimal('0')
        for row in LoteCompra.objects.values('producto').annotate(costo_prom=Avg('costo_unitario'))
    }
    mermas_qs = (
        MovimientoStock.objects
        .filter(tipo=TipoMovimiento.MERMA)
        .values('producto__id', 'producto__nombre', 'producto__codigo')
        .annotate(unidades_perdidas=Sum('cantidad'))
        .order_by('-unidades_perdidas')
    )
    mermas = []
    total_mermas = Decimal('0')
    for fila in mermas_qs:
        costo_prom = costo_promedio_por_producto.get(fila['producto__id'], Decimal('0'))
        valor = Decimal(fila['unidades_perdidas'] or 0) * costo_prom
        total_mermas += valor
        mermas.append({
            'producto': fila['producto__nombre'],
            'codigo': fila['producto__codigo'],
            'unidades_perdidas': fila['unidades_perdidas'],
            'valor_estimado': round(valor, 2),
        })

    return {
        'lotes_vencidos': list(lotes_vencidos[:15]),
        'total_vencido': round(total_vencido, 2),
        'lotes_por_vencer': list(lotes_por_vencer[:15]),
        'total_en_riesgo': round(total_en_riesgo, 2),
        'mermas': mermas[:15],
        'total_mermas': round(total_mermas, 2),
    }


# ══════════════════════════════════════════════════════════════════
#  PÉRDIDAS DENTRO DEL PERÍODO SELECCIONADO
#  (distinto de perdidas_vencimiento(), que es el estado actual del
#  depósito HOY, sin importar qué período esté filtrado arriba)
# ══════════════════════════════════════════════════════════════════

def perdidas_del_periodo(desde, hasta):
    """
    Pérdidas "concretadas" dentro del período elegido en los filtros:
    - vencido: lotes cuya fecha de vencimiento cae dentro de [desde,
      hasta] y que todavía tienen stock sin vender (la pérdida se
      concretó en ese momento porque no se llegó a vender a tiempo).
    - mermas: MovimientoStock tipo=MERMA registrados en ese rango de
      fechas, valuados al costo promedio del producto.
    """
    lotes_vencidos_periodo = (
        LoteCompra.objects
        .filter(cantidad_actual__gt=0, fecha_vencimiento__range=(desde, hasta))
        .select_related('producto')
        .annotate(valor_perdido=ExpressionWrapper(
            F('cantidad_actual') * F('costo_unitario'), output_field=MONEY))
        .order_by('fecha_vencimiento')
    )
    total_vencido_periodo = sum((l.valor_perdido for l in lotes_vencidos_periodo), Decimal('0'))

    costo_promedio_por_producto = {
        row['producto']: row['costo_prom'] or Decimal('0')
        for row in LoteCompra.objects.values('producto').annotate(costo_prom=Avg('costo_unitario'))
    }
    mermas_periodo_qs = (
        MovimientoStock.objects
        .filter(tipo=TipoMovimiento.MERMA, fecha__date__range=(desde, hasta))
        .values('producto__id')
        .annotate(unidades=Sum('cantidad'))
    )
    total_mermas_periodo = Decimal('0')
    unidades_mermas_periodo = 0
    for fila in mermas_periodo_qs:
        costo_prom = costo_promedio_por_producto.get(fila['producto__id'], Decimal('0'))
        total_mermas_periodo += Decimal(fila['unidades'] or 0) * costo_prom
        unidades_mermas_periodo += fila['unidades'] or 0

    return {
        'lotes_vencidos_periodo': list(lotes_vencidos_periodo[:15]),
        'cantidad_lotes_vencidos_periodo': lotes_vencidos_periodo.count(),
        'total_vencido_periodo': round(total_vencido_periodo, 2),
        'unidades_mermas_periodo': unidades_mermas_periodo,
        'total_mermas_periodo': round(total_mermas_periodo, 2),
        'total_perdidas_periodo': round(total_vencido_periodo + total_mermas_periodo, 2),
    }


# ══════════════════════════════════════════════════════════════════
#  GASTOS POR CATEGORÍA
#  (agrupa por descripción; si más adelante Gasto tiene un campo
#  categoria propio, cambiar el agrupamiento acá por ese campo)
# ══════════════════════════════════════════════════════════════════

def gastos_por_categoria(desde, hasta, top=8):
    return list(
        Gasto.objects.filter(fecha__range=(desde, hasta))
        .values('descripcion')
        .annotate(total=Sum('monto'))
        .order_by('-total')[:top]
    )


# ══════════════════════════════════════════════════════════════════
#  SITUACIÓN FINANCIERA ACTUAL
#  (estado en tiempo real — no depende del filtro de fecha del
#  dashboard. Responde "¿cuánta plata tengo, cuánto debo, cuánto me
#  deben?" de un vistazo.)
# ══════════════════════════════════════════════════════════════════

def _por_moneda(lista, campo_total='total'):
    """Filtra a solo las monedas con movimiento y les agrega el label."""
    labels = dict(Moneda.choices)
    return [
        {'moneda': f['moneda'], 'label': labels.get(f['moneda'], f['moneda']),
         'total': f[campo_total] or Decimal('0')}
        for f in lista if f[campo_total]
    ]


def situacion_financiera():
    # — Plata disponible: cuentas reales (no tarjetas) de caja grande —
    saldos = (
        MovimientoCaja.objects
        .filter(caja=TipoCaja.GRANDE, cuenta__activa=True, cuenta__es_credito=False)
        .values('moneda')
        .annotate(
            ingresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.INGRESO)),
            egresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.EGRESO)),
        )
    )
    saldo_cuentas = _por_moneda([
        {'moneda': f['moneda'], 'total': (f['ingresos'] or Decimal('0')) - (f['egresos'] or Decimal('0'))}
        for f in saldos
    ])

    # — Deudas propias pendientes (cuotas de crédito/préstamos activos) —
    deudas = (
        CuotaDeuda.objects
        .filter(estado=EstadoCuota.PENDIENTE, deuda__estado=EstadoDeuda.ACTIVA)
        .values('deuda__moneda')
        .annotate(total=Sum('monto'))
    )
    deudas_pendientes = _por_moneda([
        {'moneda': f['deuda__moneda'], 'total': f['total']} for f in deudas
    ])

    # — Cheques pendientes: a cobrar (a favor) vs a pagar (en contra) —
    cheques = (
        Cheque.objects
        .filter(estado=EstadoCheque.PENDIENTE)
        .values('tipo', 'moneda')
        .annotate(total=Sum('monto'))
    )
    cheques_a_cobrar = _por_moneda([
        {'moneda': f['moneda'], 'total': f['total']}
        for f in cheques if f['tipo'] == TipoCheque.A_COBRAR
    ])
    cheques_a_pagar = _por_moneda([
        {'moneda': f['moneda'], 'total': f['total']}
        for f in cheques if f['tipo'] == TipoCheque.A_PAGAR
    ])

    return {
        'saldo_cuentas': saldo_cuentas,
        'deudas_pendientes': deudas_pendientes,
        'cheques_a_cobrar': cheques_a_cobrar,
        'cheques_a_pagar': cheques_a_pagar,
    }