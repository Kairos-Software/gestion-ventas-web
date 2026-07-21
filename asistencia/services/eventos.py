import threading

from django.db import transaction
from django.utils import timezone

from core.models import DatosEmpresa

from ..models import PreferenciaAsistencia, TipoNotificacion
from .dedupe import ya_notificado
from .envio import enviar_mail_asistencia


def _fmt(valor):
    return f'{valor:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def _dias_restantes(fecha, hoy=None):
    hoy = hoy or timezone.now().date()
    return (fecha - hoy).days


def enviar_en_background(func, *args, **kwargs):
    """
    Ejecuta `func(*args, **kwargs)` (una de las notificar_* de este
    módulo) en un hilo aparte, DESPUÉS de que la transacción actual
    haya confirmado (transaction.on_commit) — así el pedido HTTP que
    creó el cheque/deuda/compra responde al toque, sin quedarse
    esperando la ida y vuelta del SMTP (1-2 segundos, se sentía como
    que el sistema se colgaba). Si no hay una transacción activa,
    on_commit() ejecuta el callback de inmediato, así que este mismo
    helper funciona igual estemos o no dentro de un atomic.

    Es "best effort": si el hilo muere junto con el proceso (ej. un
    restart del servidor justo en ese instante), el mail no sale y no
    hay reintento — para el volumen de esta app (unos pocos mails por
    día) es un costo aceptable a cambio de no sumar una cola de tareas
    (Celery, etc.) que en una VPS chica sería mucho más peso que el
    problema que resuelve.
    """
    def _enviar():
        try:
            func(*args, **kwargs)
        except Exception:
            pass

    transaction.on_commit(lambda: threading.Thread(target=_enviar, daemon=True).start())


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


def notificar_cheque_si_proximo(cheque, hoy=None):
    """
    Si el cheque recién creado ya vence dentro de la ventana de aviso
    configurada, manda la alerta al toque — sin esto, habría que
    esperar a la próxima corrida de `correr_asistencia` (una vez al
    día) para enterarse, aunque ya estuviera "vencido" según la
    ventana configurada desde el mismo momento en que se cargó.
    Se llama desde CrearChequeAjax, después de Cheque.objects.create().
    """
    pref = PreferenciaAsistencia.get_solo()
    if not pref.recibir_alerta_cheques:
        return
    destino = pref.email_efectivo
    if not destino:
        return

    dias_restantes = _dias_restantes(cheque.fecha_cobro, hoy)
    if dias_restantes < 0 or dias_restantes > pref.dias_aviso_deuda:
        return

    referencia = f'cheque-{cheque.pk}'
    if ya_notificado(TipoNotificacion.ALERTA_CHEQUE, referencia, dentro_de_dias=7):
        return

    empresa_nombre = DatosEmpresa.get_solo().nombre_comercial
    asunto = f'Kai-Cart · {empresa_nombre}: cheque por vencer pronto'
    monto_fmt = _fmt(cheque.monto)
    contexto = {
        'titulo': 'Cheque por vencer',
        'subtitulo': None,
        'intro': f'Buen día, este cheque de {empresa_nombre} vence pronto.',
        'badge_texto': 'Aviso',
        'badge_color': '#F59E0B',
        'cheques': [{
            'numero': cheque.numero_cheque or f'#{cheque.pk}',
            'es_a_cobrar': cheque.tipo == 'a_cobrar',
            'dias_restantes': dias_restantes,
            'monto_fmt': monto_fmt,
        }],
        'neto': monto_fmt if cheque.tipo == 'a_cobrar' else f'-{monto_fmt}',
    }
    enviar_mail_asistencia(
        TipoNotificacion.ALERTA_CHEQUE, destino, asunto,
        'alerta_cheques.html', contexto, referencia,
    )


def notificar_cuotas_deuda_si_proximas(deuda, hoy=None):
    """
    Análogo a notificar_cheque_si_proximo pero para las cuotas de una
    deuda recién creada: si alguna ya vence dentro de la ventana de
    aviso (por ejemplo, la primera cuota de un préstamo a pagar en
    pocos días), manda un mail al toque por cada una — en vez de
    juntarlas todas en un único mail, para que el asunto de cada mail
    sea específico a esa cuota puntual.
    """
    pref = PreferenciaAsistencia.get_solo()
    if not pref.recibir_alerta_deuda:
        return
    destino = pref.email_efectivo
    if not destino:
        return

    empresa_nombre = DatosEmpresa.get_solo().nombre_comercial

    for cuota in deuda.cuotas.all():
        dias_restantes = _dias_restantes(cuota.fecha_vencimiento, hoy)
        if dias_restantes < 0 or dias_restantes > pref.dias_aviso_deuda:
            continue

        referencia = f'deuda-cuota-{cuota.pk}'
        if ya_notificado(TipoNotificacion.ALERTA_DEUDA, referencia, dentro_de_dias=7):
            continue

        monto_fmt = _fmt(cuota.monto)
        asunto = f'Kai-Cart · {empresa_nombre}: cuota por pagar pronto'
        contexto = {
            'titulo': 'Deuda próxima a vencer',
            'subtitulo': None,
            'intro': f'Buen día, esta cuota de {empresa_nombre} vence pronto. '
                     f'Programá el pago para evitar intereses o recargos.',
            'badge_texto': 'Urgente',
            'badge_color': '#EF4444',
            'cuotas': [{
                'descripcion': deuda.descripcion or deuda.get_tipo_display(),
                'numero': cuota.numero,
                'total_cuotas': deuda.cantidad_cuotas,
                'dias_restantes': dias_restantes,
                'monto_fmt': monto_fmt,
            }],
            'total_adeudado': monto_fmt,
        }
        enviar_mail_asistencia(
            TipoNotificacion.ALERTA_DEUDA, destino, asunto,
            'alerta_deuda.html', contexto, referencia,
        )


def notificar_lotes_si_proximos(compra, hoy=None):
    """
    Análogo para los lotes recién creados al confirmar una compra: si
    alguno ya vence dentro de la ventana de aviso de vencimiento
    (típico en una compra de mercadería que ya viene con poca vida
    útil), manda el aviso al toque en vez de esperar a la corrida
    diaria. Se llama desde Compra.confirmar(), después de crear los
    lotes de todos los ítems.
    """
    from compras.models import LoteCompra

    pref = PreferenciaAsistencia.get_solo()
    if not pref.recibir_alerta_vencimiento:
        return
    destino = pref.email_efectivo
    if not destino:
        return

    empresa_nombre = DatosEmpresa.get_solo().nombre_comercial

    lotes = (
        LoteCompra.objects
        .filter(item_compra__compra=compra, activo=True, fecha_vencimiento__isnull=False)
        .select_related('producto')
    )
    for lote in lotes:
        dias_restantes = _dias_restantes(lote.fecha_vencimiento, hoy)
        if dias_restantes < 0 or dias_restantes > pref.dias_aviso_vencimiento:
            continue

        referencia = f'lote-{lote.pk}'
        if ya_notificado(TipoNotificacion.ALERTA_VENCIMIENTO, referencia, dentro_de_dias=7):
            continue

        valor_fmt = _fmt((lote.cantidad_actual or 0) * lote.costo_unitario)
        asunto = f'Kai-Cart · {empresa_nombre}: producto por vencer pronto'
        contexto = {
            'titulo': 'Producto por vencer',
            'subtitulo': None,
            'intro': f'Buen día, este producto de {empresa_nombre} está por vencer. Te '
                     f'recomendamos priorizar su venta o ponerlo en oferta antes de esa fecha.',
            'badge_texto': 'Aviso',
            'badge_color': '#F59E0B',
            'lotes': [{
                'producto_nombre': lote.producto.nombre if lote.producto else '(producto eliminado)',
                'codigo': lote.codigo,
                'dias_restantes': dias_restantes,
                'valor_fmt': valor_fmt,
            }],
            'total_valor_riesgo': valor_fmt,
        }
        enviar_mail_asistencia(
            TipoNotificacion.ALERTA_VENCIMIENTO, destino, asunto,
            'alerta_vencimiento.html', contexto, referencia,
        )
