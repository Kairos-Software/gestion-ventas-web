# core/services_email.py — mailer de recuperación de contraseña
import email.policy

from django.conf import settings
from django.contrib.staticfiles.finders import find as encontrar_static
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

# Mismo logo/CID que usa asistencia/services/envio.py para los mails de
# alertas — se duplica acá (en vez de importarlo) para que core, la app
# base de la que dependen las demás, no dependa de asistencia.
LOGO_CID = 'logo_kaicart'
LOGO_STATIC_PATH = 'core/img/kai-cart-logo-completo.png'


class _EmailConInline(EmailMultiAlternatives):
    """
    Ver la explicación completa en asistencia/services/envio.py — el
    mismo truco (add_related() sobre la parte text/html ya construida)
    para que Gmail muestre el logo embebido en el cuerpo del mail en
    vez de como archivo adjunto suelto.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._inline = []

    def adjuntar_inline(self, cid, contenido, subtype):
        self._inline.append((cid, contenido, subtype))

    def message(self, *, policy=email.policy.default):
        msg = super().message(policy=policy)
        if self._inline:
            html_part = next(
                (parte for parte in msg.walk() if parte.get_content_type() == 'text/html'),
                None,
            )
            if html_part is not None:
                for cid, contenido, subtype in self._inline:
                    html_part.add_related(contenido, 'image', subtype, cid=f'<{cid}>')
                html_part.set_param('type', 'text/html')
        return msg


def enviar_codigo_recuperacion(usuario, destinatario, codigo):
    """
    Manda el mail con el código de recuperación de contraseña al
    `destinatario` (email del usuario). Devuelve True/False según si
    el envío tuvo éxito.
    """
    contexto = {
        'usuario': usuario,
        'codigo': codigo,
        'vigencia_minutos': 15,
        'logo_cid': LOGO_CID,
        'titulo': 'Recuperar contraseña',
        'subtitulo': f'Solicitado para el usuario {usuario.username}',
        'badge_texto': 'Seguridad de la cuenta',
        'badge_color': '#1E6FA8',
    }
    asunto = 'Código para recuperar tu contraseña — Kai-Cart'
    html = render_to_string('core/emails/recuperar_password.html', {**contexto, 'asunto': asunto})
    texto_plano = strip_tags(html)

    mail = _EmailConInline(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL or None,
        to=[destinatario],
    )
    mail.attach_alternative(html, 'text/html')

    logo_path = encontrar_static(LOGO_STATIC_PATH)
    if logo_path:
        with open(logo_path, 'rb') as f:
            mail.adjuntar_inline(LOGO_CID, f.read(), 'png')

    try:
        mail.send()
        return True
    except Exception:
        return False
