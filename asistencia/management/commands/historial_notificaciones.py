"""
python manage.py historial_notificaciones [--cantidad N]

Muestra los últimos avisos automáticos que el sistema mandó (o intentó
mandar) — reportes periódicos, alertas de vencimiento/deuda/stock/
cheques, etc. De solo lectura: lee HistorialNotificacion, no manda nada
nuevo. Sirve para confirmar que el pase diario (Tarea Programada /
Task Scheduler que corre "correr_asistencia --tipo todos") sigue
funcionando, y para ver si algún envío falló (queda registrado con su
motivo, aunque no se haya notado en su momento).

OJO: que no aparezca nada reciente no siempre es un problema — varias
alertas solo se registran cuando HAY algo que avisar (ej: "alerta de
vencimiento" no deja rastro si no hay productos por vencer ese día).
Un silencio de muchos días es una señal para revisar, no una prueba
certera de que algo esté roto.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from asistencia.models import HistorialNotificacion


class Command(BaseCommand):
    help = 'Muestra los últimos avisos automáticos enviados (o que fallaron), para confirmar que el pase diario sigue funcionando.'

    def add_arguments(self, parser):
        parser.add_argument('--cantidad', type=int, default=15,
                             help='Cuántos avisos recientes mostrar (por defecto 15).')

    def handle(self, *args, **options):
        cantidad = options['cantidad']
        notificaciones = list(HistorialNotificacion.objects.order_by('-enviado_el')[:cantidad])

        if not notificaciones:
            self.stdout.write('Todavía no se registró ningún aviso automático en este sistema.')
            return

        for n in notificaciones:
            estado = self.style.SUCCESS('OK') if n.exito else self.style.ERROR('FALLÓ')
            self.stdout.write(
                f'{timezone.localtime(n.enviado_el):%d/%m/%Y %H:%M} — {estado} — '
                f'{n.get_tipo_display()} — {n.destinatario} — {n.asunto}'
            )
            if not n.exito and n.detalle_error:
                self.stdout.write(f'    Motivo del fallo: {n.detalle_error}')

        dias_desde_ultimo = (timezone.now() - notificaciones[0].enviado_el).days
        if dias_desde_ultimo >= 3:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'El último aviso registrado fue hace {dias_desde_ultimo} día(s). '
                'Puede ser normal (no siempre hay algo que avisar), pero si esperabas '
                'algo más reciente, revisá que la Tarea Programada del pase diario '
                'siga corriendo en el servidor.'
            ))
