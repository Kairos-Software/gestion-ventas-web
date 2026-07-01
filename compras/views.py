import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from productos.models import Producto, Proveedor, CombinacionVariante
from .models import Compra, ItemCompra, EstadoCompra
from core.permisos import chequear_permiso


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Nueva Compra
# ══════════════════════════════════════════════════════════════════

class NuevaCompraView(LoginRequiredMixin, TemplateView):
    """Renderiza el formulario / carrito para crear una nueva compra."""
    template_name = 'compras/nueva_compra.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'crear_compras'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_crear'] = True
        ctx['today'] = timezone.now().date().isoformat()
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar productos (para el buscador del carrito)
# ══════════════════════════════════════════════════════════════════

class BuscarProductoAjax(LoginRequiredMixin, View):
    """
    GET ?q=texto → lista de productos para el autocomplete.

    Cuando el producto tiene gestiona_variantes=True se incluye
    la lista de combinaciones activas con su stock, para que el frontend
    pueda mostrar el selector de distribución por combinación.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        # ── Modo ?pk= : producto específico con combinaciones.
        #    Usado por el editor del historial para enriquecer swatches
        #    al abrir el panel de edición de una compra anulada.
        pk_param = request.GET.get('pk', '').strip()
        if pk_param:
            try:
                p = (Producto.objects
                     .select_related('categoria', 'tipo', 'proveedor')
                     .prefetch_related('combinaciones')
                     .get(pk=pk_param))
            except Producto.DoesNotExist:
                return JsonResponse({'results': []})
            return JsonResponse({'results': [self._serializar(p)]})

        # ── Modo ?q= : búsqueda por texto ──
        q  = request.GET.get('q', '').strip()
        qs = (
            Producto.objects
            .select_related('categoria', 'tipo', 'proveedor')
            .prefetch_related('combinaciones')
            .filter(estado='activo')
            .order_by('nombre')
        )
        if q:
            # Buscar por nombre, código, código de barras global o código de barras de variante
            qs = (
                qs.filter(nombre__icontains=q) |
                qs.filter(codigo__icontains=q) |
                qs.filter(codigo_barras__icontains=q) |
                qs.filter(combinaciones__codigo_barras__icontains=q)
            ).distinct()

        return JsonResponse({'results': [self._serializar(p) for p in qs[:30]]})

    def _serializar(self, p):
        combinaciones = []
        if p.gestiona_variantes:
            combinaciones = [
                {
                    'pk':                    c.pk,
                    'descripcion':           c.descripcion_legible(),
                    'descripcion_combinacion': c.descripcion_legible(),
                    'codigo_barras':         c.codigo_barras,
                    'sku_variante':          c.sku_variante,
                    'stock_actual':          float(c.stock_actual),
                }
                for c in p.combinaciones.filter(activo=True).order_by('pk')
            ]
        return {
            'pk':                   p.pk,
            'codigo':               p.codigo,
            'nombre':               p.nombre,
            'unidad_medida':        p.get_unidad_medida_display(),
            'stock_actual':        float(p.stock_actual),
            'stock_minimo':        float(p.stock_minimo),
            'categoria':           p.categoria.nombre if p.categoria else '',
            'tipo':                p.tipo.nombre if p.tipo else '',
            'marca':               p.marca,
            'modelo':              p.modelo,
            'proveedor_pk':        p.proveedor_id or '',
            'proveedor':           p.proveedor.nombre if p.proveedor else '',
            'gestiona_variantes':  p.gestiona_variantes,
            'combinaciones':       combinaciones,
        }


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar proveedores (para el select de cada ítem)
# ══════════════════════════════════════════════════════════════════

class BuscarProveedorAjax(LoginRequiredMixin, View):
    """GET ?q=texto → lista de proveedores activos."""

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q  = request.GET.get('q', '').strip()
        qs = Proveedor.objects.filter(activo=True).order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q)
        data = [
            {
                'pk':     p.pk,
                'nombre': p.nombre,
                'cuit':   p.cuit,
                'ciudad': p.ciudad,
            }
            for p in qs[:20]
        ]
        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Guardar Borrador
#  Nuevo endpoint: crea la Compra en BORRADOR con sus ítems.
#  No toca stock. Devuelve el pk para redirigir al detalle.
# ══════════════════════════════════════════════════════════════════

class GuardarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "fecha": "2025-01-15",       // opcional, usa hoy si falta
        "notas": "...",
        "items": [
            {
                "producto_pk":       1,
                "proveedor_pk":      2,        // opcional
                "combinacion_pk":    5,        // solo si tiene variantes
                "cantidad":          "10.000",
                "costo_unitario":    "150.00",
                "moneda":            "ARS",
                "descuento_pct":     "0",
                "condicion_pago":    "contado",
                "referencia":        "FA-0001"
            },
            ...
        ]
    }

    Respuesta: { ok: true, pk: <compra_pk>, numero: "CMP-00001" }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        items_raw = body.get('items', [])
        if not items_raw:
            return JsonResponse({'error': 'El carrito está vacío.'}, status=400)

        # Usar hoy si no se provee fecha (se puede editar en el detalle)
        fecha = body.get('fecha') or timezone.now().date().isoformat()

        # — Crear cabecera en BORRADOR —
        compra = Compra(
            fecha      = fecha,
            notas      = body.get('notas', ''),
            estado     = EstadoCompra.BORRADOR,
            creado_por = request.user,
        )
        compra.save()

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
                cantidad       = Decimal(str(raw.get('cantidad', 0)))
                costo_unitario = Decimal(str(raw.get('costo_unitario', 0)))
                descuento_pct  = Decimal(str(raw.get('descuento_pct', 0)))
            except Exception:
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if costo_unitario < 0:
                errores.append(f'Ítem {idx}: el costo no puede ser negativo.')
                continue

            # — Proveedor (opcional) —
            proveedor = None
            proveedor_pk = raw.get('proveedor_pk')
            if proveedor_pk:
                proveedor = Proveedor.objects.filter(pk=proveedor_pk).first()

            # — Combinación (solo si el producto gestiona variantes) —
            combinacion = None
            combinacion_pk = raw.get('combinacion_pk')
            if producto.gestiona_variantes and combinacion_pk:
                combinacion = CombinacionVariante.objects.filter(
                    pk=combinacion_pk, producto=producto, activo=True
                ).first()
                if combinacion is None:
                    errores.append(
                        f'Ítem {idx}: la combinación indicada no existe o no pertenece al producto.'
                    )
                    continue

            # — Fecha de vencimiento (opcional, requerida para perecederos) —
            fecha_vencimiento = None
            fv_raw = raw.get('fecha_vencimiento')
            if fv_raw:
                try:
                    from datetime import datetime
                    fecha_vencimiento = datetime.strptime(fv_raw, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass  # Si el formato es inválido, se deja como None

            ItemCompra.objects.create(
                compra         = compra,
                producto       = producto,
                proveedor      = proveedor,
                combinacion    = combinacion,
                cantidad       = cantidad,
                costo_unitario = costo_unitario,
                moneda         = raw.get('moneda', 'ARS'),
                descuento_pct  = descuento_pct,
                condicion_pago = raw.get('condicion_pago', 'contado'),
                referencia     = raw.get('referencia', ''),
                notas          = raw.get('notas', ''),
                fecha_vencimiento = fecha_vencimiento,
            )

        if errores:
            compra.delete()
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # Calcular total sin confirmar (para mostrarlo en el detalle)
        compra.total = sum(item.subtotal for item in compra.items.all())
        compra.save(update_fields=['total'])

        return JsonResponse({
            'ok':     True,
            'pk':     compra.pk,
            'numero': compra.numero,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Confirmar Compra  (desde el detalle del borrador)
#  Recibe { compra_pk, fecha, notas }, actualiza cabecera y confirma.
# ══════════════════════════════════════════════════════════════════

class ConfirmarCompraAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "compra_pk": 42,
        "fecha":     "2025-01-15",
        "notas":     "..."
    }

    1. Carga el borrador existente.
    2. Actualiza fecha y notas con editar_cabecera().
    3. Llama a compra.confirmar() → suma stock, calcula total, pasa a CONFIRMADA.
    4. Devuelve { ok, pk, numero, total }.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra_pk = body.get('compra_pk')
        fecha     = body.get('fecha', '').strip()

        if not compra_pk:
            return JsonResponse({'error': 'compra_pk requerido.'}, status=400)
        if not fecha:
            return JsonResponse({'error': 'La fecha es requerida.'}, status=400)

        compra = get_object_or_404(Compra, pk=compra_pk)

        if compra.estado != EstadoCompra.BORRADOR:
            return JsonResponse(
                {'error': f'La compra ya está en estado "{compra.get_estado_display()}". Solo se pueden confirmar borradores.'},
                status=400
            )

        # Actualizar cabecera antes de confirmar
        try:
            compra.editar_cabecera(fecha=fecha, notas=body.get('notas', ''))
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        # Confirmar: suma stock + calcula total + pasa a CONFIRMADA
        try:
            compra.confirmar()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':     True,
            'pk':     compra.pk,
            'numero': compra.numero,
            'total':  str(compra.total),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar Borrador  (botón "Volver" desde el detalle)
#  Solo elimina si está en BORRADOR — no toca stock.
# ══════════════════════════════════════════════════════════════════

class EliminarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON { "compra_pk": 42 }

    Elimina un borrador sin pasar por el flujo de anulación
    (el stock nunca fue modificado, así que basta con borrar).
    Solo opera sobre compras en estado BORRADOR.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra_pk = body.get('compra_pk')
        if not compra_pk:
            return JsonResponse({'error': 'compra_pk requerido.'}, status=400)

        compra = get_object_or_404(Compra, pk=compra_pk)

        if compra.estado != EstadoCompra.BORRADOR:
            return JsonResponse(
                {'error': 'Solo se pueden eliminar borradores desde este endpoint.'},
                status=400
            )

        compra.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Documentos de compra
# ══════════════════════════════════════════════════════════════════

import os
from .models import CompraDocumento
from django.shortcuts import render as _render


class CompraDocumentoSubirAjax(LoginRequiredMixin, View):
    """
    POST multipart → sube un documento a una compra existente.
    Funciona tanto para borradores como para compras confirmadas.
    Campos: compra_pk, archivo, tipo (opcional), descripcion (opcional)
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        compra_pk = request.POST.get('compra_pk')
        if not compra_pk:
            return JsonResponse({'error': 'compra_pk requerido.'}, status=400)

        archivo = request.FILES.get('archivo')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

        if archivo.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 10 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        PERMITIDOS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf'}
        if ext not in PERMITIDOS:
            return JsonResponse(
                {'error': 'Tipo de archivo no permitido. Usá JPG, PNG, WEBP, GIF o PDF.'},
                status=400
            )

        compra = get_object_or_404(Compra, pk=compra_pk)

        doc = CompraDocumento(
            compra      = compra,
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


class CompraDocumentoEliminarAjax(LoginRequiredMixin, View):
    """POST JSON { pk } → elimina el documento y el archivo del disco."""

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        doc = get_object_or_404(CompraDocumento, pk=pk)

        if doc.archivo and os.path.isfile(doc.archivo.path):
            os.remove(doc.archivo.path)

        doc.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  VISTA — Detalle de compra
#  Sirve tanto para BORRADOR (con botón Confirmar) como para
#  CONFIRMADA/ANULADA (solo lectura + documentos).
# ══════════════════════════════════════════════════════════════════

class DetalleCompraView(LoginRequiredMixin, View):
    """
    GET /compras/detalle/<pk>/

    Contexto extra respecto a la versión anterior:
      - es_borrador: bool → el template muestra el formulario de confirmación
      - url_confirmar, url_eliminar_borrador, url_nueva_compra: para el JS
    """
    template_name = 'compras/detalle_compra.html'

    def get(self, request, pk):
        if not chequear_permiso(request.user, 'crear_compras'):
            from django.shortcuts import redirect
            return redirect('core:dashboard')

        compra = get_object_or_404(
            Compra.objects.prefetch_related(
                'items__producto',
                'items__proveedor',
                'items__combinacion',
                'documentos',
            ),
            pk=pk
        )

        from django.urls import reverse
        return _render(request, self.template_name, {
            'compra':     compra,
            'items':      compra.items.select_related('producto', 'proveedor', 'combinacion').all(),
            'documentos': compra.documentos.all(),
            # — Flags para el template —
            'es_borrador': compra.estado == EstadoCompra.BORRADOR,
            # — URLs para el JS del template —
            'url_confirmar':        reverse('compras:confirmar_compra'),
            'url_eliminar_borrador': reverse('compras:eliminar_borrador'),
            'url_nueva_compra':     reverse('compras:nueva_compra'),
            'url_historial':        reverse('compras:historial_compras'),
            'url_doc_subir':        reverse('compras:documento_subir'),
            'url_doc_eliminar':     reverse('compras:documento_eliminar'),
        })