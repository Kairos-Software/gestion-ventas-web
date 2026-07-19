# ventas/views_balanza.py
#
# Etiquetas de balanza: productos que se pesan/miden al momento de
# vender (carnicería, verdulería, panadería...). Se pesa, se genera
# una etiqueta con código único que ya trae la cantidad y el precio
# fijados, se pega en la bolsa, y en caja alcanza con escanearla — no
# se vuelve a pesar ni tipear nada. Ver EtiquetaBalanza en models.py
# para el detalle de por qué no toca stock hasta que se vende.

import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone

from productos.models import Producto, UNIDADES_FRACCIONABLES
from core.permisos import chequear_permiso
from .models import EtiquetaBalanza, EstadoEtiquetaBalanza


class BalanzaView(LoginRequiredMixin, TemplateView):
    template_name = 'ventas/balanza.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['puede_ver']    = chequear_permiso(self.request.user, 'ver_balanza')
        ctx['puede_crear']  = chequear_permiso(self.request.user, 'crear_balanza')
        ctx['puede_anular'] = chequear_permiso(self.request.user, 'anular_balanza')
        return ctx


class BalanzaBuscarProductoAjax(LoginRequiredMixin, View):
    """
    GET ?q=texto
    Busca productos que se puedan pesar/medir (unidad de medida
    fraccionable: kg, gr, lt, ml, mt, cm, mt2, mt3) para elegir en el
    generador de etiquetas.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_balanza'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q = request.GET.get('q', '').strip()
        qs = Producto.objects.filter(
            estado='activo', gestiona_stock=True, gestiona_variantes=False,
            unidad_medida__in=UNIDADES_FRACCIONABLES,
        )
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))

        resultados = [{
            'pk':            p.pk,
            'nombre':        p.nombre,
            'codigo':        p.codigo,
            'marca':         p.marca,
            'unidad_medida': p.get_unidad_medida_display(),
            'permite_fraccion': p.permite_fraccion,
            'stock_actual':  str(p.stock_actual),
            'precio_venta':  str(p.precio_venta) if p.precio_venta is not None else None,
        } for p in qs.order_by('nombre')[:20]]

        return JsonResponse({'results': resultados})


class BalanzaGenerarAjax(LoginRequiredMixin, View):
    """
    POST JSON: { "producto_pk": 5, "cantidad": "2.050" }
    Genera una etiqueta nueva con el precio del producto fijado en
    este momento. No toca stock — eso pasa recién cuando se vende.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_balanza'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        producto = Producto.objects.filter(pk=body.get('producto_pk')).first()
        if not producto:
            return JsonResponse({'error': 'Elegí un producto.'}, status=400)
        if not producto.permite_fraccion:
            return JsonResponse({
                'error': f'"{producto.nombre}" se cuenta por {producto.get_unidad_medida_display()} '
                         f'— la balanza es solo para productos que se pesan o miden (kg, lt, mt, etc.).',
            }, status=400)
        if not producto.gestiona_stock:
            return JsonResponse({'error': f'"{producto.nombre}" no gestiona stock.'}, status=400)
        if producto.precio_venta is None:
            return JsonResponse({'error': f'"{producto.nombre}" todavía no tiene un precio de venta cargado.'}, status=400)

        try:
            cantidad = Decimal(str(body.get('cantidad')))
        except (TypeError, ValueError, InvalidOperation):
            return JsonResponse({'error': 'La cantidad pesada no es un número válido.'}, status=400)
        if cantidad <= 0:
            return JsonResponse({'error': 'La cantidad pesada tiene que ser mayor a 0.'}, status=400)

        precio_unitario = producto.precio_venta
        precio_total = (cantidad * precio_unitario).quantize(Decimal('0.01'))

        etiqueta = EtiquetaBalanza.objects.create(
            producto=producto,
            producto_nombre_snapshot=producto.nombre,
            unidad_medida_snapshot=producto.get_unidad_medida_display(),
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            precio_total=precio_total,
            creado_por=request.user,
        )

        aviso_stock = None
        if cantidad > producto.stock_actual:
            aviso_stock = (
                f'Ojo: el sistema tiene registrados {producto.stock_actual} '
                f'{producto.get_unidad_medida_display()} de "{producto.nombre}", menos de lo que pesaste. '
                f'La etiqueta se generó igual — revisá el stock cargado si esto no es lo esperado.'
            )

        return JsonResponse({
            'ok': True,
            'pk': etiqueta.pk,
            'codigo': etiqueta.codigo,
            'producto_nombre': etiqueta.producto_nombre_snapshot,
            'unidad_medida': etiqueta.unidad_medida_snapshot,
            'cantidad': str(etiqueta.cantidad),
            'precio_unitario': str(etiqueta.precio_unitario),
            'precio_total': str(etiqueta.precio_total),
            'fecha': etiqueta.fecha_alta.strftime('%d/%m/%Y %H:%M'),
            'aviso_stock': aviso_stock,
        })


class BalanzaListarAjax(LoginRequiredMixin, View):
    """GET ?q=&estado= — historial de etiquetas, más nuevas primero."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_balanza'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = EtiquetaBalanza.objects.select_related('producto', 'creado_por', 'anulado_por')

        estado = request.GET.get('estado', '').strip()
        if estado in EstadoEtiquetaBalanza.values:
            qs = qs.filter(estado=estado)

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(codigo__icontains=q) | Q(producto_nombre_snapshot__icontains=q))

        puede_anular = chequear_permiso(request.user, 'anular_balanza')

        resultados = [{
            'pk':               e.pk,
            'codigo':           e.codigo,
            'producto_nombre':  e.producto_nombre_snapshot,
            'unidad_medida':    e.unidad_medida_snapshot,
            'cantidad':         str(e.cantidad),
            'precio_unitario':  str(e.precio_unitario),
            'precio_total':     str(e.precio_total),
            'estado':           e.estado,
            'estado_display':   e.get_estado_display(),
            'creado_por':       e.creado_por.get_full_name() if e.creado_por else '—',
            'fecha_alta':       e.fecha_alta.strftime('%d/%m/%Y %H:%M'),
            'puede_anular':     puede_anular and e.estado == EstadoEtiquetaBalanza.DISPONIBLE,
        } for e in qs[:200]]

        return JsonResponse({'results': resultados})


class BalanzaAnularAjax(LoginRequiredMixin, View):
    """
    POST JSON: { "pk": 5, "motivo": "pesé mal, era 1.5kg no 2.5kg" }
    Solo se puede anular una etiqueta DISPONIBLE (todavía no vendida).
    No hay que revertir nada de stock porque nunca se tocó.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'anular_balanza'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        etiqueta = EtiquetaBalanza.objects.filter(pk=body.get('pk')).first()
        if not etiqueta:
            return JsonResponse({'error': 'Esa etiqueta no existe.'}, status=404)
        if etiqueta.estado != EstadoEtiquetaBalanza.DISPONIBLE:
            return JsonResponse({
                'error': f'La etiqueta {etiqueta.codigo} ya está "{etiqueta.get_estado_display()}" — no se puede anular.',
            }, status=400)

        etiqueta.estado           = EstadoEtiquetaBalanza.ANULADA
        etiqueta.anulado_por      = request.user
        etiqueta.fecha_anulacion  = timezone.now()
        etiqueta.motivo_anulacion = (body.get('motivo') or '').strip()
        etiqueta.save(update_fields=['estado', 'anulado_por', 'fecha_anulacion', 'motivo_anulacion'])

        return JsonResponse({'ok': True})


class BalanzaBuscarCodigoAjax(LoginRequiredMixin, View):
    """
    GET ?codigo=BAL-2026-00001
    Usado desde Nueva Venta: al escanear una etiqueta de balanza,
    devuelve el producto con la cantidad y el precio YA FIJADOS por la
    etiqueta (no el precio actual del producto, que puede haber
    cambiado). El frontend arma el ítem del carrito con esos valores
    bloqueados.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        codigo = request.GET.get('codigo', '').strip()
        if not codigo:
            return JsonResponse({'error': 'Falta el código.'}, status=400)

        etiqueta = EtiquetaBalanza.objects.select_related('producto').filter(codigo__iexact=codigo).first()
        if not etiqueta:
            return JsonResponse({'error': f'No se encontró ninguna etiqueta con el código "{codigo}".'}, status=404)
        if etiqueta.estado == EstadoEtiquetaBalanza.VENDIDA:
            return JsonResponse({'error': f'La etiqueta {etiqueta.codigo} ya fue vendida — no se puede volver a usar.'}, status=400)
        if etiqueta.estado == EstadoEtiquetaBalanza.ANULADA:
            return JsonResponse({'error': f'La etiqueta {etiqueta.codigo} está anulada — pesá el producto de nuevo.'}, status=400)
        if etiqueta.producto is None:
            return JsonResponse({'error': 'El producto de esta etiqueta ya no existe.'}, status=400)

        p = etiqueta.producto
        return JsonResponse({'results': [{
            'pk':               p.pk,
            'codigo':           p.codigo,
            'nombre':           p.nombre,
            'tipo_resultado':   'simple',
            'combinacion_pk':   None,
            'variante_desc':    '',
            'gestiona_variantes': False,
            'stock_actual':     float(p.stock_actual),
            'moneda':           'ARS',
            'tipo_escaneo':     'normal',
            'lote_pk':          None,
            'match_exacto':     True,
            # Los tres campos que hacen a esto distinto de un producto normal:
            'etiqueta_balanza_pk':     etiqueta.pk,
            'etiqueta_balanza_codigo': etiqueta.codigo,
            'cantidad_fija':           str(etiqueta.cantidad),
            'precio_venta':            float(etiqueta.precio_unitario),
        }]})
