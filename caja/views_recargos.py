# caja/views_recargos.py
#
# Configuración de recargos por medio de pago (débito/crédito/QR/
# transferencia), por TARJETA/BILLETERA del cliente (Visa, Mercado Pago,
# Naranja X, Personal Pay, etc.) — ver ventas.models.TarjetaPago para por
# qué esto NO vive sobre CuentaCaja: una tarjeta/billetera con la que paga
# un cliente es un dato aparte de a cuál de las cuentas propias del
# negocio entra la plata (esa sigue siendo CuentaCaja, elegida aparte al
# cobrar la venta — ver ventas/views_nueva_venta.py).
#
# Los modelos (TarjetaPago/RecargoMedioPago) viven en ventas/models.py
# junto a MedioPago/PagoVenta — ver ese archivo para el porqué (evitar el
# import circular a nivel de módulo entre caja y ventas). Acá solo vive
# la pantalla, siguiendo el mismo patrón simple que core/views_cuentas.py
# (un endpoint "guardar" que crea o edita según venga "pk", y un toggle
# de baja/alta).

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from core.permisos import chequear_permiso

PERMISO_VER    = 'ver_recargos'
PERMISO_EDITAR = 'editar_recargos'

# Qué campo booleano de TarjetaPago corresponde a cada medio — usado para
# validar server-side que el medio elegido tiene sentido para esa tarjeta
# (defensa en profundidad: el JS ya filtra el <select>, pero un request
# armado a mano no debería poder saltearse la regla).
CAMPO_ACEPTA_POR_MEDIO = {
    'debito':        'acepta_debito',
    'credito':       'acepta_credito',
    'qr':            'acepta_qr',
    'transferencia': 'acepta_transferencia',
}


def _serializar_recargo(r):
    return {
        'pk': r.pk,
        'tarjeta_pk': r.tarjeta_id,
        'medio': r.medio,
        'medio_display': r.get_medio_display(),
        'cantidad_pagos': r.cantidad_pagos,
        'nombre_plan': r.nombre_plan,
        'recargo_pct': str(r.recargo_pct),
        'activo': r.activo,
    }


def _serializar_tarjeta(t):
    return {
        'pk': t.pk,
        'nombre': t.nombre,
        'acepta_debito': t.acepta_debito,
        'acepta_credito': t.acepta_credito,
        'acepta_qr': t.acepta_qr,
        'acepta_transferencia': t.acepta_transferencia,
    }


class RecargosView(LoginRequiredMixin, TemplateView):
    """Una tarjeta por card, con sus recargos configurados."""
    template_name = 'caja/recargos.html'

    def get_context_data(self, **kwargs):
        from ventas.models import RecargoMedioPago, TarjetaPago, MedioPago

        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_ver']    = True
        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)

        tarjetas = TarjetaPago.objects.filter(activa=True).order_by('orden', 'nombre')
        recargos = (
            RecargoMedioPago.objects
            .filter(tarjeta__in=tarjetas)
            .select_related('tarjeta')
            .order_by('tarjeta__orden', 'tarjeta__nombre', 'medio', 'cantidad_pagos')
        )

        recargos_por_tarjeta = {}
        for r in recargos:
            recargos_por_tarjeta.setdefault(r.tarjeta_id, []).append(r)

        ctx['tarjetas'] = [
            {'tarjeta': t, 'recargos': recargos_por_tarjeta.get(t.pk, [])}
            for t in tarjetas
        ]
        ctx['medios_con_recargo'] = [
            (v, l) for v, l in MedioPago.choices if v in RecargoMedioPago.MEDIOS_CON_RECARGO
        ]
        ctx['medio_credito'] = MedioPago.CREDITO
        ctx['tarjetas_json'] = json.dumps([_serializar_tarjeta(t) for t in tarjetas])

        from django.urls import reverse
        ctx['url_guardar']         = reverse('caja:recargo_guardar')
        ctx['url_baja']            = reverse('caja:recargo_baja', args=[0])      # placeholder
        ctx['url_eliminar']        = reverse('caja:recargo_eliminar', args=[0])  # placeholder
        ctx['url_tarjeta_guardar'] = reverse('caja:tarjeta_guardar')
        ctx['url_tarjeta_medios']  = reverse('caja:tarjeta_medios_guardar')
        ctx['url_tarjeta_baja']    = reverse('caja:tarjeta_baja', args=[0])      # placeholder

        return ctx


class RecargoGuardarAjax(LoginRequiredMixin, View):
    """POST JSON. Si trae 'pk', edita; si no, crea."""

    def post(self, request):
        from ventas.models import RecargoMedioPago, TarjetaPago, MedioPago

        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        tarjeta = TarjetaPago.objects.filter(pk=body.get('tarjeta_pk'), activa=True).first()
        if not tarjeta:
            return JsonResponse({'error': 'Elegí una tarjeta/billetera válida.'}, status=400)

        medio = body.get('medio') or ''
        if medio not in RecargoMedioPago.MEDIOS_CON_RECARGO:
            return JsonResponse({'error': 'Medio de pago inválido.'}, status=400)
        if not getattr(tarjeta, CAMPO_ACEPTA_POR_MEDIO[medio]):
            medio_label = dict(MedioPago.choices).get(medio, medio)
            return JsonResponse({
                'error': f'{tarjeta.nombre} no acepta {medio_label} — habilitalo primero en esta pantalla.'
            }, status=400)

        cantidad_pagos = 1
        nombre_plan = ''
        if medio == 'credito':
            try:
                cantidad_pagos = int(body.get('cantidad_pagos') or 1)
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Cantidad de pagos inválida.'}, status=400)
            if cantidad_pagos < 1:
                return JsonResponse({'error': 'La cantidad de pagos debe ser al menos 1.'}, status=400)
            nombre_plan = (body.get('nombre_plan') or '').strip()[:60]

        try:
            recargo_pct = float(body.get('recargo_pct'))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Porcentaje de recargo inválido.'}, status=400)
        if recargo_pct < 0:
            return JsonResponse({'error': 'El porcentaje de recargo no puede ser negativo.'}, status=400)

        pk = body.get('pk')
        if pk:
            recargo = get_object_or_404(RecargoMedioPago, pk=pk)
        else:
            recargo = RecargoMedioPago()

        duplicado = RecargoMedioPago.objects.filter(
            tarjeta=tarjeta, medio=medio, cantidad_pagos=cantidad_pagos,
        )
        if pk:
            duplicado = duplicado.exclude(pk=pk)
        if duplicado.exists():
            return JsonResponse({
                'error': 'Ya existe un recargo configurado para esa tarjeta, medio y cantidad de pagos.'
            }, status=400)

        recargo.tarjeta = tarjeta
        recargo.medio = medio
        recargo.cantidad_pagos = cantidad_pagos
        recargo.nombre_plan = nombre_plan
        recargo.recargo_pct = recargo_pct
        if pk:
            recargo.activo = bool(body.get('activo', recargo.activo))
        recargo.save()

        return JsonResponse({'ok': True, 'recargo': _serializar_recargo(recargo)})


class RecargoBajaAjax(LoginRequiredMixin, View):
    """Toggle de activo/inactivo (no se borra físicamente: mantiene el historial de qué se cobró cuándo)."""

    def post(self, request, pk):
        from ventas.models import RecargoMedioPago

        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        recargo = get_object_or_404(RecargoMedioPago, pk=pk)
        recargo.activo = not recargo.activo
        recargo.save(update_fields=['activo'])
        return JsonResponse({'ok': True, 'activo': recargo.activo})


class RecargoEliminarAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        from ventas.models import RecargoMedioPago

        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        recargo = get_object_or_404(RecargoMedioPago, pk=pk)
        recargo.delete()
        return JsonResponse({'ok': True})


class TarjetaGuardarAjax(LoginRequiredMixin, View):
    """POST JSON. Si trae 'pk', edita (nombre); si no, crea una tarjeta/billetera nueva."""

    def post(self, request):
        from ventas.models import TarjetaPago

        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre = (body.get('nombre') or '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es obligatorio.'}, status=400)

        pk = body.get('pk')
        if pk:
            tarjeta = get_object_or_404(TarjetaPago, pk=pk)
        else:
            tarjeta = TarjetaPago()

        duplicado = TarjetaPago.objects.filter(nombre=nombre)
        if pk:
            duplicado = duplicado.exclude(pk=pk)
        if duplicado.exists():
            return JsonResponse({'error': 'Ya existe una tarjeta/billetera con ese nombre.'}, status=400)

        tarjeta.nombre = nombre
        tarjeta.save()

        return JsonResponse({'ok': True, 'tarjeta': _serializar_tarjeta(tarjeta)})


class TarjetaMediosGuardarAjax(LoginRequiredMixin, View):
    """Guarda qué medios (débito/crédito/QR/transferencia) acepta una tarjeta/billetera."""

    def post(self, request):
        from ventas.models import TarjetaPago

        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        tarjeta = TarjetaPago.objects.filter(pk=body.get('tarjeta_pk'), activa=True).first()
        if not tarjeta:
            return JsonResponse({'error': 'Elegí una tarjeta/billetera válida.'}, status=400)

        for campo in CAMPO_ACEPTA_POR_MEDIO.values():
            if campo in body:
                setattr(tarjeta, campo, bool(body[campo]))
        tarjeta.save(update_fields=list(CAMPO_ACEPTA_POR_MEDIO.values()))

        return JsonResponse({'ok': True, 'tarjeta': _serializar_tarjeta(tarjeta)})


class TarjetaBajaAjax(LoginRequiredMixin, View):
    """Toggle de activa/inactiva — no se borra físicamente (protege el historial de PagoVenta)."""

    def post(self, request, pk):
        from ventas.models import TarjetaPago

        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        tarjeta = get_object_or_404(TarjetaPago, pk=pk)
        tarjeta.activa = not tarjeta.activa
        tarjeta.save(update_fields=['activa'])
        return JsonResponse({'ok': True, 'activa': tarjeta.activa})
