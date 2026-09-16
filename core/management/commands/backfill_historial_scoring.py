"""
Reconstruye retroactivamente el historial de scoring de los clientes,
para que el gráfico "Historial de scoring" (Estadísticas > Clientes) no
arranque vacío justo cuando se activa esta funcionalidad.

Cómo reconstruye: para cada cliente, junta las fechas reales de su
historial de crédito de los últimos VENTANA_DIAS (fecha_confirmacion y
fecha_vencimiento de sus CuotaCobro, fecha_cobro de sus cheques) y para
cada una simula qué habría dado calcular_scoring(cliente, hoy=esa_fecha).
Guarda un punto (HistorialScoring, es_backfill=True) cada vez que el
resultado difiere del último punto ya guardado.

OJO — es una reconstrucción APROXIMADA: calcular_scoring() usa el estado
ACTUAL de cada CuentaPorCobrar (activa/monto/etc.), no una foto de cómo
estaba esa cuenta en la fecha simulada. Para el uso normal (ver la
tendencia y qué la movió) alcanza; no es un registro histórico exacto.

Idempotente: correrlo de nuevo no duplica nada (HistorialScoring tiene
unique_together en cliente+fecha) — sí puede ACTUALIZAR un punto backfill
si se lo vuelve a correr y algo cambió mientras tanto (ej. se cargó una
cuota vieja que faltaba).
"""

from django.core.management.base import BaseCommand

from core.models import Cliente, HistorialScoring
from core.scoring import calcular_scoring, banda_de_score, _cheques_de_cliente, VENTANA_DIAS
from caja.models import CuotaCobro
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = ('Reconstruye el historial de scoring de los clientes a partir de fechas '
            'reales de su historial de crédito (backfill, una sola vez).')

    def add_arguments(self, parser):
        parser.add_argument('--cliente', type=int, default=None,
                             help='Reconstruir solo este cliente (pk).')

    def handle(self, *args, **opts):
        qs = Cliente.objects.all().order_by('pk')
        if opts['cliente']:
            qs = qs.filter(pk=opts['cliente'])

        limite = timezone.localtime().date() - timedelta(days=VENTANA_DIAS)

        total_clientes = 0
        total_puntos = 0
        for cliente in qs.iterator():
            fechas = self._fechas_interesantes(cliente, limite)
            if not fechas:
                continue

            total_clientes += 1
            ultimo_score = None
            for fecha in fechas:
                r = calcular_scoring(cliente, hoy=fecha)
                if r['sin_historial']:
                    continue
                if ultimo_score is not None and r['score'] == ultimo_score:
                    continue
                ultimo_score = r['score']
                banda, _ = banda_de_score(r['score'])
                HistorialScoring.objects.update_or_create(
                    cliente=cliente, fecha=fecha,
                    defaults={
                        'score': r['score'],
                        'banda': banda,
                        'desglose': r['desglose'],
                        'es_backfill': True,
                    },
                )
                total_puntos += 1

        self.stdout.write(self.style.SUCCESS(
            f'{total_clientes} cliente(s) con historial de crédito, '
            f'{total_puntos} punto(s) de scoring reconstruidos.'
        ))

    def _fechas_interesantes(self, cliente, limite):
        """Fechas reales (>= `limite`, <= hoy) donde el scoring de este
        cliente pudo haber cambiado: cuotas confirmadas o vencidas,
        cheques a cobrar/pagar relacionados."""
        hoy = timezone.localtime().date()
        fechas = set()

        cuotas = CuotaCobro.objects.filter(cuenta_por_cobrar__cliente=cliente)
        for c in cuotas.only('fecha_vencimiento', 'fecha_confirmacion'):
            if limite <= c.fecha_vencimiento <= hoy:
                fechas.add(c.fecha_vencimiento)
            if c.fecha_confirmacion:
                confirmada = timezone.localtime(c.fecha_confirmacion).date()
                if limite <= confirmada <= hoy:
                    fechas.add(confirmada)

        for ch in _cheques_de_cliente(cliente).only('fecha_cobro'):
            if ch.fecha_cobro and limite <= ch.fecha_cobro <= hoy:
                fechas.add(ch.fecha_cobro)

        return sorted(fechas)
