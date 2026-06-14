import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from productos.models import Producto, ProductoColor
from core.models import Cliente
from .models import Venta, ItemVenta, EstadoVenta, MedioPago
from core.permisos import chequear_permiso


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Nueva Venta
# ══════════════════════════════════════════════════════════════════

class NuevaVentaView(LoginRequiredMixin, TemplateView):
    template_name = 'ventas/nueva_venta.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'crear_ventas'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_crear']  = True
        ctx['today']        = timezone.now().date().isoformat()
        ctx['medios_pago']  = MedioPago.choices
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar productos
# ══════════════════════════════════════════════════════════════════

class BuscarProductoAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk_param = request.GET.get('pk', '').strip()
        if pk_param:
            try:
                p = (Producto.objects
                     .select_related('categoria', 'tipo')
                     .prefetch_related('colores')
                     .get(pk=pk_param))
            except Producto.DoesNotExist:
                return JsonResponse({'results': []})
            return JsonResponse({'results': [self._serializar(p)]})

        q  = request.GET.get('q', '').strip()
        qs = (
            Producto.objects
            .select_related('categoria', 'tipo')
            .prefetch_related('colores')
            .filter(estado='activo')
            .order_by('nombre')
        )
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(codigo__icontains=q)

        return JsonResponse({'results': [self._serializar(p) for p in qs[:30]]})

    def _serializar(self, p):
        colores = []
        if p.tiene_variantes_color:
            colores = [
                {
                    'pk':           c.pk,
                    'nombre':       c.nombre,
                    'codigo_hex':   c.codigo_hex,
                    'sku_variante': c.sku_variante,
                    'stock_actual': float(c.stock_actual),
                }
                for c in p.colores.filter(activo=True).order_by('nombre')
            ]
        return {
            'pk':                    p.pk,
            'codigo':                p.codigo,
            'nombre':                p.nombre,
            'unidad_medida':         p.get_unidad_medida_display(),
            'stock_actual':          float(p.stock_actual),
            'stock_minimo':          float(p.stock_minimo),
            'categoria':             p.categoria.nombre if p.categoria else '',
            'tipo':                  p.tipo.nombre if p.tipo else '',
            'marca':                 p.marca,
            'modelo':                p.modelo,
            'tiene_variantes_color': p.tiene_variantes_color,
            'colores':               colores,
            'precio_venta':          float(p.precio_venta) if p.precio_venta is not None else None,
            'moneda':                'ARS',
        }


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar clientes
# ══════════════════════════════════════════════════════════════════

class BuscarClienteAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q  = request.GET.get('q', '').strip()
        qs = Cliente.objects.filter(estado='activo').order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(razon_social__icontains=q)
        data = [
            {
                'pk':     c.pk,
                'nombre': c.nombre or c.razon_social or str(c),
                'codigo': c.codigo or '',
            }
            for c in qs[:20]
        ]
        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Guardar Borrador
# ══════════════════════════════════════════════════════════════════

class GuardarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "fecha":      "2025-01-15",   // opcional, usa hoy si falta
        "notas":      "...",
        "medio_pago": "efectivo",     // se guarda en el borrador, se confirma al aceptar
        "items": [ { producto_pk, cliente_pk, color_pk, cantidad,
                     precio_unitario, moneda, descuento_pct,
                     condicion_pago, referencia } ]
    }
    Respuesta: { ok, pk, numero }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        items_raw = body.get('items', [])
        if not items_raw:
            return JsonResponse({'error': 'El carrito está vacío.'}, status=400)

        fecha      = body.get('fecha') or timezone.now().date().isoformat()
        medio_pago = body.get('medio_pago', MedioPago.EFECTIVO)

        # Validar medio_pago
        valores_validos = [v for v, _ in MedioPago.choices]
        if medio_pago not in valores_validos:
            return JsonResponse({'error': f'Medio de pago inválido: {medio_pago}'}, status=400)

        venta = Venta(
            fecha      = fecha,
            notas      = body.get('notas', ''),
            medio_pago = medio_pago,
            estado     = EstadoVenta.BORRADOR,
            creado_por = request.user,
        )
        venta.save()

        errores = []
        for idx, raw in enumerate(items_raw, start=1):
            producto_pk = raw.get('producto_pk')
            if not producto_pk:
                errores.append(f'Ítem {idx}: falta producto.')
                continue

            try:
                producto = Producto.objects.get(pk=producto_pk)
            except Producto.DoesNotExist:
                errores.append(f'Ítem {idx}: producto no encontrado.')
                continue

            try:
                cantidad        = Decimal(str(raw.get('cantidad', 0)))
                precio_unitario = Decimal(str(raw.get('precio_unitario', 0)))
                descuento_pct   = Decimal(str(raw.get('descuento_pct', 0)))
            except Exception:
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if precio_unitario < 0:
                errores.append(f'Ítem {idx}: el precio no puede ser negativo.')
                continue

            cliente    = None
            cliente_pk = raw.get('cliente_pk')
            if cliente_pk:
                cliente = Cliente.objects.filter(pk=cliente_pk).first()

            color    = None
            color_pk = raw.get('color_pk')
            if color_pk:
                color = ProductoColor.objects.filter(pk=color_pk, producto=producto).first()
                if not color:
                    errores.append(f'Ítem {idx}: el color no pertenece a este producto.')
                    continue

            ItemVenta.objects.create(
                venta           = venta,
                producto        = producto,
                cliente         = cliente,
                color           = color,
                cantidad        = cantidad,
                precio_unitario = precio_unitario,
                moneda          = raw.get('moneda', 'ARS'),
                descuento_pct   = descuento_pct,
                condicion_pago  = raw.get('condicion_pago', 'contado'),
                referencia      = raw.get('referencia', ''),
                notas           = raw.get('notas', ''),
            )

        if errores:
            venta.delete()
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # Calcular el total sumando los subtotales de los ítems creados
        venta.calcular_total()

        return JsonResponse({'ok': True, 'pk': venta.pk, 'numero': venta.numero})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Confirmar Venta
# ══════════════════════════════════════════════════════════════════

class ConfirmarVentaAjax(LoginRequiredMixin, View):
    """
    POST JSON { venta_pk, fecha, notas, medio_pago }
    Confirma el borrador: resta stock, guarda confirmado_por y medio_pago.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta_pk   = body.get('venta_pk')
        fecha      = body.get('fecha', '').strip()
        medio_pago = body.get('medio_pago', '').strip()

        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)
        if not fecha:
            return JsonResponse({'error': 'La fecha es requerida.'}, status=400)
        if not medio_pago:
            return JsonResponse({'error': 'El medio de pago es requerido.'}, status=400)

        valores_validos = [v for v, _ in MedioPago.choices]
        if medio_pago not in valores_validos:
            return JsonResponse({'error': f'Medio de pago inválido: {medio_pago}'}, status=400)

        venta = get_object_or_404(Venta, pk=venta_pk)

        if venta.estado != EstadoVenta.BORRADOR:
            return JsonResponse(
                {'error': f'La venta ya está en estado "{venta.get_estado_display()}".'},
                status=400
            )

        try:
            venta.editar_cabecera(fecha=fecha, notas=body.get('notas', ''))
        except Exception as e:
            import traceback
            return JsonResponse({'error': f'editar_cabecera: {e}', 'detalle': traceback.format_exc()}, status=400)

        try:
            venta.confirmar(confirmado_por=request.user, medio_pago=medio_pago)
        except Exception as e:
            import traceback
            return JsonResponse({'error': f'confirmar: {e}', 'detalle': traceback.format_exc()}, status=400)

        return JsonResponse({
            'ok':     True,
            'pk':     venta.pk,
            'numero': venta.numero,
            'total':  str(venta.total),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar Borrador
# ══════════════════════════════════════════════════════════════════

class EliminarBorradorAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta_pk = body.get('venta_pk')
        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)

        venta = get_object_or_404(Venta, pk=venta_pk)

        if venta.estado != EstadoVenta.BORRADOR:
            return JsonResponse(
                {'error': 'Solo se pueden eliminar borradores desde este endpoint.'},
                status=400
            )

        venta.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Documentos de venta
# ══════════════════════════════════════════════════════════════════

import os
from .models import VentaDocumento
from django.shortcuts import render as _render


class VentaDocumentoSubirAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        venta_pk = request.POST.get('venta_pk')
        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)

        archivo = request.FILES.get('archivo')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

        if archivo.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 10 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf'}:
            return JsonResponse(
                {'error': 'Tipo no permitido. Usá JPG, PNG, WEBP, GIF o PDF.'},
                status=400
            )

        venta = get_object_or_404(Venta, pk=venta_pk)

        doc = VentaDocumento(
            venta       = venta,
            archivo     = archivo,
            tipo        = request.POST.get('tipo', 'otro'),
            descripcion = request.POST.get('descripcion', ''),
            subido_por  = request.user,
        )
        doc.save()

        return JsonResponse({
            'ok': True,
            'documento': {
                'pk':          doc.pk,
                'nombre':      doc.nombre_archivo,
                'url':         doc.archivo.url,
                'tipo':        doc.tipo,
                'tipo_label':  doc.get_tipo_display(),
                'descripcion': doc.descripcion,
                'es_imagen':   doc.es_imagen,
                'es_pdf':      doc.es_pdf,
                'subido_el':   doc.subido_el.strftime('%d/%m/%Y %H:%M'),
            },
        })


class VentaDocumentoEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        doc = get_object_or_404(VentaDocumento, pk=pk)

        if doc.archivo and os.path.isfile(doc.archivo.path):
            os.remove(doc.archivo.path)

        doc.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  VISTA — Detalle de venta
# ══════════════════════════════════════════════════════════════════

class DetalleVentaView(LoginRequiredMixin, View):
    template_name = 'ventas/detalle_venta.html'

    def get(self, request, pk):
        if not chequear_permiso(request.user, 'crear_ventas'):
            from django.shortcuts import redirect
            return redirect('core:dashboard')

        venta = get_object_or_404(
            Venta.objects.prefetch_related(
                'items__producto', 'items__cliente', 'items__color', 'documentos',
            ),
            pk=pk
        )

        from django.urls import reverse
        return _render(request, self.template_name, {
            'venta':     venta,
            'items':      venta.items.select_related('producto', 'cliente', 'color').all(),
            'documentos': venta.documentos.all(),
            'es_borrador': venta.estado == EstadoVenta.BORRADOR,
            'medios_pago': MedioPago.choices,
            'url_confirmar':         reverse('ventas:confirmar_venta'),
            'url_eliminar_borrador': reverse('ventas:eliminar_borrador'),
            'url_nueva_venta':       reverse('ventas:nueva_venta'),
            'url_historial':         reverse('ventas:historial_ventas'),
            'url_doc_subir':         reverse('ventas:documento_subir'),
            'url_doc_eliminar':      reverse('ventas:documento_eliminar'),
        })