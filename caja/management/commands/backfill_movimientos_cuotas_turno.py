from django.core.management.base import BaseCommand

from caja.models import (
    CuotaDeuda, CuotaCobro, EstadoCuota, EstadoTurno, TipoCuenta,
    MovimientoCaja, OrigenMovimiento, TurnoCaja,
    sincronizar_movimiento_cuota, sincronizar_movimiento_cuota_cobro,
)


class Command(BaseCommand):
    help = (
        'Backfill de cuotas de Deuda/CuentaPorCobrar pagadas/cobradas en '
        'efectivo dentro de un turno de caja que ya cerró ANTES de que '
        'TurnoCaja.cerrar() empezara a materializar ese movimiento (bug '
        'corregido en sep 2026: mientras el turno seguía abierto, ese pago '
        'nunca generaba su MovimientoCaja — solo restaba/sumaba al efectivo '
        'esperado del cierre — y nada lo creaba después, aunque el turno ya '
        'hubiera cerrado). Ese dinero SÍ está bien contado en el cierre del '
        'turno (diferencia_efectivo no cambia), pero no tenía ningún '
        'movimiento propio visible en Caja Grande explicando a dónde fue. '
        'Este comando busca esos casos y genera el movimiento que falta, '
        'con la fecha real del pago. Es idempotente: correrlo de nuevo no '
        'duplica nada (sincronizar_movimiento_cuota actualiza si ya existe). '
        'Sin --aplicar solo informa qué haría (dry-run).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                             help='Aplica los cambios. Sin esto, solo informa (dry-run).')

    def handle(self, *args, **options):
        aplicar = options['aplicar']
        total = 0

        cuotas_deuda = (
            CuotaDeuda.objects.filter(
                estado=EstadoCuota.CONFIRMADA,
                pagos__cuenta__tipo=TipoCuenta.EFECTIVO,
            )
            .distinct()
            .select_related('deuda')
        )
        for cuota in cuotas_deuda:
            if not cuota.fecha_confirmacion:
                continue
            turno = TurnoCaja.turno_que_contiene(cuota.fecha_confirmacion)
            if turno is None or turno.estado == EstadoTurno.ABIERTO:
                continue
            pago_pks = list(cuota.pagos.values_list('pk', flat=True))
            ya_existe = MovimientoCaja.objects.filter(
                origen=OrigenMovimiento.CUOTA_DEUDA, origen_app='caja', origen_id__in=pago_pks,
            ).exists()
            if ya_existe:
                continue
            self.stdout.write(
                f'  Deuda #{cuota.deuda_id} ({cuota.deuda.descripcion or "s/desc"}) — '
                f'cuota {cuota.numero}, turno #{turno.numero}, {cuota.monto} '
                f'({cuota.fecha_confirmacion.date()})'
            )
            total += 1
            if aplicar:
                sincronizar_movimiento_cuota(cuota)

        cuotas_cobro = (
            CuotaCobro.objects.filter(
                estado=EstadoCuota.CONFIRMADA,
                cuenta_cobro__tipo=TipoCuenta.EFECTIVO,
            )
            .select_related('cuenta_por_cobrar', 'cuenta_por_cobrar__cliente')
        )
        for cuota in cuotas_cobro:
            if not cuota.fecha_confirmacion:
                continue
            turno = TurnoCaja.turno_que_contiene(cuota.fecha_confirmacion)
            if turno is None or turno.estado == EstadoTurno.ABIERTO:
                continue
            ya_existe = MovimientoCaja.objects.filter(
                origen=OrigenMovimiento.CUOTA_COBRO, origen_app='caja', origen_id=cuota.pk,
            ).exists()
            if ya_existe:
                continue
            cliente = cuota.cuenta_por_cobrar.cliente.get_nombre_display()
            self.stdout.write(
                f'  CxC #{cuota.cuenta_por_cobrar_id} ({cliente}) — '
                f'cuota {cuota.numero}, turno #{turno.numero}, {cuota.monto} '
                f'({cuota.fecha_confirmacion.date()})'
            )
            total += 1
            if aplicar:
                sincronizar_movimiento_cuota_cobro(cuota)

        accion = 'Generados' if aplicar else 'Se generarían (dry-run)'
        self.stdout.write(self.style.SUCCESS(f'{accion}: {total} movimientos faltantes.'))
        if not aplicar:
            self.stdout.write('Corré con --aplicar para efectivizar los cambios.')
