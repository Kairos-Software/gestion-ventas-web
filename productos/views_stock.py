import json
from decimal import Decimal, InvalidOperation
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone

from .models import Producto, MovimientoStock, TipoMovimiento, MOVIMIENTOS_ENTRADA, CombinacionVariante, cantidad_valida_para_unidad
from .services_historial import construir_historial_stock, CATEGORIAS_HISTORIAL
from core.permisos import chequear_permiso

TIPOS_AJUSTE = {
    TipoMovimiento.AJUSTE_POS,
    TipoMovimiento.AJUSTE_NEG,
}


def _combinaciones_activas(producto):
    """Lista (no serializada) de combinaciones activas de un producto. [] si no tiene variantes."""
    if not producto.gestiona_variantes:
        return []
    return [
        {
            'pk':                    c.pk,
            'descripcion':           c.descripcion_legible(),
            'descripcion_combinacion': c.descripcion_legible(),
            'codigo_barras':         c.codigo_barras or '',
            'stock_actual':          str(c.stock_actual),
        }
        for c in producto.combinaciones.all()
        if c.activo
    ]


def _serializar_combinaciones(producto):
    """
    Devuelve un string JSON con las combinaciones activas del producto,
    listo para inyectar en data-combinaciones del <tr>.
    Igual que hace BuscarProductoAjax en compras.
    Ejemplo: '[{"pk":1,"descripcion":"Color:Rojo | Talle:M","stock_actual":"3"}]'
    Si el producto no tiene variantes devuelve '[]'.
    """
    return json.dumps(_combinaciones_activas(producto), ensure_ascii=False)


class StockView(LoginRequiredMixin, TemplateView):
    template_name = 'productos/stock.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['puede_ajustar'] = chequear_permiso(self.request.user, 'ajustar_stock')

        if not chequear_permiso(self.request.user, 'ver_stock'):
            ctx['sin_permiso'] = True
            return ctx

        qs = Producto.objects.filter(
            gestiona_stock=True
        ).select_related('categoria').prefetch_related('combinaciones').order_by('nombre')

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) |
                Q(codigo__icontains=q) |
                Q(sku__icontains=q)
            )

        filtro_alerta = self.request.GET.get('alerta', '')
        if filtro_alerta == 'bajo':
            qs = qs.filter(stock_actual__lte=F('stock_minimo'), stock_actual__gt=0)
        elif filtro_alerta == 'ok':
            qs = qs.filter(stock_actual__gt=F('stock_minimo'))
        elif filtro_alerta == 'sin_stock':
            qs = qs.filter(stock_actual__lte=0)

        paginator = Paginator(qs, 25)
        page_obj  = paginator.get_page(self.request.GET.get('page', 1))

        # ── Adjuntar combinaciones serializadas a cada producto de la página ──
        # Se hace aquí en Python para evitar construir JSON con el sistema
        # de templates de Django (frágil con {% for %} + {% if %} anidados).
        for p in page_obj:
            p.combinaciones_json_str = _serializar_combinaciones(p)
            p.valor_total_venta = (p.stock_actual or 0) * (p.precio_venta or 0)
            # Sobre la caché ya prefetcheada (sin pegarle de nuevo a la DB) —
            # usado para el "+N más" cuando hay muchas combinaciones (ver stock.html).
            p.combinaciones_activas_count = sum(1 for c in p.combinaciones.all() if c.activo)

        todos = Producto.objects.filter(gestiona_stock=True)

        ctx.update({
            'productos':        page_obj,
            'total_productos':  todos.count(),
            'stock_bajo_count': todos.filter(stock_actual__lte=F('stock_minimo'), stock_actual__gt=0).count(),
            'sin_stock_count':  todos.filter(stock_actual__lte=0).count(),
            'tipos_ajuste':     [(t, TipoMovimiento(t).label) for t in TIPOS_AJUSTE],
            'tipos_entrada':    MOVIMIENTOS_ENTRADA,
            'q':                q,
            'filtro_alerta':    filtro_alerta,
        })
        return ctx


def _formatear_fecha(valor):
    """Un date se muestra tal cual; un datetime aware se pasa antes por hora local."""
    from datetime import datetime, date
    if isinstance(valor, datetime):
        return timezone.localtime(valor).strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, date):
        return valor.strftime('%d/%m/%Y')
    return str(valor)


def _parsear_fecha(valor):
    from datetime import datetime
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None


def _fmt_num(valor):
    """
    '23.000' -> '23', '1.500' -> '1.5'. Sin esto, un DecimalField(decimal_places=3)
    manda siempre las 3 decimales y "23.000" se lee como "23 mil" — el mismo
    recorte de ceros que ya hace `floatformat:"-3"` en los templates, pero
    para valores que salen por JSON en vez de por un template de Django.
    """
    s = format(Decimal(str(valor)), 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s or '0'


class HistorialStockView(LoginRequiredMixin, TemplateView):
    """
    Página propia del historial de un producto (antes era un modal
    dentro de Stock). Los datos se cargan por AJAX vía StockHistorialAjax
    — ver historial_stock.js.
    """
    template_name = 'productos/historial_stock.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_stock'):
            ctx['sin_permiso'] = True
            return ctx

        producto = get_object_or_404(Producto, pk=kwargs['pk'], gestiona_stock=True)
        ctx.update({
            'producto':       producto,
            'combinaciones':  _combinaciones_activas(producto),
            'categorias':     CATEGORIAS_HISTORIAL,
        })
        return ctx


class StockHistorialAjax(LoginRequiredMixin, View):
    """
    GET ?producto_pk=<pk>&combinacion_pk=&categoria=&es_entrada=&
        fecha_desde=&fecha_hasta=&q=&page=<n>
    — historial unificado de movimientos (compras, facturas iniciales,
    ajustes, mermas, fraccionamientos, ventas y devoluciones) +
    conciliación contra el stock real. Ver productos/services_historial.py.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_stock'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.GET.get('producto_pk')
        if not pk:
            return JsonResponse({'error': 'producto_pk requerido.'}, status=400)

        producto = get_object_or_404(Producto, pk=pk, gestiona_stock=True)

        combinacion_pk = request.GET.get('combinacion_pk') or None
        if combinacion_pk is not None:
            combinacion = CombinacionVariante.objects.filter(pk=combinacion_pk, producto=producto).first()
            if combinacion is None:
                return JsonResponse({'error': 'La combinación no pertenece a este producto.'}, status=400)

        categoria = request.GET.get('categoria') or None
        if categoria and categoria not in dict(CATEGORIAS_HISTORIAL):
            return JsonResponse({'error': 'Categoría inválida.'}, status=400)

        es_entrada_raw = request.GET.get('es_entrada') or ''
        es_entrada = {'entrada': True, 'salida': False}.get(es_entrada_raw)

        fecha_desde = _parsear_fecha(request.GET.get('fecha_desde'))
        fecha_hasta = _parsear_fecha(request.GET.get('fecha_hasta'))
        q = request.GET.get('q', '').strip()

        try:
            page = int(request.GET.get('page', 1))
        except (TypeError, ValueError):
            page = 1

        resultado = construir_historial_stock(
            producto, combinacion_pk=combinacion_pk, categoria=categoria, es_entrada=es_entrada,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, q=q, page=page,
        )

        return JsonResponse({
            'movimientos': [
                {
                    'tipo_display':    e['tipo_label'],
                    'es_entrada':      e['es_entrada'],
                    'cantidad':        _fmt_num(e['cantidad']),
                    'combinacion':     e['combinacion_desc'],
                    'origen_label':    e['origen_label'],
                    'origen_url':      e['origen_url'],
                    'usuario':         e['usuario'],
                    'detalle':         e['detalle'],
                    'activo':          e['activo'],
                    'fecha':           _formatear_fecha(e['fecha_display']),
                }
                for e in resultado['eventos']
            ],
            'total':              resultado['total'],
            'paginas':            resultado['paginas'],
            'pagina':             resultado['pagina'],
            'tiene_siguiente':    resultado['tiene_siguiente'],
            'tiene_anterior':     resultado['tiene_anterior'],
            'stock_actual':       _fmt_num(resultado['stock_actual']),
            'stock_reconstruido': _fmt_num(resultado['stock_reconstruido']),
            'diferencia':         _fmt_num(resultado['diferencia']),
            'combinaciones':      _combinaciones_activas(producto),
        })


class StockAjusteAjax(LoginRequiredMixin, View):
    """
    POST — registra un ajuste manual de stock.

    Soporta productos con y sin variantes:

    - Sin variantes: ajusta Producto.stock_actual vía MovimientoStock.save().
    - Con variantes: requiere combinacion_pk. Registra el MovimientoStock a nivel
      producto (auditoría), ajusta CombinacionVariante.stock_actual, y luego
      llama sincronizar_stock_desde_combinaciones() para que el total del
      producto quede consistente.

    Body JSON:
    {
        "producto_pk":     12,
        "tipo":            "ajuste_pos" | "ajuste_neg",
        "cantidad":        3,
        "motivo":          "Conteo físico mayo",   // opcional
        "combinacion_pk":  5,                       // requerido si gestiona_variantes
        "costo_unitario":  850.00                   // opcional, solo para ajuste_pos
    }

    `costo_unitario` (solo tiene sentido en un ajuste positivo): costo real
    de esa mercadería, para que el lote que se genera no quede en $0 — sin
    esto, una pérdida (rotura) registrada sobre stock cargado a mano sale
    valorizada en $0, y el costo promedio del producto se distorsiona hacia
    abajo. Si no se manda, se usa el "costo de referencia" del producto
    (`Producto.costo`) como default razonable. Además, este costo pasa a
    ser el costo ACTUAL del producto (pisa el "costo de referencia" viejo
    y recalcula el precio automático — mismo mecanismo que
    Producto.activar_costo_referencia()), así el precio de venta y la
    valorización de stock en Estadísticas reflejan lo que se acaba de
    cargar, no un costo desactualizado. NUNCA genera ningún movimiento de
    caja — esa plata ya se contabilizó aparte (deuda, préstamo, o ingreso
    inicial cargado a mano), cargar este costo acá de nuevo la duplicaría.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'ajustar_stock'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        producto_pk     = body.get('producto_pk')
        tipo            = body.get('tipo', '').strip()
        motivo          = body.get('motivo', '').strip()
        combinacion_pk  = body.get('combinacion_pk')  # None si el producto no maneja variantes

        if not producto_pk:
            return JsonResponse({'ok': False, 'error': 'Falta producto_pk.'}, status=400)

        producto = get_object_or_404(Producto, pk=producto_pk, gestiona_stock=True)

        if tipo not in TIPOS_AJUSTE:
            return JsonResponse({
                'ok': False,
                'error': 'Tipo no válido. Solo se permiten ajustes manuales desde esta pantalla.'
            }, status=400)

        try:
            cantidad = Decimal(str(body.get('cantidad')))
            if cantidad <= 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return JsonResponse({'ok': False, 'error': 'La cantidad debe ser un número positivo.'}, status=400)

        if not cantidad_valida_para_unidad(producto.unidad_medida, cantidad):
            return JsonResponse({
                'ok': False,
                'error': f'"{producto.nombre}" se maneja por {producto.get_unidad_medida_display()} '
                         f'— la cantidad tiene que ser un número entero.',
            }, status=400)

        costo_unitario_raw = body.get('costo_unitario')
        if costo_unitario_raw in (None, ''):
            costo_unitario = producto.costo or Decimal('0')
        else:
            try:
                costo_unitario = Decimal(str(costo_unitario_raw))
                if costo_unitario < 0:
                    raise ValueError
            except (TypeError, ValueError, InvalidOperation):
                return JsonResponse({'ok': False, 'error': 'Costo unitario inválido.'}, status=400)

        # ── Validar / resolver combinación ──────────────────────────────
        combinacion = None
        if producto.gestiona_variantes:
            if not combinacion_pk:
                return JsonResponse({
                    'ok':    False,
                    'error': 'Este producto tiene variantes. Seleccioná una combinación para ajustar.'
                }, status=400)
            combinacion = get_object_or_404(CombinacionVariante, pk=combinacion_pk, producto=producto)
        else:
            if combinacion_pk:
                return JsonResponse({
                    'ok':    False,
                    'error': 'Este producto no maneja variantes.'
                }, status=400)

        # ── Registrar movimiento y ajustar stock ──────────────────
        try:
            with transaction.atomic():
                mov = MovimientoStock(
                    producto=producto,
                    combinacion=combinacion,
                    tipo=tipo,
                    cantidad=cantidad,
                    motivo=motivo,
                    usuario=request.user,
                )
                mov.save()  # ajusta Producto.stock_actual internamente

                es_entrada = tipo in MOVIMIENTOS_ENTRADA

                if combinacion is not None:
                    # Ajustar la combinación específica y resincronizar el total
                    # (igual que hace _sumar_stock_item / _restar_stock_item en compras)
                    if es_entrada:
                        combinacion.stock_actual += cantidad
                    else:
                        combinacion.stock_actual -= cantidad
                    combinacion.save(update_fields=['stock_actual'])
                    producto.sincronizar_stock_desde_combinaciones()

                # ── Lote genérico para que el ajuste no rompa el FIFO ──
                # Sin esto, un ajuste positivo suma a Producto.stock_actual
                # pero no a ningún LoteCompra, y al vender el sistema busca
                # stock en lotes reales (no en stock_actual) — la venta se
                # cae aunque stock_actual "diga" que hay. Sin fecha de
                # vencimiento y sin item_compra (no pasó por Compra) — no
                # importa si el producto es perecedero o no, no hay esa
                # información para un ajuste manual. `costo_unitario` SÍ se
                # guarda real (ver arriba) para que una pérdida sobre este
                # lote no salga valorizada en $0. Este lote nunca genera
                # movimiento de caja: esa plata ya se contabilizó aparte
                # (deuda/préstamo/ingreso inicial).
                if es_entrada:
                    from compras.models import LoteCompra
                    LoteCompra.objects.create(
                        item_compra       = None,
                        producto          = producto,
                        combinacion       = combinacion,
                        cantidad_inicial  = cantidad,
                        cantidad_actual   = cantidad,
                        costo_unitario    = costo_unitario,
                        fecha_vencimiento = None,
                        fecha_compra      = timezone.localtime().date(),
                    )
                    # El costo cargado en este ajuste pasa a ser el costo
                    # "actual" del producto DE VERDAD (mismo mecanismo que
                    # activar_costo_referencia(): pisa incluso a una Compra
                    # real anterior, y recalcula el precio automático) — si
                    # no, el precio de venta y las estadísticas de stock
                    # seguían mirando el costo de referencia viejo, aunque
                    # acá se haya cargado uno distinto para esta partida.
                    producto.costo = costo_unitario
                    producto.costo_activado_en = timezone.now()
                    producto.save(update_fields=['costo', 'costo_activado_en'])
                    producto.actualizar_costo_y_precio()

        except ValueError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=400)

        producto.refresh_from_db()

        combinacion_stock = None
        if combinacion is not None:
            combinacion.refresh_from_db()
            combinacion_stock = str(combinacion.stock_actual)

        return JsonResponse({
            'ok':                  True,
            'stock_anterior':      str(mov.stock_anterior),
            'stock_posterior':     str(mov.stock_posterior),
            'stock_actual':        str(producto.stock_actual),
            'stock_bajo':          producto.stock_bajo,
            'es_entrada':          mov.es_entrada,
            'tipo_display':        mov.get_tipo_display(),
            'combinacion_pk':      combinacion.pk if combinacion else None,
            'combinacion_stock':   combinacion_stock,
        })