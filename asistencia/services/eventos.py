from core.models import DatosEmpresa

from ..models import PreferenciaAsistencia, TipoNotificacion
from .dedupe import ya_notificado
from .envio import enviar_mail_asistencia


def _fmt(valor):
    return f'{valor:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def notificar_deuda_pagada(cuota):
    """
    Manda el mail de "deuda pagada" al toque, apenas se confirma el
    pago de una cuota — a diferencia de las alertas por fecha
    (vencimientos, deudas próximas a vencer, stock, cheques, reportes
    periódicos), que se evalúan a diario vía el comando
    `correr_asistencia`. Se llama desde ConfirmarCuotaAjax, después de
    CuotaDeuda.confirmar(), para no bloquear el pago si el mail falla.
    """
    pref = PreferenciaAsistencia.get_solo()
    if not pref.recibir_deuda_pagada:
        return
    destino = pref.email_efectivo
    if not destino:
        return

    referencia = f'pagada-cuota-{cuota.pk}'
    if ya_notificado(TipoNotificacion.DEUDA_PAGADA, referencia, dentro_de_dias=7):
        return

    empresa_nombre = DatosEmpresa.get_solo().nombre_comercial
    asunto = f'Kai-Cart · {empresa_nombre}: pago confirmado'
    contexto = {
        'titulo': 'Deuda pagada',
        'subtitulo': None,
        'intro': f'Buen día, buenas noticias: se confirmó el pago de esta '
                 f'cuota de {empresa_nombre}.',
        'badge_texto': 'Al día',
        'badge_color': '#10B981',
        'cuotas': [{
            'descripcion': cuota.deuda.descripcion or cuota.deuda.get_tipo_display(),
            'numero': cuota.numero,
            'total_cuotas': cuota.deuda.cantidad_cuotas,
            'fecha_confirmacion': cuota.fecha_confirmacion.strftime('%d/%m/%Y'),
            'monto_fmt': _fmt(cuota.monto),
        }],
        'total_pagado': _fmt(cuota.monto),
    }
    enviar_mail_asistencia(
        TipoNotificacion.DEUDA_PAGADA, destino, asunto,
        'deuda_pagada.html', contexto, referencia,
    )
