import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from productos.models import Producto, Proveedor
from .models import Compra, ItemCompra, EstadoCompra
from core.permisos import chequear_permiso  # ← nuevo


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Nueva Compra
# ══════════════════════════════════════════════════════════════════

class NuevaCompraView(LoginRequiredMixin, TemplateView):
    """Renderiza el formulario / carrito para crear una nueva compra."""
    template_name = 'compras/nueva_compra.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['puede_crear'] = chequear_permiso(self.request.user, 'crear_compras')  # ← nuevo
        if not chequear_permiso(self.request.user, 'crear_compras'):               # ← nuevo
            ctx['sin_permiso'] = True                                              # ← nuevo
            return ctx                                                             # ← nuevo
        ctx['today'] = timezone.now().date().isoformat()
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar productos (para el buscador del carrito)
# ══════════════════════════════════════════════════════════════════

class BuscarProductoAjax(LoginRequiredMixin, View):
    """GET ?q=texto → lista de productos para el autocomplete."""

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):          # ← nuevo
            return JsonResponse({'error': 'Sin permiso.'}, status=403)  # ← nuevo

        q  = request.GET.get('q', '').strip()
        qs = Producto.objects.filter(estado='activo').order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(codigo__icontains=q)
        data = [
            {
                'pk':            p.pk,
                'codigo':        p.codigo,
                'nombre':        p.nombre,
                'unidad_medida': p.get_unidad_medida_display(),
                'stock_actual':  str(p.stock_actual),
                'stock_minimo':  str(p.stock_minimo),
                'categoria':     p.categoria.nombre if p.categoria else '',
                'tipo':          p.tipo.nombre if p.tipo else '',
                'marca':         p.marca,
                'modelo':        p.modelo,
                'proveedor_pk':  p.proveedor_id or '',
                'proveedor':     p.proveedor.nombre if p.proveedor else '',
            }
            for p in qs[:30]
        ]
        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar proveedores (para el select de cada ítem)
# ══════════════════════════════════════════════════════════════════

class BuscarProveedorAjax(LoginRequiredMixin, View):
    """GET ?q=texto → lista de proveedores activos."""

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):          # ← nuevo
            return JsonResponse({'error': 'Sin permiso.'}, status=403)  # ← nuevo

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
#  AJAX — Confirmar Compra
# ══════════════════════════════════════════════════════════════════

class ConfirmarCompraAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "fecha": "2025-01-15",
        "notas": "...",
        "items": [
            {
                "producto_pk": 1,
                "proveedor_pk": 2,       // opcional
                "cantidad": "10.000",
                "costo_unitario": "150.00",
                "moneda": "ARS",
                "descuento_pct": "0",
                "condicion_pago": "contado",
                "referencia": "FA-0001",
                "notas": ""
            },
            ...
        ]
    }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):          # ← nuevo
            return JsonResponse({'error': 'Sin permiso.'}, status=403)  # ← nuevo

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        # — Validaciones básicas —
        fecha = body.get('fecha')
        items = body.get('items', [])

        if not fecha:
            return JsonResponse({'error': 'La fecha es requerida.'}, status=400)
        if not items:
            return JsonResponse({'error': 'El carrito está vacío.'}, status=400)

        # — Crear cabecera —
        compra = Compra(
            fecha      = fecha,
            notas      = body.get('notas', ''),
            creado_por = request.user,
        )
        compra.save()

        errores = []
        for idx, raw in enumerate(items, start=1):
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

            proveedor = None
            proveedor_pk = raw.get('proveedor_pk')
            if proveedor_pk:
                proveedor = Proveedor.objects.filter(pk=proveedor_pk).first()

            ItemCompra.objects.create(
                compra         = compra,
                producto       = producto,
                proveedor      = proveedor,
                cantidad       = cantidad,
                costo_unitario = costo_unitario,
                moneda         = raw.get('moneda', 'ARS'),
                descuento_pct  = descuento_pct,
                condicion_pago = raw.get('condicion_pago', 'contado'),
                referencia     = raw.get('referencia', ''),
                notas          = raw.get('notas', ''),
            )

        if errores:
            compra.delete()
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # — Confirmar: actualiza stock + totales —
        try:
            compra.confirmar()
        except ValueError as e:
            compra.delete()
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':     True,
            'numero': compra.numero,
            'total':  str(compra.total),
        })