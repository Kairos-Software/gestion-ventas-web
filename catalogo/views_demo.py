import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View

from .seed import cargar_datos_demo, eliminar_datos_demo

logger = logging.getLogger(__name__)


def _es_superuser_activo(user):
    return user.is_authenticated and user.is_active and user.is_superuser


# Mismo candado que ReiniciarSistemaAjax (core/views_reiniciar.py): superuser
# + DEBUG. Es una herramienta de desarrollo para previsualizar el catálogo,
# no algo pensado para tocar en producción.
@method_decorator(login_required, name='dispatch')
@method_decorator(user_passes_test(_es_superuser_activo), name='dispatch')
class CargarDatosDemoAjax(View):

    def post(self, request):
        if not settings.DEBUG:
            return JsonResponse(
                {'ok': False, 'error': 'Esta acción solo está habilitada en modo DEBUG.'}, status=403,
            )
        try:
            resumen = cargar_datos_demo()
        except ValueError as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=400)
        except Exception:
            logger.exception('Error cargando datos de prueba del catálogo.')
            return JsonResponse(
                {'ok': False, 'error': 'Ocurrió un error cargando los datos de prueba. Revisá los logs.'},
                status=500,
            )
        logger.info('Datos de prueba del catálogo cargados por %s: %s', request.user.username, resumen)
        return JsonResponse({'ok': True, 'creados': resumen})


@method_decorator(login_required, name='dispatch')
@method_decorator(user_passes_test(_es_superuser_activo), name='dispatch')
class EliminarDatosDemoAjax(View):

    def post(self, request):
        if not settings.DEBUG:
            return JsonResponse(
                {'ok': False, 'error': 'Esta acción solo está habilitada en modo DEBUG.'}, status=403,
            )
        try:
            eliminados = eliminar_datos_demo()
        except Exception:
            logger.exception('Error eliminando datos de prueba del catálogo.')
            return JsonResponse(
                {'ok': False, 'error': 'Ocurrió un error eliminando los datos de prueba. Revisá los logs.'},
                status=500,
            )
        logger.info('Datos de prueba del catálogo eliminados por %s: %s filas', request.user.username, eliminados)
        return JsonResponse({'ok': True, 'eliminados': eliminados})
