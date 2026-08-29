"""
Exportación de productos a Excel (.xlsx).

  GET productos/exportar/excel/  -> descarga el archivo
  GET productos/exportar/conteo/ -> {"total": N} para el modal (cuántas filas
                                    saldría el export con los filtros actuales)

Ambas vistas comparten el armado de queryset/filtros de export_productos.py
y están detrás del permiso `ver_productos` (exportar es leer datos que el
usuario ya puede ver en la tabla — no amerita un permiso propio ni una
migración).
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views import View

from core.permisos import chequear_permiso

from .export_productos import (
    ETIQUETAS, construir_queryset, generar_filas, normalizar_columnas,
)
from .xlsx_writer import generar_xlsx

XLSX_CONTENT_TYPE = (
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)


class ProductoExportarExcelView(LoginRequiredMixin, View):
    """GET -> devuelve un .xlsx con los productos filtrados."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return HttpResponse('Sin permiso.', status=403)

        claves   = normalizar_columnas(request.GET.get('columnas'))
        qs       = construir_queryset(request.GET)
        headers  = [ETIQUETAS[c] for c in claves]
        filas    = generar_filas(qs, claves)

        contenido = generar_xlsx(headers, filas, sheet_name='Productos')

        ts   = timezone.localtime().strftime('%Y-%m-%d_%H%M')
        resp = HttpResponse(contenido, content_type=XLSX_CONTENT_TYPE)
        resp['Content-Disposition'] = f'attachment; filename="productos_{ts}.xlsx"'
        resp['Content-Length'] = len(contenido)
        return resp


class ProductoExportarConteoAjax(LoginRequiredMixin, View):
    """GET -> {"total": N} con los mismos filtros que usaría el export."""

    def get(self, request):
        if not chequear_permiso(request.user, 'ver_productos'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        total = construir_queryset(request.GET).count()
        return JsonResponse({'total': total})
