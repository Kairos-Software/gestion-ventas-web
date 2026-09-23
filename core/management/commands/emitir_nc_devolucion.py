"""
python manage.py emitir_nc_devolucion <devolucion_numero>

Reintenta emitir la Nota de Crédito ARCA de una devolución puntual —
red de seguridad manual para cuando RegistrarDevolucionAjax ya registró
la devolución (stock repuesto, caja conciliada) pero el pedido de CAE a
ARCA falló (rechazo, corte de red, timeout, etc.), o directamente nunca
se intentó (devoluciones registradas ANTES de que existiera este
mecanismo), y el usuario quiere emitirla sin tener que rehacer la venta
ni la devolución.

`devolucion_numero` es el número que se ve en pantalla (ej: "DEV-00001",
en el detalle de la venta) — a propósito NO es el pk interno de la fila:
numero es único y es exactamente lo que el usuario tiene copiado de la
pantalla, así no hay forma de teclear un pk equivocado a mano y terminar
pidiéndole a ARCA una Nota de Crédito para la devolución de otra venta.
También acepta el número pelado (ej: "1" o "00001").

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
        parser.add_argument('devolucion_numero', type=str)

    def handle(self, *args, **options):
        crudo = options['devolucion_numero'].strip().upper()
        if crudo.startswith('DEV-'):
            numero = crudo
        else:
            try:
                numero = f'DEV-{int(crudo):05d}'
            except ValueError:
                raise CommandError(
                    f'"{options["devolucion_numero"]}" no es un número de devolución válido '
                    f'(ej: DEV-00001, tal como aparece en el detalle de la venta).'
                )

        try:
            devolucion = DevolucionVenta.objects.select_related('venta__comprobante_arca').get(
                numero=numero,
            )
        except DevolucionVenta.DoesNotExist:
            raise CommandError(f'No existe ninguna devolución "{numero}".')

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

        self.stdout.write(
            f'Pidiendo CAE para la devolución {devolucion.numero} '
            f'(venta {devolucion.venta.numero})...'
        )
        try:
            nc = facturacion.emitir_nota_credito(devolucion)
        except ArcaError as exc:
            raise CommandError(f'ARCA rechazó la Nota de Crédito: {exc}')

        self.stdout.write(self.style.SUCCESS(
            f'OK — {nc.get_tipo_comprobante_display()} {nc.numero_display}, '
            f'CAE {nc.cae}, vence {nc.cae_vencimiento}.'
        ))
