from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from core.models import DatosEmpresa


class Command(BaseCommand):
    help = (
        'Manda un mail de prueba al email de DatosEmpresa (el mismo que '
        'aparece en los tickets), para confirmar que el envío funciona '
        'antes de conectar alertas reales. Con --to se puede probar contra '
        'otro destinatario sin necesidad de tener DatosEmpresa cargado.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--to', dest='to', default=None,
            help='Email de destino para la prueba (si no se pasa, usa '
                 'DatosEmpresa.email).',
        )

    def handle(self, *args, **options):
        destino = options['to']
        if not destino:
            empresa = DatosEmpresa.get_solo()
            destino = empresa.email
        if not destino:
            raise CommandError(
                'No hay destino: pasá --to tu-mail@ejemplo.com o cargá el '
                'email en Configuración > Datos de la empresa.'
            )

        send_mail(
            subject='Prueba de asistencia — Sistema Kairos',
            message=(
                'Este es un mail de prueba del módulo de asistencia.\n\n'
                'Si lo recibiste, el envío de mail está funcionando.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            recipient_list=[destino],
        )
        self.stdout.write(self.style.SUCCESS(f'Mail de prueba enviado a {destino}'))
