"""
core/services_arca/wsaa.py

Autenticación contra WSAA (Web Service de Autenticación y Autorización) de
ARCA. Firma el TRA en Python puro con `cryptography` (CMS/PKCS7) — nada de
depender de un binario externo (`openssl`) en el PATH del proceso, que varía
entre entornos (probamos a mano y confirmamos que la firma resultante es
válida verificándola con `openssl smime -verify`, aunque no se use para
firmar).

El token/sign que devuelve ARCA vale ~12hs; se cachea en el propio
ConfiguracionArca (obtener_token no pide uno nuevo si el cacheado sigue
vigente).
"""
import base64
import html
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7
from django.utils import timezone as dj_timezone

from core.models import AmbienteArca

TZ_ARG = ZoneInfo('America/Argentina/Buenos_Aires')

WSAA_URLS = {
    AmbienteArca.TESTING: 'https://wsaahomo.afip.gov.ar/ws/services/LoginCms',
    AmbienteArca.PRODUCCION: 'https://wsaa.afip.gov.ar/ws/services/LoginCms',
}

SOAP_NS = 'http://wsaa.view.sua.dvadac.desein.afip.gov'


class ArcaError(Exception):
    """Error devuelto por ARCA (WSAA o WSFE) o de conectividad — el mensaje
    ya viene listo para mostrarle al usuario, con el motivo que informó ARCA."""


def _formato_iso_offset(momento):
    # strftime('%z') da "-0300" sin los dos puntos; ARCA espera "-03:00".
    texto = momento.strftime('%Y-%m-%dT%H:%M:%S%z')
    return f'{texto[:-2]}:{texto[-2:]}'


def _generar_tra(servicio='wsfe'):
    ahora = dj_timezone.now().astimezone(TZ_ARG)
    generacion = ahora - timedelta(minutes=10)
    expiracion = ahora + timedelta(minutes=10)
    unique_id = int(ahora.timestamp())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<loginTicketRequest version="1.0">\n'
        '  <header>\n'
        f'    <uniqueId>{unique_id}</uniqueId>\n'
        f'    <generationTime>{_formato_iso_offset(generacion)}</generationTime>\n'
        f'    <expirationTime>{_formato_iso_offset(expiracion)}</expirationTime>\n'
        '  </header>\n'
        f'  <service>{servicio}</service>\n'
        '</loginTicketRequest>'
    )


def _firmar_tra(tra_xml, certificado_pem, clave_privada_pem):
    """Firma el TRA (CMS/PKCS7, DER, con los datos incluidos — no detached)
    en Python puro, sin depender de ningún binario externo. Devuelve el
    resultado en base64, listo para meter en el pedido SOAP."""
    try:
        certificado = x509.load_pem_x509_certificate(certificado_pem.encode())
        clave_privada = serialization.load_pem_private_key(
            clave_privada_pem.encode(), password=None,
        )
    except ValueError as exc:
        raise ArcaError(f'El certificado o la clave privada no son válidos: {exc}') from exc

    cms_bytes = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(tra_xml.encode('utf-8'))
        .add_signer(certificado, clave_privada, hashes.SHA256())
        .sign(serialization.Encoding.DER, [])
    )
    return base64.b64encode(cms_bytes).decode()


def _pedir_login(config):
    if not config.tiene_certificado():
        raise ArcaError(
            'No hay certificado ARCA cargado en Configuración → Facturación Electrónica.'
        )

    tra_xml = _generar_tra('wsfe')
    cms_b64 = _firmar_tra(tra_xml, config.certificado_pem, config.clave_privada)

    envelope = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:wsaa="{SOAP_NS}">\n'
        '   <soapenv:Header/>\n'
        '   <soapenv:Body>\n'
        '      <wsaa:loginCms>\n'
        f'         <wsaa:in0>{cms_b64}</wsaa:in0>\n'
        '      </wsaa:loginCms>\n'
        '   </soapenv:Body>\n'
        '</soapenv:Envelope>'
    )

    url = WSAA_URLS[config.ambiente]
    try:
        resp = requests.post(
            url,
            data=envelope.encode('utf-8'),
            headers={'Content-Type': 'text/xml;charset=UTF-8', 'SOAPAction': '""'},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise ArcaError(f'No se pudo conectar a WSAA ({url}): {exc}') from exc

    if '<soapenv:Fault>' in resp.text or '<soap:Fault>' in resp.text:
        match = re.search(r'<faultstring[^>]*>(.*?)</faultstring>', resp.text, re.S)
        mensaje = match.group(1) if match else resp.text[:300]
        raise ArcaError(f'WSAA rechazó el pedido de autenticación: {mensaje}')

    inner_match = re.search(r'<loginCmsReturn>(.*?)</loginCmsReturn>', resp.text, re.S)
    if not inner_match:
        raise ArcaError(f'Respuesta inesperada de WSAA: {resp.text[:300]}')

    inner = html.unescape(inner_match.group(1))
    token_match = re.search(r'<token>(.*?)</token>', inner, re.S)
    sign_match = re.search(r'<sign>(.*?)</sign>', inner, re.S)
    expiracion_match = re.search(r'<expirationTime>(.*?)</expirationTime>', inner)
    if not token_match or not sign_match:
        raise ArcaError(f'WSAA no devolvió token/sign: {inner[:300]}')

    if expiracion_match:
        expira = datetime.fromisoformat(expiracion_match.group(1))
    else:
        expira = dj_timezone.now() + timedelta(hours=12)

    return token_match.group(1), sign_match.group(1), expira


def obtener_token(config):
    """
    Devuelve (token, sign) vigentes para `config`, reutilizando el cache
    guardado en el propio ConfiguracionArca mientras no esté por vencer;
    si no hay uno vigente, pide uno nuevo a ARCA y lo cachea.
    """
    ahora = dj_timezone.now()
    margen = timedelta(minutes=1)
    if config.wsaa_token and config.wsaa_expira and config.wsaa_expira > ahora + margen:
        return config.wsaa_token, config.wsaa_sign

    token, sign, expira = _pedir_login(config)
    config.wsaa_token = token
    config.wsaa_sign = sign
    config.wsaa_expira = expira
    config.save(update_fields=['wsaa_token', 'wsaa_sign', 'wsaa_expira'])
    return token, sign
