import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import CuentaFinanciera, TipoCuenta
from .permisos import chequear_permiso


class CuentaCrearEditarAjax(LoginRequiredMixin, View):
    """POST JSON. Si trae 'pk', edita; si no, crea."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_cuentas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre = (body.get('nombre') or '').strip()
        if not nombre:
            return JsonResponse({'error': 'El nombre es obligatorio.'}, status=400)

        tipo = body.get('tipo') or ''
        if tipo not in TipoCuenta.values:
            return JsonResponse({'error': 'Tipo de cuenta inválido.'}, status=400)

        try:
            saldo_inicial = Decimal(str(body.get('saldo_actual', 0)))
        except InvalidOperation:
            return JsonResponse({'error': 'Saldo inválido.'}, status=400)

        dia_cierre = body.get('dia_cierre') or None
        dia_venc = body.get('dia_vencimiento') or None
        if tipo != TipoCuenta.TARJETA_CREDITO:
            dia_cierre = None
            dia_venc = None

        pk = body.get('pk')
        if pk:
            cuenta = get_object_or_404(CuentaFinanciera, pk=pk)
        else:
            cuenta = CuentaFinanciera()
            cuenta.saldo_actual = saldo_inicial  # solo se setea al crear

        cuenta.nombre = nombre
        cuenta.titular = (body.get('titular') or '').strip()
        cuenta.tipo = tipo
        cuenta.terminada_en = (body.get('terminada_en') or '').strip()
        cuenta.dia_cierre = dia_cierre
        cuenta.dia_vencimiento = dia_venc
        cuenta.activa = bool(body.get('activa', True))
        cuenta.save()

        return JsonResponse({'ok': True, 'pk': cuenta.pk})


class CuentaEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'editar_cuentas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        cuenta = get_object_or_404(CuentaFinanciera, pk=pk)
        # Baja lógica, no borrado: si ya tiene movimientos históricos en
        # Compras/Ventas ligados por FK, borrarla de verdad rompería esos registros.
        cuenta.activa = False
        cuenta.save(update_fields=['activa'])
        return JsonResponse({'ok': True})