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
    Variante, OpcionVariante, CombinacionVariante,
    CategoriaProducto, TipoProducto,
)
from .forms import (
    ProductoForm, ProductoImagenForm,
    CategoriaProductoForm, TipoProductoForm,
    VarianteForm, OpcionVarianteForm, CombinacionVarianteForm,
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
        'gestiona_variantes':    p.gestiona_variantes,
        'estado':                p.estado,
        'publicado':             p.publicado,
        'destacado':             p.destacado,
        'requiere_refrigeracion': p.requiere_refrigeracion,
        'es_fragil':             p.es_fragil,
        'es_peligroso':          p.es_peligroso,
        'es_perecedero':         p.es_perecedero,
        'posicion_deposito':     p.posicion_deposito,
        'notas':                 p.notas,
        'tags':                  p.tags,
        # Indicadores útiles para el frontend
        'tiene_movimientos':     p.movimientos_stock.exists(),
        'total_combinaciones':   p.combinaciones.filter(activo=True).count() if p.gestiona_variantes else 0,
    }


def _serializar_producto_fila(p):
    """
    Serializa un Producto con los campos que usa la tabla del listado
    (nombres de categoría/tipo, imagen, indicador de stock bajo, etc.).
    Se usa para repintar una fila de la tabla sin recargar la página
    entera — a diferencia de _serializar_producto(), que sirve para
    precargar el formulario de edición.
    """
    imagen = p.imagen_principal
    return {
        'pk':                    p.pk,
        'codigo':                p.codigo,
        'sku':                   p.sku,
        'nombre':                p.nombre,
        'marca':                 p.marca,
        'modelo':                p.modelo,
        'gestiona_variantes':    p.gestiona_variantes,
        'categoria_nombre':      p.categoria.nombre if p.categoria_id else '',
        'tipo_nombre':           p.tipo.nombre if p.tipo_id else '',
        'precio_venta':          str(p.precio_venta) if p.precio_venta else '',
        'gestiona_stock':        p.gestiona_stock,
        'stock_actual':          str(p.stock_actual),
        'stock_bajo':            p.stock_bajo,
        'stock_minimo':          str(p.stock_minimo),
        'unidad_medida_display': p.get_unidad_medida_display(),
        'estado':                p.estado,
        'publicado':             p.publicado,
        'imagen_url':            imagen.imagen.url if imagen else '',
    }


def _serializar_variante(v):
    """Serializa una Variante para respuestas JSON."""
    return {
        'pk':           v.pk,
        'nombre':       v.nombre,
        'descripcion':  v.descripcion,
        'orden':        v.orden,
        'activo':       v.activo,
        'total':        v.total_opciones,
    }


def _serializar_opcion_variante(o):
    """Serializa una OpcionVariante para respuestas JSON."""
    return {
        'pk':           o.pk,
        'variante_pk':  o.variante_id,
        'variante_nombre': o.variante.nombre,
        'nombre':       o.nombre,
        'descripcion':  o.descripcion,
        'orden':        o.orden,
        'activo':       o.activo,
    }


def _descripcion_combinacion(c):
    """Descripción legible de una combinación (campo o generada desde opciones)."""
    return c.descripcion_legible()


def _validar_payload_combinacion(producto, opciones_pks, combinacion_pk=None, codigo_barras=''):
    """Valida opciones, duplicados y código de barras único."""
    if not opciones_pks:
        return {'opciones': ['Debe seleccionar al menos una opción de variante.']}

    try:
        opciones_pks = [int(pk) for pk in opciones_pks]
    except (TypeError, ValueError):
        return {'opciones': ['Opciones de variante inválidas.']}

    opciones = list(
        OpcionVariante.objects.filter(pk__in=opciones_pks, activo=True)
        .select_related('variante')
    )
    if len(opciones) != len(set(opciones_pks)):
        return {'opciones': ['Una o más opciones no existen o están inactivas.']}

    variantes_ids = [op.variante_id for op in opciones]
    if len(variantes_ids) != len(set(variantes_ids)):
        return {
            'opciones': [
                'No puede haber dos valores del mismo tipo de variante en una combinación.'
            ],
        }

    objetivo = set(opciones_pks)
    for comb in producto.combinaciones.exclude(pk=combinacion_pk):
        existentes = set(comb.opciones.values_list('opcion_id', flat=True))
        if existentes == objetivo:
            return {'opciones': ['Ya existe una combinación con esas mismas opciones.']}

    codigo_barras = (codigo_barras or '').strip()
    if codigo_barras:
        qs = CombinacionVariante.objects.filter(codigo_barras=codigo_barras)
        if combinacion_pk:
            qs = qs.exclude(pk=combinacion_pk)
        if qs.exists():
            return {'codigo_barras': ['Ya existe otra combinación con ese código de barras.']}

        qs_prod = Producto.objects.filter(codigo_barras=codigo_barras)
        if qs_prod.exists():
            return {'codigo_barras': ['Ese código de barras ya está asignado a otro producto.']}

    return None


def _aplicar_opciones_combinacion(combinacion, opciones_pks):
    """Reemplaza las opciones de una combinación y sincroniza su descripción."""
    from .models import CombinacionVarianteOpcion

    combinacion.opciones.all().delete()
    for opcion_pk in opciones_pks:
        opcion = get_object_or_404(OpcionVariante, pk=opcion_pk)
        CombinacionVarianteOpcion.objects.create(combinacion=combinacion, opcion=opcion)
    combinacion.sincronizar_descripcion()


def _serializar_combinacion(c):
    """Serializa una CombinacionVariante para respuestas JSON."""
    desc = _descripcion_combinacion(c)
    return {
        'pk':                c.pk,
        'producto_pk':       c.producto_id,
        'codigo_barras':     c.codigo_barras,
        'sku_variante':      c.sku_variante,
        'sku_efectivo':      c.sku_efectivo,
        'stock_actual':      c.stock_actual,
        'activo':            c.activo,
        'descripcion':       desc,
        'descripcion_combinacion': desc,
        'opciones':          [
            _serializar_opcion_variante(op.opcion)
            for op in c.opciones.select_related('opcion__variante').all()
        ],
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
        if inst and body.get('gestiona_variantes') and not inst.gestiona_variantes:
            if inst.movimientos_stock.exists():
                # No bloqueamos, pero el frontend ya mostró la advertencia.
                # El backend acepta el cambio — el stock existente queda en stock_actual
                # y el usuario deberá asignarlo manualmente a las combinaciones.
                pass

        # Django's CheckboxInput no reconoce True/False nativos de JSON —
        # espera 'on', 'true' o '1'. Normalizamos todos los booleanos del payload.
        BOOL_FIELDS = [
            'publicado', 'destacado',
            'requiere_refrigeracion', 'es_fragil', 'es_peligroso', 'es_perecedero',
            'gestiona_stock', 'permite_stock_negativo',
            'gestiona_variantes',
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

            if producto.gestiona_variantes and producto.codigo_barras:
                producto.codigo_barras = ''
                producto.save(update_fields=['codigo_barras'])

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

            resultado = _serializar_producto_fila(producto)
            resultado['ok']           = True
            resultado['creado']       = inst is None
            resultado['stock_maximo'] = str(producto.stock_maximo) if producto.stock_maximo else ''
            return JsonResponse(resultado)

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
    Incluye combinaciones activas cuando el producto tiene variantes.
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
                'pk':                   p.pk,
                'codigo':               p.codigo,
                'nombre':               p.nombre,
                'precio':               str(p.precio_venta) if p.precio_venta else '',
                'gestiona_variantes':   p.gestiona_variantes,
                'combinaciones':        [],
            }
            if p.gestiona_variantes:
                item['combinaciones'] = [
                    _serializar_combinacion(c)
                    for c in p.combinaciones.filter(activo=True).order_by('pk')
                ]
            data.append(item)

        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  VARIANTES GENÉRICAS — AJAX
# ══════════════════════════════════════════════════════════════════

class VarianteListaAjax(LoginRequiredMixin, View):
    """GET → lista todas las variantes."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs   = Variante.objects.all().order_by('orden', 'nombre')
        data = [_serializar_variante(v) for v in qs]
        return JsonResponse({'results': data})


class VarianteAccionesAjax(LoginRequiredMixin, View):
    """POST → crea o edita una variante."""

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
            variante = get_object_or_404(Variante, pk=pk)
        else:
            variante = Variante()

        qs = Variante.objects.filter(nombre__iexact=nombre)
        if variante.pk:
            qs = qs.exclude(pk=variante.pk)
        if qs.exists():
            return JsonResponse({'ok': False, 'errors': {'nombre': ['Ya existe una variante con ese nombre.']}}, status=400)

        variante.nombre      = nombre
        variante.descripcion = body.get('descripcion', variante.descripcion if variante.pk else '')
        variante.orden       = int(body.get('orden', variante.orden if variante.pk else 0))
        variante.activo      = body.get('activo', True)
        variante.save()

        return JsonResponse({
            'ok':    True,
            'pk':    variante.pk,
            'nombre': variante.nombre,
            'creado': pk is None,
            'data':  _serializar_variante(variante),
        })


class VarianteEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina una variante. Bloquea si tiene opciones asociadas."""

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

        variante = get_object_or_404(Variante, pk=pk)
        total    = variante.opciones.count()
        if total > 0:
            return JsonResponse({
                'ok':    False,
                'error': f'No se puede eliminar. Tiene {total} opción{"es" if total != 1 else ""} asociada{"s" if total != 1 else ""}.',
            }, status=400)

        nombre = variante.nombre
        variante.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})


class OpcionVarianteListaAjax(LoginRequiredMixin, View):
    """GET ?variante_pk=<pk> → lista todas las opciones de una variante."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        variante_pk = request.GET.get('variante_pk')
        if variante_pk:
            qs = OpcionVariante.objects.filter(variante_id=variante_pk).order_by('orden', 'nombre')
        else:
            qs = OpcionVariante.objects.all().order_by('variante__orden', 'variante__nombre', 'orden', 'nombre')

        data = [_serializar_opcion_variante(o) for o in qs]
        return JsonResponse({'results': data})


class OpcionVarianteAccionesAjax(LoginRequiredMixin, View):
    """POST → crea o edita una opción de variante."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_categorias'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        variante_pk = body.get('variante_pk')
        if not variante_pk:
            return JsonResponse({'error': 'variante_pk requerido.'}, status=400)

        variante = get_object_or_404(Variante, pk=variante_pk)

        nombre = body.get('nombre', '').strip()
        if not nombre:
            return JsonResponse({'ok': False, 'errors': {'nombre': ['El nombre es obligatorio.']}}, status=400)

        pk = body.get('pk')
        if pk:
            opcion = get_object_or_404(OpcionVariante, pk=pk)
        else:
            opcion = OpcionVariante(variante=variante)

        qs = OpcionVariante.objects.filter(variante=variante, nombre__iexact=nombre)
        if opcion.pk:
            qs = qs.exclude(pk=opcion.pk)
        if qs.exists():
            return JsonResponse({'ok': False, 'errors': {'nombre': ['Ya existe una opción con ese nombre para esta variante.']}}, status=400)

        opcion.nombre      = nombre
        opcion.descripcion = body.get('descripcion', opcion.descripcion if opcion.pk else '')
        opcion.orden       = int(body.get('orden', opcion.orden if opcion.pk else 0))
        opcion.activo      = body.get('activo', True)
        opcion.save()

        return JsonResponse({
            'ok':    True,
            'pk':    opcion.pk,
            'nombre': opcion.nombre,
            'creado': pk is None,
            'data':  _serializar_opcion_variante(opcion),
        })


class OpcionVarianteEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina una opción de variante."""

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

        opcion = get_object_or_404(OpcionVariante, pk=pk)
        nombre = opcion.nombre
        opcion.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})


class CombinacionVarianteListaAjax(LoginRequiredMixin, View):
    """
    GET ?producto_pk=<pk> → lista todas las combinaciones de un producto.
    Incluye activas e inactivas para que el formulario pueda mostrarlas todas.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        pk = request.GET.get('producto_pk')
        if not pk:
            return JsonResponse({'error': 'producto_pk requerido.'}, status=400)

        producto      = get_object_or_404(Producto, pk=pk)
        combinaciones = producto.combinaciones.all().order_by('pk')

        return JsonResponse({
            'combinaciones':       [_serializar_combinacion(c) for c in combinaciones],
            'gestiona_variantes':  producto.gestiona_variantes,
            'stock_total':         str(producto.stock_actual),
        })


class CombinacionVarianteAccionesAjax(LoginRequiredMixin, View):
    """
    POST → crea o edita una combinación de variantes.

    Payload JSON:
      {
        pk           (int, opcional — si viene, edita; si no, crea),
        producto_pk  (int, requerido al crear),
        codigo_barras (str, opcional),
        sku_variante (str, opcional),
        stock_actual (decimal, requerido al crear),
        opciones     (list, requerido — lista de pk de OpcionVariante),
        activo       (bool, opcional),
      }
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
            combinacion = get_object_or_404(CombinacionVariante, pk=pk)
            codigo_barras = body.get('codigo_barras', combinacion.codigo_barras).strip()

            opciones_pks = body.get('opciones')
            if opciones_pks is not None:
                errores = _validar_payload_combinacion(
                    combinacion.producto,
                    opciones_pks,
                    combinacion_pk=combinacion.pk,
                    codigo_barras=codigo_barras,
                )
                if errores:
                    return JsonResponse({'ok': False, 'errors': errores}, status=400)

            combinacion.codigo_barras = codigo_barras
            combinacion.sku_variante = body.get('sku_variante', combinacion.sku_variante).strip()
            combinacion.activo = body.get('activo', combinacion.activo)

            if opciones_pks is not None:
                _aplicar_opciones_combinacion(combinacion, opciones_pks)

            combinacion.save()
            combinacion.refresh_from_db()
            return JsonResponse({
                'ok': True,
                'creado': False,
                'combinacion': _serializar_combinacion(combinacion),
            })

        # ── Creación ─────────────────────────────────────────────
        producto_pk = body.get('producto_pk')
        if not producto_pk:
            return JsonResponse({'error': 'producto_pk requerido.'}, status=400)

        producto = get_object_or_404(Producto, pk=producto_pk)
        opciones_pks = body.get('opciones', [])
        codigo_barras = body.get('codigo_barras', '').strip()

        errores = _validar_payload_combinacion(
            producto,
            opciones_pks,
            codigo_barras=codigo_barras,
        )
        if errores:
            return JsonResponse({'ok': False, 'errors': errores}, status=400)

        try:
            stock_actual = int(body.get('stock_actual', 0))
            if stock_actual < 0:
                raise ValueError
        except (TypeError, ValueError):
            return JsonResponse({
                'ok': False, 'errors': {'stock_actual': ['La cantidad no puede ser negativa.']},
            }, status=400)

        combinacion = CombinacionVariante(
            producto=producto,
            codigo_barras=codigo_barras,
            sku_variante=body.get('sku_variante', '').strip(),
            stock_actual=stock_actual,
            activo=body.get('activo', True),
        )
        combinacion.save()
        _aplicar_opciones_combinacion(combinacion, opciones_pks)
        combinacion.refresh_from_db()

        return JsonResponse({
            'ok': True,
            'creado': True,
            'combinacion': _serializar_combinacion(combinacion),
        })


class CombinacionVarianteStockAjax(LoginRequiredMixin, View):
    """
    POST → ajusta el stock_actual de una combinación específica.
    No pasa por MovimientoStock (sprint actual).

    Payload JSON:
      {
        pk           (int, requerido — pk del CombinacionVariante),
        stock_actual (decimal, requerido — nuevo valor absoluto de stock),
      }
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

        combinacion = get_object_or_404(CombinacionVariante, pk=pk)

        try:
            nuevo_stock = int(body.get('stock_actual'))
            if nuevo_stock < 0 and not combinacion.producto.permite_stock_negativo:
                raise ValueError('Stock negativo no permitido para este producto.')
        except (TypeError, ValueError) as e:
            if 'negativo' in str(e):
                return JsonResponse({'ok': False, 'error': str(e)}, status=400)
            return JsonResponse({
                'ok': False, 'error': 'La cantidad debe ser un número entero válido.'
            }, status=400)

        stock_anterior   = combinacion.stock_actual
        combinacion.stock_actual = nuevo_stock
        combinacion.save()  # dispara sincronización en Producto.stock_actual

        combinacion.producto.refresh_from_db()

        return JsonResponse({
            'ok':              True,
            'stock_anterior':  str(stock_anterior),
            'stock_posterior': str(nuevo_stock),
            'stock_total':     str(combinacion.producto.stock_actual),
            'combinacion':     _serializar_combinacion(combinacion),
        })


class CombinacionVarianteToggleActivoAjax(LoginRequiredMixin, View):
    """
    POST → activa o desactiva una combinación (no la elimina).
    Desactivar una combinación la excluye del stock total del producto.

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

        combinacion        = get_object_or_404(CombinacionVariante, pk=pk)
        combinacion.activo = not combinacion.activo
        combinacion.save()  # dispara sincronización en Producto.stock_actual

        return JsonResponse({
            'ok':          True,
            'activo':      combinacion.activo,
            'combinacion': _serializar_combinacion(combinacion),
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