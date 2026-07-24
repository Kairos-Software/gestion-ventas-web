"""
Datos de prueba para poder previsualizar el catálogo público sin tener
que cargar productos reales a mano. Todo lo que crea esta herramienta
queda registrado en DatoDemo (ver catalogo/models.py) para poder
borrarlo después sin tocar nada cargado manualmente — y además todo
lleva el prefijo "DEMO - " en el nombre, para que se distinga a
simple vista en las listas del sistema.

Las imágenes se bajan de picsum.photos (seed determinístico por
producto, para que recargar los mismos datos dé las mismas fotos). Si
no hay conexión, se genera un placeholder de color liso localmente con
Pillow — no depende de internet para funcionar.
"""
import hashlib
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import requests
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from productos.models import (
    AplicacionOferta, CategoriaProducto, EstadoProducto, ModoPrecio,
    Oferta, PaqueteComponente, Producto, ProductoImagen, TipoOferta,
)
from .models import DatoDemo

logger = logging.getLogger(__name__)

PREFIJO_DEMO = 'DEMO - '

CATEGORIAS_DEMO = ['Bebidas', 'Almacén', 'Limpieza', 'Snacks', 'Congelados']

# (nombre, categoría, precio, destacado, agotado, cantidad de imágenes)
PRODUCTOS_DEMO = [
    ('Agua mineral 500ml',           'Bebidas',    Decimal('450'),  False, False, 2),
    ('Gaseosa cola 1.5L',            'Bebidas',    Decimal('1200'), True,  False, 2),
    ('Cerveza rubia 473ml',          'Bebidas',    Decimal('900'),  False, False, 1),
    ('Arroz largo fino 1kg',         'Almacén',    Decimal('1350'), False, False, 2),
    ('Fideos tallarín 500g',         'Almacén',    Decimal('890'),  False, False, 1),
    ('Aceite de girasol 900ml',      'Almacén',    Decimal('2100'), True,  False, 2),
    ('Detergente concentrado 750ml', 'Limpieza',   Decimal('1600'), False, False, 1),
    ('Lavandina 1L',                 'Limpieza',   Decimal('780'),  False, True,  1),
    ('Papas fritas 150g',            'Snacks',     Decimal('1100'), True,  False, 2),
    ('Maní salado 200g',             'Snacks',     Decimal('950'),  False, False, 1),
    ('Helado de crema 1L',           'Congelados', Decimal('3200'), False, False, 2),
    ('Hamburguesas x4',              'Congelados', Decimal('2600'), False, False, 1),
]

# (nombre, precio, [(nombre del producto componente, cantidad), ...])
PAQUETES_DEMO = [
    ('Combo Asado', Decimal('5500'), [
        ('Cerveza rubia 473ml', 6), ('Hamburguesas x4', 1),
    ]),
    ('Combo Limpieza Hogar', Decimal('2100'), [
        ('Detergente concentrado 750ml', 1), ('Lavandina 1L', 1),
    ]),
    ('Pack Merienda', Decimal('1800'), [
        ('Papas fritas 150g', 1), ('Maní salado 200g', 1), ('Gaseosa cola 1.5L', 1),
    ]),
    ('Combo Despensa Básica', Decimal('4200'), [
        ('Arroz largo fino 1kg', 1), ('Fideos tallarín 500g', 2), ('Aceite de girasol 900ml', 1),
    ]),
]


def _registrar(obj):
    DatoDemo.objects.get_or_create(
        content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk,
    )


def _placeholder_generado(texto, lado=800):
    from PIL import Image, ImageDraw

    color = tuple(int(hashlib.md5(texto.encode()).hexdigest()[i:i + 2], 16) for i in (0, 2, 4))
    img = Image.new('RGB', (lado, lado), color)
    ImageDraw.Draw(img).text((24, lado // 2 - 10), texto, fill='white')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


def _imagen_demo(seed, lado=800):
    try:
        resp = requests.get(f'https://picsum.photos/seed/{seed}/{lado}/{lado}', timeout=3)
        resp.raise_for_status()
        return resp.content
    except Exception:
        logger.warning('No se pudo bajar imagen demo de picsum (seed=%s), genero placeholder local.', seed)
        return _placeholder_generado(seed, lado)


@transaction.atomic
def cargar_datos_demo():
    if DatoDemo.objects.exists():
        raise ValueError('Ya hay datos de prueba cargados — eliminalos antes de volver a cargar.')

    resumen = {'categorias': 0, 'productos': 0, 'imagenes': 0, 'paquetes': 0, 'ofertas': 0}

    categorias = {}
    for i, nombre in enumerate(CATEGORIAS_DEMO):
        cat = CategoriaProducto.objects.create(
            nombre=f'{PREFIJO_DEMO}{nombre}', activo=True, orden=i,
            descripcion='Categoría de prueba — creada por la herramienta de datos demo.',
        )
        _registrar(cat)
        categorias[nombre] = cat
        resumen['categorias'] += 1

    productos = {}
    tareas_imagen = []  # (producto, idx, seed) — se resuelven todas en paralelo después
    for nombre, cat_nombre, precio, destacado, agotado, n_imgs in PRODUCTOS_DEMO:
        p = Producto.objects.create(
            nombre=f'{PREFIJO_DEMO}{nombre}',
            categoria=categorias[cat_nombre],
            descripcion_publica=f'{nombre} — producto de prueba para previsualizar el catálogo.',
            precio_venta=precio,
            modo_precio=ModoPrecio.MANUAL,
            estado=EstadoProducto.AGOTADO if agotado else EstadoProducto.ACTIVO,
            publicado=True,
            destacado=destacado,
            stock_actual=Decimal('0') if agotado else Decimal('25'),
        )
        _registrar(p)
        productos[nombre] = p
        resumen['productos'] += 1

        for idx in range(n_imgs):
            tareas_imagen.append((p, idx, f'kai-cart-{p.pk}-{idx}'))

    # Las imágenes se bajan todas juntas en paralelo — una por una (como era
    # antes) con 12 productos podía tardar más de un minuto si picsum.photos
    # respondía lento, y el click se sentía "colgado".
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = pool.map(lambda t: (t[0], t[1], _imagen_demo(t[2])), tareas_imagen)
        for p, idx, data in resultados:
            img = ProductoImagen.objects.create(
                producto=p, imagen=ContentFile(data, name=f'demo-{p.pk}-{idx}.jpg'),
                es_portada=(idx == 0), orden=idx,
            )
            _registrar(img)
            resumen['imagenes'] += 1

    for nombre, precio, componentes in PAQUETES_DEMO:
        pq = Producto.objects.create(
            nombre=f'{PREFIJO_DEMO}{nombre}',
            descripcion_publica=f'{nombre} — combo de prueba para previsualizar el catálogo.',
            precio_venta=precio,
            modo_precio=ModoPrecio.MANUAL,
            estado=EstadoProducto.ACTIVO,
            publicado=True,
            es_paquete=True,
            gestiona_stock=False,
        )
        _registrar(pq)
        resumen['paquetes'] += 1
        for nombre_comp, cantidad in componentes:
            comp = PaqueteComponente.objects.create(
                paquete=pq, producto=productos[nombre_comp], cantidad=cantidad,
            )
            _registrar(comp)

    hoy = timezone.now().date()
    hasta = hoy + timedelta(days=30)

    oferta_pct = Oferta.objects.create(
        nombre=f'{PREFIJO_DEMO}20% en Snacks', tipo=TipoOferta.PORCENTAJE,
        porcentaje=Decimal('20'), fecha_inicio=hoy, fecha_fin=hasta,
        aplicacion=AplicacionOferta.AUTOMATICA, activa=True,
    )
    oferta_pct.categorias.add(categorias['Snacks'])
    _registrar(oferta_pct)
    resumen['ofertas'] += 1

    oferta_umbral = Oferta.objects.create(
        nombre=f'{PREFIJO_DEMO}10% llevando $5000 o más', tipo=TipoOferta.UMBRAL,
        porcentaje=Decimal('10'), monto_minimo=Decimal('5000'),
        fecha_inicio=hoy, fecha_fin=hasta,
        aplicacion=AplicacionOferta.AUTOMATICA, activa=True,
    )
    _registrar(oferta_umbral)
    resumen['ofertas'] += 1

    return resumen


@transaction.atomic
def eliminar_datos_demo():
    registros = list(DatoDemo.objects.select_related('content_type').all())
    por_modelo = {}
    for r in registros:
        por_modelo.setdefault(r.content_type.model, []).append(r.object_id)

    # Los archivos de imagen no se borran solos al eliminar la fila (así
    # es en todo el proyecto — ver ProductoImagenEliminarAjax en
    # productos/views_productos.py, que también lo hace a mano).
    for pk in por_modelo.get('productoimagen', []):
        img = ProductoImagen.objects.filter(pk=pk).first()
        if img and img.imagen and os.path.isfile(img.imagen.path):
            os.remove(img.imagen.path)

    eliminados = 0
    # Orden importa: los paquetes primero, para que al cascadear se lleven
    # puesto sus PaqueteComponente y liberen el PROTECT sobre los productos
    # componente (que se borran en la segunda tanda).
    eliminados += Producto.objects.filter(
        pk__in=por_modelo.get('producto', []), es_paquete=True,
    ).delete()[0]
    eliminados += Producto.objects.filter(
        pk__in=por_modelo.get('producto', []), es_paquete=False,
    ).delete()[0]
    eliminados += Oferta.objects.filter(pk__in=por_modelo.get('oferta', [])).delete()[0]
    eliminados += CategoriaProducto.objects.filter(pk__in=por_modelo.get('categoriaproducto', [])).delete()[0]

    # Lo que quede (imágenes/componentes ya cascadeados con su producto,
    # o cualquier registro huérfano) se limpia junto con la tabla de tracking.
    DatoDemo.objects.all().delete()

    return eliminados
