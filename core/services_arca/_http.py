"""
core/services_arca/_http.py

`servicios1.afip.gov.ar` (WSFEv1 de PRODUCCIÓN) todavía negocia TLS con un
grupo Diffie-Hellman de 1024 bits. OpenSSL 3.x (el que trae Ubuntu 22.04+ /
Debian 12) lo rechaza por defecto con:

    [SSL: DH_KEY_TOO_SMALL] dh key too small

y el handshake ni siquiera llega a validar el certificado. En homologación
no pasa (wswhomo/wsaahomo tienen TLS moderno), por eso aparece recién al
pasar a producción.

`sesion_arca()` devuelve una `requests.Session` que baja el nivel de
seguridad de OpenSSL a SECLEVEL=1 (permite DH de 1024) **solo** para las
llamadas a ARCA. La validación del certificado del servidor sigue activa
(`create_default_context` mantiene verify + check_hostname): no se apaga la
seguridad, solo se tolera el grupo DH viejo que usa AFIP.
"""
import ssl

import requests
from requests.adapters import HTTPAdapter


class _ArcaTLSAdapter(HTTPAdapter):
    def __init__(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        # SECLEVEL=1 -> mínimo 80 bits -> admite el DH de 1024 de AFIP.
        ctx.set_ciphers('DEFAULT@SECLEVEL=1')
        self._ssl_context = ctx
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs.setdefault('ssl_context', self._ssl_context)
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        kwargs.setdefault('ssl_context', self._ssl_context)
        return super().proxy_manager_for(*args, **kwargs)


_SESION = None


def sesion_arca():
    """Session compartida para todas las llamadas a ARCA (WSAA + WSFE)."""
    global _SESION
    if _SESION is None:
        s = requests.Session()
        s.mount('https://', _ArcaTLSAdapter())
        _SESION = s
    return _SESION
