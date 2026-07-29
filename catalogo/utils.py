from urllib.parse import quote_plus


def google_maps_link(direccion):
    """
    Link de búsqueda de Google Maps a partir de una dirección en texto
    libre — no requiere API key ni coordenadas cargadas, a diferencia de
    un mapa embebido. '' si no hay dirección.
    """
    direccion = (direccion or '').strip()
    if not direccion:
        return ''
    return f'https://www.google.com/maps/search/?api=1&query={quote_plus(direccion)}'


def wa_link_ar(telefono_crudo):
    """
    Arma el link de wa.me a partir de un teléfono argentino escrito en
    cualquier formato habitual (con o sin 0/15, con o sin +54, etc.).
    La gente rara vez escribe el formato que pide WhatsApp (54 9 +
    característica + número) — lo normal es solo "característica +
    número" (ej: 3624023093). Reglas que aplicamos, en orden:
    - Nos quedamos solo con los dígitos.
    - Si ya viene con 00 o 54 de prefijo, no lo duplicamos.
    - Si empieza con 0 (como se marca en el país), lo sacamos.
    - Si no tiene el 9 que WhatsApp exige para celulares argentinos,
      se lo agregamos.
    No es infalible — no hay forma de adivinar si alguien metió un
    "15" en el medio — pero cubre el caso normal de la mayoría de la
    gente: característica + número, sin prefijos.
    """
    digitos = ''.join(ch for ch in telefono_crudo if ch.isdigit())
    if not digitos:
        return ''
    if digitos.startswith('00'):
        digitos = digitos[2:]
    if digitos.startswith('54'):
        digitos = digitos[2:]
    if digitos.startswith('0'):
        digitos = digitos[1:]
    if not digitos.startswith('9'):
        digitos = '9' + digitos
    return f'https://wa.me/54{digitos}'
