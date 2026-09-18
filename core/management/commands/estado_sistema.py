"""
python manage.py estado_sistema

Panorama general de solo lectura de ESTA instalación puntual: qué versión
del código tiene, si le falta aplicar alguna actualización de la base de
datos, cuánto pesa la base y cuánto espacio ocupan los archivos subidos
(fotos, comprobantes). Pensado para el caso de tener el mismo sistema
clonado una vez por cliente: sirve para confirmar de un vistazo si ESTA
instalación puntual quedó al día después de un `git pull`, sin necesitar
acceso por consola.
"""
import os
import shutil
import subprocess
import sys
from io import StringIO

import django
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Panorama de esta instalación: versión de código, migraciones pendientes, tamaño de la base y espacio usado por archivos subidos.'

    def handle(self, *args, **options):
        self.stdout.write('— Código —')
        self._mostrar_git()
        self.stdout.write('')

        self.stdout.write('— Base de datos —')
        self._mostrar_migraciones()
        self._mostrar_tamano_bd()
        self.stdout.write('')

        self.stdout.write('— Archivos subidos —')
        self._mostrar_media()
        self.stdout.write('')

        self.stdout.write(f'Python {sys.version.split()[0]} — Django {django.get_version()}')

    def _mostrar_git(self):
        # Separador "|" (ASCII) en vez de un guión largo en el propio
        # --format: pasar un caracter no-ASCII como argumento de consola
        # y decodificar la salida del subproceso con la codificación
        # equivocada del sistema operativo puede corromperlo (mojibake).
        # El guión largo se arma acá, del lado de Python, nunca cruza el
        # límite del subproceso.
        try:
            r = subprocess.run(
                ['git', 'log', '-1', '--format=%h|%ci|%s'],
                cwd=settings.BASE_DIR, capture_output=True,
                encoding='utf-8', errors='replace', timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                partes = r.stdout.strip().split('|', 2)
                if len(partes) == 3:
                    commit, fecha, mensaje = partes
                    self.stdout.write(
                        f'Última actualización de código instalada: '
                        f'{commit} — {fecha} — {mensaje}'
                    )
                else:
                    self.stdout.write(f'Última actualización de código instalada: {r.stdout.strip()}')
            else:
                self.stdout.write('No se pudo leer el historial de código en este servidor.')
        except Exception as exc:
            self.stdout.write(f'No se pudo consultar el historial de código: {exc}')

    def _mostrar_migraciones(self):
        buffer = StringIO()
        call_command('showmigrations', '--plan', stdout=buffer, no_color=True)
        pendientes = [
            linea.strip() for linea in buffer.getvalue().splitlines()
            if linea.strip().startswith('[ ]')
        ]
        if pendientes:
            self.stdout.write(self.style.WARNING(
                f'Faltan aplicar {len(pendientes)} actualización(es) de la base de datos '
                '(hace falta correr "python manage.py migrate" en este servidor):'
            ))
            for linea in pendientes:
                self.stdout.write(f'  {linea}')
        else:
            self.stdout.write(self.style.SUCCESS('La base de datos está al día con el código instalado.'))

    def _mostrar_tamano_bd(self):
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_size_pretty(pg_database_size(current_database()))')
                tamano = cursor.fetchone()[0]
            self.stdout.write(f'Tamaño de la base de datos: {tamano}')
        except Exception as exc:
            self.stdout.write(f'No se pudo medir el tamaño de la base de datos: {exc}')

    def _mostrar_media(self):
        media_root = settings.MEDIA_ROOT
        total_bytes = 0
        cantidad = 0
        for root, _dirs, files in os.walk(media_root):
            for nombre in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, nombre))
                    cantidad += 1
                except OSError:
                    continue
        self.stdout.write(
            f'Fotos y comprobantes guardados: {cantidad} archivo(s), '
            f'{total_bytes / (1024 * 1024):.1f} MB en total.'
        )
        try:
            uso = shutil.disk_usage(media_root)
            self.stdout.write(
                f'Espacio libre en el disco del servidor: '
                f'{uso.free / (1024 ** 3):.1f} GB de {uso.total / (1024 ** 3):.1f} GB.'
            )
        except Exception:
            pass
