from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.db.models import Q

from .models import Compra, EstadoCompra
from core.permisos import chequear_permiso


class HistorialComprasView(LoginRequiredMixin, TemplateView):
    template_name = 'compras/historial_compras.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_compras'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_ver']      = True
        ctx['puede_editar']   = chequear_permiso(self.request.user, 'editar_compras')
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, 'eliminar_compras')
        ctx['estados']        = EstadoCompra.choices
        return ctx


class ListarComprasAjax(LoginRequiredMixin, View):
    PAGE_SIZE = 20

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Compra.objects.filter(
            estado__in=[EstadoCompra.CONFIRMADA, EstadoCompra.ANULADA]
        ).prefetch_related(
            'items__producto',
            'items__proveedor',
            'items__color',
            'documentos',
        ).order_by('-fecha', '-fecha_alta')

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(numero__icontains=q) | Q(notas__icontains=q))

        estado = request.GET.get('estado', '').strip()
        if estado:
            qs = qs.filter(estado=estado)

        fecha_desde = request.GET.get('fecha_desde', '').strip()
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)

        fecha_hasta = request.GET.get('fecha_hasta', '').strip()
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        try:
            page = max(1, int(request.GET.get('page', 1)))
        except ValueError:
            page = 1

        total   = qs.count()
        offset  = (page - 1) * self.PAGE_SIZE
        compras = qs[offset: offset + self.PAGE_SIZE]

        puede_editar   = chequear_permiso(request.user, 'editar_compras')
        puede_eliminar = chequear_permiso(request.user, 'eliminar_compras')

        data = []
        for c in compras:
            items = []
            for item in c.items.all():
                # color_hex desde el objeto color (no en snapshot, pero útil para swatches)
                color_hex = ''
                if item.color and hasattr(item.color, 'codigo_hex'):
                    color_hex = item.color.codigo_hex or ''

                tiene_color = bool(item.color_id or item.color_nombre)

                items.append({
                    'producto_pk':      item.producto_id,
                    'producto_cod':     item.producto_codigo or (item.producto.codigo if item.producto else ''),
                    'producto_nombre':  item.producto_nombre or (item.producto.nombre if item.producto else '(eliminado)'),
                    'producto_display': item.nombre_producto_display,
                    # ── color ──
                    'color_pk':         item.color_id or '',
                    'color_nombre':     item.nombre_color_display,
                    'color_hex':        color_hex,
                    'tiene_color':      tiene_color,
                    # ──────────
                    'proveedor_pk':     item.proveedor_id or '',
                    'proveedor':        item.nombre_proveedor_display,
                    'cantidad':         str(item.cantidad),
                    'costo_unitario':   str(item.costo_unitario),
                    'moneda':           item.moneda,
                    'descuento_pct':    str(item.descuento_pct),
                    'condicion_pago':   item.get_condicion_pago_display(),
                    'referencia':       item.referencia,
                    'notas':            item.notas,
                    'subtotal':         str(item.subtotal),
                })

            documentos = []
            for doc in c.documentos.all():
                documentos.append({
                    'pk':          doc.pk,
                    'tipo':        doc.tipo,
                    'tipo_label':  doc.get_tipo_display(),
                    'descripcion': doc.descripcion,
                    'nombre':      doc.nombre_archivo,
                    'url':         doc.archivo.url if doc.archivo else '',
                    'es_imagen':   doc.es_imagen,
                    'es_pdf':      doc.es_pdf,
                    'subido_el':   doc.subido_el.strftime('%d/%m/%Y %H:%M'),
                })

            data.append({
                'pk':                     c.pk,
                'numero':                 c.numero,
                'fecha':                  c.fecha.strftime('%d/%m/%Y'),
                'fecha_iso':              c.fecha.strftime('%Y-%m-%d'),
                'estado':                 c.estado,
                'estado_label':           c.get_estado_display(),
                'total':                  str(c.total),
                'notas':                  c.notas,
                'creado_por':             c.creado_por.get_full_name() if c.creado_por else '—',
                'items':                  items,
                'items_count':            len(items),
                'documentos':             documentos,
                'puede_anular':           puede_editar   and c.estado == EstadoCompra.CONFIRMADA,
                'puede_editar':           puede_editar   and c.estado == EstadoCompra.ANULADA,
                'puede_eliminar':         puede_eliminar,
                'eliminar_revierte_stock': c.estado == EstadoCompra.CONFIRMADA,
            })

        return JsonResponse({
            'results':   data,
            'total':     total,
            'page':      page,
            'page_size': self.PAGE_SIZE,
            'has_next':  (offset + self.PAGE_SIZE) < total,
            'has_prev':  page > 1,
        })