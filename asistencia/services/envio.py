from email.mime.image import MIMEImage

from django.conf import settings
from django.contrib.staticfiles.finders import find as encontrar_static
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from core.models import DatosEmpresa

from ..models import HistorialNotificacion

# El branding del mail (header) es el de Kai-Cart, el sistema en sí —
# el mismo logo que ya se usa en base.html y en login.html — NO el
# logo del negocio/cliente (ese es DatosEmpresa.logo, que solo se usa
# para lo específico de cada cliente, ej. en tickets). Se toma directo
# del static de la app core para no depender de que el cliente haya
# cargado nada.
LOGO_CID = 'logo_kaicart'
LOGO_STATIC_PATH = 'core/img/logo2.png'


def _contexto_empresa():
    empresa = DatosEmpresa.get_solo()
    return {
        'empresa': empresa,
        'empresa_nombre': empresa.nombre_comercial,
        'logo_cid': LOGO_CID,
    }


def enviar_mail_asistencia(tipo, destinatario, asunto, template, contexto, referencia=''):
    """
    Renderiza `asistencia/emails/<template>`, arma el mail (HTML +
    versión texto plano, con el logo de Kai-Cart embebido) y lo manda.
    Registra el resultado en HistorialNotificacion, sea éxito o error,
    para poder auditar envíos y para que las alertas puedan chequear
    si ya se avisaron antes (ver services/dedupe.py).
    """
    contexto_completo = {**_contexto_empresa(), **contexto, 'asunto': asunto}
    html = render_to_string(f'asistencia/emails/{template}', contexto_completo)
    texto_plano = strip_tags(html)

    email = EmailMultiAlternatives(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL or None,
        to=[destinatario],
    )
    email.attach_alternative(html, 'text/html')

    logo_path = encontrar_static(LOGO_STATIC_PATH)
    if logo_path:
        with open(logo_path, 'rb') as f:
            img = MIMEImage(f.read())
        img.add_header('Content-ID', f'<{LOGO_CID}>')
        img.add_header('Content-Disposition', 'inline', filename='kai-cart.png')
        email.attach(img)

    exito, detalle_error = True, ''
    try:
        email.send()
    except Exception as exc:
        exito = False
        detalle_error = str(exc)

    HistorialNotificacion.objects.create(
        tipo=tipo,
        referencia=str(referencia)[:50],
        destinatario=destinatario,
        asunto=asunto,
        exito=exito,
        detalle_error=detalle_error,
    )
    return exito
