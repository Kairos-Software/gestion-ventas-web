import os
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse

from .models import DatosEmpresa, CondicionIVA
from .permisos import chequear_permiso

EXTENSIONES_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp'}


class EmpresaGuardarAjax(LoginRequiredMixin, View):
    """POST JSON con los datos de texto de la empresa (crea o actualiza el único registro)."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_empresa'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre_comercial = (body.get('nombre_comercial') or '').strip()
        if not nombre_comercial:
            return JsonResponse({'error': 'El nombre comercial es obligatorio.'}, status=400)

        condicion_iva = body.get('condicion_iva') or ''
        if condicion_iva and condicion_iva not in CondicionIVA.values:
            return JsonResponse({'error': 'Condición frente al IVA inválida.'}, status=400)

        empresa = DatosEmpresa.get_solo()
        empresa.nombre_comercial = nombre_comercial
        empresa.razon_social     = (body.get('razon_social') or '').strip()
        empresa.cuit             = (body.get('cuit') or '').strip()
        empresa.condicion_iva    = condicion_iva
        empresa.domicilio        = (body.get('domicilio') or '').strip()
        empresa.telefono         = (body.get('telefono') or '').strip()
        empresa.email            = (body.get('email') or '').strip()
        empresa.save()

        return JsonResponse({'ok': True})


class EmpresaLogoAjax(LoginRequiredMixin, View):
    """POST (FormData, campo 'logo') = subir/reemplazar. DELETE = quitar el logo actual."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_empresa'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        archivo = request.FILES.get('logo')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)
        if archivo.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 5 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in EXTENSIONES_PERMITIDAS:
            return JsonResponse({'error': 'Usá JPG, PNG o WEBP.'}, status=400)

        empresa = DatosEmpresa.get_solo()
        self._borrar_archivo_actual(empresa)
        empresa.logo = archivo
        empresa.save(update_fields=['logo'])
        return JsonResponse({'ok': True, 'logo_url': empresa.logo.url})

    def delete(self, request):
        if not chequear_permiso(request.user, 'editar_empresa'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        empresa = DatosEmpresa.get_solo()
        self._borrar_archivo_actual(empresa)
        empresa.logo = None
        empresa.save(update_fields=['logo'])
        return JsonResponse({'ok': True})

    def _borrar_archivo_actual(self, empresa):
        if empresa.logo and os.path.isfile(empresa.logo.path):
            os.remove(empresa.logo.path)