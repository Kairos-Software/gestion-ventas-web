"""
Convierte cuentas por cobrar de "cuotas fijas" a "saldo libre".

Sirve al activar el modo cuenta corriente (ver
core.models.usa_cuenta_corriente): las deudas de cuotas fijas no dejan
imputar fracciones en la cascada FIFO de cobro, así que conviene pasarlas
a saldo libre. Solo convierte las que es seguro convertir:

  - estado ACTIVA
  - sin cuotas CONFIRMADA de verdad todavía (0 pagos reales), o con
    algunas confirmadas pero SIN cheques en trámite

Descarta las cuotas PENDIENTE pre-generadas (no movieron plata) y deja
`modo_cuotas=libre` — el saldo pasa a ser total − cobrado. Es
reversible en la práctica volviendo a cargar un plan, pero no hay
"des-conversión" automática.

Sin --aplicar solo informa (dry-run).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from caja.models import (
    CuentaPorCobrar, CuotaCobro, Cheque,
    EstadoDeuda, EstadoCuota, EstadoCheque, ModoCuotas,
)


class Command(BaseCommand):
    help = 'Pasa las cuentas por cobrar de cuotas fijas a saldo libre (para el modo cuenta corriente).'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Aplica los cambios. Sin esto, solo informa (dry-run).')
        parser.add_argument('--cliente', type=int, default=None,
                            help='Limitar a un cliente (pk).')

    def handle(self, *args, **opts):
        aplicar = opts['aplicar']
        qs = CuentaPorCobrar.objects.filter(
            estado=EstadoDeuda.ACTIVA, modo_cuotas=ModoCuotas.FIJAS,
        ).select_related('cliente')
        if opts['cliente']:
            qs = qs.filter(cliente_id=opts['cliente'])

        total = qs.count()
        self.stdout.write(f'Cuentas por cobrar en cuotas fijas activas: {total}')

        convertibles, bloqueadas = [], []
        for cxc in qs:
            tiene_cheque = Cheque.objects.filter(
                cuota_cobro__cuenta_por_cobrar=cxc,
                estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO),
            ).exists()
            if tiene_cheque:
                bloqueadas.append((cxc, 'cheque en trámite en alguna cuota'))
            else:
                convertibles.append(cxc)

        self.stdout.write(f'  Convertibles: {len(convertibles)}')
        self.stdout.write(f'  Bloqueadas:   {len(bloqueadas)}')
        for cxc, motivo in bloqueadas:
            self.stdout.write(f'    - #{cxc.pk} {cxc.cliente.get_nombre_display()}: {motivo}')

        if not aplicar:
            self.stdout.write(self.style.WARNING('\nDry-run. Volvé a correr con --aplicar para convertir.'))
            for cxc in convertibles:
                pend = cxc.cuotas.filter(estado=EstadoCuota.PENDIENTE).count()
                conf = cxc.cuotas.filter(estado=EstadoCuota.CONFIRMADA).count()
                self.stdout.write(
                    f'    - #{cxc.pk} {cxc.cliente.get_nombre_display()} '
                    f'(saldo ${cxc.saldo_pendiente}, {conf} cobradas / {pend} pendientes a descartar)'
                )
            return

        convertidas = 0
        with transaction.atomic():
            for cxc in convertibles:
                cxc.cuotas.filter(estado=EstadoCuota.PENDIENTE).delete()
                cxc.modo_cuotas = ModoCuotas.LIBRE
                cxc.cantidad_cuotas = None
                cxc.save(update_fields=['modo_cuotas', 'cantidad_cuotas'])
                convertidas += 1

        self.stdout.write(self.style.SUCCESS(f'\nListo: {convertidas} cuentas pasadas a saldo libre.'))
