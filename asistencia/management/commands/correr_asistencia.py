from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from asistencia.models import CanalNotificacion, PreferenciaAsistencia, TipoNotificacion
from asistencia.services import alertas, reporte_periodico
from asistencia.services.dedupe import ya_notificado
from asistencia.services.envio import enviar_mail_asistencia
from core.models import DatosEmpresa

TIPOS = [
    'periodico_mensual', 'periodico_semanal', 'vencimiento',
    'deuda', 'deuda_pagada', 'cuota_cobro_confirmada', 'stock', 'cheques', 'todos',
]


class Command(BaseCommand):
    help = (
        'Corre los reportes/alertas de asistencia y los manda por mail. '
        'El destinatario y qué tipos mandar salen SIEMPRE de Configuración '
        '> Notificaciones (PreferenciaAsistencia) — este comando no acepta '
        'un destino por parámetro a propósito, para que se comporte igual '
        'en desarrollo y en producción (ver probar_asistencia.py). '
        '--fecha permite fingir qué día es "hoy" sin tocar el reloj.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--tipo', choices=TIPOS, default='todos')
        parser.add_argument('--fecha', default=None,
                             help='Fecha simulada de "hoy" (YYYY-MM-DD). '
                                  'Por defecto, la fecha real.')
        parser.add_argument('--forzar', action='store_true',
                             help='Ignora el dedupe: manda igual aunque ya '
                                  'se haya avisado lo mismo hace poco.')

    def handle(self, *args, **options):
        hoy = date.fromisoformat(options['fecha']) if options['fecha'] else timezone.localtime().date()
        forzar = options['forzar']
        tipo = options['tipo']

        # Scoring de riesgo de pago: la mora envejece sola. Este pase
        # diario refresca el padrón entero de una — además del refresco
        # perezoso que hacen las vistas (inicio / lista de clientes).
        # Va antes de los chequeos de canal/destino: no depende de que
        # haya notificaciones configuradas. Nunca frena el resto.
        if tipo == 'todos':
            try:
                from core.models import recalcular_scoring_pendientes
                # limite=None: sin tope (es un batch nocturno). Con la
                # antigüedad por defecto: saltea los que un evento ya
                # recalculó hoy, refresca el resto (la mora envejece sola).
                n = recalcular_scoring_pendientes(limite=None)
                self.stdout.write(f'Scoring de clientes: {n} recalculado(s).')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Scoring de clientes: fallo ({e}).'))

        pref = PreferenciaAsistencia.get_solo()
        destino = pref.email_efectivo
        empresa_nombre = DatosEmpresa.get_solo().nombre_comercial
        saludo = 'Buen día,'

        self.stdout.write(f'Simulando "hoy" = {hoy:%d/%m/%Y} — canal: {pref.get_canal_display()}')

        if pref.canal == CanalNotificacion.NINGUNO:
            self.stdout.write('Canal de notificaciones en "Ninguno": no se manda nada.')
            return
        if not destino:
            self.stdout.write(self.style.ERROR(
                'No hay email de destino: cargalo en Configuración > Notificaciones.'
            ))
            return

        if tipo in ('periodico_mensual', 'todos') and pref.recibir_reporte_mensual:
            self._reporte_periodico(hoy, destino, forzar, pref, empresa_nombre, saludo, mensual=True)
        if tipo in ('periodico_semanal', 'todos') and pref.recibir_reporte_semanal:
            self._reporte_periodico(hoy, destino, forzar, pref, empresa_nombre, saludo, mensual=False)
        if tipo in ('vencimiento', 'todos') and pref.recibir_alerta_vencimiento:
            self._alerta_vencimiento(hoy, destino, forzar, pref, empresa_nombre, saludo)
        if tipo in ('deuda', 'todos') and pref.recibir_alerta_deuda:
            self._alerta_deuda(hoy, destino, forzar, pref, empresa_nombre, saludo)
        # 'deuda_pagada' NO entra en 'todos': en producción ese mail lo
        # dispara al toque asistencia.services.eventos.notificar_deuda_pagada
        # (ver ConfirmarCuotaAjax) apenas se confirma el pago. Acá queda
        # solo para poder previsualizar el diseño con --tipo deuda_pagada
        # (ver probar_asistencia.py).
        if tipo == 'deuda_pagada' and pref.recibir_deuda_pagada:
            self._deuda_pagada(hoy, destino, forzar, empresa_nombre, saludo)
        # 'cuota_cobro_confirmada' tampoco entra en 'todos': mismo criterio
        # que 'deuda_pagada' — en producción sale al toque desde
        # asistencia.services.eventos.notificar_cuota_cobro_confirmada
        # (ver ConfirmarCuotaCobroAjax) apenas se confirma el cobro.
        if tipo == 'cuota_cobro_confirmada' and pref.recibir_cuota_cobro_confirmada:
            self._cuota_cobro_confirmada(hoy, destino, forzar, empresa_nombre, saludo)
        if tipo in ('stock', 'todos') and pref.recibir_stock_estancado:
            self._stock_estancado(hoy, destino, forzar, pref, empresa_nombre, saludo)
        if tipo in ('cheques', 'todos') and pref.recibir_alerta_cheques:
            self._alerta_cheques(hoy, destino, forzar, pref, empresa_nombre, saludo)

    # ── helpers de envío ─────────────────────────────────────────

    def _enviar(self, tipo_notif, destino, asunto, template, contexto, referencia, forzar):
        if not forzar and ya_notificado(tipo_notif, referencia, dentro_de_dias=7):
            self.stdout.write(f'  (omitido, ya notificado hace poco) {asunto}')
            return
        ok = enviar_mail_asistencia(tipo_notif, destino, asunto, template, contexto, referencia)
        if ok:
            self.stdout.write(self.style.SUCCESS(f'  OK: {asunto}'))
        else:
            self.stdout.write(self.style.ERROR(f'  ERROR al mandar: {asunto}'))

    # ── cada reporte/alerta ──────────────────────────────────────
    # Los colores de badge_color son la paleta real del sistema
    # (core/static/core/css/base.css): naranja de marca, y
    # success/warning/danger/info para el semáforo de urgencia.

    def _reporte_periodico(self, hoy, destino, forzar, pref, empresa_nombre, saludo, mensual):
        if mensual:
            if not forzar and hoy.day != pref.dia_mes_reporte:
                self.stdout.write(
                    f'  Reporte mensual: hoy no es el día configurado '
                    f'({pref.dia_mes_reporte}), no se manda.'
                )
                return
            desde = hoy.replace(day=1)
            periodo = 'mensual'
            asunto = f'Kai-Cart · Reporte mensual de {empresa_nombre} ({hoy:%B %Y})'
            referencia = f'mensual-{hoy:%Y-%m}'
        else:
            if not forzar and hoy.weekday() != pref.dia_semana_reporte:
                self.stdout.write(
                    f'  Reporte semanal: hoy no es el día configurado, no se manda.'
                )
                return
            desde = hoy - timedelta(days=6)
            periodo = 'semanal'
            asunto = f'Kai-Cart · Reporte semanal de {empresa_nombre} (semana del {desde:%d/%m})'
            referencia = f'semanal-{hoy:%Y-%W}'

        contexto = reporte_periodico.construir_contexto(
            desde, hoy, dias_aviso_vencimiento=pref.dias_aviso_vencimiento,
        )
        contexto.update({
            'titulo': f'Reporte {periodo}',
            'subtitulo': f'Del {desde:%d/%m/%Y} al {hoy:%d/%m/%Y}',
            'intro': f'{saludo} este es tu reporte {periodo} de {empresa_nombre}: un resumen '
                     f'de tus ventas, ganancias y movimientos de caja de este período.',
            'badge_texto': 'Reporte',
            'badge_color': '#1E6FA8',
        })
        self._enviar(TipoNotificacion.REPORTE_PERIODICO, destino, asunto,
                     'reporte_periodico.html', contexto, referencia, forzar)

    def _alerta_vencimiento(self, hoy, destino, forzar, pref, empresa_nombre, saludo):
        datos = alertas.productos_por_vencer(pref.dias_aviso_vencimiento, hoy=hoy)
        if not datos['lotes']:
            self.stdout.write('  Sin productos por vencer.')
            return
        n = len(datos['lotes'])
        asunto = f'Kai-Cart · {empresa_nombre}: {n} producto(s) por vencer'
        datos.update({
            'titulo': 'Productos por vencer', 'subtitulo': None,
            'intro': f'{saludo} estos productos de {empresa_nombre} están próximos a vencer. '
                     f'Se recomienda priorizar su venta antes de esa fecha.',
            'badge_texto': 'Aviso', 'badge_color': '#F59E0B',
        })
        self._enviar(TipoNotificacion.ALERTA_VENCIMIENTO, destino, asunto,
                     'alerta_vencimiento.html', datos, f'venc-{hoy:%Y-%m-%d}', forzar)

    def _alerta_deuda(self, hoy, destino, forzar, pref, empresa_nombre, saludo):
        datos = alertas.deudas_por_vencer(pref.dias_aviso_deuda, hoy=hoy)
        if not datos['cuotas']:
            self.stdout.write('  Sin deudas próximas a vencer.')
            return
        n = len(datos['cuotas'])
        asunto = f'Kai-Cart · {empresa_nombre}: {n} cuota(s) por pagar pronto'
        datos.update({
            'titulo': 'Deudas próximas a vencer', 'subtitulo': None,
            'intro': f'{saludo} estas cuotas de {empresa_nombre} vencen pronto. Programá el '
                     f'pago para evitar intereses o recargos.',
            'badge_texto': 'Urgente', 'badge_color': '#EF4444',
        })
        self._enviar(TipoNotificacion.ALERTA_DEUDA, destino, asunto,
                     'alerta_deuda.html', datos, f'deuda-{hoy:%Y-%m-%d}', forzar)

    def _deuda_pagada(self, hoy, destino, forzar, empresa_nombre, saludo):
        datos = alertas.deudas_pagadas_recientemente(7, hoy=hoy)
        if not datos['cuotas']:
            self.stdout.write('  Sin pagos recientes.')
            return
        # Texto neutro/administrativo a propósito (ver mismo comentario
        # en asistencia/services/eventos.py): "buenas noticias, pago
        # confirmado" es casi calcado al fraseo típico de phishing de
        # confirmación de pago, y Gmail lo manda a Spam con bastante
        # consistencia por eso.
        asunto = f'Kai-Cart · {empresa_nombre}: registro de pago de cuota'
        datos.update({
            'titulo': 'Deudas pagadas', 'subtitulo': None,
            'intro': f'{saludo} se registraron en el sistema estos pagos de cuotas de '
                     f'{empresa_nombre}.',
            'badge_texto': 'Al día', 'badge_color': '#10B981',
        })
        self._enviar(TipoNotificacion.DEUDA_PAGADA, destino, asunto,
                     'deuda_pagada.html', datos, f'pagada-{hoy:%Y-%m-%d}', forzar)

    def _cuota_cobro_confirmada(self, hoy, destino, forzar, empresa_nombre, saludo):
        datos = alertas.cuotas_cobro_pagadas_recientemente(7, hoy=hoy)
        if not datos['cuotas']:
            self.stdout.write('  Sin cobros recientes.')
            return
        asunto = f'Kai-Cart · {empresa_nombre}: registro de cobro de cuota'
        datos.update({
            'titulo': 'Cobros confirmados', 'subtitulo': None,
            'intro': f'{saludo} se registraron en el sistema estos cobros de cuotas de '
                     f'{empresa_nombre}.',
            'badge_texto': 'Cobrado', 'badge_color': '#10B981',
        })
        self._enviar(TipoNotificacion.CUOTA_COBRO_CONFIRMADA, destino, asunto,
                     'cuota_cobro_confirmada.html', datos, f'cobrada-{hoy:%Y-%m-%d}', forzar)

    def _stock_estancado(self, hoy, destino, forzar, pref, empresa_nombre, saludo):
        datos = alertas.stock_estancado(pref.dias_stock_estancado)
        if not datos['productos']:
            self.stdout.write('  Sin stock estancado.')
            return
        asunto = f'Kai-Cart · {empresa_nombre}: stock sin movimiento'
        datos.update({
            'titulo': 'Stock sin movimiento', 'subtitulo': None,
            'intro': f'{saludo} estos productos de {empresa_nombre} tienen stock cargado '
                     f'pero sin ventas registradas hace tiempo — conviene revisar precio '
                     f'y rotación.',
            'badge_texto': 'Sugerencia', 'badge_color': '#1E6FA8',
        })
        self._enviar(TipoNotificacion.STOCK_ESTANCADO, destino, asunto,
                     'stock_estancado.html', datos, f'stock-{hoy:%Y-%m-%d}', forzar)

    def _alerta_cheques(self, hoy, destino, forzar, pref, empresa_nombre, saludo):
        datos = alertas.cheques_por_vencer(pref.dias_aviso_deuda, hoy=hoy)
        if not datos['cheques']:
            self.stdout.write('  Sin cheques próximos a vencer.')
            return
        n = len(datos['cheques'])
        asunto = f'Kai-Cart · {empresa_nombre}: {n} cheque(s) por vencer'
        datos.update({
            'titulo': 'Cheques por vencer', 'subtitulo': None,
            'intro': f'{saludo} estos cheques de {empresa_nombre} vencen pronto.',
            'badge_texto': 'Aviso', 'badge_color': '#F59E0B',
        })
        self._enviar(TipoNotificacion.ALERTA_CHEQUE, destino, asunto,
                     'alerta_cheques.html', datos, f'cheques-{hoy:%Y-%m-%d}', forzar)
