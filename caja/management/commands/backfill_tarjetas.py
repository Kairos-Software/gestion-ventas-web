from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from caja.models import (
    Deuda, EstadoCuota, TipoDeuda,
    sincronizar_movimiento_cuota_tarjeta, sincronizar_movimiento_deuda_tarjeta,
)


class Command(BaseCommand):
    help = (
        'Backfill de saldo de tarjeta para deudas de compra_credito creadas '
        'ANTES de esta funcionalidad (saldo de tarjeta / split capital-interés '
        'por cuota). Recalcula monto_capital en cada cuota (mismo reparto '
        'proporcional que generar_cuotas) y genera los movimientos de tarjeta '
        'que falten: el débito al crear la deuda y el crédito de capital en '
        'cada cuota ya confirmada. No toca préstamos ni los movimientos de '
        'cuenta_pago/cuenta_acreditacion (esos ya estaban bien desde antes). '
        'Es idempotente: correrlo dos veces no duplica nada. Sin --aplicar '
        'solo informa qué haría (dry-run).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                             help='Aplica los cambios. Sin esto, solo informa (dry-run).')

    def handle(self, *args, **options):
        aplicar = options['aplicar']
        deudas = Deuda.objects.filter(tipo=TipoDeuda.COMPRA_CREDITO).prefetch_related('cuotas')

        total_deudas = 0
        total_cuotas_corregidas = 0

        for deuda in deudas:
            cuotas = list(deuda.cuotas.order_by('numero'))
            if not cuotas:
                continue

            capital_base = (deuda.monto_original / deuda.cantidad_cuotas).quantize(Decimal('0.01'))
            acumulado_capital = Decimal('0')
            for cuota in cuotas:
                if cuota.numero < deuda.cantidad_cuotas:
                    monto_capital = capital_base
                    acumulado_capital += monto_capital
                else:
                    monto_capital = deuda.monto_original - acumulado_capital

                if cuota.monto_capital != monto_capital:
                    self.stdout.write(
                        f'  Deuda #{deuda.pk} cuota {cuota.numero}: '
                        f'monto_capital {cuota.monto_capital} -> {monto_capital}'
                    )
                    total_cuotas_corregidas += 1
                    if aplicar:
                        cuota.monto_capital = monto_capital
                        cuota.save(update_fields=['monto_capital'])

            if aplicar:
                with transaction.atomic():
                    sincronizar_movimiento_deuda_tarjeta(deuda)
                    for cuota in cuotas:
                        if cuota.estado == EstadoCuota.CONFIRMADA:
                            sincronizar_movimiento_cuota_tarjeta(cuota)

            total_deudas += 1

        accion = 'Aplicado' if aplicar else 'Se aplicaría (dry-run)'
        self.stdout.write(self.style.SUCCESS(
            f'{accion}: {total_deudas} deudas de compra_credito revisadas, '
            f'{total_cuotas_corregidas} cuotas con monto_capital corregido.'
        ))
        if not aplicar:
            self.stdout.write('Corré con --aplicar para efectivizar los cambios.')
