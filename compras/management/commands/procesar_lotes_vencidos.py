from django.core.management.base import BaseCommand

from compras.models import procesar_lotes_vencidos


class Command(BaseCommand):
    help = (
        'Da de baja como pérdida (automática, por vencimiento) los lotes '
        'activos cuya fecha_vencimiento ya pasó. Ya se ejecuta solo al '
        'visitar Inventario; este comando es para programarlo aparte '
        '(ej: Task Scheduler de Windows) si hace falta que corra aunque '
        'nadie abra la pantalla ese día.'
    )

    def handle(self, *args, **options):
        perdidas = procesar_lotes_vencidos()
        if not perdidas:
            self.stdout.write('No había lotes vencidos con stock.')
            return
        self.stdout.write(f'Se registraron {len(perdidas)} pérdida(s) por vencimiento:')
        for p in perdidas:
            self.stdout.write(f'  - {p.producto_nombre_snapshot}: {p.cantidad}u (lote {p.lote_codigo_snapshot})')
