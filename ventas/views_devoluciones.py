import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from productos.models import cantidad_valida_para_unidad
from core.permisos import chequear_permiso
from .models import Venta, ItemVenta, registrar_devolucion


PERMISO_DEVOLUCIONES = 'registrar_devoluciones'


class RegistrarDevolucionAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "venta_pk": 123,
        "descripcion": "Cliente trajo 2 unidades, una rota",
        "cuenta_pk": 4,          // opcional si monto=0
        "monto": "1500.00",
        "cotizacion": null,      // solo si la cuenta no es en pesos
        "items": [
            {"item_venta_pk": 456, "cantidad": "1", "es_perdida": false},
            {"item_venta_pk": 456, "cantidad": "1", "es_perdida": true, "motivo_perdida": "rotura"}
        ]
    }

    Se permiten dos entradas para el mismo item_venta_pk si una porción
    vuelve a stock y otra se marca como pérdida. Toda la lógica de
    negocio (reponer al lote exacto, registrar la pérdida, armar el
    reembolso) vive en registrar_devolucion() (ventas/models.py).
    """

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_DEVOLUCIONES):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta_pk = body.get('venta_pk')
        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)
        venta = get_object_or_404(Venta, pk=venta_pk)

        items_raw = body.get('items') or []
        if not items_raw:
            return JsonResponse({'error': 'Elegí al menos un ítem a devolver.'}, status=400)

        items_data = []
        for raw in items_raw:
            item_pk = raw.get('item_venta_pk')
            item_venta = ItemVenta.objects.filter(pk=item_pk, venta_id=venta.pk).select_related('producto').first()
            if item_venta is None:
                return JsonResponse({'error': f'Ítem inválido (pk={item_pk}).'}, status=400)

            try:
                cantidad = Decimal(str(raw.get('cantidad')))
            except (InvalidOperation, TypeError, ValueError):
                return JsonResponse({'error': 'Cantidad inválida.'}, status=400)
            if cantidad <= 0:
                return JsonResponse({'error': 'La cantidad a devolver debe ser mayor a 0.'}, status=400)
            if item_venta.producto and not cantidad_valida_para_unidad(item_venta.producto.unidad_medida, cantidad):
                return JsonResponse({
                    'error': f'"{item_venta.nombre_producto_display}" se vende por unidades enteras.',
                }, status=400)

            items_data.append({
                'item_venta': item_venta,
                'cantidad': cantidad,
                'es_perdida': bool(raw.get('es_perdida')),
                'motivo_perdida': raw.get('motivo_perdida') or None,
            })

        cuenta = None
        cuenta_pk = body.get('cuenta_pk')
        if cuenta_pk:
            from caja.models import CuentaCaja, TipoCaja
            cuenta = CuentaCaja.objects.filter(pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True).first()
            if cuenta is None:
                return JsonResponse({'error': 'Elegí una cuenta válida para el reembolso.'}, status=400)

        try:
            monto = Decimal(str(body.get('monto') or '0'))
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({'error': 'Monto inválido.'}, status=400)

        cotizacion = None
        if body.get('cotizacion'):
            try:
                cotizacion = Decimal(str(body['cotizacion']))
            except (InvalidOperation, TypeError, ValueError):
                return JsonResponse({'error': 'Cotización inválida.'}, status=400)

        try:
            devolucion = registrar_devolucion(
                venta=venta, items_data=items_data, descripcion=body.get('descripcion', ''),
                usuario=request.user, cuenta=cuenta, monto=monto, cotizacion=cotizacion,
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok': True,
            'numero': devolucion.numero,
            'monto': str(devolucion.monto),
        })
