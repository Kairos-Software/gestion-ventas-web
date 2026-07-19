"""
══════════════════════════════════════════════════════════════════
 INVENTARIO — Listado de lotes con stock disponible
══════════════════════════════════════════════════════════════════
No es un modelo nuevo: consulta LoteCompra, que ya se genera solo
al confirmar/anular/reactivar una Compra (ver compras/models.py).
Esta pantalla es de solo lectura — no crea ni modifica lotes.
"""

import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q, F
from django.utils import timezone
from datetime import timedelta

from .models import (
    LoteCompra, Perdida, MotivoPerdida, registrar_perdida, procesar_lotes_vencidos,
    Fraccionamiento, fraccionar,
)
from productos.models import Producto, cantidad_valida_para_unidad
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

        # Da de baja como pérdida (automática) lo que venció desde la
        # última vez que alguien visitó esta pantalla — ver
        # procesar_lotes_vencidos() para el porqué de este approach.
        procesar_lotes_vencidos()

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
            'unidad_medida':         producto.get_unidad_medida_display() if producto else '',
            'unidades_por_presentacion': (producto.unidades_por_presentacion or '') if producto else '',
            'contenido_neto':        str(producto.contenido_neto) if producto and producto.contenido_neto else '',
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


# ══════════════════════════════════════════════════════════════════
#  AJAX — Registrar pérdida manual (rotura, extravío, otro)
# ══════════════════════════════════════════════════════════════════

class RegistrarPerdidaAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "lote_pk":         12,
        "cantidad":        2,
        "motivo":          "rotura" | "otro",   // "vencimiento" es automático, no se elige a mano
        "motivo_detalle":  "Llegó roto del transporte"
    }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'ajustar_stock'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        lote_pk = body.get('lote_pk')
        motivo  = (body.get('motivo') or '').strip()
        detalle = (body.get('motivo_detalle') or '').strip()

        if not lote_pk:
            return JsonResponse({'error': 'Falta lote_pk.'}, status=400)
        if motivo == MotivoPerdida.VENCIMIENTO:
            return JsonResponse({
                'error': 'El vencimiento se registra solo — elegí "Rotura / daño" u "Otro".'
            }, status=400)
        if motivo not in MotivoPerdida.values:
            return JsonResponse({'error': f'Motivo inválido: {motivo}'}, status=400)

        try:
            cantidad = Decimal(str(body.get('cantidad')))
            if cantidad <= 0:
                raise ValueError
        except (TypeError, ValueError, InvalidOperation):
            return JsonResponse({'error': 'La cantidad debe ser un número positivo.'}, status=400)

        lote = get_object_or_404(LoteCompra, pk=lote_pk)

        if lote.producto and not cantidad_valida_para_unidad(lote.producto.unidad_medida, cantidad):
            return JsonResponse({
                'error': f'"{lote.producto.nombre}" se maneja por {lote.producto.get_unidad_medida_display()} '
                         f'— la cantidad tiene que ser un número entero.'
            }, status=400)

        try:
            perdida = registrar_perdida(
                lote=lote, cantidad=cantidad, motivo=motivo,
                motivo_detalle=detalle, usuario=request.user, automatica=False,
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        lote.refresh_from_db()
        return JsonResponse({
            'ok':                True,
            'pk':                perdida.pk,
            'lote_cantidad_actual': lote.cantidad_actual,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listado de pérdidas (vencimiento + manuales)
# ══════════════════════════════════════════════════════════════════

class ListarPerdidasAjax(LoginRequiredMixin, View):
    """GET — últimas pérdidas registradas, más nuevas primero."""

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Perdida.objects.select_related('registrado_por', 'producto')[:100]

        resultados = [{
            'pk':               p.pk,
            'fecha':            p.fecha.strftime('%d/%m/%Y'),
            'producto_nombre':  p.producto_nombre_snapshot,
            'variante_desc':    p.combinacion_desc_snapshot,
            'lote_codigo':      p.lote_codigo_snapshot,
            'cantidad':         p.cantidad,
            'unidad_medida':    p.producto.get_unidad_medida_display() if p.producto else '',
            'costo_unitario':   str(p.costo_unitario_snapshot),
            'costo_total':      str(p.costo_total),
            'motivo':           p.motivo,
            'motivo_label':     p.get_motivo_display(),
            'motivo_detalle':   p.motivo_detalle,
            'automatica':       p.automatica,
            'registrado_por':   p.registrado_por.get_full_name() if p.registrado_por else ('Sistema' if p.automatica else '—'),
        } for p in qs]

        total_costo = sum((p.costo_total for p in qs), Decimal('0'))

        return JsonResponse({'results': resultados, 'total_costo': str(total_costo)})


# ══════════════════════════════════════════════════════════════════
#  FRACCIONAMIENTO — armar un producto empaquetado a partir de otro
#  a granel (ver fraccionar() en models.py para la lógica completa).
# ══════════════════════════════════════════════════════════════════

class BuscarProductosFraccionarAjax(LoginRequiredMixin, View):
    """
    GET ?q=texto&excluir=<pk>
    Busca productos simples (sin variantes) para elegir como origen o
    destino de un fraccionamiento. `excluir` saca un pk puntual de los
    resultados (para que el destino no pueda ser el mismo que el origen).
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q = request.GET.get('q', '').strip()
        excluir_pk = request.GET.get('excluir', '').strip()

        qs = Producto.objects.filter(
            estado='activo', gestiona_stock=True, gestiona_variantes=False,
        )
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
        if excluir_pk:
            qs = qs.exclude(pk=excluir_pk)

        resultados = [{
            'pk':               p.pk,
            'nombre':           p.nombre,
            'codigo':           p.codigo,
            'marca':            p.marca,
            'unidad_medida':    p.get_unidad_medida_display(),
            'unidad_medida_key': p.unidad_medida,
            'permite_fraccion': p.permite_fraccion,
            'stock_actual':     str(p.stock_actual),
            'unidades_por_presentacion': p.unidades_por_presentacion or '',
            'contenido_neto':   str(p.contenido_neto) if p.contenido_neto else '',
        } for p in qs.order_by('nombre')[:20]]

        return JsonResponse({'results': resultados})


class FraccionarAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "producto_origen_pk":  5,
        "producto_destino_pk": 8,
        "cantidad_origen":     "5",
        "cantidad_paquetes":   "50",
        "notas":               ""
    }
    `cantidad_origen` = cuánto de producto_origen se va a usar.
    `cantidad_paquetes` = cuántas unidades de producto_destino se arman.
    """

    def post(self, request):
        # Mismo permiso que BuscarProductosFraccionarAjax y ListarFraccionamientosAjax
        # (antes pedía 'ajustar_stock', que no es el que se chequea para buscar/listar —
        # un usuario podía armar todo el fraccionamiento en pantalla y recién enterarse
        # que no tenía permiso al confirmar).
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        origen_pk  = body.get('producto_origen_pk')
        destino_pk = body.get('producto_destino_pk')
        if not origen_pk or not destino_pk:
            return JsonResponse({'error': 'Elegí el producto de origen y el de destino.'}, status=400)

        try:
            cantidad_origen = Decimal(str(body.get('cantidad_origen')))
            paquetes        = Decimal(str(body.get('cantidad_paquetes')))
        except (TypeError, ValueError, InvalidOperation):
            return JsonResponse({'error': 'Las cantidades tienen que ser números válidos.'}, status=400)

        producto_origen  = get_object_or_404(Producto, pk=origen_pk)
        producto_destino = get_object_or_404(Producto, pk=destino_pk)

        try:
            frac = fraccionar(
                producto_origen=producto_origen,
                producto_destino=producto_destino,
                cantidad_origen=cantidad_origen,
                cantidad_paquetes=paquetes,
                usuario=request.user,
                notas=(body.get('notas') or '').strip(),
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        producto_origen.refresh_from_db()
        producto_destino.refresh_from_db()

        return JsonResponse({
            'ok': True,
            'pk': frac.pk,
            'costo_unitario_calculado': str(frac.costo_unitario_calculado),
            'stock_origen':  str(producto_origen.stock_actual),
            'stock_destino': str(producto_destino.stock_actual),
        })


class ListarFraccionamientosAjax(LoginRequiredMixin, View):
    """GET — historial de fraccionamientos, más nuevos primero."""

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Fraccionamiento.objects.select_related('creado_por', 'producto_origen', 'producto_destino')[:100]

        resultados = [{
            'pk':                       f.pk,
            'fecha':                    f.fecha.strftime('%d/%m/%Y'),
            'producto_origen':          f.producto_origen_nombre_snapshot,
            'producto_destino':         f.producto_destino_nombre_snapshot,
            'cantidad_total_origen':    str(f.cantidad_total_origen),
            'unidad_origen':            f.producto_origen.get_unidad_medida_display() if f.producto_origen else '',
            'cantidad_paquetes':        str(f.cantidad_paquetes),
            'unidad_destino':           f.producto_destino.get_unidad_medida_display() if f.producto_destino else '',
            'costo_unitario_calculado': str(f.costo_unitario_calculado),
            'notas':                    f.notas,
            'creado_por':               f.creado_por.get_full_name() if f.creado_por else '—',
        } for f in qs]

        return JsonResponse({'results': resultados})