"""
asistencia/management/commands/probar_asistencia.py

COMANDO DE PRUEBA. Genera datos de ejemplo (si hace falta) y manda los
7 mails de asistencia (reporte mensual, semanal, vencimiento, deuda
por pagar, deuda pagada, stock estancado, cheques) a una casilla de
prueba, para poder revisar diseño y contenido sin esperar a que pase
un mes de verdad o venza una deuda real.

CÓMO USARLO
-----------
    python manage.py probar_asistencia

Se puede correr las veces que haga falta: si ya hay datos de prueba
cargados (productos/ventas/compras con el prefijo "TEST - "), los
reutiliza en vez de duplicarlos. Para forzar datos nuevos de cero:

    python manage.py probar_asistencia --regenerar-datos

QUÉ CAMBIAR SEGÚN EL CASO
--------------------------
1) CASILLA QUE RECIBE (destino):
   NO se pasa por parámetro ni se hardcodea en correr_asistencia — sale
   SIEMPRE del email de destino cargado en Configuración > Notificaciones
   (PreferenciaAsistencia.email_destino). Si ese campo está vacío, no se
   manda nada — a propósito NO cae en el email de Datos de la empresa
   (ese es público, el mismo de los tickets, y nunca se le avisó al
   usuario que sus alertas podrían terminar ahí). Este es el
   comportamiento real, igual en desarrollo y en producción.

   Este comando de prueba (solo este) SIEMPRE pisa ese campo con el
   mail escrito abajo en EMAIL_DE_RESPALDO, sin condiciones — así el
   test es 100% predecible: para cambiar a dónde llegan los mails de
   prueba, editá esa línea acá abajo y guardá el archivo, nada más.
   No hace falta tocar el navegador para nada de esto.

2) CASILLA QUE ENVÍA (remitente):
   Eso tampoco se toca acá: se configura en .env.local / .env.production
   (EMAIL_HOST_USER / EMAIL_HOST_PASSWORD / EMAIL_BACKEND). Hoy manda
   desde un Gmail personal para poder probar; el día que el negocio
   quiera un remitente "oficial" propio, se cambia ahí sin tocar código.

3) QUÉ REPORTES/ALERTAS SE MANDAN Y CADA CUÁNTO:
   También sale de Configuración > Notificaciones — los toggles de
   cada tipo (mensual, semanal, vencimiento, deuda, etc.) y los "días
   de aviso" de cada uno. Si algo no llega, revisá que esté activado ahí.

4) FECHA SIMULADA (probar el corte de mes, por ejemplo):
       python manage.py probar_asistencia --fecha 2026-08-01

5) DATOS DE PRUEBA:
   --regenerar-datos borra lo viejo (solo lo que tiene el prefijo
   "TEST - ") y crea todo de nuevo. Es un atajo para desarrollo nada
   más — jamás correr esto en producción.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from asistencia.models import PreferenciaAsistencia
from compras.models import Compra
from productos.models import CategoriaProducto, Oferta, Producto
from ventas.models import Venta

# Este comando de prueba SIEMPRE manda acá, sin condiciones — editá
# esta línea para cambiar a dónde llegan los mails de prueba. No afecta
# a correr_asistencia (el comando "real", que solo mira Configuración).
EMAIL_DE_RESPALDO = 'dn.lopez.2804@gmail.com'


class Command(BaseCommand):
    help = (
        'Genera datos de ejemplo (si hace falta) y manda los reportes/'
        'alertas de asistencia según lo configurado en Configuración > '
        'Notificaciones. Ver el docstring del archivo para más detalle.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--fecha', default=None,
                             help='Fecha simulada de "hoy" (YYYY-MM-DD).')
        parser.add_argument('--regenerar-datos', action='store_true',
                             help='Borra los datos de prueba anteriores y '
                                  'crea todo de nuevo.')

    def handle(self, *args, **options):
        fecha = options['fecha']
        regenerar = options['regenerar_datos']

        pref = PreferenciaAsistencia.get_solo()
        pref.email_destino = EMAIL_DE_RESPALDO
        pref.save(update_fields=['email_destino'])
        self.stdout.write(f'Este test manda a {EMAIL_DE_RESPALDO} (se define arriba, en este archivo).')

        hay_datos = Producto.objects.filter(nombre__startswith='TEST - ').exists()

        if regenerar and hay_datos:
            self.stdout.write('Borrando datos de prueba anteriores...')
            self._limpiar_datos_previos()
            hay_datos = False

        if not hay_datos:
            self.stdout.write('Generando datos de prueba (productos, ventas, deudas, cheques)...')
            call_command('generar_datos_prueba')
        else:
            self.stdout.write(
                'Ya había datos de prueba cargados, los reutilizo '
                '(pasá --regenerar-datos si querés recrearlos de cero).'
            )

        self.stdout.write('Mandando los reportes/alertas configurados...')
        call_command('correr_asistencia', tipo='todos', fecha=fecha, forzar=True)
        # 'deuda_pagada' quedó afuera de 'todos' a propósito (en
        # producción ese mail sale al toque al confirmar el pago, no
        # del batch diario) — se prueba aparte para no perder cobertura
        # del diseño de ese mail acá.
        call_command('correr_asistencia', tipo='deuda_pagada', fecha=fecha, forzar=True)
        self.stdout.write(self.style.SUCCESS('Listo. Revisá la casilla (y la carpeta de spam).'))

    def _limpiar_datos_previos(self):
        """
        Borra SOLO lo que generó generar_datos_prueba (todo lo que
        cuelga de un producto "TEST - "), sin tocar ventas/compras
        reales que pueda haber en la misma base más adelante.
        """
        from caja.models import Cheque, CuentaCaja, Deuda, MovimientoCaja

        ventas_test = Venta.objects.filter(items__producto__nombre__startswith='TEST - ').distinct()
        compras_test = Compra.objects.filter(items__producto__nombre__startswith='TEST - ').distinct()
        venta_ids = list(ventas_test.values_list('pk', flat=True))
        compra_ids = list(compras_test.values_list('pk', flat=True))
        deuda_ids = list(
            Deuda.objects.filter(pago_compra__compra_id__in=compra_ids).values_list('pk', flat=True)
        )

        ventas_test.delete()
        compras_test.delete()
        Deuda.objects.filter(pk__in=deuda_ids).delete()
        Cheque.objects.filter(numero_cheque__startswith='TEST - ').delete()

        # MovimientoCaja no tiene FK real a Venta/Compra (se vincula por
        # origen_app/origen_id), así que no cae solo con el cascade de
        # arriba: hay que borrarlo explícitamente por esos ids.
        MovimientoCaja.objects.filter(origen_app='ventas', origen_id__in=venta_ids).delete()
        MovimientoCaja.objects.filter(origen_app='compras', origen_id__in=compra_ids).delete()

        CuentaCaja.objects.filter(nombre__startswith='TEST - ').delete()
        Oferta.objects.filter(nombre__startswith='TEST - ').delete()
        Producto.objects.filter(nombre__startswith='TEST - ').delete()
        CategoriaProducto.objects.filter(nombre__startswith='TEST - ').delete()
