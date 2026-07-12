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

from .models import Producto, MovimientoStock, TipoMovimiento, MOVIMIENTOS_ENTRADA, CombinacionVariante
from core.permisos import chequear_permiso

TIPOS_AJUSTE = {
    TipoMovimiento.AJUSTE_POS,
    TipoMovimiento.AJUSTE_NEG,
}


def _serializar_combinaciones(producto):
    """
    Devuelve un string JSON con las combinaciones activas del producto,
    listo para inyectar en data-combinaciones del <tr>.
    Igual que hace BuscarProductoAjax en compras.
    Ejemplo: '[{"pk":1,"descripcion":"Color:Rojo | Talle:M","stock_actual":"3"}]'
    Si el producto no tiene variantes devuelve '[]'.
    """
    if not producto.gestiona_variantes:
        return '[]'
    combinaciones = [
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
    return json.dumps(combinaciones, ensure_ascii=False)


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


class StockHistorialAjax(LoginRequiredMixin, View):
    """GET ?producto_pk=<pk>&page=<n> — historial paginado de movimientos."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_stock'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.GET.get('producto_pk')
        if not pk:
            return JsonResponse({'error': 'producto_pk requerido.'}, status=400)

        producto = get_object_or_404(Producto, pk=pk, gestiona_stock=True)
        qs = MovimientoStock.objects.filter(
            producto=producto
        ).select_related('usuario').order_by('-fecha')

        paginator = Paginator(qs, 20)
        pag       = paginator.get_page(request.GET.get('page', 1))

        return JsonResponse({
            'movimientos': [
                {
                    'pk':              m.pk,
                    'tipo_display':    m.get_tipo_display(),
                    'es_entrada':      m.es_entrada,
                    'cantidad':        str(m.cantidad),
                    'stock_anterior':  str(m.stock_anterior),
                    'stock_posterior': str(m.stock_posterior),
                    'motivo':          m.motivo,
                    'referencia':      m.referencia,
                    'usuario':         (m.usuario.get_full_name() or m.usuario.username) if m.usuario else '—',
                    'fecha':           m.fecha.strftime('%d/%m/%Y %H:%M'),
                }
                for m in pag
            ],
            'total':           paginator.count,
            'paginas':         paginator.num_pages,
            'pagina':          pag.number,
            'tiene_siguiente': pag.has_next(),
            'tiene_anterior':  pag.has_previous(),
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
        "combinacion_pk":  5                        // requerido si gestiona_variantes
    }
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
                # cae aunque stock_actual "diga" que hay. Se crea sin costo,
                # sin fecha de vencimiento y sin item_compra (no pasó por
                # Compra) — no importa si el producto es perecedero o no,
                # no hay esa información para un ajuste manual.
                if es_entrada:
                    from compras.models import LoteCompra
                    LoteCompra.objects.create(
                        item_compra       = None,
                        producto          = producto,
                        combinacion       = combinacion,
                        cantidad_inicial  = int(cantidad),
                        cantidad_actual   = int(cantidad),
                        costo_unitario    = Decimal('0'),
                        fecha_vencimiento = None,
                        fecha_compra      = timezone.now().date(),
                    )

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