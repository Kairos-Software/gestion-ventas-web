"""
Compresión de imágenes de producto/paquete antes de guardarlas en disco.

Sin esto, una foto de celular sin comprimir (3-5 MB) se guarda tal cual en
el disco de la propia VPS (MEDIA_ROOT) — con varios clientes y varias
imágenes por producto, eso se come el disco muy rápido. Acá se redimensiona
a un lado máximo razonable para catálogo web y se recomprime, manteniendo
buena calidad visual.
"""
import os
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

LADO_MAXIMO = 1600
CALIDAD_JPEG = 82


def comprimir_imagen_subida(archivo, lado_maximo=LADO_MAXIMO, calidad=CALIDAD_JPEG):
    """
    Recibe un archivo de imagen (subido o abierto desde storage) y devuelve
    un ContentFile ya redimensionado/recomprimido, listo para asignar a un
    ImageField. Las imágenes con transparencia (PNG) se conservan como PNG
    optimizado; el resto se convierte a JPEG, que pesa mucho menos para
    fotos de producto.
    """
    archivo.seek(0)
    imagen = Image.open(archivo)
    imagen = ImageOps.exif_transpose(imagen)  # respeta la orientación real de fotos de celular

    tiene_alfa = imagen.mode in ('RGBA', 'LA') or (imagen.mode == 'P' and 'transparency' in imagen.info)

    if imagen.width > lado_maximo or imagen.height > lado_maximo:
        imagen.thumbnail((lado_maximo, lado_maximo), Image.LANCZOS)

    buffer = BytesIO()
    nombre_base = os.path.splitext(os.path.basename(archivo.name))[0]

    if tiene_alfa:
        if imagen.mode != 'RGBA':
            imagen = imagen.convert('RGBA')
        imagen.save(buffer, format='PNG', optimize=True)
        nombre_final = f'{nombre_base}.png'
    else:
        if imagen.mode != 'RGB':
            imagen = imagen.convert('RGB')
        imagen.save(buffer, format='JPEG', quality=calidad, optimize=True, progressive=True)
        nombre_final = f'{nombre_base}.jpg'

    buffer.seek(0)
    return ContentFile(buffer.read(), name=nombre_final)
