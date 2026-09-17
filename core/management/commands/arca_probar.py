"""
python manage.py arca_probar [--emitir] [--cuit CUIT] [--tipo CBTE_TIPO]

Reproduce en Python la prueba manual hecha a mano contra homologación:
autentica (WSAA), consulta el estado del servicio (FEDummy) y el último
comprobante autorizado (FECompUltimoAutorizado). Con --emitir, además pide
un CAE de prueba (Factura C, $1000, Consumidor Final) — sirve para validar
que ConfiguracionArca + core/services_arca/ funcionan de punta a punta antes
de construir cualquier UI de venta encima.

--tipo permite consultar el último autorizado de OTRO tipo de comprobante
(por defecto Factura C) sin emitir nada — es de solo lectura, así que sirve
para chequear si el punto de venta está habilitado para un tipo antes de
programar nada: si ARCA devuelve un número (aunque sea 0), está habilitado;
si responde con un error, hay que habilitarlo en el portal de ARCA primero.
Tabla de códigos (familia Factura/Nota de Débito/Nota de Crédito):
  A: 1 / 2 / 3      B: 6 / 7 / 8      C: 11 / 12 / 13
Ej: --tipo 13 chequea si se puede emitir Nota de Crédito C.
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import ConfiguracionArca, DatosEmpresa
from core.services_arca import wsaa, wsfe
from core.services_arca.tipos import CondicionIvaReceptor, DOC_TIPO_CONSUMIDOR_FINAL
from core.services_arca.wsaa import ArcaError
from ventas.models import TipoComprobante


class Command(BaseCommand):
    help = 'Prueba la conexión con ARCA (WSAA + WSFE) usando ConfiguracionArca.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--emitir', action='store_true',
            help='Además de probar la conexión, pide un CAE de prueba (Factura C, $1000, Consumidor Final).',
        )
        parser.add_argument(
            '--cuit', type=str, default=None,
            help='CUIT a usar (por defecto, el de DatosEmpresa).',
        )
        parser.add_argument(
            '--tipo', type=int, default=None,
            help='Código de tipo de comprobante a consultar en FECompUltimoAutorizado '
                 '(por defecto, Factura C = 11). Solo consulta, no emite nada.',
        )

    def handle(self, *args, **options):
        config = ConfiguracionArca.get_solo()
        if not config.tiene_certificado():
            raise CommandError(
                'No hay certificado cargado. Cargalo en Configuración → '
                'Facturación Electrónica, o completá certificado_pem/clave_privada '
                'en ConfiguracionArca.'
            )

        cuit = options['cuit'] or DatosEmpresa.get_solo().cuit
        if not cuit:
            raise CommandError(
                'No hay CUIT configurado (ni en DatosEmpresa ni pasado con --cuit).'
            )
        cuit = cuit.replace('-', '').strip()

        self.stdout.write(f'Ambiente: {config.get_ambiente_display()}')
        self.stdout.write(f'Punto de venta: {config.punto_venta}')
        self.stdout.write(f'CUIT: {cuit}')
        self.stdout.write('')

        try:
            self.stdout.write('Autenticando (WSAA)...')
            wsaa.obtener_token(config)
            self.stdout.write(self.style.SUCCESS('  OK — token obtenido/reutilizado.'))

            self.stdout.write('Consultando estado del servicio (FEDummy)...')
            estado = wsfe.fe_dummy(config)
            self.stdout.write(self.style.SUCCESS(f'  OK — {estado}'))

            tipo_consulta = options['tipo'] or TipoComprobante.FACTURA_C
            self.stdout.write(f'Consultando último comprobante autorizado (tipo {tipo_consulta})...')
            ultimo = wsfe.comp_ultimo_autorizado(
                config, cuit, config.punto_venta, tipo_consulta,
            )
            self.stdout.write(self.style.SUCCESS(f'  OK — último Nro: {ultimo}'))
            if options['tipo']:
                self.stdout.write(self.style.SUCCESS(
                    '  → El punto de venta SÍ está habilitado para este tipo de comprobante.'
                ))

            if options['emitir']:
                self.stdout.write('Pidiendo CAE de prueba (Factura C, $1000, Consumidor Final)...')
                resultado = wsfe.solicitar_cae(
                    config,
                    cuit=cuit,
                    tipo_comprobante=TipoComprobante.FACTURA_C,
                    doc_tipo=DOC_TIPO_CONSUMIDOR_FINAL,
                    doc_nro='0',
                    condicion_iva_receptor_id=CondicionIvaReceptor.CONSUMIDOR_FINAL,
                    importe_total=1000,
                    importe_neto=1000,
                    importe_iva=0,
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  OK — Comprobante Nro {resultado["numero"]}, '
                    f'CAE {resultado["cae"]}, vence {resultado["cae_vencimiento"]}'
                ))
        except ArcaError as exc:
            raise CommandError(str(exc))
