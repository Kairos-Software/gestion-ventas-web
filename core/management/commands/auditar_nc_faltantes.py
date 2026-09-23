"""
python manage.py auditar_nc_faltantes

Barrido de SOLO LECTURA sobre todas las ventas facturadas ante ARCA para
encontrar huecos fiscales — no solo el caso puntual que lo motivó, sino
cualquiera parecido que pueda estar escondido:

  a) Devoluciones que ya están registradas (stock/caja resueltos) pero
     nunca llegaron a tener su Nota de Crédito ARCA — se pueden resolver
     con `emitir_nc_devolucion <pk>` sin tocar stock/plata de nuevo.

  b) Ventas que quedaron ANULADAS con comprobante ARCA todavía vigente y
     SIN ninguna DevolucionVenta asociada — señal de que se usaron con
     Venta.anular() (el mecanismo viejo, antes de que existiera
     DevolucionVenta/la Nota de Crédito automática, y antes del guard que
     hoy bloquea anular una venta facturada). Para estas, HOY el sistema
     no tiene ninguna forma automática de emitir la Nota de Crédito — no
     hay ningún `devolucion_pk` al que apuntar. Hace falta resolverlas
     caso por caso.

No modifica nada.
"""
from django.core.management.base import BaseCommand

from ventas.models import EstadoVenta, Venta


class Command(BaseCommand):
    help = (
        'Audita (solo lectura) ventas facturadas ante ARCA con devoluciones '
        'sin Nota de Crédito, o anuladas sin devolución registrada.'
    )

    def handle(self, *args, **options):
        ventas = (
            Venta.objects
            .filter(comprobante_arca__isnull=False)
            .select_related('comprobante_arca')
            .prefetch_related('devoluciones__nota_credito_arca')
            .order_by('fecha', 'numero')
        )

        anuladas_sin_devolucion = []
        devoluciones_sin_nc = []

        for venta in ventas:
            devoluciones = list(venta.devoluciones.all())

            if venta.estado == EstadoVenta.ANULADA and not devoluciones:
                anuladas_sin_devolucion.append(venta)
                continue

            for dev in devoluciones:
                if getattr(dev, 'nota_credito_arca', None) is None:
                    devoluciones_sin_nc.append(dev)

        self.stdout.write(f'Revisadas {ventas.count()} venta(s) facturada(s) ante ARCA.\n')

        if not anuladas_sin_devolucion and not devoluciones_sin_nc:
            self.stdout.write(self.style.SUCCESS('No se encontró ningún hueco fiscal. Todo en orden.'))
            return

        if devoluciones_sin_nc:
            self.stdout.write(self.style.WARNING(
                f'{len(devoluciones_sin_nc)} devolución(es) con factura ARCA pero SIN Nota de '
                f'Crédito — se puede reintentar con "emitir_nc_devolucion <pk>":'
            ))
            for dev in devoluciones_sin_nc:
                cbte = dev.venta.comprobante_arca
                self.stdout.write(
                    f'  - Devolución {dev.numero} (pk={dev.pk}) de la venta {dev.venta.numero} '
                    f'({dev.venta.fecha}) — factura {cbte.get_tipo_comprobante_display()} '
                    f'{cbte.numero_display}, monto devuelto ${dev.monto}.'
                )
            self.stdout.write('')

        if anuladas_sin_devolucion:
            self.stdout.write(self.style.ERROR(
                f'{len(anuladas_sin_devolucion)} venta(s) ANULADA(S) con factura ARCA vigente y SIN '
                f'ninguna devolución registrada — el sistema hoy no tiene ninguna forma automática de '
                f'emitir la Nota de Crédito para estas, hace falta revisarlas caso por caso:'
            ))
            for venta in anuladas_sin_devolucion:
                cbte = venta.comprobante_arca
                self.stdout.write(
                    f'  - Venta {venta.numero} ({venta.fecha}), {venta.cliente_display} — factura '
                    f'{cbte.get_tipo_comprobante_display()} {cbte.numero_display}, CAE {cbte.cae}, '
                    f'importe ${cbte.importe_total}.'
                )
