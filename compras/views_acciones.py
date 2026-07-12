import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

# ── IMPORTANTE: CombinacionVariante debe importarse para que editar_completa
#    pueda resolver las variantes y _sumar_stock_item funcione correctamente ──
from productos.models import Producto, Proveedor, CombinacionVariante
from .models import Compra, EstadoCompra
from core.permisos import chequear_permiso


class AnularCompraAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'editar_compras'):
            return JsonResponse({'error': 'No tenés permiso para anular compras.'}, status=403)
        try:
            body = json.loads(request.body)
            pk   = body.get('pk')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra = get_object_or_404(Compra, pk=pk)
        try:
            compra.anular()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':           True,
            'numero':       compra.numero,
            'estado':       compra.estado,
            'estado_label': compra.get_estado_display(),
        })


class ReactivarCompraAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'editar_compras'):
            return JsonResponse({'error': 'No tenés permiso para reactivar compras.'}, status=403)
        try:
            body = json.loads(request.body)
            pk   = body.get('pk')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra = get_object_or_404(Compra, pk=pk)
        try:
            compra.reactivar()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':           True,
            'numero':       compra.numero,
            'estado':       compra.estado,
            'estado_label': compra.get_estado_display(),
        })


class EliminarCompraAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_compras'):
            return JsonResponse({'error': 'No tenés permiso para eliminar compras.'}, status=403)
        try:
            body = json.loads(request.body)
            pk   = body.get('pk')
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra = get_object_or_404(Compra, pk=pk)

        if compra.estado == EstadoCompra.BORRADOR:
            return JsonResponse(
                {'error': 'Las compras en borrador no se eliminan desde el historial.'},
                status=400
            )

        numero         = compra.numero
        era_confirmada = compra.estado == EstadoCompra.CONFIRMADA

        try:
            compra.delete()
        except Exception as e:
            return JsonResponse({'error': f'Error al eliminar: {str(e)}'}, status=500)

        return JsonResponse({
            'ok':              True,
            'numero':          numero,
            'stock_revertido': era_confirmada,
        })


class EditarCompraAjax(LoginRequiredMixin, View):
    """
    POST JSON — edita una compra ANULADA, reemplaza sus ítems y la re-confirma.

    Cada ítem del body puede tener combinacion_pk si el producto maneja variantes.
    Para productos con variantes, el frontend envía 1 item por cada combinación > 0.

    Body:
    {
        "pk": 5,
        "fecha": "2025-01-15",
        "notas": "...",
        "items": [
            {
                "producto_pk":       1,
                "proveedor_pk":      2,        // opcional
                "combinacion_pk":    3,        // para productos con variantes
                "cantidad":          "3",
                "costo_unitario":    "12.00",
                "moneda":            "ARS",
                "descuento_pct":     "0",
                "condicion_pago":    "contado",
                "referencia":        ""
            },
            ...
        ]
    }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_compras'):
            return JsonResponse({'error': 'No tenés permiso para editar compras.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'Falta el pk de la compra.'}, status=400)

        compra = get_object_or_404(Compra, pk=pk)

        if compra.estado != EstadoCompra.ANULADA:
            return JsonResponse(
                {'error': 'Solo se pueden editar compras que estén anuladas. Anulá la compra primero.'},
                status=400
            )

        fecha     = body.get('fecha')
        items_raw = body.get('items', [])

        if not fecha:
            return JsonResponse({'error': 'La fecha es requerida.'}, status=400)
        if not items_raw:
            return JsonResponse({'error': 'La compra debe tener al menos un ítem.'}, status=400)

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
                costo_unitario = Decimal(str(raw.get('costo_unitario', 0)))
                descuento_pct  = Decimal(str(raw.get('descuento_pct', 0)))
            except (InvalidOperation, Exception):
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if costo_unitario < 0:
                errores.append(f'Ítem {idx}: el costo no puede ser negativo.')
                continue

            # ── Proveedor (opcional) ─────────────────────────────────
            proveedor    = None
            proveedor_pk = raw.get('proveedor_pk')
            if proveedor_pk:
                proveedor = Proveedor.objects.filter(pk=proveedor_pk).first()

            # ── Combinación (solo para productos con variantes) ───────
            combinacion    = None
            combinacion_pk = raw.get('combinacion_pk')
            if combinacion_pk:
                combinacion = CombinacionVariante.objects.filter(pk=combinacion_pk, producto=producto).first()
                if not combinacion:
                    errores.append(f'Ítem {idx}: la combinación seleccionada no pertenece a este producto.')
                    continue

            # Si el producto requiere combinación pero no se mandó ninguna
            if producto.gestiona_variantes and combinacion is None:
                errores.append(
                    f'Ítem {idx}: "{producto.nombre}" maneja variantes. '
                    f'Cada combinación debe enviarse como un ítem separado con su combinacion_pk.'
                )
                continue
            # ────────────────────────────────────────────────────────

            # ── Fecha de vencimiento (requerida si el producto es perecedero;
            #    la validación fuerte ya la hace _crear_lote_desde_item en el
            #    modelo, esto solo intenta parsear el string recibido) ──
            fecha_vencimiento = None
            fv_raw = raw.get('fecha_vencimiento')
            if fv_raw:
                try:
                    from datetime import datetime
                    fecha_vencimiento = datetime.strptime(fv_raw, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass  # formato inválido → se deja None, el modelo lo va a rechazar si hace falta

            items_data.append({
                'producto':       producto,
                'proveedor':      proveedor,
                'combinacion':    combinacion,
                'cantidad':       cantidad,
                'costo_unitario': costo_unitario,
                'moneda':         raw.get('moneda', 'ARS'),
                'descuento_pct':  descuento_pct,
                'lista_descuento_nombre': raw.get('lista_descuento_nombre', ''),
                'condicion_pago': raw.get('condicion_pago', 'contado'),
                'referencia':     raw.get('referencia', ''),
                'notas':          raw.get('notas', ''),
                'fecha_vencimiento': fecha_vencimiento,
            })

        if errores:
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        try:
            compra.editar_completa(
                fecha      = fecha,
                notas      = body.get('notas', ''),
                items_data = items_data,
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':           True,
            'numero':       compra.numero,
            'total':        str(compra.total),
            'estado':       compra.estado,
            'estado_label': compra.get_estado_display(),
        })