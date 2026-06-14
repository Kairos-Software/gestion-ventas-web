from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.db.models import Q

from .models import Venta, EstadoVenta, MedioPago
from core.permisos import chequear_permiso


class HistorialVentasView(LoginRequiredMixin, TemplateView):
    template_name = 'ventas/historial_ventas.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_ventas'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_ver']      = True
        ctx['puede_editar']   = chequear_permiso(self.request.user, 'editar_ventas')
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, 'eliminar_ventas')
        ctx['estados']        = EstadoVenta.choices
        ctx['medios_pago']    = MedioPago.choices
        return ctx


class ListarVentasAjax(LoginRequiredMixin, View):
    PAGE_SIZE = 20

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Venta.objects.filter(
            estado__in=[EstadoVenta.CONFIRMADA, EstadoVenta.ANULADA]
        ).select_related(
            'creado_por',
            'confirmado_por',
        ).prefetch_related(
            'items__producto',
            'items__cliente',
            'items__color',
            'documentos',
        ).order_by('-fecha', '-fecha_alta')

        # — Filtros —
        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(numero__icontains=q) | Q(notas__icontains=q))

        estado = request.GET.get('estado', '').strip()
        if estado:
            qs = qs.filter(estado=estado)

        medio_pago = request.GET.get('medio_pago', '').strip()
        if medio_pago:
            qs = qs.filter(medio_pago=medio_pago)

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

        total  = qs.count()
        offset = (page - 1) * self.PAGE_SIZE
        ventas = qs[offset: offset + self.PAGE_SIZE]

        puede_editar   = chequear_permiso(request.user, 'editar_ventas')
        puede_eliminar = chequear_permiso(request.user, 'eliminar_ventas')

        # Íconos SVG por medio de pago (inline, sin necesidad de fuente de iconos)
        MEDIO_PAGO_ICON = {
            'efectivo':      '💵',
            'transferencia': '🏦',
            'debito':        '💳',
            'credito':       '💳',
            'qr':            '📱',
        }

        data = []
        for v in ventas:
            items = []
            for item in v.items.all():
                color_hex = ''
                if item.color and hasattr(item.color, 'codigo_hex'):
                    color_hex = item.color.codigo_hex or ''

                tiene_color = bool(item.color_id or item.color_nombre)

                items.append({
                    'producto_pk':      item.producto_id,
                    'producto_cod':     item.producto_codigo or (item.producto.codigo if item.producto else ''),
                    'producto_nombre':  item.producto_nombre or (item.producto.nombre if item.producto else '(eliminado)'),
                    'producto_display': item.nombre_producto_display,
                    'color_pk':         item.color_id or '',
                    'color_nombre':     item.nombre_color_display,
                    'color_hex':        color_hex,
                    'tiene_color':      tiene_color,
                    'cliente_pk':       item.cliente_id or '',
                    'cliente':          item.nombre_cliente_display,
                    'cantidad':         str(item.cantidad),
                    'precio_unitario':  str(item.precio_unitario),
                    'moneda':           item.moneda,
                    'descuento_pct':    str(item.descuento_pct),
                    'condicion_pago':   item.get_condicion_pago_display(),
                    'referencia':       item.referencia,
                    'notas':            item.notas,
                    'subtotal':         str(item.subtotal),
                })

            documentos = []
            for doc in v.documentos.all():
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

            # — Usuarios —
            def _nombre_usuario(u):
                if not u:
                    return '—'
                return u.get_full_name() or u.username or '—'

            creado_por     = _nombre_usuario(v.creado_por)
            confirmado_por = _nombre_usuario(v.confirmado_por)

            # Si no hay confirmado_por pero hay creado_por, usamos creado_por
            # (ventas confirmadas antes de agregar el campo)
            if confirmado_por == '—' and creado_por != '—':
                confirmado_por = creado_por

            data.append({
                'pk':                      v.pk,
                'numero':                  v.numero,
                'fecha':                   v.fecha.strftime('%d/%m/%Y'),
                'fecha_iso':               v.fecha.strftime('%Y-%m-%d'),
                'estado':                  v.estado,
                'estado_label':            v.get_estado_display(),
                'total':                   str(v.total),
                'notas':                   v.notas,
                # — Medio de pago —
                'medio_pago':              v.medio_pago,
                'medio_pago_label':        v.get_medio_pago_display(),
                'medio_pago_icon':         MEDIO_PAGO_ICON.get(v.medio_pago, '💰'),
                # — Usuarios —
                'creado_por':              creado_por,
                'confirmado_por':          confirmado_por,
                # — Ítems y docs —
                'items':                   items,
                'items_count':             len(items),
                'documentos':              documentos,
                # — Permisos de acción —
                'puede_anular':            puede_editar   and v.estado == EstadoVenta.CONFIRMADA,
                'puede_editar':            puede_editar   and v.estado == EstadoVenta.ANULADA,
                'puede_eliminar':          puede_eliminar,
                'eliminar_revierte_stock': v.estado == EstadoVenta.CONFIRMADA,
            })

        return JsonResponse({
            'results':   data,
            'total':     total,
            'page':      page,
            'page_size': self.PAGE_SIZE,
            'has_next':  (offset + self.PAGE_SIZE) < total,
            'has_prev':  page > 1,
        })