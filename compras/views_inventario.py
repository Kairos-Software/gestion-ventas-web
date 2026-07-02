"""
══════════════════════════════════════════════════════════════════
 INVENTARIO — Listado de lotes con stock disponible
══════════════════════════════════════════════════════════════════
No es un modelo nuevo: consulta LoteCompra, que ya se genera solo
al confirmar/anular/reactivar una Compra (ver compras/models.py).
Esta pantalla es de solo lectura — no crea ni modifica lotes.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.db.models import Q, F
from django.utils import timezone
from datetime import timedelta

from .models import LoteCompra
from core.permisos import chequear_permiso


# ══════════════════════════════════════════════════════════════════
#  PÁGINA PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class InventarioView(LoginRequiredMixin, TemplateView):
    """Renderiza la pantalla de Inventario. La tabla se llena por AJAX."""
    template_name = 'compras/inventario.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'crear_compras'):
            ctx['sin_permiso'] = True
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listado / búsqueda
# ══════════════════════════════════════════════════════════════════

class ListarLotesAjax(LoginRequiredMixin, View):
    """
    GET ?q=texto&vencimiento=vencido|por_vencer|ok

    Devuelve los lotes ACTIVOS con cantidad_actual > 0.
    Orden: primero los que vencen antes (FEFO); los sin vencimiento
    quedan al final. Después, por fecha de compra más reciente.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = (
            LoteCompra.objects
            .select_related('producto', 'producto__categoria', 'combinacion',
                             'item_compra', 'item_compra__proveedor')
            .filter(activo=True, cantidad_actual__gt=0)
        )

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(codigo__iexact=q) |
                Q(producto__nombre__icontains=q) |
                Q(producto__codigo__icontains=q) |
                Q(combinacion__descripcion_combinacion__icontains=q)
            )

        filtro_venc = request.GET.get('vencimiento', '').strip()
        if filtro_venc:
            hoy = timezone.now().date()
            if filtro_venc == 'vencido':
                qs = qs.filter(fecha_vencimiento__lt=hoy)
            elif filtro_venc == 'por_vencer':
                qs = qs.filter(fecha_vencimiento__gte=hoy,
                                fecha_vencimiento__lte=hoy + timedelta(days=7))
            elif filtro_venc == 'ok':
                qs = qs.filter(
                    Q(fecha_vencimiento__isnull=True) |
                    Q(fecha_vencimiento__gt=hoy + timedelta(days=7))
                )

        qs = qs.order_by(F('fecha_vencimiento').asc(nulls_last=True), '-fecha_compra')

        return JsonResponse({'results': [self._serializar(l) for l in qs]})

    # ── Serialización ────────────────────────────────────────────
    def _serializar(self, lote):
        producto    = lote.producto
        combinacion = lote.combinacion
        item        = lote.item_compra

        hoy = timezone.now().date()
        estado_vencimiento = None
        if lote.fecha_vencimiento:
            if lote.fecha_vencimiento < hoy:
                estado_vencimiento = 'vencido'
            elif lote.fecha_vencimiento <= hoy + timedelta(days=7):
                estado_vencimiento = 'por_vencer'
            else:
                estado_vencimiento = 'ok'

        return {
            'pk':                    lote.pk,
            'codigo':                lote.codigo,
            'producto_nombre':       producto.nombre if producto else '(producto eliminado)',
            'producto_codigo':       producto.codigo if producto else '',
            'variante_desc':         combinacion.descripcion_legible() if combinacion else '',
            'categoria':             producto.categoria.nombre if producto and producto.categoria else '',
            'proveedor':             item.nombre_proveedor_display if item else '',
            'cantidad_actual':       lote.cantidad_actual,
            'cantidad_inicial':      lote.cantidad_inicial,
            'porcentaje_restante':   lote.porcentaje_restante,
            'costo_unitario':        str(lote.costo_unitario),
            'fecha_vencimiento':     lote.fecha_vencimiento.strftime('%d/%m/%Y') if lote.fecha_vencimiento else None,
            'fecha_vencimiento_iso': lote.fecha_vencimiento.isoformat() if lote.fecha_vencimiento else None,
            'estado_vencimiento':    estado_vencimiento,
            'fecha_compra':          lote.fecha_compra.strftime('%d/%m/%Y'),
            'es_perecedero':         producto.es_perecedero if producto else False,
        }


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar por código (pensado para el escaneo de la etiqueta)
# ══════════════════════════════════════════════════════════════════

class BuscarLotePorCodigoAjax(LoginRequiredMixin, View):
    """
    GET ?codigo=LT-2025-00001

    Match exacto — al escanear la etiqueta pegada en el producto,
    el frontend manda directo el texto leído acá y trae toda la
    info del lote (costo, vencimiento, producto, variante).
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        codigo = request.GET.get('codigo', '').strip()
        if not codigo:
            return JsonResponse({'error': 'Falta el código.'}, status=400)

        lote = (
            LoteCompra.objects
            .select_related('producto', 'producto__categoria', 'combinacion',
                             'item_compra', 'item_compra__proveedor')
            .filter(codigo__iexact=codigo)
            .first()
        )
        if not lote:
            return JsonResponse(
                {'error': f'No se encontró ningún lote con el código "{codigo}".'},
                status=404
            )

        listador = ListarLotesAjax()
        return JsonResponse({'result': listador._serializar(lote)})