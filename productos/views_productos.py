import json
import os
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator

from .models import (
    Producto, ProductoImagen,
    CategoriaProducto, TipoProducto,
)
from .forms import (
    ProductoForm, ProductoImagenForm,
    CategoriaProductoForm, TipoProductoForm,
)
from core.permisos import chequear_permiso  # ← único import nuevo


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
        'precio_mayorista':      str(p.precio_mayorista) if p.precio_mayorista else '',
        'precio_oferta':         str(p.precio_oferta) if p.precio_oferta else '',
        'alicuota_iva':          p.alicuota_iva,
        'precio_incluye_iva':    p.precio_incluye_iva,
        'stock_actual':          str(p.stock_actual),
        'stock_minimo':          str(p.stock_minimo),
        'stock_maximo':          str(p.stock_maximo) if p.stock_maximo else '',
        'permite_stock_negativo': p.permite_stock_negativo,
        'gestiona_stock':        p.gestiona_stock,
        'estado':                p.estado,
        'publicado':             p.publicado,
        'destacado':             p.destacado,
        'requiere_refrigeracion': p.requiere_refrigeracion,
        'es_fragil':             p.es_fragil,
        'es_peligroso':          p.es_peligroso,
        'posicion_deposito':     p.posicion_deposito,
        'notas':                 p.notas,
        'tags':                  p.tags,
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

        # ── Permisos para el template ─────────────────────────────
        ctx['puede_crear']    = chequear_permiso(self.request.user, 'crear_productos')
        ctx['puede_editar']   = chequear_permiso(self.request.user, 'editar_productos')
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, 'eliminar_productos')
        ctx['puede_gestionar_categorias'] = chequear_permiso(self.request.user, 'gestionar_categorias')

        if not chequear_permiso(self.request.user, 'ver_productos'):
            ctx['sin_permiso'] = True
            return ctx

        qs = Producto.objects.select_related('categoria', 'tipo', 'proveedor').all()

        # — Búsqueda —
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(nombre__icontains=q)         \
                 | qs.filter(codigo__icontains=q)       \
                 | qs.filter(sku__icontains=q)          \
                 | qs.filter(marca__icontains=q)        \
                 | qs.filter(codigo_barras__icontains=q)

        # — Filtros —
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

        # Crear o editar requieren permisos distintos
        permiso = 'editar_productos' if inst else 'crear_productos'
        if not chequear_permiso(request.user, permiso):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        form = ProductoForm(body, instance=inst)

        if form.is_valid():
            producto = form.save()
            return JsonResponse({
                'ok':     True,
                'pk':     producto.pk,
                'codigo': producto.codigo,
                'nombre': producto.nombre,
                'creado': inst is None,
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

        # Eliminar archivos físicos de imágenes antes de borrar el registro
        for img in producto.imagenes.all():
            if img.imagen and os.path.isfile(img.imagen.path):
                os.remove(img.imagen.path)

        nombre = str(producto)
        producto.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})


class ProductoBuscarAjax(LoginRequiredMixin, View):
    """GET → búsqueda rápida para selects/autocomplete (ej: en compras)."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q  = request.GET.get('q', '').strip()
        qs = Producto.objects.filter(estado='activo').order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(codigo__icontains=q)
        data = [
            {'pk': p.pk, 'codigo': p.codigo, 'nombre': p.nombre,
             'precio': str(p.precio_venta) if p.precio_venta else ''}
            for p in qs[:20]
        ]
        return JsonResponse({'results': data})


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

        producto = get_object_or_404(Producto, pk=pk)

        # Determinar si es la primera imagen (se vuelve portada automáticamente)
        es_portada = not producto.imagenes.exists()

        img = ProductoImagen(
            producto   = producto,
            imagen     = imagen,
            es_portada = es_portada,
            descripcion= request.POST.get('descripcion', ''),
            orden      = int(request.POST.get('orden', 0)),
        )
        img.save()

        return JsonResponse({
            'ok':       True,
            'imagen_pk': img.pk,
            'url':      img.imagen.url,
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

        # Eliminar archivo físico
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
        img.save()  # el modelo se encarga de desmarcar las demás
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  CATEGORÍAS — AJAX (gestión desde el modal del producto)
# ══════════════════════════════════════════════════════════════════

class CategoriaListaAjax(LoginRequiredMixin, View):
    """GET → lista todas las categorías (para poblar el manager del modal)."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs   = CategoriaProducto.objects.all().order_by('orden', 'nombre')
        data = [_serializar_categoria(c) for c in qs]
        return JsonResponse({'results': data})


class CategoriaAccionesAjax(LoginRequiredMixin, View):
    """
    POST → crea o edita una categoría.
    Payload JSON: { pk (opcional), nombre, descripcion, orden, activo }
    """

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

        # Verificar unicidad
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
    """
    POST → elimina una categoría.
    Bloquea si tiene productos asociados.
    """

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

        cat = get_object_or_404(CategoriaProducto, pk=pk)

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
#  TIPOS — AJAX (gestión desde el modal del producto)
# ══════════════════════════════════════════════════════════════════

class TipoListaAjax(LoginRequiredMixin, View):
    """GET → lista todos los tipos (para poblar el manager del modal)."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs   = TipoProducto.objects.all().order_by('orden', 'nombre')
        data = [_serializar_tipo(t) for t in qs]
        return JsonResponse({'results': data})


class TipoAccionesAjax(LoginRequiredMixin, View):
    """
    POST → crea o edita un tipo.
    Payload JSON: { pk (opcional), nombre, descripcion, orden, activo }
    """

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

        # Verificar unicidad
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
    """
    POST → elimina un tipo.
    Bloquea si tiene productos asociados.
    """

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

        tipo = get_object_or_404(TipoProducto, pk=pk)

        total = tipo.productos.count()
        if total > 0:
            return JsonResponse({
                'ok':    False,
                'error': f'No se puede eliminar. Tiene {total} producto{"s" if total != 1 else ""} asociado{"s" if total != 1 else ""}.',
            }, status=400)

        nombre = tipo.nombre
        tipo.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})