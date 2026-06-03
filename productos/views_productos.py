import json
import os
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

from .models import (
    Producto, ProductoImagen, ProductoColor,
    CategoriaProducto, TipoProducto,
)
from .forms import (
    ProductoForm, ProductoImagenForm,
    CategoriaProductoForm, TipoProductoForm,
)
from core.permisos import chequear_permiso


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def _serializar_producto(p):
    """Serializa un Producto para respuestas JSON."""
    return {
        'pk':                    p.pk,
        'codigo':                p.codigo,
        'sku':                   p.sku,
        'codigo_barras':         p.codigo_barras,
        'nombre':                p.nombre,
        'nombre_corto':          p.nombre_corto,
        'descripcion':           p.descripcion,
        'descripcion_publica':   p.descripcion_publica,
        'categoria':             p.categoria_id,
        'tipo':                  p.tipo_id,
        'marca':                 p.marca,
        'modelo':                p.modelo,
        'fabricante':            p.fabricante,
        'pais_origen':           p.pais_origen,
        'proveedor':             p.proveedor_id,
        'unidad_medida':         p.unidad_medida,
        'contenido_neto':        str(p.contenido_neto) if p.contenido_neto else '',
        'peso_kg':               str(p.peso_kg) if p.peso_kg else '',
        'alto_cm':               str(p.alto_cm) if p.alto_cm else '',
        'ancho_cm':              str(p.ancho_cm) if p.ancho_cm else '',
        'profundidad_cm':        str(p.profundidad_cm) if p.profundidad_cm else '',
        'precio_venta':          str(p.precio_venta) if p.precio_venta else '',
        # alicuota_iva: se guarda siempre como '21' (general). No se expone al frontend.
        'stock_actual':          str(p.stock_actual),
        'stock_minimo':          str(p.stock_minimo),
        'stock_maximo':          str(p.stock_maximo) if p.stock_maximo else '',
        'permite_stock_negativo': p.permite_stock_negativo,
        'gestiona_stock':        p.gestiona_stock,
        'tiene_variantes_color': p.tiene_variantes_color,
        'color_unico':           p.color_unico,
        'estado':                p.estado,
        'publicado':             p.publicado,
        'destacado':             p.destacado,
        'requiere_refrigeracion': p.requiere_refrigeracion,
        'es_fragil':             p.es_fragil,
        'es_peligroso':          p.es_peligroso,
        'posicion_deposito':     p.posicion_deposito,
        'notas':                 p.notas,
        'tags':                  p.tags,
        # Indicadores útiles para el frontend
        'tiene_movimientos':     p.movimientos_stock.exists(),
        'total_colores':         p.colores.filter(activo=True).count() if p.tiene_variantes_color else 0,
    }


def _serializar_color(c):
    """Serializa un ProductoColor para respuestas JSON."""
    return {
        'pk':           c.pk,
        'producto_pk':  c.producto_id,
        'nombre':       c.nombre,
        'codigo_hex':   c.codigo_hex,
        'sku_variante': c.sku_variante,
        'sku_efectivo': c.sku_efectivo,
        'stock_actual': c.stock_actual,
        'activo':       c.activo,
    }


def _serializar_categoria(c):
    return {
        'pk':           c.pk,
        'nombre':       c.nombre,
        'descripcion':  c.descripcion,
        'orden':        c.orden,
        'activo':       c.activo,
        'total':        c.total_productos,
    }


def _serializar_tipo(t):
    return {
        'pk':           t.pk,
        'nombre':       t.nombre,
        'descripcion':  t.descripcion,
        'orden':        t.orden,
        'activo':       t.activo,
        'total':        t.total_productos,
    }


# ══════════════════════════════════════════════════════════════════
#  LISTADO / GESTIÓN PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class GestionProductosView(LoginRequiredMixin, TemplateView):
    """Vista principal — renderiza la página con la tabla de productos."""
    template_name = 'productos/productos.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        ctx['puede_crear']    = chequear_permiso(self.request.user, 'crear_productos')
        ctx['puede_editar']   = chequear_permiso(self.request.user, 'editar_productos')
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, 'eliminar_productos')
        ctx['puede_gestionar_categorias'] = chequear_permiso(self.request.user, 'gestionar_categorias')

        if not chequear_permiso(self.request.user, 'ver_productos'):
            ctx['sin_permiso'] = True
            return ctx

        qs = Producto.objects.select_related('categoria', 'tipo', 'proveedor').all()

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(nombre__icontains=q)         \
                 | qs.filter(codigo__icontains=q)       \
                 | qs.filter(sku__icontains=q)          \
                 | qs.filter(marca__icontains=q)        \
                 | qs.filter(codigo_barras__icontains=q)

        estado    = self.request.GET.get('estado', '')
        categoria = self.request.GET.get('categoria', '')
        tipo      = self.request.GET.get('tipo', '')
        stock_bajo = self.request.GET.get('stock_bajo', '')

        if estado:
            qs = qs.filter(estado=estado)
        if categoria:
            qs = qs.filter(categoria__pk=categoria)
        if tipo:
            qs = qs.filter(tipo__pk=tipo)
        if stock_bajo == '1':
            from django.db.models import F
            qs = qs.filter(gestiona_stock=True, stock_actual__lte=F('stock_minimo'))

        qs = qs.order_by('nombre')
        paginator = Paginator(qs, 20)
        page      = self.request.GET.get('page', 1)

        ctx['productos']   = paginator.get_page(page)
        ctx['form']        = ProductoForm()
        ctx['total']       = Producto.objects.count()
        ctx['activos']     = Producto.objects.filter(estado='activo').count()
        ctx['publicados']  = Producto.objects.filter(publicado=True).count()
        ctx['categorias']  = CategoriaProducto.objects.filter(activo=True).order_by('orden', 'nombre')
        ctx['tipos']       = TipoProducto.objects.filter(activo=True).order_by('orden', 'nombre')
        ctx['q']           = q
        ctx['filtro_estado']    = estado
        ctx['filtro_categoria'] = categoria
        ctx['filtro_tipo']      = tipo
        ctx['filtro_stock_bajo'] = stock_bajo
        return ctx


# ══════════════════════════════════════════════════════════════════
#  CRUD PRODUCTO — AJAX
# ══════════════════════════════════════════════════════════════════

class ProductoCrearEditarAjax(LoginRequiredMixin, View):
    """
    GET  → devuelve datos del producto para precargar el modal de edición.
    POST → crea o edita un producto.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.GET.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)
        producto = get_object_or_404(Producto, pk=pk)
        return JsonResponse(_serializar_producto(producto))

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk   = body.get('pk')
        inst = get_object_or_404(Producto, pk=pk) if pk else None

        permiso = 'editar_productos' if inst else 'crear_productos'
        if not chequear_permiso(request.user, permiso):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        # Validar intento de activar variantes en producto con movimientos de stock
        if inst and body.get('tiene_variantes_color') and not inst.tiene_variantes_color:
            if inst.movimientos_stock.exists():
                # No bloqueamos, pero el frontend ya mostró la advertencia.
                # El backend acepta el cambio — el stock existente queda en stock_actual
                # y el usuario deberá asignarlo manualmente a los colores.
                pass

        # Django's CheckboxInput no reconoce True/False nativos de JSON —
        # espera 'on', 'true' o '1'. Normalizamos todos los booleanos del payload.
        BOOL_FIELDS = [
            'publicado', 'destacado',
            'requiere_refrigeracion', 'es_fragil', 'es_peligroso',
            'gestiona_stock', 'permite_stock_negativo',
            'tiene_variantes_color',
        ]
        form_data = dict(body)
        for f in BOOL_FIELDS:
            if f in form_data:
                form_data[f] = 'on' if form_data[f] else ''

        # alicuota_iva no se captura del frontend — se fuerza siempre a General (21%)
        form_data['alicuota_iva'] = '21'

        form = ProductoForm(form_data, instance=inst)

        if form.is_valid():
            producto = form.save()

            # stock_minimo y stock_maximo se asignan aqui explicitamente porque
            # pueden no estar en los fields del ProductoForm (se ignoran en silence).
            update_fields = []
            try:
                stock_minimo = int(body.get('stock_minimo') or 0)
                if stock_minimo < 0:
                    stock_minimo = 0
                producto.stock_minimo = stock_minimo
                update_fields.append('stock_minimo')
            except (TypeError, ValueError):
                pass

            raw_maximo = body.get('stock_maximo')
            if raw_maximo not in (None, '', 'null'):
                try:
                    stock_maximo = int(raw_maximo)
                    if stock_maximo >= 0:
                        producto.stock_maximo = stock_maximo
                        update_fields.append('stock_maximo')
                except (TypeError, ValueError):
                    pass
            else:
                producto.stock_maximo = None
                update_fields.append('stock_maximo')

            if update_fields:
                producto.save(update_fields=update_fields)

            return JsonResponse({
                'ok':           True,
                'pk':           producto.pk,
                'codigo':       producto.codigo,
                'nombre':       producto.nombre,
                'creado':       inst is None,
                'stock_minimo': str(producto.stock_minimo),
                'stock_maximo': str(producto.stock_maximo) if producto.stock_maximo else '',
            })

        return JsonResponse({'ok': False, 'errors': form.errors}, status=400)


class ProductoEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina un producto (y sus imágenes físicas del disco)."""

    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)

        producto = get_object_or_404(Producto, pk=pk)

        for img in producto.imagenes.all():
            if img.imagen and os.path.isfile(img.imagen.path):
                os.remove(img.imagen.path)

        nombre = str(producto)
        producto.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})


class ProductoBuscarAjax(LoginRequiredMixin, View):
    """
    GET → búsqueda rápida para selects/autocomplete (ej: en compras).
    Incluye colores activos cuando el producto tiene variantes de color.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q  = request.GET.get('q', '').strip()
        qs = Producto.objects.filter(estado='activo').order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(codigo__icontains=q)

        data = []
        for p in qs[:20]:
            item = {
                'pk':                    p.pk,
                'codigo':                p.codigo,
                'nombre':                p.nombre,
                'precio':                str(p.precio_venta) if p.precio_venta else '',
                'tiene_variantes_color': p.tiene_variantes_color,
                'colores':               [],
            }
            if p.tiene_variantes_color:
                item['colores'] = [
                    _serializar_color(c)
                    for c in p.colores.filter(activo=True).order_by('nombre')
                ]
            data.append(item)

        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  VARIANTES DE COLOR — AJAX
# ══════════════════════════════════════════════════════════════════

class ProductoColorListaAjax(LoginRequiredMixin, View):
    """
    GET ?producto_pk=<pk> → lista todos los colores de un producto.
    Incluye activos e inactivos para que el formulario pueda mostrarlos todos.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.GET.get('producto_pk')
        if not pk:
            return JsonResponse({'error': 'producto_pk requerido.'}, status=400)

        producto = get_object_or_404(Producto, pk=pk)
        colores  = producto.colores.all().order_by('nombre')

        return JsonResponse({
            'colores':               [_serializar_color(c) for c in colores],
            'tiene_variantes_color': producto.tiene_variantes_color,
            'stock_total':           str(producto.stock_actual),
        })


class ProductoColorAccionesAjax(LoginRequiredMixin, View):
    """
    POST → crea o edita un color de producto.

    Payload JSON:
      {
        pk           (int, opcional — si viene, edita; si no, crea),
        producto_pk  (int, requerido al crear),
        nombre       (str, requerido),
        codigo_hex   (str, opcional, formato #RRGGBB),
        sku_variante (str, opcional),
        stock_actual (decimal, requerido al crear, ignorado en edición de datos),
        stock_minimo (decimal, opcional),
        orden        (int, opcional),
      }

    Al crear, stock_actual se aplica directamente y dispara la sincronización
    en Producto.stock_actual via ProductoColor.save().
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')

        # ── Edición ──────────────────────────────────────────────
        if pk:
            color = get_object_or_404(ProductoColor, pk=pk)

            nombre = body.get('nombre', '').strip()
            if not nombre:
                return JsonResponse({
                    'ok': False, 'errors': {'nombre': ['El nombre es obligatorio.']}
                }, status=400)

            # Verificar unicidad dentro del producto (excluyendo el actual)
            if (ProductoColor.objects
                    .filter(producto=color.producto, nombre__iexact=nombre)
                    .exclude(pk=pk)
                    .exists()):
                return JsonResponse({
                    'ok': False, 'errors': {'nombre': ['Ya existe un color con ese nombre para este producto.']}
                }, status=400)

            color.nombre       = nombre
            color.codigo_hex   = body.get('codigo_hex', color.codigo_hex).strip()
            color.sku_variante = body.get('sku_variante', color.sku_variante).strip()

            color.save()  # dispara sincronización en Producto.stock_actual
            return JsonResponse({'ok': True, 'creado': False, 'color': _serializar_color(color)})

        # ── Creación ─────────────────────────────────────────────
        producto_pk = body.get('producto_pk')
        if not producto_pk:
            return JsonResponse({'error': 'producto_pk requerido.'}, status=400)

        producto = get_object_or_404(Producto, pk=producto_pk)

        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({
                'ok': False, 'errors': {'nombre': ['El nombre es obligatorio.']}
            }, status=400)

        if ProductoColor.objects.filter(producto=producto, nombre__iexact=nombre).exists():
            return JsonResponse({
                'ok': False, 'errors': {'nombre': ['Ya existe un color con ese nombre para este producto.']}
            }, status=400)

        # Validar hex si viene
        codigo_hex = body.get('codigo_hex', '').strip()
        if codigo_hex and (len(codigo_hex) != 7 or not codigo_hex.startswith('#')):
            return JsonResponse({
                'ok': False, 'errors': {'codigo_hex': ['Formato inválido. Use #RRGGBB.']}
            }, status=400)

        try:
            stock_actual = int(body.get('stock_actual', 0))
            if stock_actual < 0:
                raise ValueError
        except (TypeError, ValueError):
            return JsonResponse({
                'ok': False, 'errors': {'stock_actual': ['La cantidad no puede ser negativa.']}
            }, status=400)

        color = ProductoColor(
            producto     = producto,
            nombre       = nombre,
            codigo_hex   = codigo_hex,
            sku_variante = body.get('sku_variante', '').strip(),
            stock_actual = stock_actual,
        )
        color.save()  # dispara sincronización en Producto.stock_actual

        return JsonResponse({'ok': True, 'creado': True, 'color': _serializar_color(color)})


class ProductoColorStockAjax(LoginRequiredMixin, View):
    """
    POST → ajusta el stock_actual de un color específico.
    No pasa por MovimientoStock (sprint actual).

    Payload JSON:
      {
        pk           (int, requerido — pk del ProductoColor),
        stock_actual (decimal, requerido — nuevo valor absoluto de stock),
      }

    FUTURO: cuando MovimientoStock tenga FK a ProductoColor, este endpoint
    deberá crear un MovimientoStock de tipo AJUSTE_POS o AJUSTE_NEG según
    la diferencia, para mantener el historial completo.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'ajustar_stock'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        color = get_object_or_404(ProductoColor, pk=pk)

        try:
            nuevo_stock = int(body.get('stock_actual'))
            if nuevo_stock < 0 and not color.producto.permite_stock_negativo:
                raise ValueError('Stock negativo no permitido para este producto.')
        except (TypeError, ValueError) as e:
            if 'negativo' in str(e):
                return JsonResponse({'ok': False, 'error': str(e)}, status=400)
            return JsonResponse({
                'ok': False, 'error': 'La cantidad debe ser un número entero válido.'
            }, status=400)

        stock_anterior   = color.stock_actual
        color.stock_actual = nuevo_stock
        color.save()  # dispara sincronización en Producto.stock_actual

        color.producto.refresh_from_db()

        return JsonResponse({
            'ok':              True,
            'stock_anterior':  str(stock_anterior),
            'stock_posterior': str(nuevo_stock),
            'stock_total':     str(color.producto.stock_actual),
            'color':           _serializar_color(color),
        })


class ProductoColorToggleActivoAjax(LoginRequiredMixin, View):
    """
    POST → activa o desactiva un color (no lo elimina).
    Desactivar un color lo excluye del stock total del producto.

    Payload JSON: { pk (int) }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        color        = get_object_or_404(ProductoColor, pk=pk)
        color.activo = not color.activo
        color.save()  # dispara sincronización en Producto.stock_actual

        return JsonResponse({
            'ok':    True,
            'activo': color.activo,
            'color':  _serializar_color(color),
        })


# ══════════════════════════════════════════════════════════════════
#  IMÁGENES — AJAX
# ══════════════════════════════════════════════════════════════════

class ProductoImagenSubirAjax(LoginRequiredMixin, View):
    """POST → sube una imagen al producto (multipart/form-data)."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.POST.get('producto_pk')
        if not pk:
            return JsonResponse({'error': 'producto_pk requerido.'}, status=400)

        imagen = request.FILES.get('imagen')
        if not imagen:
            return JsonResponse({'error': 'No se recibió ninguna imagen.'}, status=400)

        producto  = get_object_or_404(Producto, pk=pk)
        es_portada = not producto.imagenes.exists()

        img = ProductoImagen(
            producto    = producto,
            imagen      = imagen,
            es_portada  = es_portada,
            descripcion = request.POST.get('descripcion', ''),
            orden       = int(request.POST.get('orden', 0)),
        )
        img.save()

        return JsonResponse({
            'ok':        True,
            'imagen_pk': img.pk,
            'url':       img.imagen.url,
            'es_portada': img.es_portada,
        })


class ProductoImagenEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina una imagen del producto."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk  = body.get('pk')
        img = get_object_or_404(ProductoImagen, pk=pk)

        if img.imagen and os.path.isfile(img.imagen.path):
            os.remove(img.imagen.path)

        img.delete()
        return JsonResponse({'ok': True})


class ProductoImagenPortadaAjax(LoginRequiredMixin, View):
    """POST → marca una imagen como portada (y desmarca las demás)."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk  = body.get('pk')
        img = get_object_or_404(ProductoImagen, pk=pk)
        img.es_portada = True
        img.save()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  CATEGORÍAS — AJAX
# ══════════════════════════════════════════════════════════════════

class CategoriaListaAjax(LoginRequiredMixin, View):
    """GET → lista todas las categorías."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs   = CategoriaProducto.objects.all().order_by('orden', 'nombre')
        data = [_serializar_categoria(c) for c in qs]
        return JsonResponse({'results': data})


class CategoriaAccionesAjax(LoginRequiredMixin, View):
    """POST → crea o edita una categoría."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_categorias'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'ok': False, 'errors': {'nombre': ['El nombre es obligatorio.']}}, status=400)

        pk = body.get('pk')
        if pk:
            cat = get_object_or_404(CategoriaProducto, pk=pk)
        else:
            cat = CategoriaProducto()

        qs = CategoriaProducto.objects.filter(nombre__iexact=nombre)
        if cat.pk:
            qs = qs.exclude(pk=cat.pk)
        if qs.exists():
            return JsonResponse({'ok': False, 'errors': {'nombre': ['Ya existe una categoría con ese nombre.']}}, status=400)

        cat.nombre      = nombre
        cat.descripcion = body.get('descripcion', cat.descripcion if cat.pk else '')
        cat.orden       = int(body.get('orden', cat.orden if cat.pk else 0))
        cat.activo      = body.get('activo', True)
        cat.save()

        return JsonResponse({
            'ok':    True,
            'pk':    cat.pk,
            'nombre': cat.nombre,
            'creado': pk is None,
            'data':  _serializar_categoria(cat),
        })


class CategoriaEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina una categoría. Bloquea si tiene productos asociados."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_categorias'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)

        cat   = get_object_or_404(CategoriaProducto, pk=pk)
        total = cat.productos.count()
        if total > 0:
            return JsonResponse({
                'ok':    False,
                'error': f'No se puede eliminar. Tiene {total} producto{"s" if total != 1 else ""} asociado{"s" if total != 1 else ""}.',
            }, status=400)

        nombre = cat.nombre
        cat.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})


# ══════════════════════════════════════════════════════════════════
#  TIPOS — AJAX
# ══════════════════════════════════════════════════════════════════

class TipoListaAjax(LoginRequiredMixin, View):
    """GET → lista todos los tipos."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs   = TipoProducto.objects.all().order_by('orden', 'nombre')
        data = [_serializar_tipo(t) for t in qs]
        return JsonResponse({'results': data})


class TipoAccionesAjax(LoginRequiredMixin, View):
    """POST → crea o edita un tipo."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_categorias'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'ok': False, 'errors': {'nombre': ['El nombre es obligatorio.']}}, status=400)

        pk = body.get('pk')
        if pk:
            tipo = get_object_or_404(TipoProducto, pk=pk)
        else:
            tipo = TipoProducto()

        qs = TipoProducto.objects.filter(nombre__iexact=nombre)
        if tipo.pk:
            qs = qs.exclude(pk=tipo.pk)
        if qs.exists():
            return JsonResponse({'ok': False, 'errors': {'nombre': ['Ya existe un tipo con ese nombre.']}}, status=400)

        tipo.nombre      = nombre
        tipo.descripcion = body.get('descripcion', tipo.descripcion if tipo.pk else '')
        tipo.orden       = int(body.get('orden', tipo.orden if tipo.pk else 0))
        tipo.activo      = body.get('activo', True)
        tipo.save()

        return JsonResponse({
            'ok':    True,
            'pk':    tipo.pk,
            'nombre': tipo.nombre,
            'creado': pk is None,
            'data':  _serializar_tipo(tipo),
        })


class TipoEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina un tipo. Bloquea si tiene productos asociados."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_categorias'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)

        tipo  = get_object_or_404(TipoProducto, pk=pk)
        total = tipo.productos.count()
        if total > 0:
            return JsonResponse({
                'ok':    False,
                'error': f'No se puede eliminar. Tiene {total} producto{"s" if total != 1 else ""} asociado{"s" if total != 1 else ""}.',
            }, status=400)

        nombre = tipo.nombre
        tipo.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})