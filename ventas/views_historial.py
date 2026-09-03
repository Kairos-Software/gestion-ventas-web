from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.db.models import Q

from .models import Venta, EstadoVenta, MedioPago, DevolucionVenta
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
        ctx['turnos']         = self._turnos_para_filtro()
        return ctx

    @staticmethod
    def _turnos_para_filtro(limite=180):
        """Turnos para el <select> del filtro — nº + rango horario legible.
        El filtro en sí lo resuelve ListarVentasAjax (?turno=<pk>), por
        fecha_alta dentro de la ventana del turno, igual que el botón
        'Ver ventas de este turno' del historial de caja."""
        from caja.models import TurnoCaja
        opciones = []
        for t in TurnoCaja.objects.order_by('-fecha_apertura')[:limite]:
            rango = t.fecha_apertura.strftime('%d/%m/%y %H:%M')
            if t.fecha_cierre:
                rango += t.fecha_cierre.strftime(' → %d/%m %H:%M')
            else:
                rango += ' → (abierto)'
            opciones.append({'pk': t.pk, 'label': f'#{t.numero} · {rango}'})
        return opciones


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
            'anulado_por',
            'editado_por',
        ).prefetch_related(
            'items__producto',
            'items__cliente',
            'items__combinacion',
            'items__consumos',
            'documentos',
            'pagos__cuenta',
            'pagos__tarjeta',
            'pagos__cuenta_por_cobrar',
            'pagos__cheques',
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

        # — Filtro por turno o día, usado por el botón "Ver ventas" del
        # historial de caja (turno/día). Se basa en fecha_alta (instante
        # real de creación), igual que TurnoCaja._ventas_en_turno() y
        # TurnoCaja.turno_que_contiene() — así una venta cae siempre en
        # un único turno/día, sin importar si más tarde se editó su
        # fecha contable.
        turno_pk = request.GET.get('turno', '').strip()
        if turno_pk:
            from caja.models import TurnoCaja
            turno = TurnoCaja.objects.filter(pk=turno_pk).first()
            if not turno:
                return JsonResponse({'error': 'El turno indicado no existe.'}, status=400)
            qs = qs.filter(fecha_alta__gte=turno.fecha_apertura)
            if turno.fecha_cierre:
                qs = qs.filter(fecha_alta__lte=turno.fecha_cierre)
        else:
            dia = request.GET.get('dia', '').strip()
            if dia:
                qs = qs.filter(fecha_alta__date=dia)

        try:
            page = max(1, int(request.GET.get('page', 1)))
        except ValueError:
            page = 1

        total  = qs.count()
        offset = (page - 1) * self.PAGE_SIZE
        ventas = qs[offset: offset + self.PAGE_SIZE]

        puede_editar   = chequear_permiso(request.user, 'editar_ventas')
        puede_eliminar = chequear_permiso(request.user, 'eliminar_ventas')

        def _nombre_usuario(u):
            if not u:
                return None
            return u.get_full_name() or u.username or None

        def _fmt_dt(dt):
            if not dt:
                return None
            return dt.strftime('%d/%m/%Y %H:%M')

        data = []
        for v in ventas:
            items = []
            for item in v.items.all():
                tiene_variante = bool(item.combinacion_id or item.combinacion_descripcion)

                # — Origen del stock: FIFO (más viejo) o lote(s) puntual(es) —
                # 'SIN STOCK' aparece cuando parte (o todo) se vendió sin
                # stock (ver ConfiguracionVentas.permitir_venta_sin_stock).
                lotes = item.lotes_utilizados
                lotes_reales = [l for l in lotes if l and l != 'SIN STOCK']
                vendio_sin_stock = 'SIN STOCK' in lotes
                if item.tipo_escaneo == 'lote_especifico' and lotes_reales:
                    origen_label = ' + '.join(lotes_reales)
                    if vendio_sin_stock:
                        origen_label += ' + sin stock'
                elif lotes_reales:
                    origen_label = f'FIFO ({", ".join(lotes_reales)})'
                    if vendio_sin_stock:
                        origen_label += ' + sin stock'
                elif vendio_sin_stock:
                    origen_label = 'Vendido sin stock'
                else:
                    origen_label = '—'

                items.append({
                    'producto_pk':      item.producto_id,
                    'producto_cod':     item.producto_codigo or (item.producto.codigo if item.producto else ''),
                    'producto_nombre':  item.producto_nombre or (item.producto.nombre if item.producto else '(eliminado)'),
                    'producto_display': item.nombre_producto_display,
                    'combinacion_pk':      item.combinacion_id or '',
                    'combinacion_nombre':  item.nombre_combinacion_display,
                    'tiene_variante':      tiene_variante,
                    'cliente_pk':       item.cliente_id or '',
                    'cliente':          item.nombre_cliente_display,
                    'cantidad':         str(item.cantidad),
                    'precio_unitario':  str(item.precio_unitario),
                    'moneda':           item.moneda,
                    'descuento_pct':    str(item.descuento_pct),
                    'lista_descuento_nombre': item.lista_descuento_nombre,
                    'oferta_aplicada_nombre': item.oferta_aplicada_nombre,
                    'condicion_pago':   item.get_condicion_pago_display(),
                    'referencia':       item.referencia,
                    'notas':            item.notas,
                    'subtotal':         str(item.subtotal),
                    'origen_label':     origen_label,
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

            # — Auditoría —
            creado_por     = _nombre_usuario(v.creado_por)
            confirmado_por = _nombre_usuario(v.confirmado_por)
            anulado_por    = _nombre_usuario(v.anulado_por)
            editado_por    = _nombre_usuario(v.editado_por)

            # Fallback: si no hay confirmado_por usar creado_por (ventas viejas)
            if not confirmado_por and creado_por:
                confirmado_por = creado_por

            # — Pagos múltiples — con el detalle real de cada línea
            # (antes solo mostraba medio/monto/cuenta, perdiendo tarjeta,
            # recargo, plan de cuotas, y el vínculo con la cuenta por
            # cobrar/cheque que generó, si los hay).
            pagos = []
            for p in v.pagos.all():
                linea = {
                    'medio':         p.medio,
                    'medio_label':   p.get_medio_display(),
                    'monto':         str(p.monto),
                    'monto_base':    str(p.monto_base),
                    'cuenta':        p.cuenta.nombre if p.cuenta_id else None,
                    'tarjeta':       p.tarjeta.nombre if p.tarjeta_id else None,
                    'cotizacion':    str(p.cotizacion) if p.cotizacion else None,
                    'recargo_pct':   str(p.recargo_pct),
                    'recargo_monto': str(p.recargo_monto),
                    'redondeo_monto': str(p.redondeo_monto),
                    'excedente_label': p.etiqueta_excedente,
                    'cantidad_pagos': p.cantidad_pagos,
                    'nombre_plan':   p.nombre_plan,
                    'etiqueta_plan': p.etiqueta_plan if p.cantidad_pagos > 1 or p.nombre_plan else None,
                }
                cxc = getattr(p, 'cuenta_por_cobrar', None)
                if cxc:
                    linea['cuenta_por_cobrar'] = {
                        'pk':               cxc.pk,
                        'estado':           cxc.estado,
                        'estado_label':     cxc.get_estado_display(),
                        'modo_cuotas':      cxc.modo_cuotas,
                        'cantidad_cuotas':  cxc.cantidad_cuotas,
                        'saldo_pendiente':  str(cxc.saldo_pendiente),
                    }
                cheques = list(p.cheques.all())
                if cheques:
                    linea['cheques'] = [
                        {
                            'pk':             ch.pk,
                            'numero_cheque':  ch.numero_cheque,
                            'estado':         ch.estado,
                            'estado_label':   ch.get_estado_display(),
                            'fecha_cobro':    ch.fecha_cobro.strftime('%d/%m/%Y'),
                        }
                        for ch in cheques
                    ]
                pagos.append(linea)

            # El total de la venta (v.total) es el precio de lista, sin
            # recargo — correcto para IVA/ARCA, pero como "Total" del
            # historial confundía (mostraba menos de lo que el cliente
            # pagó de verdad). total_cobrado es lo que realmente entró:
            # precio + recargos de todas las líneas de pago.
            total_recargos = sum((p.recargo_monto for p in v.pagos.all()), Decimal('0'))
            total_redondeos = sum((p.redondeo_monto for p in v.pagos.all()), Decimal('0'))
            total_cobrado = v.total + total_recargos + total_redondeos

            data.append({
                'pk':                      v.pk,
                'numero':                  v.numero,
                'fecha':                   v.fecha.strftime('%d/%m/%Y'),
                'fecha_iso':               v.fecha.strftime('%Y-%m-%d'),
                'estado':                  v.estado,
                'estado_label':            v.get_estado_display(),
                'total':                   str(v.total),
                'total_recargos':          str(total_recargos),
                'total_redondeos':         str(total_redondeos),
                'total_cobrado':           str(total_cobrado),
                'descuento_global_pct':    str(v.descuento_global_pct),
                'oferta_global_nombre':    v.oferta_global_nombre,
                'notas':                   v.notas,
                'cliente_display':         v.cliente_display,
                # — Medio de pago —
                'medio_pago':              v.medio_pago,
                'medio_pago_label':        v.get_medio_pago_display(),
                'pagos':                   pagos,
                # — Auditoría —
                'creado_por':              creado_por or '—',
                'confirmado_por':          confirmado_por or '—',
                'fecha_confirmacion':      _fmt_dt(v.fecha_confirmacion),
                'anulado_por':             anulado_por,
                'fecha_anulacion':         _fmt_dt(v.fecha_anulacion),
                'editado_por':             editado_por,
                'fecha_edicion':           _fmt_dt(v.fecha_edicion),
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


class HistorialDevolucionesView(LoginRequiredMixin, TemplateView):
    """Lista centralizada de todas las devoluciones (de cualquier venta) —
    la venta individual solo muestra un resumen de las suyas, ver
    detalle_venta.html; acá es donde se buscan/repasan todas juntas."""
    template_name = 'ventas/historial_devoluciones.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_ventas'):
            ctx['sin_permiso'] = True
        return ctx


class ListarDevolucionesAjax(LoginRequiredMixin, View):
    PAGE_SIZE = 20

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = DevolucionVenta.objects.select_related(
            'venta', 'cuenta', 'creado_por',
        ).prefetch_related('items').order_by('-fecha_alta')

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(numero__icontains=q) | Q(descripcion__icontains=q) | Q(venta__numero__icontains=q)
            )

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

        total = qs.count()
        offset = (page - 1) * self.PAGE_SIZE
        devoluciones = qs[offset: offset + self.PAGE_SIZE]

        def _nombre_usuario(u):
            if not u:
                return None
            return u.get_full_name() or u.username or None

        data = []
        for dev in devoluciones:
            items = [
                {
                    'producto_nombre': it.producto_nombre_snapshot,
                    'combinacion_desc': it.combinacion_desc_snapshot,
                    'cantidad':   str(it.cantidad),
                    'es_perdida': it.es_perdida,
                }
                for it in dev.items.all()
            ]
            data.append({
                'pk':          dev.pk,
                'numero':      dev.numero,
                'fecha':       dev.fecha.strftime('%d/%m/%Y'),
                'descripcion': dev.descripcion,
                'venta_pk':     dev.venta_id,
                'venta_numero': dev.venta.numero,
                'monto':       str(dev.monto),
                'cuenta':      dev.cuenta.nombre if dev.cuenta else '',
                'moneda':      dev.cuenta.moneda if dev.cuenta else '',
                'items':       items,
                'tiene_perdida': any(it['es_perdida'] for it in items),
                'creado_por':  _nombre_usuario(dev.creado_por),
            })

        return JsonResponse({
            'results':   data,
            'total':     total,
            'page':      page,
            'page_size': self.PAGE_SIZE,
            'has_next':  (offset + self.PAGE_SIZE) < total,
            'has_prev':  page > 1,
        })