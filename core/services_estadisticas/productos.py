"""
core/services_estadisticas/productos.py

Estado del inventario: valorización del stock actual, productos sin
movimiento ("stock muerto"), stock bajo/crítico, rendimiento de
paquetes, y pérdidas por vencimiento/merma.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import F, Avg, Count, ExpressionWrapper, Sum
from django.utils import timezone

from compras.models import LoteCompra
from productos.models import MovimientoStock, TipoMovimiento, Producto
from ventas.models import ItemVenta, EstadoVenta, ConsumoLoteVenta

from . import MONEY
from .ventas import SUBTOTAL_EXPR, COSTO_CONSUMO_EXPR


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
#  VALORIZACIÓN DEL STOCK ACTUAL (tiempo real)
# ══════════════════════════════════════════════════════════════════

def valorizacion_stock():
    """Cuánto vale, a costo, todo el stock que tenés hoy."""
    productos = Producto.objects.filter(gestiona_stock=True, stock_actual__gt=0)
    total = productos.annotate(
        valor=ExpressionWrapper(F('stock_actual') * F('costo_actual'), output_field=MONEY),
    ).aggregate(total=Sum('valor'))['total'] or Decimal('0')

    return {
        'total_valorizado': round(total, 2),
        'cantidad_productos': productos.count(),
    }


# ══════════════════════════════════════════════════════════════════
#  STOCK BAJO / CRÍTICO
#  Misma definición que la alerta del Dashboard (core/views.py:
#  gestiona_stock=True, con stock pero por debajo del mínimo cargado).
# ══════════════════════════════════════════════════════════════════

def stock_bajo(top=30):
    productos = (
        Producto.objects
        .filter(gestiona_stock=True, stock_actual__gt=0, stock_actual__lte=F('stock_minimo'))
        .order_by('stock_actual')[:top]
    )
    return [
        {
            'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo,
            'stock_actual': p.stock_actual, 'stock_minimo': p.stock_minimo,
        }
        for p in productos
    ]


# ══════════════════════════════════════════════════════════════════
#  PRODUCTOS SIN MOVIMIENTO ("stock muerto")
#  Tienen stock cargado pero no se vendieron en los últimos N días —
#  plata inmovilizada en la góndola/depósito.
# ══════════════════════════════════════════════════════════════════

def sin_movimiento(dias=60, top=30):
    hoy = timezone.now().date()
    limite = hoy - timedelta(days=dias)

    vendidos_recientemente = (
        ItemVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA, venta__fecha__gte=limite)
        .exclude(producto__isnull=True)
        .values_list('producto_id', flat=True)
        .distinct()
    )

    productos = (
        Producto.objects
        .filter(gestiona_stock=True, stock_actual__gt=0)
        .exclude(id__in=vendidos_recientemente)
        .annotate(valor=ExpressionWrapper(F('stock_actual') * F('costo_actual'), output_field=MONEY))
        .order_by('-valor')[:top]
    )
    return [
        {
            'id': p.id, 'nombre': p.nombre, 'codigo': p.codigo,
            'stock_actual': p.stock_actual, 'valor': p.valor or Decimal('0'),
        }
        for p in productos
    ]


# ══════════════════════════════════════════════════════════════════
#  RENDIMIENTO DE PAQUETES (combos)
# ══════════════════════════════════════════════════════════════════

def rendimiento_paquetes(desde, hasta, top=10):
    items = (
        ItemVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA, venta__fecha__range=(desde, hasta),
                producto__es_paquete=True)
        .annotate(subtotal_calc=SUBTOTAL_EXPR)
    )

    ingresos_por_paquete = (
        items.values('producto__id', 'producto__nombre', 'producto__codigo')
        .annotate(ingresos=Sum('subtotal_calc'), unidades=Sum('cantidad'), cant_ventas=Count('venta', distinct=True))
        .order_by('-ingresos')
    )

    costos_por_paquete = (
        ConsumoLoteVenta.objects
        .filter(item_venta__venta__estado=EstadoVenta.CONFIRMADA,
                item_venta__venta__fecha__range=(desde, hasta),
                item_venta__producto__es_paquete=True)
        .annotate(costo_calc=COSTO_CONSUMO_EXPR)
        .values('item_venta__producto__id')
        .annotate(costo=Sum('costo_calc'))
    )
    costos_dict = {c['item_venta__producto__id']: c['costo'] or Decimal('0') for c in costos_por_paquete}

    ranking = []
    for fila in ingresos_por_paquete:
        paquete_id = fila['producto__id']
        ingresos = fila['ingresos'] or Decimal('0')
        costo = costos_dict.get(paquete_id, Decimal('0'))
        ranking.append({
            'id': paquete_id,
            'nombre': fila['producto__nombre'],
            'codigo': fila['producto__codigo'],
            'ingresos': ingresos,
            'ganancia': ingresos - costo,
            'unidades': fila['unidades'] or 0,
        })

    ranking.sort(key=lambda r: r['ganancia'], reverse=True)
    return ranking[:top]
