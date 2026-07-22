import os
import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse

from .models import DatosEmpresa, CondicionIVA, ConfiguracionArca, AmbienteArca
from .permisos import chequear_permiso
from .services_arca import certificados, wsaa, wsfe
from .services_arca.wsaa import ArcaError

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


class EmpresaArcaGuardarAjax(LoginRequiredMixin, View):
    """POST JSON con la configuración de facturación electrónica ARCA
    (ambiente, punto de venta, certificado y clave privada)."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_empresa'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        ambiente = body.get('ambiente') or AmbienteArca.TESTING
        if ambiente not in AmbienteArca.values:
            return JsonResponse({'error': 'Ambiente inválido.'}, status=400)

        try:
            punto_venta = int(body.get('punto_venta') or 0)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Punto de venta inválido.'}, status=400)
        if punto_venta <= 0:
            return JsonResponse({'error': 'El punto de venta debe ser mayor a 0.'}, status=400)

        config = ConfiguracionArca.get_solo()
        config.habilitado = bool(body.get('habilitado'))
        config.ambiente = ambiente
        config.punto_venta = punto_venta

        certificado_pem = (body.get('certificado_pem') or '').strip()
        clave_privada_pem = (body.get('clave_privada_pem') or '').strip()
        if certificado_pem:
            config.certificado_pem = certificado_pem
        if clave_privada_pem:
            # Cambiar el ambiente/certificado invalida cualquier token cacheado.
            config.clave_privada = clave_privada_pem
            config.wsaa_token = ''
            config.wsaa_sign = ''
            config.wsaa_expira = None

        config.save()
        return JsonResponse({'ok': True, 'tiene_certificado': config.tiene_certificado()})


class EmpresaArcaGenerarCsrAjax(LoginRequiredMixin, View):
    """POST: genera clave privada + CSR en el servidor (sin que el usuario
    toque una terminal). Guarda la clave cifrada de inmediato y devuelve
    el CSR para que lo suba a ARCA — ese trámite no se puede automatizar.

    La respuesta incluye la clave privada en texto plano UNA sola vez —
    nunca se vuelve a servir después de esta respuesta (no se guarda en
    ningún campo legible ni se manda de nuevo al recargar la página). Es
    la única oportunidad que tiene el usuario de hacerse una copia propia
    para poder restaurarla más adelante sin rehacer el trámite con ARCA."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_empresa'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        empresa = DatosEmpresa.get_solo()
        if not empresa.cuit:
            return JsonResponse(
                {'error': 'Cargá primero el CUIT en "Datos de la empresa" — el CSR lo necesita.'},
                status=400,
            )

        config = ConfiguracionArca.get_solo()
        csr_pem, alias, clave_pem = certificados.generar_csr(config, empresa.cuit, empresa.nombre_comercial)
        return JsonResponse({'ok': True, 'csr': csr_pem, 'alias': alias, 'clave_privada': clave_pem})


class EmpresaArcaProbarAjax(LoginRequiredMixin, View):
    """POST: prueba la conexión con ARCA usando la configuración guardada —
    primero autentica (WSAA, valida que el certificado sea válido y esté
    autorizado) y después consulta el estado del servicio (FEDummy)."""

    def post(self, request):
        if not chequear_permiso(request.user, 'editar_empresa'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        config = ConfiguracionArca.get_solo()
        if not config.tiene_certificado():
            return JsonResponse({'error': 'Todavía no cargaste un certificado.'}, status=400)

        try:
            wsaa.obtener_token(config)
            estado = wsfe.fe_dummy(config)
        except ArcaError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        return JsonResponse({'ok': True, 'ambiente': config.ambiente, 'estado': estado})