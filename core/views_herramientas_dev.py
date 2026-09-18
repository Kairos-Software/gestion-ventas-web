# core/views_herramientas_dev.py
"""
Panel de "Herramientas de desarrollador" — expone desde el navegador un
subconjunto de management commands (ver core/herramientas_dev_catalogo.py
para el porqué de cuáles sí y cuáles no), solo para superusuarios.

Mismo candado que core/views_reiniciar.py y catalogo/views_demo.py:
usuario autenticado + activo + is_superuser. A propósito NO pasa por el
sistema de Roles/permisos (chequear_permiso) — esto no debe ser
delegable a un Rol, es estrictamente "el dueño del sistema".

La vista de ejecución nunca recibe el nombre real de un management
command del cliente: solo un slug que se busca en HERRAMIENTAS. Si no
está ahí, no hay ninguna forma de ejecutar nada (ver construir_args_kwargs
para cómo se arman los args/kwargs reales de call_command, y por qué
params_fijos se aplica siempre al final).
"""
import json
import logging
from io import StringIO

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View

from core.herramientas_dev_catalogo import (
    HERRAMIENTAS, ParametroInvalido, construir_args_kwargs, serializar_para_frontend,
)
from core.models import ConfiguracionArca, DatosEmpresa

logger = logging.getLogger(__name__)

# Cortamos la salida capturada para no inflar la respuesta ni trabar el
# navegador si alguien corre algo sobre una base grande (ej. rastrear_stock
# con --todos, o un backfill con miles de filas).
SALIDA_MAXIMA = 200_000


def _es_superuser_activo(user):
    return user.is_authenticated and user.is_active and user.is_superuser


@login_required
@user_passes_test(_es_superuser_activo)
def herramientas_dev(request):
    config_arca = ConfiguracionArca.get_solo()
    empresa = DatosEmpresa.get_solo()

    contexto = {
        'herramientas_json': json.dumps(serializar_para_frontend()),
        'ambiente_arca': config_arca.ambiente,
        'ambiente_arca_display': config_arca.get_ambiente_display(),
        'email_empresa_default': empresa.email,
    }
    return render(request, 'core/herramientas_dev.html', contexto)


@method_decorator(login_required, name='dispatch')
@method_decorator(user_passes_test(_es_superuser_activo), name='dispatch')
class EjecutarHerramientaAjax(View):
    """
    POST JSON: {"herramienta": "<slug>", "params": {...}}

    Respuesta OK (200): {"ok": true, "salida": "...", "truncado": bool}
    Error de validación/negocio (400): {"ok": false, "error": "...",
        "salida_parcial": "...", "truncado": bool}
    Error inesperado (500): {"ok": false, "error": "mensaje genérico"}
    """

    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'JSON inválido.'}, status=400)

        slug = body.get('herramienta')
        tool = HERRAMIENTAS.get(slug)
        if tool is None:
            logger.warning(
                'Herramienta dev no reconocida: %r (usuario %s)',
                slug, request.user.username,
            )
            return JsonResponse({'ok': False, 'error': 'Herramienta no reconocida.'}, status=400)

        params_crudos = body.get('params') or {}
        if not isinstance(params_crudos, dict):
            return JsonResponse({'ok': False, 'error': 'Formato de parámetros inválido.'}, status=400)

        try:
            args, kwargs = construir_args_kwargs(tool, params_crudos)
        except ParametroInvalido as exc:
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

        buffer = StringIO()
        status_code = 200
        error_msg = None
        try:
            call_command(tool['command'], *args, stdout=buffer, stderr=buffer, no_color=True, **kwargs)
        except CommandError as exc:
            status_code = 400
            error_msg = str(exc)
        except Exception:
            status_code = 500
            error_msg = 'Ocurrió un error ejecutando la herramienta. Revisá los logs.'
            logger.exception(
                'Error ejecutando herramienta dev "%s" (usuario %s)',
                slug, request.user.username,
            )

        salida = buffer.getvalue()
        truncado = len(salida) > SALIDA_MAXIMA
        if truncado:
            salida = salida[:SALIDA_MAXIMA] + '\n\n[... salida truncada ...]'

        logger.warning(
            'Herramienta dev "%s" ejecutada por %s. args=%s kwargs=%s ok=%s',
            slug, request.user.username, args, kwargs, status_code == 200,
        )

        if status_code == 200:
            return JsonResponse({'ok': True, 'salida': salida, 'truncado': truncado})
        return JsonResponse(
            {'ok': False, 'error': error_msg, 'salida_parcial': salida, 'truncado': truncado},
            status=status_code,
        )
