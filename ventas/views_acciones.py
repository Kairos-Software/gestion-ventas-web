import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

# ── IMPORTANTE: ProductoColor debe importarse para que editar_completa
#    pueda resolver las variantes y _restar_stock_item funcione correctamente ──
from productos.models import Producto, ProductoColor
from core.models import Cliente
from .models import Venta, EstadoVenta
from core.permisos import chequear_permiso


class AnularVentaAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'editar_ventas'):
            return JsonResponse({'error': 'No tenés permiso para anular ventas.'}, status=403)
        try:
            body = json.loads(request.body)
            pk   = body.get('pk')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta = get_object_or_404(Venta, pk=pk)
        try:
            venta.anular()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':           True,
            'numero':       venta.numero,
            'estado':       venta.estado,
            'estado_label': venta.get_estado_display(),
        })


class ReactivarVentaAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'editar_ventas'):
            return JsonResponse({'error': 'No tenés permiso para reactivar ventas.'}, status=403)
        try:
            body = json.loads(request.body)
            pk   = body.get('pk')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta = get_object_or_404(Venta, pk=pk)
        try:
            venta.reactivar()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':           True,
            'numero':       venta.numero,
            'estado':       venta.estado,
            'estado_label': venta.get_estado_display(),
        })


class EliminarVentaAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_ventas'):
            return JsonResponse({'error': 'No tenés permiso para eliminar ventas.'}, status=403)
        try:
            body = json.loads(request.body)
            pk   = body.get('pk')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta = get_object_or_404(Venta, pk=pk)

        if venta.estado == EstadoVenta.BORRADOR:
            return JsonResponse(
                {'error': 'Las ventas en borrador no se eliminan desde el historial.'},
                status=400
            )

        numero         = venta.numero
        era_confirmada = venta.estado == EstadoVenta.CONFIRMADA

        try:
            venta.delete()
        except Exception as e:
            return JsonResponse({'error': f'Error al eliminar: {str(e)}'}, status=500)

        return JsonResponse({
            'ok':              True,
            'numero':          numero,
            'stock_revertido': era_confirmada,
        })


class EditarVentaAjax(LoginRequiredMixin, View):
    """
    POST JSON — edita una venta ANULADA, reemplaza sus ítems y la re-confirma.

    Cada ítem del body puede tener color_pk si el producto maneja variantes.
    Para productos con colores, el frontend envía 1 item por cada color > 0.

    Body:
    {
        "pk": 5,
        "fecha": "2025-01-15",
        "notas": "...",
        "items": [
            {
                "producto_pk":    1,
                "cliente_pk":     2,        // opcional
                "color_pk":       3,        // para productos con variantes de color
                "cantidad":       "3",
                "precio_unitario": "12.00",
                "moneda":         "ARS",
                "descuento_pct":  "0",
                "condicion_pago": "contado",
                "referencia":     ""
            },
            ...
        ]
    }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_ventas'):
            return JsonResponse({'error': 'No tenés permiso para editar ventas.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'Falta el pk de la venta.'}, status=400)

        venta = get_object_or_404(Venta, pk=pk)

        if venta.estado != EstadoVenta.ANULADA:
            return JsonResponse(
                {'error': 'Solo se pueden editar ventas que estén anuladas. Anulá la venta primero.'},
                status=400
            )

        fecha     = body.get('fecha')
        items_raw = body.get('items', [])

        if not fecha:
            return JsonResponse({'error': 'La fecha es requerida.'}, status=400)
        if not items_raw:
            return JsonResponse({'error': 'La venta debe tener al menos un ítem.'}, status=400)

        items_data = []
        errores    = []

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
                precio_unitario = Decimal(str(raw.get('precio_unitario', 0)))
                descuento_pct  = Decimal(str(raw.get('descuento_pct', 0)))
            except (InvalidOperation, Exception):
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if precio_unitario < 0:
                errores.append(f'Ítem {idx}: el precio no puede ser negativo.')
                continue

            # ── Cliente (opcional) ─────────────────────────────────
            cliente    = None
            cliente_pk = raw.get('cliente_pk')
            if cliente_pk:
                cliente = Cliente.objects.filter(pk=cliente_pk).first()

            # ── Color (solo para productos con variantes) ────────────
            color    = None
            color_pk = raw.get('color_pk')
            if color_pk:
                color = ProductoColor.objects.filter(pk=color_pk, producto=producto).first()
                if not color:
                    errores.append(f'Ítem {idx}: el color seleccionado no pertenece a este producto.')
                    continue

            # Si el producto requiere color pero no se mandó ninguno
            if producto.tiene_variantes_color and color is None:
                errores.append(
                    f'Ítem {idx}: "{producto.nombre}" maneja variantes de color. '
                    f'Cada color debe enviarse como un ítem separado con su color_pk.'
                )
                continue
            # ────────────────────────────────────────────────────────

            items_data.append({
                'producto':       producto,
                'cliente':      cliente,
                'color':          color,
                'cantidad':       cantidad,
                'precio_unitario': precio_unitario,
                'moneda':         raw.get('moneda', 'ARS'),
                'descuento_pct':  descuento_pct,
                'condicion_pago': raw.get('condicion_pago', 'contado'),
                'referencia':     raw.get('referencia', ''),
                'notas':          raw.get('notas', ''),
            })

        if errores:
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        try:
            venta.editar_completa(
                fecha      = fecha,
                notas      = body.get('notas', ''),
                items_data = items_data,
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':           True,
            'numero':       venta.numero,
            'total':        str(venta.total),
            'estado':       venta.estado,
            'estado_label': venta.get_estado_display(),
        })
