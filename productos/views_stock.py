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

from .models import Producto, MovimientoStock, TipoMovimiento, MOVIMIENTOS_ENTRADA
from productos.models import ProductoColor
from core.permisos import chequear_permiso

TIPOS_AJUSTE = {
    TipoMovimiento.AJUSTE_POS,
    TipoMovimiento.AJUSTE_NEG,
}


def _serializar_colores(producto):
    """
    Devuelve un string JSON con los colores activos del producto,
    listo para inyectar en data-colores del <tr>.
    Igual que hace BuscarProductoAjax en compras.
    Ejemplo: '[{"pk":1,"nombre":"Rojo","codigo_hex":"#e00","stock_actual":"3"}]'
    Si el producto no tiene variantes de color devuelve '[]'.
    """
    if not producto.tiene_variantes_color:
        return '[]'
    colores = [
        {
            'pk':          c.pk,
            'nombre':      c.nombre,
            'codigo_hex':  c.codigo_hex or '',
            'stock_actual': str(c.stock_actual),
        }
        for c in producto.colores.all()   # ya viene del prefetch_related
        if c.activo
    ]
    return json.dumps(colores, ensure_ascii=False)


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
        ).select_related('categoria').prefetch_related('colores').order_by('nombre')

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

        # ── Adjuntar colores serializados a cada producto de la página ──
        # Se hace aquí en Python para evitar construir JSON con el sistema
        # de templates de Django (frágil con {% for %} + {% if %} anidados).
        for p in page_obj:
            p.colores_json_str = _serializar_colores(p)

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

    Soporta productos con y sin variantes de color:

    - Sin colores: ajusta Producto.stock_actual vía MovimientoStock.save().
    - Con colores: requiere color_pk. Registra el MovimientoStock a nivel
      producto (auditoría), ajusta ProductoColor.stock_actual, y luego
      llama sincronizar_stock_desde_colores() para que el total del
      producto quede consistente.

    Body JSON:
    {
        "producto_pk": 12,
        "tipo":        "ajuste_pos" | "ajuste_neg",
        "cantidad":    3,
        "motivo":      "Conteo físico mayo",   // opcional
        "color_pk":    5                        // requerido si tiene_variantes_color
    }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'ajustar_stock'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        producto_pk = body.get('producto_pk')
        tipo        = body.get('tipo', '').strip()
        motivo      = body.get('motivo', '').strip()
        color_pk    = body.get('color_pk')  # None si el producto no maneja colores

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

        # ── Validar / resolver color ──────────────────────────────
        color = None
        if producto.tiene_variantes_color:
            if not color_pk:
                return JsonResponse({
                    'ok':    False,
                    'error': 'Este producto tiene variantes de color. Seleccioná un color para ajustar.'
                }, status=400)
            color = get_object_or_404(ProductoColor, pk=color_pk, producto=producto)
        else:
            if color_pk:
                return JsonResponse({
                    'ok':    False,
                    'error': 'Este producto no maneja variantes de color.'
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

                if color is not None:
                    # Ajustar el color específico y resincronizar el total
                    # (igual que hace _sumar_stock_item / _restar_stock_item en compras)
                    es_entrada = tipo in MOVIMIENTOS_ENTRADA
                    if es_entrada:
                        color.stock_actual += cantidad
                    else:
                        color.stock_actual -= cantidad
                    color.save(update_fields=['stock_actual'])
                    producto.sincronizar_stock_desde_colores()

        except ValueError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=400)

        producto.refresh_from_db()

        color_stock = None
        if color is not None:
            color.refresh_from_db()
            color_stock = str(color.stock_actual)

        return JsonResponse({
            'ok':              True,
            'stock_anterior':  str(mov.stock_anterior),
            'stock_posterior': str(mov.stock_posterior),
            'stock_actual':    str(producto.stock_actual),
            'stock_bajo':      producto.stock_bajo,
            'es_entrada':      mov.es_entrada,
            'tipo_display':    mov.get_tipo_display(),
            'color_pk':        color.pk if color else None,
            'color_stock':     color_stock,
        })