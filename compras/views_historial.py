from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.db.models import Q

from .models import Compra, EstadoCompra
from core.permisos import chequear_permiso  # ← nuevo


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Historial de Compras
# ══════════════════════════════════════════════════════════════════

class HistorialComprasView(LoginRequiredMixin, TemplateView):
    """Renderiza la página del historial de compras."""
    template_name = 'compras/historial_compras.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['puede_ver'] = chequear_permiso(self.request.user, 'ver_compras')  # ← nuevo
        if not chequear_permiso(self.request.user, 'ver_compras'):             # ← nuevo
            ctx['sin_permiso'] = True                                          # ← nuevo
            return ctx                                                         # ← nuevo
        ctx['estados'] = EstadoCompra.choices
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listar compras con filtros
# ══════════════════════════════════════════════════════════════════

class ListarComprasAjax(LoginRequiredMixin, View):
    """
    GET con parámetros opcionales:
      ?q=CMP-00001       busca por número
      ?estado=confirmada
      ?fecha_desde=2025-01-01
      ?fecha_hasta=2025-12-31
      ?page=1
    """
    PAGE_SIZE = 20

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_compras'):            # ← nuevo
            return JsonResponse({'error': 'Sin permiso.'}, status=403)  # ← nuevo

        qs = Compra.objects.prefetch_related(
            'items__producto',
            'items__proveedor',
        ).order_by('-fecha', '-fecha_alta')

        # — Filtros —
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(numero__icontains=q) |
                Q(notas__icontains=q)
            )

        estado = request.GET.get('estado', '').strip()
        if estado:
            qs = qs.filter(estado=estado)

        fecha_desde = request.GET.get('fecha_desde', '').strip()
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)

        fecha_hasta = request.GET.get('fecha_hasta', '').strip()
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        # — Paginación simple —
        try:
            page = max(1, int(request.GET.get('page', 1)))
        except ValueError:
            page = 1

        total  = qs.count()
        offset = (page - 1) * self.PAGE_SIZE
        compras = qs[offset: offset + self.PAGE_SIZE]

        data = []
        for c in compras:
            items = []
            for item in c.items.all():
                items.append({
                    'producto_pk':     item.producto_id,
                    'producto_cod':    item.producto.codigo,
                    'producto_nombre': item.producto.nombre,
                    'proveedor_pk':    item.proveedor_id or '',
                    'proveedor':       item.proveedor.nombre if item.proveedor else '—',
                    'cantidad':        str(item.cantidad),
                    'costo_unitario':  str(item.costo_unitario),
                    'moneda':          item.moneda,
                    'descuento_pct':   str(item.descuento_pct),
                    'condicion_pago':  item.get_condicion_pago_display(),
                    'referencia':      item.referencia,
                    'subtotal':        str(item.subtotal),
                })

            data.append({
                'pk':           c.pk,
                'numero':       c.numero,
                'fecha':        c.fecha.strftime('%d/%m/%Y'),
                'estado':       c.estado,
                'estado_label': c.get_estado_display(),
                'total':        str(c.total),
                'notas':        c.notas,
                'creado_por':   c.creado_por.get_full_name() if c.creado_por else '—',
                'items':        items,
                'items_count':  len(items),
            })

        return JsonResponse({
            'results':   data,
            'total':     total,
            'page':      page,
            'page_size': self.PAGE_SIZE,
            'has_next':  (offset + self.PAGE_SIZE) < total,
            'has_prev':  page > 1,
        })