"""
Recalcula el scoring de riesgo de pago de los clientes.

NO hace falta programar esto como tarea aparte. El scoring se mantiene
solo por tres vías:
  1. En cada evento (cobro de cuota, cheque rebotado, venta confirmada…)
     se recalcula el cliente afectado al instante.
  2. Al abrir el inicio o la lista de clientes, el sistema pone al día
     de a tandas los puntajes vencidos (recalcular_scoring_pendientes).
  3. El pase diario de notificaciones (manage.py correr_asistencia
     --tipo todos, que ya se corre por el Programador de tareas) refresca
     el padrón entero.

Este comando queda para el backfill inicial (una corrida al migrar) y
para depurar a mano. --detalle imprime cada cliente con su banda.
"""

from django.core.management.base import BaseCommand

from core.models import Cliente


class Command(BaseCommand):
    help = 'Recalcula el scoring de todos los clientes (o de uno con --cliente <pk>).'

    def add_arguments(self, parser):
        parser.add_argument('--cliente', type=int, default=None,
                            help='Recalcular solo este cliente (pk).')
        parser.add_argument('--detalle', action='store_true',
                            help='Imprime cada cliente con su puntaje y banda.')

    def handle(self, *args, **opts):
        qs = Cliente.objects.all().order_by('pk')
        if opts['cliente']:
            qs = qs.filter(pk=opts['cliente'])

        total = 0
        cambios = 0
        for cliente in qs.iterator():
            antes = cliente.scoring
            cliente.recalcular_scoring(commit=True)
            total += 1
            if cliente.scoring != antes:
                cambios += 1
            if opts['detalle']:
                flecha = '' if cliente.scoring == antes else f'  ({antes} → {cliente.scoring})'
                self.stdout.write(
                    f'{cliente.codigo or cliente.pk:14} '
                    f'{cliente.get_nombre_display()[:34]:34} '
                    f'{cliente.scoring:>4}  {cliente.scoring_banda_label}{flecha}'
                )

        self.stdout.write(self.style.SUCCESS(
            f'{total} cliente(s) recalculado(s), {cambios} con cambio de puntaje.'
        ))
