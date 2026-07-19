import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import (
    Producto, PaqueteComponente, ModoPrecio, EstadoProducto, UnidadMedida,
    generar_codigo_barras_paquete,
)
from core.permisos import chequear_permiso


def _serializar_paquete(p):
    return {
        'pk':           p.pk,
        'nombre':       p.nombre,
        'codigo':       p.codigo,
        'codigo_barras': p.codigo_barras,
        'descripcion':  p.descripcion,
        'precio_venta': str(p.precio_venta) if p.precio_venta is not None else '',
        'activo':       p.estado == EstadoProducto.ACTIVO,
        'stock_disponible': p.stock_disponible_paquete,
        'componentes':  [
            {
                'pk':       comp.pk,
                'producto_pk': comp.producto_id,
                'nombre':   comp.producto.nombre,
                'codigo':   comp.producto.codigo,
                'cantidad': str(comp.cantidad),
            }
            for comp in p.componentes.select_related('producto').all()
        ],
    }


# ══════════════════════════════════════════════════════════════════
#  PÁGINA — Gestión de paquetes (dentro de Catálogo)
# ══════════════════════════════════════════════════════════════════

class GestionPaquetesView(LoginRequiredMixin, TemplateView):
    template_name = 'productos/paquetes.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'gestionar_paquetes'):
            ctx['sin_permiso'] = True
        return ctx


# ══════════════════════════════════════════════════════════════════
#  PAQUETES — AJAX
# ══════════════════════════════════════════════════════════════════

class PaqueteListaAjax(LoginRequiredMixin, View):
    """GET → lista todos los paquetes."""

    def get(self, request):
        if not chequear_permiso(request.user, 'gestionar_paquetes'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Producto.objects.filter(es_paquete=True).prefetch_related('componentes__producto').order_by('nombre')
        return JsonResponse({'results': [_serializar_paquete(p) for p in qs]})


class PaqueteAccionesAjax(LoginRequiredMixin, View):
    """POST → crea o edita un paquete (Producto con es_paquete=True) y sus componentes."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_paquetes'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        errors = {}

        nombre = body.get('nombre', '').strip()
        if not nombre:
            errors['nombre'] = ['El nombre es obligatorio.']

        try:
            precio_venta = Decimal(str(body.get('precio_venta', '')))
            if precio_venta < 0:
                errors['precio_venta'] = ['El precio no puede ser negativo.']
        except Exception:
            errors['precio_venta'] = ['El precio es inválido.']
            precio_venta = None

        componentes_raw = body.get('componentes', [])
        if not componentes_raw:
            errors['componentes'] = ['Agregá al menos un producto componente.']

        pk = body.get('pk')
        if pk:
            paquete = get_object_or_404(Producto, pk=pk, es_paquete=True)
        else:
            paquete = Producto(es_paquete=True)

        if nombre:
            qs = Producto.objects.filter(nombre__iexact=nombre, es_paquete=True)
            if paquete.pk:
                qs = qs.exclude(pk=paquete.pk)
            if qs.exists():
                errors['nombre'] = ['Ya existe un paquete con ese nombre.']

        # Validar componentes: productos reales, distintos del propio
        # paquete, que no sean a su vez otro paquete (nada de combos
        # anidados) y con cantidad > 0. Sin variantes en esta primera
        # versión — cada componente es un producto simple.
        componentes_validados = []
        vistos = set()
        for idx, c in enumerate(componentes_raw, start=1):
            producto_pk = c.get('producto_pk')
            producto_comp = Producto.objects.filter(pk=producto_pk).first()
            if not producto_comp:
                errors['componentes'] = [f'Componente {idx}: producto inválido.']
                break
            if paquete.pk and producto_comp.pk == paquete.pk:
                errors['componentes'] = ['Un paquete no puede tener a sí mismo como componente.']
                break
            if producto_comp.es_paquete:
                errors['componentes'] = [f'"{producto_comp.nombre}" es otro paquete — no se pueden anidar paquetes.']
                break
            try:
                cantidad = Decimal(str(c.get('cantidad', 0)))
                if cantidad <= 0:
                    raise ValueError
            except Exception:
                errors['componentes'] = [f'Componente {idx}: cantidad inválida.']
                break
            if producto_comp.pk in vistos:
                errors['componentes'] = [f'"{producto_comp.nombre}" está repetido — sumá la cantidad en una sola línea.']
                break
            vistos.add(producto_comp.pk)
            componentes_validados.append({'producto': producto_comp, 'cantidad': cantidad})

        if errors:
            return JsonResponse({'ok': False, 'errors': errors}, status=400)

        # El paquete no existe como producto físico hasta que se arma:
        # no tiene un código de barras de fábrica para escanear al
        # cargarlo. Siempre se genera uno propio (imprimible) para que
        # quede escaneable en caja como cualquier otro producto — no
        # se acepta uno a mano (no hay nada real que escanear todavía).
        # Al editar un paquete ya existente, conserva el que ya tenía.
        codigo_barras = paquete.codigo_barras if paquete.pk else generar_codigo_barras_paquete()

        paquete.nombre        = nombre
        paquete.descripcion   = body.get('descripcion', '')
        paquete.precio_venta  = precio_venta
        paquete.modo_precio   = ModoPrecio.MANUAL
        paquete.gestiona_stock = False
        paquete.unidad_medida = UnidadMedida.UNIDAD
        paquete.codigo_barras = codigo_barras
        paquete.estado        = EstadoProducto.ACTIVO if body.get('activo', True) else EstadoProducto.INACTIVO
        paquete.save()

        paquete.componentes.all().delete()
        for c in componentes_validados:
            PaqueteComponente.objects.create(
                paquete=paquete, producto=c['producto'], cantidad=c['cantidad'],
            )

        return JsonResponse({
            'ok':     True,
            'pk':     paquete.pk,
            'nombre': paquete.nombre,
            'creado': pk is None,
            'data':   _serializar_paquete(paquete),
        })


class PaqueteEliminarAjax(LoginRequiredMixin, View):
    """POST → elimina un paquete. Las ventas viejas conservan su snapshot
    (ItemVenta.producto_nombre), así que borrar el paquete no rompe el
    historial — mismo criterio que eliminar cualquier Producto."""

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_paquetes'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'PK requerido.'}, status=400)

        paquete = get_object_or_404(Producto, pk=pk, es_paquete=True)
        nombre = paquete.nombre
        paquete.delete()
        return JsonResponse({'ok': True, 'nombre': nombre})
