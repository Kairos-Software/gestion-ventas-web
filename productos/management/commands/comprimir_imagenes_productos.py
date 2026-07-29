from django.core.management.base import BaseCommand

from productos.models import ProductoImagen
from productos.utils_imagenes import comprimir_imagen_subida


class Command(BaseCommand):
    help = (
        'Recomprime las imágenes de producto/paquete ya subidas (las nuevas ya '
        'se comprimen solas al subirlas, ver ProductoImagen.save()). Pensado '
        'para correr una sola vez y recuperar el espacio que ocuparon fotos '
        'de celular sin comprimir. Es seguro repetirlo: si una imagen ya está '
        'comprimida y no hay ahorro, se deja tal cual.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Solo informa cuánto se ahorraría, sin modificar ningún archivo.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        total_antes = 0
        total_despues = 0
        procesadas = 0
        omitidas = 0
        sin_archivo = 0

        for img in ProductoImagen.objects.select_related('producto').iterator():
            if not img.imagen:
                sin_archivo += 1
                continue

            storage = img.imagen.storage
            nombre_viejo = img.imagen.name

            if not storage.exists(nombre_viejo):
                sin_archivo += 1
                continue

            peso_original = img.imagen.size
            with img.imagen.open('rb') as f:
                nuevo_contenido = comprimir_imagen_subida(f)

            if nuevo_contenido.size >= peso_original:
                omitidas += 1
                continue

            procesadas    += 1
            total_antes   += peso_original
            total_despues += nuevo_contenido.size

            if dry_run:
                self.stdout.write(
                    f'{nombre_viejo}: {peso_original / 1024:.0f} KB -> {nuevo_contenido.size / 1024:.0f} KB'
                )
                continue

            # Borrar el archivo viejo ANTES de guardar el nuevo: si el nombre no
            # cambia (misma extensión), el storage no pisa un archivo existente
            # y guardaría el nuevo con un sufijo aparte, dejando el viejo huérfano.
            storage.delete(nombre_viejo)
            img.imagen.save(nuevo_contenido.name, nuevo_contenido, save=True)

        self.stdout.write(self.style.SUCCESS(
            f'Procesadas: {procesadas} | Omitidas (ya comprimidas): {omitidas} | '
            f'Sin archivo en disco: {sin_archivo}'
        ))
        if total_antes:
            ahorro_mb = (total_antes - total_despues) / (1024 * 1024)
            porcentaje = (1 - total_despues / total_antes) * 100
            self.stdout.write(self.style.SUCCESS(
                f'Espacio antes: {total_antes / (1024 * 1024):.1f} MB | '
                f'después: {total_despues / (1024 * 1024):.1f} MB | '
                f'ahorro: {ahorro_mb:.1f} MB ({porcentaje:.0f}%)'
            ))
        if dry_run:
            self.stdout.write(self.style.WARNING('Modo --dry-run: no se modificó ningún archivo.'))
