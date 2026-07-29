import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.permisos import chequear_permiso
from productos.models import AplicacionOferta, BaseCalculoUmbral, TipoOferta, ofertas_vigentes_hoy
from ventas.models import EstadoVenta, ItemVenta, Venta

from .models import EstadoPedido, ItemPedido, Pedido
from .utils import wa_link_ar
from .views import _disponible_compra, _info_oferta, _productos_publicados_base

MAX_ITEMS_POR_PEDIDO = 40


def _resolver_oferta_global(ofertas, items_a_crear):
    """
    De las ofertas vigentes tipo=UMBRAL con aplicación AUTOMÁTICA, la que
    más descuento dé sobre este pedido (o None). Solo se consideran las
    automáticas porque el visitante del catálogo no tiene forma de elegir
    una manual — esas quedan para que el vendedor las aplique a mano
    desde Nueva Venta. Mismo criterio que _resolverOfertaGlobal en
    ventas/nueva_venta.js, para que el monto no cambie al convertir el
    pedido en venta.
    """
    total_bruto = sum((it['producto'].precio_venta * it['cantidad'] for it in items_a_crear), start=Decimal('0'))
    total_neto = sum((it['precio_unitario'] * it['cantidad'] for it in items_a_crear), start=Decimal('0'))

    mejor, mejor_pct = None, Decimal('-1')
    for oferta in ofertas:
        if oferta.tipo != TipoOferta.UMBRAL or oferta.aplicacion != AplicacionOferta.AUTOMATICA:
            continue
        monto = total_bruto if oferta.base_calculo == BaseCalculoUmbral.BRUTO else total_neto
        pct = oferta.descuento_para_total(monto)
        if pct > mejor_pct:
            mejor, mejor_pct = oferta, pct
    return (mejor, mejor_pct) if mejor and mejor_pct > 0 else (None, Decimal('0'))


# ══════════════════════════════════════════════════════════════════
#  PÚBLICO — el visitante del catálogo confirma su pedido
# ══════════════════════════════════════════════════════════════════

class CrearPedidoAjax(View):
    """
    POST público (sin login — lo llama el carrito del catálogo). Recibe
    el carrito armado en el navegador y lo convierte en un Pedido real:
    - Nunca confía en el precio que manda el cliente — lo recalcula acá
      con el precio/oferta vigente en este momento.
    - Si algún producto ya no está disponible (se agotó, se despublicó),
      esa línea se descarta en silencio en vez de romper todo el pedido.
    """

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'JSON inválido.'}, status=400)

        telefono = str(body.get('contacto_telefono', '')).strip()[:40]
        if not telefono:
            return JsonResponse({'ok': False, 'error': 'Dejanos tu WhatsApp para poder coordinar el pedido.'}, status=400)

        nombre = str(body.get('contacto_nombre', '')).strip()[:150]
        notas = str(body.get('notas', '')).strip()[:1000]

        items_raw = body.get('items', [])
        if not isinstance(items_raw, list) or not items_raw:
            return JsonResponse({'ok': False, 'error': 'El carrito está vacío.'}, status=400)
        items_raw = items_raw[:MAX_ITEMS_POR_PEDIDO]

        ofertas = ofertas_vigentes_hoy()
        productos_disponibles = _productos_publicados_base()

        items_a_crear = []
        for item in items_raw:
            try:
                producto_id = int(item.get('producto_id'))
                cantidad = Decimal(str(item.get('cantidad', 1)))
            except (TypeError, ValueError, InvalidOperation):
                continue
            # El catálogo público solo vende por unidades enteras, sin
            # importar la unidad de medida del producto (kg, litros, etc.
            # se coordinan puntualmente por WhatsApp, no acá). El carrito
            # nunca manda fracciones, pero esto igual se valida acá por si
            # alguien le pega directo a la API salteando la pantalla.
            if cantidad <= 0 or cantidad != cantidad.to_integral_value():
                continue

            producto = productos_disponibles.filter(pk=producto_id).first()
            if not producto or not _disponible_compra(producto):
                continue

            oferta_info = _info_oferta(producto, ofertas, cantidad=cantidad)
            precio = oferta_info['precio_final'] if oferta_info else producto.precio_venta
            if precio is None:
                continue

            items_a_crear.append({'producto': producto, 'cantidad': cantidad, 'precio_unitario': precio})

        if not items_a_crear:
            return JsonResponse(
                {'ok': False, 'error': 'Ninguno de los productos del carrito está disponible ahora mismo.'},
                status=400,
            )

        oferta_global, pct_global = _resolver_oferta_global(ofertas, items_a_crear)

        with transaction.atomic():
            pedido = Pedido.objects.create(
                contacto_nombre=nombre, contacto_telefono=telefono, notas=notas,
                descuento_global_pct=pct_global,
                oferta_global_nombre=oferta_global.nombre if oferta_global else '',
            )
            for it in items_a_crear:
                ItemPedido.objects.create(
                    pedido=pedido, producto=it['producto'],
                    cantidad=it['cantidad'], precio_unitario=it['precio_unitario'],
                )

        return JsonResponse({'ok': True, 'pedido_pk': pedido.pk})


# ══════════════════════════════════════════════════════════════════
#  INTERNO — campanita de notificaciones (ver core/base.html)
# ══════════════════════════════════════════════════════════════════

def _serializar_pedido(p):
    return {
        'pk': p.pk,
        'contacto_nombre': p.contacto_nombre,
        'contacto_telefono': p.contacto_telefono,
        'notas': p.notas,
        'estado': p.estado,
        'leido': p.leido,
        'subtotal': str(p.subtotal),
        'descuento_global_pct': str(p.descuento_global_pct),
        'oferta_global_nombre': p.oferta_global_nombre,
        'total': str(p.total),
        'cantidad_items': p.items.count(),
        'fecha_alta': p.fecha_alta.isoformat(),
        'venta_pk': p.venta_id,
        'wa_link': wa_link_ar(p.contacto_telefono),
    }


class PedidosListaAjax(LoginRequiredMixin, View):
    """
    GET → últimos pedidos (para la campanita). Abrir la lista marca como
    leídos los que en ese momento estaban pendientes de leer — mismo
    criterio que Instagram/Facebook: no hace falta tocar cada uno.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_pedidos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pedidos = list(Pedido.objects.prefetch_related('items')[:20])
        no_leidos_ids = [p.pk for p in pedidos if not p.leido]
        if no_leidos_ids:
            Pedido.objects.filter(pk__in=no_leidos_ids).update(leido=True)
            for p in pedidos:
                if p.pk in no_leidos_ids:
                    p.leido = True

        return JsonResponse({
            'resultados': [_serializar_pedido(p) for p in pedidos],
            'no_leidos': len(no_leidos_ids),
        })


class PedidosNoLeidosAjax(LoginRequiredMixin, View):
    """GET liviano → solo el contador, para pintar el badge sin marcar nada como leído."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_pedidos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        return JsonResponse({'no_leidos': Pedido.objects.filter(leido=False).count()})


class PedidoVenderAjax(LoginRequiredMixin, View):
    """
    POST → convierte el pedido en un borrador de Venta (o reusa el que
    ya existía) y devuelve la URL de Nueva Venta con ese borrador
    cargado, lista para confirmar — mismo mecanismo que "Editar carrito"
    en el historial de ventas (?editar=<pk>).
    """

    def post(self, request, pk):
        if not chequear_permiso(request.user, 'ver_pedidos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pedido = get_object_or_404(Pedido, pk=pk)

        if pedido.venta_id and pedido.venta.estado == EstadoVenta.BORRADOR:
            venta = pedido.venta
        else:
            with transaction.atomic():
                venta = Venta.objects.create(
                    fecha=timezone.now().date(), creado_por=request.user,
                    descuento_global_pct=pedido.descuento_global_pct,
                    oferta_global_nombre=pedido.oferta_global_nombre,
                )
                for item in pedido.items.select_related('producto').all():
                    if not item.producto_id:
                        continue  # el producto se borró después del pedido — no hay nada que cargar
                    ItemVenta.objects.create(
                        venta=venta, producto=item.producto,
                        cantidad=item.cantidad, precio_unitario=item.precio_unitario,
                    )
                pedido.venta = venta
                pedido.estado = EstadoPedido.VENDIDO
                pedido.leido = True
                pedido.save(update_fields=['venta', 'estado', 'leido'])

        url = reverse('ventas:nueva_venta') + f'?editar={venta.pk}'
        return JsonResponse({'ok': True, 'redirect': url})


# ══════════════════════════════════════════════════════════════════
#  INTERNO — historial de pedidos (ver todos, descartar, eliminar)
# ══════════════════════════════════════════════════════════════════

class PedidosHistorialView(LoginRequiredMixin, TemplateView):
    """
    Pantalla completa con TODOS los pedidos (a diferencia de la
    campanita, que solo muestra los últimos 20 y existe para avisar
    de lo nuevo). Acá se puede filtrar por estado, descartar un
    pedido, reactivarlo o borrarlo definitivamente.
    """
    template_name = 'catalogo/pedidos_historial.html'
    PAGE_SIZE = 20

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'ver_pedidos'):
            ctx['sin_permiso'] = True
            return ctx

        qs = Pedido.objects.prefetch_related('items').order_by('-fecha_alta')

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(contacto_nombre__icontains=q) | Q(contacto_telefono__icontains=q))

        filtro_estado = self.request.GET.get('estado', '').strip()
        if filtro_estado in EstadoPedido.values:
            qs = qs.filter(estado=filtro_estado)

        try:
            page_num = int(self.request.GET.get('page', 1))
        except ValueError:
            page_num = 1
        pedidos = Paginator(qs, self.PAGE_SIZE).get_page(page_num)
        for p in pedidos:
            p.wa_link = wa_link_ar(p.contacto_telefono)

        ctx.update({
            'pedidos': pedidos,
            'q': q,
            'filtro_estado': filtro_estado,
            'estados': EstadoPedido.choices,
        })
        return ctx


class PedidoCambiarEstadoAjax(LoginRequiredMixin, View):
    """
    POST {"accion": "descartar" | "reactivar"} → cancela un pedido
    pendiente o lo vuelve a poner como pendiente. Un pedido ya
    convertido en venta no se puede tocar desde acá — para eso está
    la venta misma (anularla desde Ventas).
    """
    ACCIONES = {'descartar': EstadoPedido.DESCARTADO, 'reactivar': EstadoPedido.PENDIENTE}

    def post(self, request, pk):
        if not chequear_permiso(request.user, 'ver_pedidos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pedido = get_object_or_404(Pedido, pk=pk)
        if pedido.estado == EstadoPedido.VENDIDO:
            return JsonResponse(
                {'error': 'Este pedido ya se convirtió en una venta — para deshacerlo, anulá esa venta.'},
                status=400,
            )

        try:
            body = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            body = {}

        nuevo_estado = self.ACCIONES.get(body.get('accion'))
        if not nuevo_estado:
            return JsonResponse({'error': 'Acción inválida.'}, status=400)

        pedido.estado = nuevo_estado
        pedido.save(update_fields=['estado'])
        return JsonResponse({'ok': True, 'estado': pedido.estado, 'estado_label': pedido.get_estado_display()})


class PedidoEliminarAjax(LoginRequiredMixin, View):
    """
    POST → borra el registro del pedido. Si ya se había convertido en
    una venta, la venta NO se toca — esto solo borra la "ficha" del
    pedido del catálogo, no lo que ya se vendió.
    """

    def post(self, request, pk):
        if not chequear_permiso(request.user, 'ver_pedidos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pedido = get_object_or_404(Pedido, pk=pk)
        pedido.delete()
        return JsonResponse({'ok': True})
