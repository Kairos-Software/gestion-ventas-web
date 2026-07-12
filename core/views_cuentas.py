# core/views_cuentas.py
#
# CRUD de CuentaCaja desde Configuración (dueño del negocio).
# CuentaCaja vive en la app `caja` (es el ledger real de la plata),
# pero se carga y edita acá porque Configuración es donde vive el
# resto de los datos restringidos del negocio (ver views_empresa.py).
# Caja Grande solo LEE estas cuentas, no las gestiona (Fase 2).

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from caja.models import CuentaCaja, TipoCaja, TipoCuenta, CUENTA_EFECTIVO_DEFAULT_NOMBRE
from productos.models import Moneda
from .permisos import chequear_permiso

PERMISO = 'editar_cuentas'


class CuentaCrearEditarAjax(LoginRequiredMixin, View):
    """POST JSON. Si trae 'pk', edita; si no, crea. Siempre en caja=GRANDE."""

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre = (body.get('nombre') or '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es obligatorio.'}, status=400)
        if nombre == CUENTA_EFECTIVO_DEFAULT_NOMBRE:
            return JsonResponse(
                {'error': 'Ese nombre está reservado para la cuenta de efectivo, que se crea sola.'},
                status=400,
            )

        moneda = body.get('moneda') or ''
        if moneda not in Moneda.values:
            return JsonResponse({'error': 'Moneda inválida.'}, status=400)

        es_credito = bool(body.get('es_credito'))

        dia_cierre = body.get('dia_cierre') or None
        dia_vencimiento = body.get('dia_vencimiento') or None
        if es_credito:
            try:
                dia_cierre = int(dia_cierre) if dia_cierre else None
                dia_vencimiento = int(dia_vencimiento) if dia_vencimiento else None
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Día de cierre/vencimiento inválido.'}, status=400)
            for dia in (dia_cierre, dia_vencimiento):
                if dia is not None and not (1 <= dia <= 31):
                    return JsonResponse({'error': 'El día debe estar entre 1 y 31.'}, status=400)
        else:
            dia_cierre = None
            dia_vencimiento = None

        pk = body.get('pk')
        if pk:
            cuenta = get_object_or_404(CuentaCaja, pk=pk, caja=TipoCaja.GRANDE)
            if cuenta.nombre == CUENTA_EFECTIVO_DEFAULT_NOMBRE:
                return JsonResponse({'error': 'La cuenta de efectivo no se edita desde acá.'}, status=400)
        else:
            cuenta = CuentaCaja(caja=TipoCaja.GRANDE)

        duplicado = CuentaCaja.objects.filter(nombre=nombre, caja=TipoCaja.GRANDE, moneda=moneda)
        if pk:
            duplicado = duplicado.exclude(pk=pk)
        if duplicado.exists():
            return JsonResponse({'error': 'Ya existe una cuenta con ese nombre en esa moneda.'}, status=400)

        cuenta.nombre = nombre
        cuenta.moneda = moneda
        cuenta.tipo = TipoCuenta.OTRA
        cuenta.es_credito = es_credito
        cuenta.titular = (body.get('titular') or '').strip()
        cuenta.terminada_en = (body.get('terminada_en') or '').strip()
        cuenta.dia_cierre = dia_cierre
        cuenta.dia_vencimiento = dia_vencimiento
        if pk:
            cuenta.activa = bool(body.get('activa', cuenta.activa))
        cuenta.save()

        return JsonResponse({'ok': True, 'pk': cuenta.pk})


class CuentaEliminarAjax(LoginRequiredMixin, View):
    """Baja lógica: nunca se borra físicamente (MovimientoCaja tiene FK protegida)."""

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        cuenta = get_object_or_404(CuentaCaja, pk=pk, caja=TipoCaja.GRANDE)
        if cuenta.nombre == CUENTA_EFECTIVO_DEFAULT_NOMBRE:
            return JsonResponse({'error': 'La cuenta de efectivo no se puede dar de baja.'}, status=400)

        cuenta.activa = not cuenta.activa
        cuenta.save(update_fields=['activa'])
        return JsonResponse({'ok': True, 'activa': cuenta.activa})
