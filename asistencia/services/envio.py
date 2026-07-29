import email.policy

from django.conf import settings
from django.contrib.staticfiles.finders import find as encontrar_static
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from core.models import DatosEmpresa

from ..models import HistorialNotificacion

# El branding del mail (header) es el de Kai-Cart, el sistema en sí —
# el mismo logo COMPLETO (con el texto "Kai-Cart", no el ícono suelto)
# que ya se usa en base.html y en login.html — NO el logo del negocio/
# cliente (ese es DatosEmpresa.logo, que solo se usa para lo específico
# de cada cliente, ej. en tickets). Se toma directo del static de la
# app core para no depender de que el cliente haya cargado nada.
LOGO_CID = 'logo_kaicart'
LOGO_STATIC_PATH = 'core/img/kai-cart-logo-completo.png'


class _EmailConInline(EmailMultiAlternatives):
    """
    EmailMultiAlternatives que además embebe imágenes inline (por
    Content-ID) DENTRO de la alternativa text/html, en vez de mandarlas
    como archivo adjunto aparte.

    Por qué no se usa el `.attach()` de siempre: en Django 6, cualquier
    cosa agregada con `.attach()` fuerza el contenedor raíz del mail a
    multipart/mixed — el mismo tipo que se usa para adjuntos reales —
    y ahí es donde Gmail (y el resto de los clientes) lo mostraba como
    "1 archivo adjunto" en vez de mostrar el logo en el cuerpo del
    mail. El viejo truco (`email.mixed_subtype = 'related'`) que
    forzaba multipart/related ya no existe: Django 6 lo bloquea a
    propósito (AttributeError "no longer supports the undocumented
    `mixed_subtype` attribute") y no da ningún reemplazo público a
    ese nivel.

    La forma que sigue andando es intervenir el email.message.EmailMessage
    de Python ya construido (Django lo arma con la policy moderna, que
    sí soporta esto): ubicar la parte text/html y llamarle
    `.add_related()`, que el propio stdlib convierte in-place en
    multipart/related(text/html, imagen) sin tocar el resto del mensaje
    (ver la documentación de email.message.MIMEPart.add_related).
    Como EmailMessage.message() arma un objeto nuevo en cada llamada,
    hay que hacer esta conversión ACÁ (pisando message()) y no antes:
    los backends (smtp/console/locmem) llaman a message() una sola vez
    para serializar, así que da igual en qué método se enganche.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._inline = []  # lista de (cid, bytes, subtype)

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
                    # add_related() NO agrega los corchetes angulares del
                    # Content-ID por su cuenta — hay que pasarlos ya
                    # incluidos, si no el header queda "Content-ID: cid"
                    # en vez de "Content-ID: <cid>" (inválido según RFC
                    # 2045/2392) y el cliente de mail no puede resolver
                    # la referencia cid: del HTML, así que la muestra
                    # como adjunto suelto en vez de embebida.
                    html_part.add_related(contenido, 'image', subtype, cid=f'<{cid}>')
                # add_related() convierte html_part en el contenedor
                # multipart/related (misma identidad de objeto, por eso
                # se puede seguir usando la misma variable acá) — pero
                # no le agrega el parámetro `type="text/html"` que pide
                # RFC 2387 para indicar cuál de las partes es la "raíz".
                # Sin esto, Gmail (entre otros) no logra resolver bien
                # la relación y termina mostrando la imagen como un
                # archivo adjunto suelto en vez de embebida en el cuerpo.
                html_part.set_param('type', 'text/html')
        return msg


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
    versión texto plano, con el logo de Kai-Cart embebido en el cuerpo)
    y lo manda. Registra el resultado en HistorialNotificacion, sea
    éxito o error, para poder auditar envíos y para que las alertas
    puedan chequear si ya se avisaron antes (ver services/dedupe.py).
    """
    contexto_completo = {**_contexto_empresa(), **contexto, 'asunto': asunto}
    html = render_to_string(f'asistencia/emails/{template}', contexto_completo)
    texto_plano = strip_tags(html)

    email = _EmailConInline(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL or None,
        to=[destinatario],
    )
    email.attach_alternative(html, 'text/html')

    logo_path = encontrar_static(LOGO_STATIC_PATH)
    if logo_path:
        with open(logo_path, 'rb') as f:
            email.adjuntar_inline(LOGO_CID, f.read(), 'png')

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
