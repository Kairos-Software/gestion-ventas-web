"""
core/services_estadisticas/productos.py

Estado del inventario: valorización del stock actual, productos sin
movimiento ("stock muerto"), stock bajo/crítico, rendimiento de
paquetes, y pérdidas por vencimiento/merma.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from django.db.models import F, Avg, Count, ExpressionWrapper, Min, Sum
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
    hoy = timezone.localtime().date()
    limite_alerta = hoy + timedelta(days=dias_alerta)

    lotes_vencidos = (
        LoteCompra.objects
        .filter(activo=True, cantidad_actual__gt=0, fecha_vencimiento__lt=hoy)
        .select_related('producto')
        .annotate(valor_perdido=ExpressionWrapper(
            F('cantidad_actual') * F('costo_unitario'), output_field=MONEY))
        .order_by('fecha_vencimiento')
    )
    cantidad_lotes_vencidos = lotes_vencidos.count()
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
    cantidad_lotes_por_vencer = lotes_por_vencer.count()
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
        'cantidad_lotes_vencidos': cantidad_lotes_vencidos,
        'total_vencido': round(total_vencido, 2),
        'lotes_por_vencer': list(lotes_por_vencer[:15]),
        'cantidad_lotes_por_vencer': cantidad_lotes_por_vencer,
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
        .filter(activo=True, cantidad_actual__gt=0,
                fecha_vencimiento__range=(desde, hasta),
                fecha_vencimiento__lt=timezone.localtime().date())
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
    """
    Cuánto vale el stock que tenés hoy, de dos formas distintas:
    - `total_valorizado` (a costo): capital inmovilizado en mercadería —
      lo que costó/costaría reponerla. Sirve para saber cuánto tenés
      invertido en inventario.
    - `total_venta` (a precio de venta): lo que entraría a la caja si se
      vendiera TODO el stock a precio de lista, sin descuentos. Sirve
      para comparar contra las deudas — "si liquido todo, ¿cubro lo que
      debo?" — que es una pregunta distinta a "cuánto tengo invertido".
    """
    productos = Producto.objects.filter(gestiona_stock=True, stock_actual__gt=0)
    agregado = productos.annotate(
        valor_costo=ExpressionWrapper(F('stock_actual') * F('costo_actual'), output_field=MONEY),
        valor_venta=ExpressionWrapper(F('stock_actual') * F('precio_venta'), output_field=MONEY),
    ).aggregate(total_costo=Sum('valor_costo'), total_venta=Sum('valor_venta'))

    return {
        'total_valorizado': round(agregado['total_costo'] or Decimal('0'), 2),
        'total_venta': round(agregado['total_venta'] or Decimal('0'), 2),
        'cantidad_productos': productos.count(),
    }


# ══════════════════════════════════════════════════════════════════
#  STOCK BAJO / CRÍTICO
#  Incluye agotados: un producto con stock cero es más urgente que uno
#  con pocas unidades. Solo se alerta si tiene un mínimo configurado.
# ══════════════════════════════════════════════════════════════════

def _stock_bajo_queryset():
    return Producto.objects.filter(
        gestiona_stock=True, stock_minimo__gt=0,
        stock_actual__lte=F('stock_minimo'),
    )


def contar_stock_bajo():
    return _stock_bajo_queryset().count()


def stock_bajo(top=30):
    productos = _stock_bajo_queryset().order_by('stock_actual')[:top]
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
    hoy = timezone.localtime().date()
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
        unidades = fila['unidades'] or Decimal('0')
        ranking.append({
            'id': paquete_id,
            'nombre': fila['producto__nombre'],
            'codigo': fila['producto__codigo'],
            'ingresos': ingresos,
            'costo': costo,
            'ganancia': ingresos - costo,
            'unidades': unidades,
            'precio_prom': (ingresos / unidades) if unidades else Decimal('0'),
            'margen_sobre_costo': ((ingresos - costo) / costo * 100) if costo else None,
        })

    ranking.sort(key=lambda r: r['ganancia'], reverse=True)
    return ranking[:top]


# ══════════════════════════════════════════════════════════════════
#  PREDICCIÓN DE REPOSICIÓN DE STOCK
#  Cuándo se agotaría cada producto si sigue vendiéndose al ritmo de
#  los últimos días, y cuánta plata conviene tener lista (y en qué
#  momento) para reponerlo. Es una AYUDA para decidir, no una
#  certeza — se proyecta el promedio reciente hacia adelante, sin
#  contemplar estacionalidad, promociones ni demoras del proveedor.
# ══════════════════════════════════════════════════════════════════

DIAS_HISTORIAL_VELOCIDAD = 90
VENTAS_MINIMAS_CONFIABLE = 3
DIAS_MINIMOS_CONFIABLE = 14
DIAS_URGENTE = 7
DIAS_COBERTURA_RECOMENDADA = 60
MESES_ADELANTE = 6
DIAS_TENDENCIA_RECIENTE = 30
UMBRAL_TENDENCIA = Decimal('0.15')  # ±15% entre el ritmo reciente y el de 90 días para no marcar ruido como tendencia

_NOMBRES_MES = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
    'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


def _nombre_mes(d, hoy):
    nombre = _NOMBRES_MES[d.month - 1].capitalize()
    return nombre if d.year == hoy.year else f'{nombre} {d.year}'


def _fin_de_mes(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _primer_dia_mes_siguiente(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _rangos_por_cuando(hoy):
    """
    [(desde, hasta, etiqueta), ...] automático, sin que el usuario elija
    nada: primero una ventana "urgente" de `DIAS_URGENTE` días, después
    lo que queda del mes en curso (si sobra algo después de esa ventana),
    y después un mes calendario completo a la vez hasta `MESES_ADELANTE`.
    """
    rangos = []
    limite_urgente = hoy + timedelta(days=DIAS_URGENTE)
    rangos.append((hoy, limite_urgente, 'Necesitás comprar ya'))

    fin_mes_actual = _fin_de_mes(hoy)
    if limite_urgente < fin_mes_actual:
        rangos.append((limite_urgente + timedelta(days=1), fin_mes_actual, 'Resto de este mes'))

    cursor = _primer_dia_mes_siguiente(fin_mes_actual)
    for _ in range(MESES_ADELANTE):
        fin = _fin_de_mes(cursor)
        inicio = max(cursor, limite_urgente + timedelta(days=1))
        if inicio <= fin:
            rangos.append((inicio, fin, _nombre_mes(cursor, hoy)))
        cursor = _primer_dia_mes_siguiente(fin)
    return rangos


def prediccion_reposicion():
    """
    Para cada producto con stock gestionado y ventas en los últimos
    `DIAS_HISTORIAL_VELOCIDAD` días:
    - velocidad: unidades/día vendidas en ese período (o desde su
      primera venta, si el producto es más nuevo que ese período —
      si no, un producto recién agregado parecería vender mucho más
      lento de lo real, por dividir sobre días en que ni existía).
    - dias_hasta_agotamiento / fecha_estimada: cuándo llegaría a 0 si
      se sigue vendiendo al mismo ritmo.
    - recomendado_unidades / costo_estimado: una reposición que cubra
      `DIAS_COBERTURA_RECOMENDADA` días desde el agotamiento estimado,
      sin superar `stock_maximo` si fue configurado. El monto es una
      estimación al costo actual; si falta ese costo se informa aparte.
    Todo esto se agrupa automáticamente por "cuándo" (`_rangos_por_cuando`)
    para poder ver cuánta plata hace falta reservar cada mes, sin que el
    usuario tenga que elegir ninguna ventana — solo se proyecta hasta
    `MESES_ADELANTE` meses, más allá de eso no tiene sentido mostrarlo.
    """
    hoy = timezone.localtime().date()
    desde_historial = hoy - timedelta(days=DIAS_HISTORIAL_VELOCIDAD)
    desde_reciente = hoy - timedelta(days=DIAS_TENDENCIA_RECIENTE)

    ventas_por_producto = (
        ItemVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA,
                venta__fecha__range=(desde_historial, hoy),
                producto__isnull=False)
        .values('producto_id')
        .annotate(unidades=Sum('cantidad'), primera_venta=Min('venta__fecha'),
                  cant_ventas=Count('venta', distinct=True))
    )
    datos_venta = {f['producto_id']: f for f in ventas_por_producto}

    # Ventana corta (aparte de la de 90 días) solo para detectar si el
    # producto viene acelerando o frenando — no cambia ningún cálculo de
    # cantidad/costo, es puramente informativo (badge de tendencia).
    unidades_recientes = {
        f['producto_id']: f['unidades'] or Decimal('0')
        for f in (
            ItemVenta.objects
            .filter(venta__estado=EstadoVenta.CONFIRMADA,
                    venta__fecha__range=(desde_reciente, hoy),
                    producto__isnull=False)
            .values('producto_id')
            .annotate(unidades=Sum('cantidad'))
        )
    }

    rangos = _rangos_por_cuando(hoy)
    limite_horizonte = rangos[-1][1]

    filas = []
    productos = (
        Producto.objects
        .filter(gestiona_stock=True, id__in=datos_venta.keys())
        .select_related('proveedor')
    )
    for p in productos:
        datos = datos_venta[p.id]
        unidades = datos['unidades'] or Decimal('0')
        if unidades <= 0:
            continue

        dias_con_datos = max((hoy - max(datos['primera_venta'], desde_historial)).days, 1)
        velocidad_diaria = unidades / Decimal(dias_con_datos)
        if velocidad_diaria <= 0:
            continue
        if p.stock_actual > velocidad_diaria * Decimal((limite_horizonte - hoy).days):
            continue  # ni siquiera se agotaría dentro del horizonte mostrado

        dias_hasta_agotamiento = (
            0 if p.stock_actual <= 0 else
            int((p.stock_actual / velocidad_diaria).to_integral_value(rounding=ROUND_CEILING))
        )
        fecha_estimada = hoy + timedelta(days=dias_hasta_agotamiento)
        if fecha_estimada > limite_horizonte:
            continue  # se agotaría más allá de lo que tiene sentido proyectar

        # La reposición se proyecta para cuando se agote, no para hoy:
        # restar el stock actual ocultaba compras necesarias en meses futuros.
        # Si ya hay stock negativo, también hay que cubrir ese faltante.
        faltante_actual = max(-p.stock_actual, Decimal('0'))
        recomendado = velocidad_diaria * Decimal(DIAS_COBERTURA_RECOMENDADA) + faltante_actual
        if p.stock_maximo is not None:
            recomendado = min(recomendado, p.stock_maximo + faltante_actual)
        recomendado = max(recomendado, Decimal('0'))
        if p.permite_fraccion:
            recomendado = recomendado.quantize(Decimal('0.001'), rounding=ROUND_CEILING)
        else:
            recomendado = recomendado.to_integral_value(rounding=ROUND_CEILING)
            if p.stock_maximo is not None:
                recomendado = min(
                    recomendado,
                    (p.stock_maximo + faltante_actual).to_integral_value(rounding=ROUND_FLOOR),
                )
        if recomendado <= 0:
            continue  # el stock máximo configurado no permite reponer

        costo_estimado = round(recomendado * p.costo_actual, 2) if p.costo_actual is not None else None

        tendencia = None
        if dias_con_datos >= DIAS_TENDENCIA_RECIENTE:
            dias_reciente_efectivo = min(DIAS_TENDENCIA_RECIENTE, dias_con_datos)
            velocidad_reciente = unidades_recientes.get(p.id, Decimal('0')) / Decimal(dias_reciente_efectivo)
            if velocidad_reciente > velocidad_diaria * (1 + UMBRAL_TENDENCIA):
                tendencia = 'acelerando'
            elif velocidad_reciente < velocidad_diaria * (1 - UMBRAL_TENDENCIA):
                tendencia = 'frenando'
            else:
                tendencia = 'estable'

        filas.append({
            'id': p.id,
            'nombre': p.nombre,
            'codigo': p.codigo,
            'unidad_medida': p.get_unidad_medida_display(),
            'proveedor': p.proveedor.nombre if p.proveedor_id else None,
            'stock_actual': p.stock_actual,
            'velocidad_semanal': round(velocidad_diaria * 7, 2),
            'dias_hasta_agotamiento': dias_hasta_agotamiento,
            'fecha_estimada': fecha_estimada,
            'recomendado_unidades': recomendado,
            'costo_estimado': costo_estimado,
            'tendencia': tendencia,
            'poco_confiable': (datos['cant_ventas'] or 0) < VENTAS_MINIMAS_CONFIABLE
                              or dias_con_datos < DIAS_MINIMOS_CONFIABLE,
        })

    filas.sort(key=lambda f: f['dias_hasta_agotamiento'])

    buckets = []
    for desde, hasta, etiqueta in rangos:
        del_bucket = sorted(
            (f for f in filas if desde <= f['fecha_estimada'] <= hasta),
            key=lambda f: f['dias_hasta_agotamiento'],
        )
        buckets.append({
            'etiqueta': etiqueta,
            'desde': desde,
            'hasta': hasta,
            'productos': del_bucket,
            'cantidad_productos': len(del_bucket),
            'total_estimado': round(sum((f['costo_estimado'] or Decimal('0') for f in del_bucket), Decimal('0')), 2),
            'sin_costo': sum(f['costo_estimado'] is None for f in del_bucket),
        })

    por_proveedor = {}
    for f in filas:
        clave = f['proveedor'] or 'Sin proveedor asignado'
        if clave not in por_proveedor:
            por_proveedor[clave] = {'proveedor': clave, 'cantidad_productos': 0, 'total_estimado': Decimal('0')}
        por_proveedor[clave]['cantidad_productos'] += 1
        por_proveedor[clave]['total_estimado'] += f['costo_estimado'] or Decimal('0')
    por_proveedor = sorted(por_proveedor.values(), key=lambda g: g['total_estimado'], reverse=True)
    for g in por_proveedor:
        g['total_estimado'] = round(g['total_estimado'], 2)

    return {
        'hoy': hoy,
        'buckets': buckets,
        'productos': filas,
        'por_proveedor': por_proveedor,
        'total_estimado': round(sum((f['costo_estimado'] or Decimal('0') for f in filas), Decimal('0')), 2),
        'sin_costo': sum(f['costo_estimado'] is None for f in filas),
        'cantidad_productos': len(filas),
        'ventas_analizadas': sum((d['cant_ventas'] or 0) for d in datos_venta.values()),
    }
