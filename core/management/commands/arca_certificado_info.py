"""
python manage.py arca_certificado_info

Lee el certificado digital de ARCA ya cargado en ConfiguracionArca y
muestra a nombre de quién está y cuándo vence — de solo lectura, no se
conecta a ningún servicio externo, solo interpreta el archivo que ya
está guardado. Sirve para enterarse de un vencimiento próximo ANTES de
que la facturación empiece a fallar sola (los certificados de ARCA
duran un tiempo limitado y hay que renovarlos a mano en su portal).
"""
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import ConfiguracionArca


def _titular(cert):
    """CN + Nº de serie (donde ARCA guarda el CUIT) en texto legible —
    cert.subject.rfc4514_string() muestra el OID crudo (2.5.4.5=...) para
    el campo Nº de serie, nada entendible para alguien que no es dev."""
    def _atributo(oid):
        valores = cert.subject.get_attributes_for_oid(oid)
        return valores[0].value if valores else None

    cn = _atributo(NameOID.COMMON_NAME)
    serie = _atributo(NameOID.SERIAL_NUMBER)
    partes = [p for p in (cn, serie) if p]
    return ' — '.join(partes) if partes else cert.subject.rfc4514_string()


class Command(BaseCommand):
    help = 'Muestra a nombre de quién está y cuándo vence el certificado ARCA cargado en esta instalación.'

    def handle(self, *args, **options):
        config = ConfiguracionArca.get_solo()
        if not config.certificado_pem:
            raise CommandError(
                'Todavía no hay ningún certificado cargado en '
                'Configuración → Facturación Electrónica.'
            )

        try:
            cert = x509.load_pem_x509_certificate(
                config.certificado_pem.encode(), default_backend(),
            )
        except Exception as exc:
            raise CommandError(f'No se pudo leer el certificado cargado: {exc}')

        vencimiento = cert.not_valid_after_utc
        dias = (vencimiento - timezone.now()).days

        self.stdout.write(f'Certificado a nombre de: {_titular(cert)}')
        self.stdout.write(f'Vence el: {vencimiento:%d/%m/%Y}')

        if dias < 0:
            self.stdout.write(self.style.ERROR(
                f'VENCIDO hace {abs(dias)} día(s) — hay que renovarlo en el '
                'portal de ARCA antes de poder seguir facturando.'
            ))
        elif dias <= 30:
            self.stdout.write(self.style.WARNING(
                f'Vence en {dias} día(s) — conviene renovarlo pronto.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Vence en {dias} día(s). Todavía hay tiempo de sobra.'
            ))
