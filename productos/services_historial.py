"""
productos/services_historial.py
────────────────────────────────────────────────────────────────────
Historial unificado de movimientos de stock de un producto (o de una
combinación de variante puntual).

El sistema no tiene un único "libro de stock": cada camino de entrada o
salida deja su rastro en un modelo distinto —

    Compra / Factura inicial     → LoteCompra (vía ItemCompra → Compra)
    Ajuste manual / merma /
    fraccionamiento              → MovimientoStock
    Venta                        → ConsumoLoteVenta (vía ItemVenta → Venta)
    Devolución de venta          → DevolucionVentaConsumo

Este módulo junta las cuatro fuentes para un producto en una sola línea
de tiempo y reconstruye el stock "según el historial" sumando/restando
cada evento en orden cronológico, para poder compararlo contra el
stock_actual real — el mismo diagnóstico que ya hacía
`manage.py rastrear_stock` por shell (ver
compras/management/commands/rastrear_stock.py), ahora disponible desde
la web, en el mismo lugar donde ya se está mirando el producto.

Es un módulo de solo lectura: no crea ni modifica ningún registro.

IMPORTANTE: la conciliación (stock_reconstruido/diferencia) siempre se
calcula sobre el conjunto COMPLETO de eventos (respetando solo el
filtro de combinación, que cambia contra qué stock_actual se compara)
— filtrarla por categoría/fecha/texto la volvería sin sentido. Los
demás filtros solo recortan qué se MUESTRA en la lista paginada.
"""
from decimal import Decimal

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

# Categorías posibles de un evento — para el filtro "Tipo de movimiento".
# Los 4 primeros valores son fijos (no vienen de TipoMovimiento); los de
# ajuste/merma/fraccionamiento reusan el valor real de
# productos.models.TipoMovimiento tal cual, para no inventar un mapeo aparte.
CATEGORIAS_HISTORIAL = [
    ('compra',           'Compra'),
    ('factura_inicial',  'Factura inicial'),
    ('ajuste_pos',       'Ajuste positivo'),
    ('ajuste_neg',       'Ajuste negativo'),
    ('merma',            'Merma / Pérdida'),
    ('fracc_e',          'Fraccionamiento (armado)'),
    ('fracc_s',          'Fraccionamiento (consumido)'),
    ('venta',            'Venta'),
    ('devolucion',       'Devolución'),
]


def _evento(fecha_orden, fecha_display, categoria, tipo_label, es_entrada, cantidad,
            combinacion_desc, origen_label, origen_url, usuario, detalle, activo):
    return {
        'fecha_orden':      fecha_orden,
        'fecha_display':    fecha_display,
        'categoria':        categoria,
        'tipo_label':       tipo_label,
        'es_entrada':       es_entrada,
        'cantidad':         cantidad,
        'combinacion_desc': combinacion_desc,
        'origen_label':     origen_label,
        'origen_url':       origen_url,
        'usuario':          usuario,
        'detalle':          detalle,
        'activo':           activo,
    }


def _nombre_usuario(user):
    if user is None:
        return '—'
    return user.get_full_name() or user.username


def _eventos_compras(producto, combinacion_pk):
    """
    Compra y Factura inicial dejan un LoteCompra con item_compra
    apuntando a un ItemCompra real. Se excluyen a propósito los lotes
    con item_compra=None (ajuste manual o fraccionamiento): esos ya
    quedan cubiertos por MovimientoStock en _eventos_ajustes, y
    contarlos aquí también los duplicaría en la línea de tiempo.
    """
    from compras.models import LoteCompra

    qs = (LoteCompra.objects
          .filter(producto=producto, item_compra__isnull=False)
          .select_related('item_compra__compra__creado_por', 'combinacion'))
    if combinacion_pk:
        qs = qs.filter(combinacion_id=combinacion_pk)

    eventos = []
    for lote in qs:
        compra = lote.item_compra.compra
        if compra is None:
            continue
        es_inicial = getattr(compra, 'es_carga_inicial', False)
        if es_inicial:
            origen_label = f'Factura inicial {compra.numero}'
            origen_url   = f"{reverse('compras:factura_inicial_historial')}?producto={producto.codigo}"
        else:
            origen_label = f'Compra {compra.numero}'
            origen_url   = reverse('compras:detalle_compra', kwargs={'pk': compra.pk})

        eventos.append(_evento(
            fecha_orden      = (lote.fecha_compra, lote.fecha_alta),
            fecha_display    = lote.fecha_compra,
            categoria        = 'factura_inicial' if es_inicial else 'compra',
            tipo_label       = 'Factura inicial' if es_inicial else 'Compra',
            es_entrada       = True,
            cantidad         = lote.cantidad_inicial,
            combinacion_desc = lote.combinacion.descripcion_legible() if lote.combinacion_id else '',
            origen_label     = origen_label,
            origen_url       = origen_url,
            usuario          = _nombre_usuario(compra.creado_por),
            detalle          = f'Lote {lote.codigo}' if lote.codigo else '',
            activo           = lote.activo,
        ))
    return eventos


def _eventos_ajustes(producto, combinacion_pk):
    """
    Solo ajuste manual (positivo/negativo) — el único caso que NO tiene
    ningún otro modelo propio detrás (por eso no hay origen_url: no hay
    a dónde llevar más que a este mismo historial). Merma y
    fraccionamiento se sacaron de acá — ver _eventos_mermas y
    _eventos_fraccionamientos, que ahora se leen de Perdida/
    Fraccionamiento directo (dan un pk real para poder linkear).
    """
    from productos.models import MovimientoStock, TipoMovimiento

    qs = (MovimientoStock.objects
          .filter(producto=producto, tipo__in=[TipoMovimiento.AJUSTE_POS, TipoMovimiento.AJUSTE_NEG])
          .select_related('usuario', 'combinacion'))
    if combinacion_pk:
        qs = qs.filter(combinacion_id=combinacion_pk)

    eventos = []
    for m in qs:
        fecha_local = timezone.localtime(m.fecha)
        eventos.append(_evento(
            fecha_orden      = (fecha_local.date(), m.fecha),
            fecha_display    = fecha_local,
            categoria        = m.tipo,
            tipo_label       = m.get_tipo_display(),
            es_entrada       = m.es_entrada,
            cantidad         = m.cantidad,
            combinacion_desc = m.combinacion.descripcion_legible() if m.combinacion_id else '',
            origen_label     = m.get_tipo_display(),
            origen_url       = '',
            usuario          = _nombre_usuario(m.usuario),
            detalle          = ' · '.join(x for x in (m.motivo, m.referencia) if x),
            activo           = True,
        ))
    return eventos


def _eventos_mermas(producto, combinacion_pk):
    """Merma / pérdida (rotura, extravío, vencimiento) — modelo Perdida."""
    from compras.models import Perdida

    qs = Perdida.objects.filter(producto=producto).select_related('registrado_por')
    if combinacion_pk:
        qs = qs.filter(combinacion_id=combinacion_pk)

    eventos = []
    for p in qs:
        detalle = p.get_motivo_display()
        if p.motivo_detalle:
            detalle += f' · {p.motivo_detalle}'
        if p.lote_codigo_snapshot:
            detalle += f' · Lote {p.lote_codigo_snapshot}'

        eventos.append(_evento(
            fecha_orden      = (p.fecha, p.fecha_alta),
            fecha_display    = p.fecha,
            categoria        = 'merma',
            tipo_label       = 'Merma / Pérdida',
            es_entrada       = False,
            cantidad         = p.cantidad,
            combinacion_desc = p.combinacion_desc_snapshot,
            origen_label     = 'Merma / Pérdida',
            origen_url       = f"{reverse('compras:inventario')}?perdida={p.pk}",
            usuario          = _nombre_usuario(p.registrado_por) if not p.automatica else 'Sistema (automático)',
            detalle          = detalle,
            activo           = True,
        ))
    return eventos


def _eventos_fraccionamientos(producto, combinacion_pk):
    """
    Fraccionamiento (armar un producto empaquetado a partir de otro a
    granel) — modelo Fraccionamiento. No soporta variantes todavía (ver
    fraccionar() en compras/models.py), así que si se está filtrando por
    una combinación puntual, no hay nada que mostrar acá.
    """
    if combinacion_pk:
        return []

    from compras.models import Fraccionamiento

    qs = (Fraccionamiento.objects
          .filter(Q(producto_origen=producto) | Q(producto_destino=producto))
          .select_related('creado_por'))

    eventos = []
    for f in qs:
        origen_url = f"{reverse('compras:inventario')}?fraccionamiento={f.pk}"
        if f.producto_origen_id == producto.id:
            eventos.append(_evento(
                fecha_orden      = (f.fecha, f.fecha_alta),
                fecha_display    = f.fecha,
                categoria        = 'fracc_s',
                tipo_label       = 'Fraccionamiento (consumido)',
                es_entrada       = False,
                cantidad         = f.cantidad_total_origen,
                combinacion_desc = '',
                origen_label     = 'Fraccionamiento (consumido)',
                origen_url       = origen_url,
                usuario          = _nombre_usuario(f.creado_por),
                detalle          = f'Armó {f.producto_destino_nombre_snapshot}',
                activo           = True,
            ))
        if f.producto_destino_id == producto.id:
            eventos.append(_evento(
                fecha_orden      = (f.fecha, f.fecha_alta),
                fecha_display    = f.fecha,
                categoria        = 'fracc_e',
                tipo_label       = 'Fraccionamiento (armado)',
                es_entrada       = True,
                cantidad         = f.cantidad_paquetes,
                combinacion_desc = '',
                origen_label     = 'Fraccionamiento (armado)',
                origen_url       = origen_url,
                usuario          = _nombre_usuario(f.creado_por),
                detalle          = f'Desde {f.producto_origen_nombre_snapshot}',
                activo           = True,
            ))
    return eventos


def _eventos_ventas(producto, combinacion_pk):
    """
    Una venta consume lote(s) reales (ConsumoLoteVenta.lote) salvo que
    se haya vendido "sin stock" (permitir_venta_sin_stock), en cuyo caso
    lote=None y el producto solo se puede resolver vía item_venta. Un
    componente de paquete sí tiene lote real, pero item_venta es el del
    paquete — por eso se filtra por cualquiera de los dos caminos.
    """
    from ventas.models import ConsumoLoteVenta, EstadoVenta

    filtro_producto = Q(item_venta__producto=producto) | Q(lote__producto=producto)
    qs = (ConsumoLoteVenta.objects
          .filter(filtro_producto)
          .select_related('item_venta__venta__confirmado_por', 'item_venta__combinacion',
                           'lote__combinacion')
          .distinct())
    if combinacion_pk:
        qs = qs.filter(Q(item_venta__combinacion_id=combinacion_pk) | Q(lote__combinacion_id=combinacion_pk))

    eventos = []
    for c in qs:
        venta   = c.item_venta.venta
        anulada = venta.estado == EstadoVenta.ANULADA
        if c.lote_id and c.lote.combinacion_id:
            combinacion = c.lote.combinacion
        else:
            combinacion = c.item_venta.combinacion

        eventos.append(_evento(
            fecha_orden      = (venta.fecha, c.fecha_alta),
            fecha_display    = venta.fecha,
            categoria        = 'venta',
            tipo_label       = 'Venta',
            es_entrada       = False,
            cantidad         = c.cantidad,
            combinacion_desc = combinacion.descripcion_legible() if combinacion else '',
            origen_label     = f'Venta {venta.numero}',
            origen_url       = reverse('ventas:detalle_venta', kwargs={'pk': venta.pk}),
            usuario          = _nombre_usuario(venta.confirmado_por),
            detalle          = 'sin stock' if c.lote_id is None else f'Lote {c.lote_codigo_snapshot}',
            activo           = not anulada,
        ))
    return eventos


def _eventos_devoluciones(producto, combinacion_pk):
    """
    Cada porción devuelta repone stock al lote de origen (o, si esa
    porción se vendió "sin stock", al total del producto directo). Si
    además se marcó como pérdida, la baja correspondiente ya aparece
    por separado en _eventos_ajustes (MovimientoStock MERMA) — son dos
    eventos reales (repuso y luego la dio de baja), se muestran los dos.
    """
    from ventas.models import DevolucionVentaConsumo

    filtro_producto = (Q(lote__producto=producto) |
                        Q(devolucion_item__item_venta__producto=producto))
    qs = (DevolucionVentaConsumo.objects
          .filter(filtro_producto)
          .select_related('devolucion_item__devolucion__venta', 'devolucion_item__devolucion__creado_por',
                           'devolucion_item__item_venta__combinacion', 'lote__combinacion')
          .distinct())
    if combinacion_pk:
        qs = qs.filter(Q(lote__combinacion_id=combinacion_pk) |
                        Q(devolucion_item__item_venta__combinacion_id=combinacion_pk))

    eventos = []
    for c in qs:
        dev = c.devolucion_item.devolucion
        if c.lote_id and c.lote.combinacion_id:
            combinacion = c.lote.combinacion
        elif c.devolucion_item.item_venta_id:
            combinacion = c.devolucion_item.item_venta.combinacion
        else:
            combinacion = None

        eventos.append(_evento(
            fecha_orden      = (dev.fecha, dev.fecha_alta),
            fecha_display    = dev.fecha,
            categoria        = 'devolucion',
            tipo_label       = 'Devolución',
            es_entrada       = True,
            cantidad         = c.cantidad,
            combinacion_desc = combinacion.descripcion_legible() if combinacion else '',
            origen_label     = f'Devolución {dev.numero} (venta {dev.venta.numero})',
            origen_url       = f"{reverse('ventas:historial_devoluciones')}?q={dev.numero}",
            usuario          = _nombre_usuario(dev.creado_por),
            detalle          = 'pasó a pérdida' if c.fue_perdida else '',
            activo           = True,
        ))
    return eventos


def _pasa_filtros(e, categoria, es_entrada, fecha_desde, fecha_hasta, q):
    if categoria and e['categoria'] != categoria:
        return False
    if es_entrada is not None and e['es_entrada'] != es_entrada:
        return False

    fecha_negocio = e['fecha_orden'][0]
    if fecha_desde and fecha_negocio < fecha_desde:
        return False
    if fecha_hasta and fecha_negocio > fecha_hasta:
        return False

    if q:
        haystack = ' '.join([
            e['origen_label'], e['detalle'], e['usuario'], e['combinacion_desc'], e['tipo_label'],
        ]).lower()
        if q.lower() not in haystack:
            return False

    return True


def construir_historial_stock(producto, combinacion_pk=None, categoria=None, es_entrada=None,
                               fecha_desde=None, fecha_hasta=None, q='', page=1, page_size=20):
    """
    Devuelve un dict con la línea de tiempo combinada (paginada, más
    reciente primero, con los filtros de categoría/entrada-salida/fecha/
    texto ya aplicados) y la conciliación stock_actual vs. stock
    reconstruido a partir de la línea de tiempo COMPLETA (sin esos
    filtros — ver nota del módulo).

    `fecha_desde`/`fecha_hasta` deben venir como `date` (o None); el
    parseo de query params es responsabilidad de la vista.
    """
    combinacion_pk = int(combinacion_pk) if combinacion_pk else None

    eventos = (
        _eventos_compras(producto, combinacion_pk)
        + _eventos_ajustes(producto, combinacion_pk)
        + _eventos_mermas(producto, combinacion_pk)
        + _eventos_fraccionamientos(producto, combinacion_pk)
        + _eventos_ventas(producto, combinacion_pk)
        + _eventos_devoluciones(producto, combinacion_pk)
    )
    eventos.sort(key=lambda e: e['fecha_orden'])

    stock_reconstruido = Decimal('0')
    for e in eventos:
        cantidad = Decimal(str(e['cantidad']))
        stock_reconstruido += cantidad if e['es_entrada'] else -cantidad

    if combinacion_pk:
        from productos.models import CombinacionVariante
        combinacion  = CombinacionVariante.objects.filter(pk=combinacion_pk, producto=producto).first()
        stock_actual = combinacion.stock_actual if combinacion else Decimal('0')
    else:
        stock_actual = producto.stock_actual

    eventos_filtrados = [
        e for e in eventos
        if _pasa_filtros(e, categoria, es_entrada, fecha_desde, fecha_hasta, q)
    ]
    eventos_filtrados.reverse()  # más reciente primero

    total       = len(eventos_filtrados)
    page_size   = max(1, page_size)
    num_paginas = max(1, -(-total // page_size))
    page        = max(1, min(page, num_paginas))
    inicio      = (page - 1) * page_size

    return {
        'eventos':            eventos_filtrados[inicio:inicio + page_size],
        'total':              total,
        'pagina':             page,
        'paginas':            num_paginas,
        'tiene_siguiente':    page < num_paginas,
        'tiene_anterior':     page > 1,
        'stock_actual':       stock_actual,
        'stock_reconstruido': stock_reconstruido,
        'diferencia':         (stock_actual or Decimal('0')) - stock_reconstruido,
    }
