import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View

from core.permisos import chequear_permiso

from .models import CanalNotificacion, PreferenciaAsistencia


class PreferenciaAsistenciaGuardarAjax(LoginRequiredMixin, View):
    """
    Guarda la configuración de reportes/alertas. Requiere el permiso
    'gestionar_notificaciones', que está en PERMISOS_RESTRINGIDOS
    (core.models): solo un superusuario puede otorgárselo a alguien
    —ver core.permisos.filtrar_permisos_otorgables—, pero quien lo
    tenga (típicamente el dueño del negocio) puede usarlo sin ser
    superusuario (ver el docstring de PreferenciaAsistencia).
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_notificaciones'):
            return JsonResponse({'error': 'Sin permiso para modificar esto.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        canal = body.get('canal') or CanalNotificacion.EMAIL
        if canal not in CanalNotificacion.values:
            return JsonResponse({'error': 'Canal inválido.'}, status=400)

        def _dia(valor, minimo, maximo, default):
            try:
                n = int(valor)
            except (TypeError, ValueError):
                return default
            return n if minimo <= n <= maximo else default

        pref = PreferenciaAsistencia.get_solo()
        pref.canal = canal
        pref.email_destino = (body.get('email_destino') or '').strip()
        pref.whatsapp_destino = (body.get('whatsapp_destino') or '').strip()

        pref.recibir_reporte_mensual = bool(body.get('recibir_reporte_mensual'))
        pref.dia_mes_reporte = _dia(body.get('dia_mes_reporte'), 1, 28, pref.dia_mes_reporte)
        pref.recibir_reporte_semanal = bool(body.get('recibir_reporte_semanal'))
        pref.dia_semana_reporte = _dia(body.get('dia_semana_reporte'), 0, 6, pref.dia_semana_reporte)

        pref.recibir_alerta_vencimiento = bool(body.get('recibir_alerta_vencimiento'))
        pref.dias_aviso_vencimiento = _dia(body.get('dias_aviso_vencimiento'), 1, 90, pref.dias_aviso_vencimiento)
        pref.recibir_alerta_deuda = bool(body.get('recibir_alerta_deuda'))
        pref.dias_aviso_deuda = _dia(body.get('dias_aviso_deuda'), 1, 30, pref.dias_aviso_deuda)
        pref.recibir_deuda_pagada = bool(body.get('recibir_deuda_pagada'))
        pref.recibir_stock_estancado = bool(body.get('recibir_stock_estancado'))
        pref.dias_stock_estancado = _dia(body.get('dias_stock_estancado'), 1, 365, pref.dias_stock_estancado)
        pref.recibir_alerta_cheques = bool(body.get('recibir_alerta_cheques'))

        pref.save()
        return JsonResponse({'ok': True})
