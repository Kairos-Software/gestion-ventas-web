"""
python manage.py emitir_nc_devolucion <devolucion_pk>

Reintenta emitir la Nota de Crédito ARCA de una devolución puntual —
red de seguridad manual para cuando RegistrarDevolucionAjax ya registró
la devolución (stock repuesto, caja conciliada) pero el pedido de CAE a
ARCA falló (rechazo, corte de red, timeout, etc.), y el usuario quiere
reintentarlo sin tener que rehacer la venta ni la devolución.

Es seguro reintentar las veces que haga falta: emitir_nota_credito()
devuelve la NotaCreditoArca existente sin pedir un CAE nuevo si la
devolución ya tiene una (ver core/services_arca/facturacion.py). Si la
venta no tiene comprobante ARCA, no hace nada (no es un caso de error).
"""
from django.core.management.base import BaseCommand, CommandError

from core.services_arca import facturacion
from core.services_arca.wsaa import ArcaError
from ventas.models import DevolucionVenta


class Command(BaseCommand):
    help = 'Reintenta emitir la Nota de Crédito ARCA de una devolución puntual.'

    def add_arguments(self, parser):
        parser.add_argument('devolucion_pk', type=int)

    def handle(self, *args, **options):
        try:
            devolucion = DevolucionVenta.objects.select_related('venta__comprobante_arca').get(
                pk=options['devolucion_pk'],
            )
        except DevolucionVenta.DoesNotExist:
            raise CommandError(f'No existe ninguna DevolucionVenta con pk={options["devolucion_pk"]}.')

        existente = getattr(devolucion, 'nota_credito_arca', None)
        if existente is not None:
            self.stdout.write(self.style.WARNING(
                f'Esta devolución ya tiene una Nota de Crédito emitida: '
                f'{existente.get_tipo_comprobante_display()} {existente.numero_display} '
                f'(CAE {existente.cae}). No se pide una nueva.'
            ))
            return

        if not hasattr(devolucion.venta, 'comprobante_arca'):
            self.stdout.write(self.style.WARNING(
                'La venta de esta devolución no tiene comprobante ARCA (no fue facturada '
                'electrónicamente) — no corresponde emitir Nota de Crédito.'
            ))
            return

        self.stdout.write(f'Pidiendo CAE para la devolución {devolucion.numero}...')
        try:
            nc = facturacion.emitir_nota_credito(devolucion)
        except ArcaError as exc:
            raise CommandError(f'ARCA rechazó la Nota de Crédito: {exc}')

        self.stdout.write(self.style.SUCCESS(
            f'OK — {nc.get_tipo_comprobante_display()} {nc.numero_display}, '
            f'CAE {nc.cae}, vence {nc.cae_vencimiento}.'
        ))
