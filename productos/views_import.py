"""
Importación de productos desde Excel (.xlsx).

  GET  productos/importar/plantilla/  -> descarga una planilla vacía con
                                         los encabezados correctos
  POST productos/importar/analizar/   -> {resumen, filas, ...} SIN escribir
  POST productos/importar/aplicar/    -> crea/actualiza dentro de una
                                         transacción y devuelve el resultado

`analizar` y `aplicar` reciben el archivo por multipart (campo `archivo`).
La vista no guarda estado entre las dos llamadas: el front manda el mismo
archivo en las dos.

Permisos: `analizar`/`aplicar` exigen `crear_productos` Y `editar_productos`
(la importación hace las dos cosas). La plantilla vacía sale con
`ver_productos` (no tiene datos).
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View

from core.permisos import chequear_permiso

from .import_productos import (
    analizar, aplicar, plantilla_headers, pistas_encabezado,
)
from .xlsx_reader import leer_xlsx, XlsxError
from .xlsx_writer import generar_xlsx

XLSX_CONTENT_TYPE = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

MAX_BYTES = 5 * 1024 * 1024  # 5 MB — una planilla de productos honesta no llega


def _puede_importar(user):
    return (
        chequear_permiso(user, 'crear_productos')
        and chequear_permiso(user, 'editar_productos')
    )


def _leer_archivo(request):
    """Devuelve (headers, filas, meta, error_response). Si error_response
    no es None, la vista debe devolverlo tal cual."""
    archivo = request.FILES.get('archivo')
    if archivo is None:
        return None, None, None, JsonResponse(
            {'error': 'No se recibió ningún archivo.'}, status=400)
    if archivo.size > MAX_BYTES:
        return None, None, None, JsonResponse(
            {'error': 'El archivo es demasiado grande (máximo 5 MB).'}, status=400)
    if not archivo.name.lower().endswith('.xlsx'):
        return None, None, None, JsonResponse(
            {'error': 'El archivo tiene que ser un Excel .xlsx.'}, status=400)
    try:
        headers, filas, meta = leer_xlsx(
            archivo.read(), pistas_encabezado=pistas_encabezado())
    except XlsxError as e:
        return None, None, None, JsonResponse({'error': str(e)}, status=400)
    except Exception:
        return None, None, None, JsonResponse(
            {'error': 'No se pudo leer el archivo. ¿Es un .xlsx válido?'}, status=400)
    return headers, filas, meta, None


class ProductoImportarPlantillaView(LoginRequiredMixin, View):
    """GET -> .xlsx vacío con los encabezados importables."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return HttpResponse('Sin permiso.', status=403)

        # Solo los encabezados (sin filas de ejemplo, para que importar la
        # plantilla sin editar no cree nada). El orden es el mismo que el
        # de la exportación; ninguna columna es obligatoria salvo Nombre
        # para las filas nuevas.
        headers = plantilla_headers()
        contenido = generar_xlsx(headers, [], sheet_name='Productos')
        resp = HttpResponse(contenido, content_type=XLSX_CONTENT_TYPE)
        resp['Content-Disposition'] = (
            'attachment; filename="plantilla_importar_productos.xlsx"'
        )
        resp['Content-Length'] = len(contenido)
        return resp


class ProductoImportarAnalizarAjax(LoginRequiredMixin, View):
    """POST multipart (archivo) -> análisis, sin tocar la base."""

    def post(self, request):
        if not _puede_importar(request.user):
            return JsonResponse(
                {'error': 'Necesitás permiso para crear y editar productos.'},
                status=403)

        headers, filas, meta, err = _leer_archivo(request)
        if err is not None:
            return err

        res = analizar(headers, filas, meta)
        return JsonResponse(res.a_dict())


class ProductoImportarAplicarAjax(LoginRequiredMixin, View):
    """POST multipart (archivo) -> crea/actualiza todo lo aplicable."""

    def post(self, request):
        if not _puede_importar(request.user):
            return JsonResponse(
                {'error': 'Necesitás permiso para crear y editar productos.'},
                status=403)

        headers, filas, meta, err = _leer_archivo(request)
        if err is not None:
            return err

        res = aplicar(headers, filas, meta)

        data = res.a_dict()
        data['ts'] = timezone.localtime().strftime('%d/%m/%Y %H:%M')
        status = 200 if data['ok'] else 400
        return JsonResponse(data, status=status)
