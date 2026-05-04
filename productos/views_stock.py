import json
from decimal import Decimal, InvalidOperation
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, F

from .models import Producto, MovimientoStock, TipoMovimiento, MOVIMIENTOS_ENTRADA
from core.permisos import chequear_permiso  # ← único import nuevo

TIPOS_AJUSTE = {
    TipoMovimiento.AJUSTE_POS,
    TipoMovimiento.AJUSTE_NEG,
}


class StockView(LoginRequiredMixin, TemplateView):
    template_name = 'productos/stock.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # ── Permisos para el template ─────────────────────────────
        ctx['puede_ajustar'] = chequear_permiso(self.request.user, 'ajustar_stock')

        if not chequear_permiso(self.request.user, 'ver_stock'):
            ctx['sin_permiso'] = True
            return ctx

        qs = Producto.objects.filter(
            gestiona_stock=True
        ).select_related('categoria').order_by('nombre')

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
        productos = paginator.get_page(self.request.GET.get('page', 1))

        todos = Producto.objects.filter(gestiona_stock=True)

        ctx.update({
            'productos':        productos,
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
    """POST — registra un ajuste manual de stock."""

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

        try:
            mov = MovimientoStock(
                producto=producto,
                tipo=tipo,
                cantidad=cantidad,
                motivo=motivo,
                usuario=request.user,
            )
            mov.save()
        except ValueError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=400)

        producto.refresh_from_db()

        return JsonResponse({
            'ok':              True,
            'stock_anterior':  str(mov.stock_anterior),
            'stock_posterior': str(mov.stock_posterior),
            'stock_actual':    str(producto.stock_actual),
            'stock_bajo':      producto.stock_bajo,
            'es_entrada':      mov.es_entrada,
            'tipo_display':    mov.get_tipo_display(),
        })