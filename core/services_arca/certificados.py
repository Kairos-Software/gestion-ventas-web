"""
core/services_arca/certificados.py

Genera la clave privada + CSR que hay que subir a ARCA, sin terminal ni
OpenSSL a mano — reemplaza el procedimiento manual que se hizo una vez
por consola al desarrollar esta integración.

La clave privada se guarda cifrada de inmediato en ConfiguracionArca (el
usuario nunca la ve ni la maneja). El CSR se le devuelve para que lo suba
a ARCA — ese paso no se puede automatizar: solo el titular, con su propia
Clave Fiscal, puede autorizarlo. El mismo CSR sirve para pedir tanto el
certificado de testing (WSASS) como el de producción (Administrador de
Certificados Digitales) — no hace falta generar uno para cada ambiente.
"""
import re

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.utils import timezone


def _alias_seguro(nombre):
    """Solo letras/números — WSASS rechaza cualquier otro carácter en el alias."""
    limpio = re.sub(r'[^a-zA-Z0-9]', '', nombre or '')
    return (limpio[:20] or 'sistema').lower()


def generar_csr(config, cuit, nombre_empresa):
    """
    Genera un par de claves RSA 2048 nuevo, guarda la privada cifrada en
    `config` (ConfiguracionArca) y devuelve (csr_pem, alias, clave_pem).

    Genera un par nuevo cada vez que se llama — si ya había un
    certificado cargado, queda invalidado (no corresponde a la clave
    nueva), así que hay que volver a autorizarlo en ARCA.

    `clave_pem` se devuelve en texto plano SOLO en este momento — es la
    única vez que existe fuera de la base (cifrada). El llamador es
    responsable de mostrarla una única vez y no guardarla en ningún lado
    del lado del servidor ni en el HTML de páginas futuras.
    """
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    clave_pem = clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    alias = _alias_seguro(nombre_empresa)
    cuit_limpio = (cuit or '').replace('-', '').strip()

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, 'AR'),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, nombre_empresa or 'Empresa'),
        x509.NameAttribute(NameOID.COMMON_NAME, alias),
        x509.NameAttribute(NameOID.SERIAL_NUMBER, f'CUIT {cuit_limpio}'),
    ])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(clave, hashes.SHA256())
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()

    config.clave_privada = clave_pem  # setter: cifra y guarda en clave_privada_enc
    config.csr_pendiente = csr_pem
    config.csr_generado_el = timezone.now()
    # La clave vieja (si había) ya no corresponde a ningún certificado
    # cargado — evita quedarse con un certificado "guardado" que en
    # realidad no se puede usar porque su clave privada ya no está.
    config.certificado_pem = ''
    config.wsaa_token = ''
    config.wsaa_sign = ''
    config.wsaa_expira = None
    config.save()

    return csr_pem, alias, clave_pem
