from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


def _catalogo_hero_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/hero{ext}'


def _catalogo_institucional_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/institucional{ext}'


def _catalogo_kinetic_hero_fondo_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/kinetic-hero-fondo{ext}'


def _catalogo_bento_hero_spot1_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/bento-hero-spot1{ext}'


def _catalogo_bento_hero_spot2_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/bento-hero-spot2{ext}'


def _catalogo_directo_hero_pieza1_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/directo-hero-pieza1{ext}'


def _catalogo_directo_hero_pieza2_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/directo-hero-pieza2{ext}'


def _catalogo_directo_hero_pieza3_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/directo-hero-pieza3{ext}'


def _catalogo_cta_final_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/cta-final{ext}'


def _catalogo_kinetic_banner_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/kinetic-banner{ext}'


def _catalogo_coleccion_editorial_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/colecciones-editorial/{instance.pk}{ext}'


def _catalogo_tile_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    # Puede haber varios tiles a la vez, la ruta va por pk — requiere que
    # la fila ya exista (se sube en un segundo paso, ver
    # catalogo/views_config.py:CatalogoTileImagenAjax).
    return f'catalogo/tiles/{instance.pk}{ext}'


class PlantillaCatalogo(models.TextChoices):
    ALMACEN   = 'almacen',   'Almacén'
    BENTO     = 'bento',     'Bento'
    KINETIC   = 'kinetic',   'Kinetic'
    # El slug interno sigue siendo 'lumina' (campos de color, carpeta de
    # templates, CSS/JS) — solo cambió el nombre visible tras el rediseño
    # cobalto/coral, que ya no tiene nada que ver con la identidad pastel
    # original. Renombrar el slug implicaría migrar campos de modelo sin
    # ganar nada para el dueño, que solo ve la etiqueta.
    LUMINA    = 'lumina',    'Directo'
    EDITORIAL = 'editorial', 'Editorial'


class ConfiguracionCatalogo(models.Model):
    """
    Contenido editable del catálogo público — no diseño, sino los textos
    e imagen que cambian según el negocio (título del hero, bajada,
    sobre nosotros, contacto). Editable desde Configuración → Catálogo
    público (ver core/views.py:configuracion), con vista previa en vivo.
    Mismo patrón singleton que DatosEmpresa (ver core/models.py).
    hero_titulo/hero_imagen son exclusivos de la plantilla "almacen" (esa
    no tiene carrusel). hero_subtitulo lo usan las cuatro plantillas.
    hero_producto lo usan "almacen"/"bento" para armar la tarjeta
    lateral del hero ("kinetic" tiene su propio panel de stats en su lugar)
    — en "bento", hero_subtitulo es el texto de respaldo hasta que se carga
    el primer slide (ver SlideHeroCatalogo).
    """
    plantilla = models.CharField(
        'Plantilla activa', max_length=20,
        choices=PlantillaCatalogo.choices, default=PlantillaCatalogo.ALMACEN,
    )
    hero_titulo = models.CharField(
        'Título principal', max_length=200, blank=True,
        help_text='Vacío = usa el nombre comercial de la empresa.',
    )
    hero_subtitulo = models.TextField(
        'Bajada / subtítulo', blank=True,
        help_text='Vacío = usa un texto genérico.',
    )
    hero_imagen = models.ImageField(
        'Imagen del hero', upload_to=_catalogo_hero_path, blank=True, null=True,
        help_text='Opcional — si no se carga, el hero se muestra sin foto.',
    )
    hero_producto = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        verbose_name='Producto destacado en el hero',
        help_text='Vacío = se elige automáticamente (el destacado más reciente).',
    )
    hero_imagen_sin_fondo = models.BooleanField(
        'Hero sin tarjeta de fondo (Almacén)', default=False,
        help_text='Si la foto del hero (subida arriba, o la del producto destacado) ya tiene el '
                   'fondo transparente recortado, activá esto para que flote sin la tarjeta '
                   'rectangular detrás.',
    )
    tiles_destacados_titulo = models.CharField(
        'Título de la fila de categorías/marcas (Almacén)', max_length=100, blank=True,
        help_text='Vacío = usa "Categorías y marcas".',
    )
    kinetic_hero_fondo = models.ImageField(
        'Imagen de fondo del hero (Kinetic)', upload_to=_catalogo_kinetic_hero_fondo_path, blank=True, null=True,
        help_text='Opcional, exclusiva de "Kinetic" — si no se carga, el hero se ve sin fondo, '
                   'igual que ahora. Se muestra oscurecida y difuminada detrás del texto.',
    )
    # Las 2 tarjetas "spotlight" del hero de Bento (ver bento/home.html) —
    # mismo criterio que BannerCatalogo.imagen: la presencia de la imagen
    # decide el modo, sin un campo de "modo" aparte. Con imagen cargada,
    # esa tarjeta muestra la foto tal cual (sin datos de producto); vacío,
    # sigue mostrando el producto (spot1 reusa hero_producto de arriba,
    # spot2 tiene su propio campo porque hero_producto ya está tomado).
    hero_spot1_imagen = models.ImageField(
        'Imagen — tarjeta 1 del hero (Bento)', upload_to=_catalogo_bento_hero_spot1_path, blank=True, null=True,
        help_text='Opcional — con imagen cargada, reemplaza al producto destacado de arriba en esta tarjeta.',
    )
    hero_spot2_producto = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        verbose_name='Producto — tarjeta 2 del hero (Bento)',
        help_text='Vacío = se elige automáticamente (combo destacado, o el siguiente producto destacado).',
    )
    hero_spot2_imagen = models.ImageField(
        'Imagen — tarjeta 2 del hero (Bento)', upload_to=_catalogo_bento_hero_spot2_path, blank=True, null=True,
        help_text='Opcional — con imagen cargada, reemplaza al producto de esta tarjeta.',
    )
    directo_hero_producto1 = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        verbose_name='Producto — pieza 1 del hero (Directo)',
        help_text='Vacío = usa el primer producto destacado automático.',
    )
    directo_hero_imagen1 = models.ImageField(
        'Imagen — pieza 1 del hero (Directo)', upload_to=_catalogo_directo_hero_pieza1_path,
        blank=True, null=True,
        help_text='Opcional — con imagen cargada, reemplaza al producto de esta pieza.',
    )
    directo_hero_producto2 = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        verbose_name='Producto — pieza 2 del hero (Directo)',
        help_text='Vacío = usa el segundo producto destacado automático.',
    )
    directo_hero_imagen2 = models.ImageField(
        'Imagen — pieza 2 del hero (Directo)', upload_to=_catalogo_directo_hero_pieza2_path,
        blank=True, null=True,
        help_text='Opcional — con imagen cargada, reemplaza al producto de esta pieza.',
    )
    directo_hero_producto3 = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        verbose_name='Producto — pieza 3 del hero (Directo)',
        help_text='Vacío = usa el tercer producto destacado automático.',
    )
    directo_hero_imagen3 = models.ImageField(
        'Imagen — pieza 3 del hero (Directo)', upload_to=_catalogo_directo_hero_pieza3_path,
        blank=True, null=True,
        help_text='Opcional — con imagen cargada, reemplaza al producto de esta pieza.',
    )
    sobre_nosotros = models.TextField('Sobre nosotros', blank=True)
    mostrar_historia_en_home = models.BooleanField(
        '"Nuestra historia" también en la home (Bento)', default=True,
        help_text='El texto de arriba siempre se muestra en La Tienda. Desactivá esto si no '
                   'querés repetirlo también en la portada del catálogo.',
    )
    cta_final_titulo = models.CharField(
        'Título — banda final (Bento)', max_length=150, blank=True,
        help_text='Opcional — con título cargado aparece una banda de cierre al final de la '
                   'home, para un mensaje distinto al de "Nuestra historia" (ej. envíos, '
                   'empresas). Vacío = no se muestra.',
    )
    cta_final_texto = models.CharField('Bajada — banda final (Bento)', max_length=250, blank=True)
    cta_final_boton_texto = models.CharField('Texto del botón — banda final (Bento)', max_length=40, blank=True)
    cta_final_boton_url = models.CharField('Link del botón — banda final (Bento)', max_length=300, blank=True)
    cta_final_imagen = models.ImageField(
        'Imagen de fondo — banda final (Bento)', upload_to=_catalogo_cta_final_path, blank=True, null=True,
        help_text='Opcional — sin imagen, la banda se ve con el color de fondo liso de siempre.',
    )
    contacto_texto = models.TextField(
        'Texto de contacto', blank=True,
        help_text='Se muestra junto a los datos de contacto en el pie de página.',
    )
    # — Personalización visual/textual — colores de marca, uno por plantilla
    # (cada plantilla tiene su propia identidad, elegir un color en una no
    # debe "contaminar" a las demás). "almacen" usa color_marca/color_marca_
    # secundario (nombres históricos, sin migrar datos).
    color_marca = models.CharField(
        'Color de marca (Almacén)', max_length=7, blank=True,
        help_text='Código hex, ej: #ff9343. Vacío = color por defecto. Botones, precios y detalles.',
    )
    color_marca_secundario = models.CharField(
        'Color secundario (Almacén)', max_length=7, blank=True,
        help_text='Código hex, ej: #111e2f. Vacío = color por defecto. Encabezado, hero y pie de página.',
    )
    color_marca_bento = models.CharField(
        'Color de marca (Bento)', max_length=7, blank=True,
        help_text='Código hex. Vacío = color por defecto de Bento.',
    )
    color_marca_secundario_bento = models.CharField(
        'Color secundario (Bento)', max_length=7, blank=True,
        help_text='Código hex. Vacío = color por defecto de Bento.',
    )
    color_marca_lumina = models.CharField(
        'Color de marca (Lumina)', max_length=7, blank=True,
        help_text='Código hex. Vacío = color por defecto de Lumina.',
    )
    color_marca_secundario_lumina = models.CharField(
        'Color secundario (Lumina)', max_length=7, blank=True,
        help_text='Código hex. Vacío = color por defecto de Lumina.',
    )
    # Fondo predominante de Bento — exclusivo de esta plantilla (a diferencia
    # de color_marca_bento/color_marca_secundario_bento, que son acentos,
    # esto es el fondo de página en sí: crema en modo claro, azul oscuro en
    # modo oscuro). Dos campos porque son 2 colores independientes, uno por
    # modo — no uno derivado del otro.
    color_fondo_bento = models.CharField(
        'Color de fondo — modo claro (Bento)', max_length=7, blank=True,
        help_text='Código hex. Vacío = color por defecto de Bento.',
    )
    color_fondo_bento_oscuro = models.CharField(
        'Color de fondo — modo oscuro (Bento)', max_length=7, blank=True,
        help_text='Código hex. Vacío = color por defecto de Bento.',
    )
    # Kinetic es siempre oscura (no tiene modo claro/oscuro como Bento) —
    # un solo campo alcanza. El resto de la paleta (superficies, bordes)
    # se deriva de este color en CSS con color-mix(), así que un solo hex
    # mantiene el contraste sin que el dueño tenga que elegir 4 tonos.
    color_fondo_kinetic = models.CharField(
        'Color de fondo (Kinetic)', max_length=7, blank=True,
        help_text='Código hex. Vacío = negro por defecto de Kinetic.',
    )
    # Acento principal de Kinetic — campo propio (antes reutilizaba
    # color_marca de Almacén "para no duplicar campos", pero eso violaba la
    # independencia de plantillas: cambiar el color de Almacén cambiaba el
    # de Kinetic sin que nadie lo pidiera, y el panel de admin mostraba/
    # guardaba el color equivocado al estar parado en la pestaña Kinetic.
    # El secundario (--k-secondary) sigue fijo a propósito, no tiene campo.
    color_marca_kinetic = models.CharField(
        'Color de marca (Kinetic)', max_length=7, blank=True,
        help_text='Código hex. Vacío = color por defecto de Kinetic.',
    )
    color_marca_editorial = models.CharField(
        'Color principal (Editorial)', max_length=7, blank=True,
        help_text='Código hex. Vacío = rojo editorial por defecto.',
    )
    color_marca_secundario_editorial = models.CharField(
        'Color de tinta (Editorial)', max_length=7, blank=True,
        help_text='Código hex. Vacío = negro editorial por defecto.',
    )
    # Las 3 filas de la tarjeta "En vivo" del hero — antes texto fijo
    # ("CATÁLOGO: N productos" / "STOCK: actualizado en tiempo real" /
    # "PEDIDOS: a consultar"), el dueño pidió poder escribir otra cosa ahí.
    # Vacío = se sigue mostrando el valor de siempre (conteo real de
    # productos y el texto según haya WhatsApp cargado o no, ver
    # _contexto_base/home.html) — así nadie pierde el comportamiento actual
    # por no haber tocado esto.
    kinetic_hero_stat1_titulo = models.CharField('Etiqueta 1 (tarjeta hero, Kinetic)', max_length=20, blank=True)
    kinetic_hero_stat1_valor  = models.CharField('Valor 1 (tarjeta hero, Kinetic)', max_length=40, blank=True)
    kinetic_hero_stat2_titulo = models.CharField('Etiqueta 2 (tarjeta hero, Kinetic)', max_length=20, blank=True)
    kinetic_hero_stat2_valor  = models.CharField('Valor 2 (tarjeta hero, Kinetic)', max_length=40, blank=True)
    kinetic_hero_stat3_titulo = models.CharField('Etiqueta 3 (tarjeta hero, Kinetic)', max_length=20, blank=True)
    kinetic_hero_stat3_valor  = models.CharField('Valor 3 (tarjeta hero, Kinetic)', max_length=40, blank=True)
    nav_catalogo_label = models.CharField('Texto del menú "Catálogo"', max_length=30, blank=True)
    nav_ofertas_label  = models.CharField('Texto del menú "Ofertas"', max_length=30, blank=True)
    nav_combos_label   = models.CharField('Texto del menú "Combos"', max_length=30, blank=True)
    nav_tienda_label   = models.CharField('Texto del menú "La tienda"', max_length=30, blank=True)

    # — Página institucional "La tienda" (/la-tienda/) — información del
    # negocio separada del catálogo a propósito: quien entra a comprar no
    # tiene por qué ver esto, pero existe a un click (nav "La tienda").
    institucional_titulo = models.CharField(
        'Título de portada', max_length=200, blank=True,
        help_text='Vacío = usa un título genérico.',
    )
    institucional_bajada = models.TextField(
        'Bajada de portada', blank=True,
        help_text='Vacío = usa un texto genérico.',
    )
    institucional_imagen = models.ImageField(
        'Imagen de portada', upload_to=_catalogo_institucional_path, blank=True, null=True,
        help_text='Opcional — si no se carga, la portada se muestra sin foto.',
    )
    destacado1_titulo = models.CharField('Título', max_length=80, blank=True)
    destacado1_texto  = models.CharField('Texto', max_length=200, blank=True)
    destacado2_titulo = models.CharField('Título', max_length=80, blank=True)
    destacado2_texto  = models.CharField('Texto', max_length=200, blank=True)
    destacado3_titulo = models.CharField('Título', max_length=80, blank=True)
    destacado3_texto  = models.CharField('Texto', max_length=200, blank=True)
    horarios_texto = models.TextField(
        'Horarios de atención', blank=True,
        help_text='Texto libre, ej: "Lun a Vie 9 a 18 hs · Sáb 9 a 13 hs".',
    )
    instagram_url = models.CharField('Instagram', max_length=200, blank=True)
    facebook_url  = models.CharField('Facebook', max_length=200, blank=True)
    tiktok_url    = models.CharField('TikTok', max_length=200, blank=True)

    actualizado_el = models.DateTimeField(auto_now=True)

    # Textos que se muestran cuando el campo respectivo está vacío — una
    # sola fuente de verdad para que el template (|default:) y el JS de
    # la vista previa en vivo (configuracion.js) no diverjan.
    DEFAULT_HERO_SUBTITULO = (
        'Mirá los productos disponibles, las ofertas del momento y armá '
        'tu pedido — coordinamos el pago y la entrega por WhatsApp.'
    )
    DEFAULT_SOBRE_NOSOTROS = (
        'Trabajamos para ofrecerte los mejores productos con atención personalizada.'
    )
    DEFAULT_COLOR_MARCA = '#ff9343'
    DEFAULT_COLOR_MARCA_SECUNDARIO = '#111e2f'
    # Default propio de "bento" — si color_marca/color_marca_secundario están
    # vacíos, cada plantilla tiene que caer en SU propia identidad (naranja/
    # navy para almacén, verde lima/índigo para bento), no en la del otro.
    DEFAULT_COLOR_MARCA_BENTO = '#6fa525'
    DEFAULT_COLOR_MARCA_SECUNDARIO_BENTO = '#262b52'
    # Mismos valores que ya estaban hardcodeados en bento.css (--paper en
    # :root y en html[data-theme="dark"]) — quedar vacío cae en estos.
    DEFAULT_COLOR_FONDO_BENTO = '#faf9f6'
    DEFAULT_COLOR_FONDO_BENTO_OSCURO = '#121320'
    # DEFAULT_COLOR_MARCA_KINETIC respalda a color_marca_kinetic (editable).
    # El secundario sigue sin campo propio — acento fijo en kinetic.css,
    # queda acá solo como referencia del valor hardcodeado.
    DEFAULT_COLOR_MARCA_KINETIC = '#ff3366'
    DEFAULT_COLOR_MARCA_SECUNDARIO_KINETIC = '#00e699'
    # Mismo valor que ya estaba hardcodeado en kinetic.css (--k-bg) — quedar
    # vacío cae en este.
    DEFAULT_COLOR_FONDO_KINETIC = '#0d0d0f'
    # Etiquetas fijas de la tarjeta "En vivo" del hero — los VALORES de la 1
    # y la 3 no tienen constante acá porque son calculados (conteo real de
    # productos / según haya WhatsApp cargado), no texto fijo — ver
    # home.html y _contexto_base en views.py.
    DEFAULT_KINETIC_HERO_STAT1_TITULO = 'CATÁLOGO'
    DEFAULT_KINETIC_HERO_STAT2_TITULO = 'STOCK'
    DEFAULT_KINETIC_HERO_STAT2_VALOR  = 'ACTUALIZADO EN TIEMPO REAL'
    DEFAULT_KINETIC_HERO_STAT3_TITULO = 'PEDIDOS'
    # Default propio de "lumina" — cobalto + coral, e-commerce prolijo.
    DEFAULT_COLOR_MARCA_LUMINA = '#1E3A5F'
    DEFAULT_COLOR_MARCA_SECUNDARIO_LUMINA = '#FF5A3C'
    DEFAULT_COLOR_MARCA_EDITORIAL = '#D6432E'
    DEFAULT_COLOR_MARCA_SECUNDARIO_EDITORIAL = '#121212'
    DEFAULT_NAV_CATALOGO = 'Catálogo'
    DEFAULT_NAV_OFERTAS  = 'Ofertas'
    DEFAULT_NAV_COMBOS   = 'Combos'
    DEFAULT_NAV_TIENDA   = 'La tienda'

    DEFAULT_INSTITUCIONAL_TITULO = 'Conocé nuestra historia'
    DEFAULT_INSTITUCIONAL_BAJADA = (
        'Más que un catálogo — quiénes somos, dónde estamos y cómo te podemos ayudar.'
    )
    DEFAULT_DESTACADO1_TITULO = 'Atención personalizada'
    DEFAULT_DESTACADO1_TEXTO  = 'Te acompañamos antes, durante y después de la compra.'
    DEFAULT_DESTACADO2_TITULO = 'Coordinamos por WhatsApp'
    DEFAULT_DESTACADO2_TEXTO  = 'Sin registros ni cuentas — hablás directo con nosotros.'
    DEFAULT_DESTACADO3_TITULO = 'Calidad que se nota'
    DEFAULT_DESTACADO3_TEXTO  = 'Elegimos con cuidado cada producto que ofrecemos.'

    class Meta:
        verbose_name        = 'Configuración del catálogo'
        verbose_name_plural  = 'Configuración del catálogo'

    def __str__(self):
        return 'Configuración del catálogo'

    @classmethod
    def get_solo(cls):
        obj, _creado = cls.objects.get_or_create(pk=1)
        return obj


def _catalogo_slide_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    # A diferencia de _catalogo_hero_path (singleton, ruta fija a propósito),
    # acá puede haber varios slides a la vez — la ruta tiene que ser por pk
    # para no pisarse entre sí. Requiere que la fila ya exista (se sube en
    # un segundo paso, después de crear el slide sin imagen — ver
    # catalogo/views_config.py:CatalogoSlideImagenAjax).
    return f'catalogo/slides/{instance.pk}{ext}'


class SlideHeroCatalogo(models.Model):
    """
    Un slide del carrusel de hero — exclusivo de la plantilla "bento"
    (ver ConfiguracionCatalogo.hero_titulo/hero_subtitulo/hero_imagen,
    que cumplen el rol equivalente pero fijo/sin carrusel en "almacen").
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='slides',
    )
    imagen = models.ImageField('Imagen', upload_to=_catalogo_slide_path, blank=True, null=True)
    eyebrow = models.CharField('Texto pequeño (arriba del título)', max_length=60, blank=True)
    titulo = models.CharField('Título', max_length=200)
    descripcion = models.TextField('Descripción', blank=True)
    cta_texto = models.CharField('Texto del botón', max_length=60, default='Ver catálogo completo')
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Slide del hero (catálogo)'
        verbose_name_plural  = 'Slides del hero (catálogo)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.titulo


class TipoTileDestacado(models.TextChoices):
    CATEGORIA = 'categoria', 'Categoría'
    MARCA     = 'marca',     'Marca'


class TileDestacadoCatalogo(models.Model):
    """
    Acceso directo con imagen a una categoría o marca — al hacer click,
    filtra el catálogo automáticamente (mismo mecanismo de ?categoria=/
    ?marca= que ya usan los filtros de la sidebar, ver catalogo/views.py).
    Exclusivo de "almacen" por ahora. "marca" es texto libre porque en
    Producto también lo es (no hay un modelo de marcas separado).
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='tiles_destacados',
    )
    tipo = models.CharField(
        'Tipo', max_length=10, choices=TipoTileDestacado.choices, default=TipoTileDestacado.CATEGORIA,
    )
    categoria = models.ForeignKey(
        'productos.CategoriaProducto', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Categoría', help_text='Usada si el tipo es "Categoría".',
    )
    marca = models.CharField(
        'Marca', max_length=100, blank=True, help_text='Usada si el tipo es "Marca".',
    )
    etiqueta = models.CharField(
        'Etiqueta (opcional)', max_length=60, blank=True,
        help_text='Vacío = usa el nombre de la categoría o el valor de la marca tal cual.',
    )
    imagen = models.ImageField('Imagen', upload_to=_catalogo_tile_path, blank=True, null=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Categoría/marca destacada (catálogo)'
        verbose_name_plural  = 'Categorías/marcas destacadas (catálogo)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.etiqueta or (self.categoria.nombre if self.categoria_id else self.marca) or f'Tile #{self.pk}'


class GondolaAlmacenCatalogo(models.Model):
    """
    Fila automática de productos de una categoría, exclusiva de Almacén.
    El dueño elige el pasillo y opcionalmente personaliza los textos; los
    productos se toman del catálogo publicado para no mantener otra lista.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='gondolas_almacen',
    )
    categoria = models.ForeignKey(
        'productos.CategoriaProducto', on_delete=models.CASCADE,
        verbose_name='Categoría', related_name='gondolas_catalogo_almacen',
    )
    titulo = models.CharField(
        'Título (opcional)', max_length=80, blank=True,
        help_text='Vacío = usa el nombre de la categoría.',
    )
    subtitulo = models.CharField('Bajada (opcional)', max_length=140, blank=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Góndola destacada (Almacén)'
        verbose_name_plural = 'Góndolas destacadas (Almacén)'
        ordering = ['orden', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['configuracion', 'categoria'],
                name='catalogo_gondola_almacen_categoria_unica',
            ),
        ]

    def __str__(self):
        return self.titulo or self.categoria.nombre


def _catalogo_galeria_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    # Mismo motivo que _catalogo_slide_path: puede haber varias fotos a la
    # vez, la ruta va por pk — requiere que la fila ya exista (se sube en
    # un segundo paso, ver catalogo/views_config.py:CatalogoGaleriaImagenAjax).
    return f'catalogo/galeria/{instance.pk}{ext}'


class ImagenInstitucional(models.Model):
    """
    Una foto de la galería de la página institucional (/la-tienda/) — el
    local, el equipo, productos en contexto, lo que el dueño quiera
    mostrar. Sin relación con el catálogo de productos en sí.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='galeria',
    )
    imagen = models.ImageField('Imagen', upload_to=_catalogo_galeria_path, blank=True, null=True)
    titulo = models.CharField('Título (opcional)', max_length=100, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Imagen de la galería institucional'
        verbose_name_plural  = 'Imágenes de la galería institucional'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.titulo or f'Imagen #{self.pk}'


def _catalogo_banner_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    # Mismo motivo que _catalogo_slide_path: puede haber varios banners a la
    # vez, la ruta va por pk — requiere que la fila ya exista (se sube en un
    # segundo paso, ver catalogo/views_config.py:CatalogoBannerImagenAjax).
    return f'catalogo/banners/{instance.pk}{ext}'


class PosicionBanner(models.TextChoices):
    DEBAJO_HERO       = 'debajo_hero',       'Debajo del hero (ancho completo)'
    ANTES_GRILLA      = 'antes_grilla',      'Arriba de la grilla de productos'
    ANTES_DESTACADOS  = 'antes_destacados',  'Antes de Destacados'
    ANTES_COMBOS      = 'antes_combos',      'Antes de Combos armados'


class BannerCatalogo(models.Model):
    """
    Banner promocional opcional — hasta MAX_BANNERS en total, repartidos
    entre las posiciones disponibles (ver catalogo/views_config.py).
    Exclusivo de "almacen" por ahora. Sin imagen se muestra como bloque de
    color sólido con el texto; con imagen, la
    imagen va de fondo con un degradé para que el texto se siga leyendo.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='banners',
    )
    posicion = models.CharField(
        'Ubicación', max_length=20, choices=PosicionBanner.choices, default=PosicionBanner.DEBAJO_HERO,
    )
    imagen = models.ImageField('Imagen (opcional)', upload_to=_catalogo_banner_path, blank=True, null=True)
    titulo = models.CharField('Título', max_length=100)
    texto = models.CharField('Bajada (opcional)', max_length=200, blank=True)
    color_fondo = models.CharField(
        'Color de fondo', max_length=7, blank=True,
        help_text='Código hex. Vacío = usa el color secundario de la marca. Solo se ve si el banner no tiene imagen.',
    )
    cta_texto = models.CharField('Texto del botón (opcional)', max_length=40, blank=True)
    cta_url = models.CharField(
        'Link del botón (opcional)', max_length=300, blank=True,
        help_text='Sin texto Y link del botón cargados los dos, el banner no muestra botón.',
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Banner promocional (catálogo)'
        verbose_name_plural  = 'Banners promocionales (catálogo)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.titulo

    @property
    def muestra_cta(self):
        return bool(self.cta_texto and self.cta_url)


def _catalogo_ticker_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/ticker/{instance.pk}{ext}'


class TickerMensajeCatalogo(models.Model):
    """
    Mensaje corto de la franja de anuncios arriba del header (ver
    catalogo/plantillas/bento/base.html) — solo texto, rota en el
    front con JS (ver catalogo.js). Exclusivo de "bento" por ahora.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='ticker_mensajes',
    )
    texto = models.CharField('Mensaje', max_length=120)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Mensaje de la barra de anuncios (catálogo)'
        verbose_name_plural  = 'Mensajes de la barra de anuncios (catálogo)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.texto


def _catalogo_marca_logo_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    # Igual que _catalogo_tile_path: la ruta va por pk, se sube en un
    # segundo paso (ver catalogo/views_config.py:CatalogoMarcaLogoImagenAjax).
    return f'catalogo/marcas/{instance.pk}{ext}'


class MarcaLogoCatalogo(models.Model):
    """
    Fila de "nuestras marcas" (logos en badge circular) — a diferencia de
    TileDestacadoCatalogo (tipo=MARCA), esto no filtra el catálogo al
    click, es solo prestigio/confianza. Exclusivo de "bento" por ahora.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='marcas_logo',
    )
    nombre = models.CharField('Nombre de la marca', max_length=60)
    logo = models.ImageField('Logo', upload_to=_catalogo_marca_logo_path, blank=True, null=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Marca (catálogo)'
        verbose_name_plural  = 'Marcas (catálogo)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.nombre


class PosicionBannerBento(models.TextChoices):
    """
    A diferencia de PosicionBanner (Almacén, "franja ancha" en las 4),
    cada posición de Bento se dibuja distinto — ver catalogo/plantillas/
    bento/home.html — por eso los nombres describen la forma real, no un
    lugar genérico de la página.
    """
    NOVEDADES         = 'novedades',         'Novedades (rail de tarjetas, arriba)'
    PROMOS_MES        = 'promos_mes',        'Promos del mes (grilla fija de 4)'
    ANTES_DESTACADOS  = 'antes_destacados',  'Antes de Destacados (franja ancha)'
    ANTES_COMBOS      = 'antes_combos',      'Antes de Combos armados (franja ancha)'


def _catalogo_banner_bento_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/banners-bento/{instance.pk}{ext}'


class BannerBentoCatalogo(models.Model):
    """
    Banner promocional opcional de Bento — con límite independiente por
    formato visual (ver catalogo/views_config.py). Mismos campos que BannerCatalogo (Almacén)
    pero modelo y tabla propios: son conceptos distintos aunque compartan
    forma de datos, cada plantilla maneja los suyos sin cruzarse. Exclusivo
    de "bento".
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='banners_bento',
    )
    posicion = models.CharField(
        'Dónde va', max_length=20, choices=PosicionBannerBento.choices, default=PosicionBannerBento.NOVEDADES,
    )
    imagen = models.ImageField('Imagen (opcional)', upload_to=_catalogo_banner_bento_path, blank=True, null=True)
    titulo = models.CharField('Título', max_length=100)
    texto = models.CharField('Bajada (opcional)', max_length=200, blank=True)
    color_fondo = models.CharField(
        'Color de fondo', max_length=7, blank=True,
        help_text='Código hex. Vacío = usa el color secundario de la marca. Solo se ve si el banner no tiene imagen.',
    )
    cta_texto = models.CharField('Texto del botón (opcional)', max_length=40, blank=True)
    cta_url = models.CharField(
        'Link del botón (opcional)', max_length=300, blank=True,
        help_text='Sin texto Y link del botón cargados los dos, el banner no muestra botón.',
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Banner promocional (Bento)'
        verbose_name_plural  = 'Banners promocionales (Bento)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.titulo

    @property
    def muestra_cta(self):
        return bool(self.cta_texto and self.cta_url)


class TickerMensajeKineticCatalogo(models.Model):
    """
    Mensaje corto que rota en la barra de estado del header (ver
    catalogo/plantillas/kinetic/base.html) — reemplaza el texto fijo
    "STOCK ACTUALIZADO EN TIEMPO REAL" cuando hay al menos uno cargado.
    Mismo concepto que TickerMensajeCatalogo (Bento) pero tabla propia —
    exclusivo de "kinetic", nunca se cruzan.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='ticker_mensajes_kinetic',
    )
    texto = models.CharField('Mensaje', max_length=80)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Mensaje de la barra de estado (Kinetic)'
        verbose_name_plural  = 'Mensajes de la barra de estado (Kinetic)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.texto


def _catalogo_banner_kinetic_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/banners-kinetic/{instance.pk}{ext}'


class BannerKineticCatalogo(models.Model):
    """
    Banner promocional de Kinetic — hasta MAX_BANNERS_KINETIC, mostrados en
    un rail horizontal (ver catalogo/plantillas/kinetic/home.html). Mismos
    campos que BannerBentoCatalogo pero sin 'posicion': Kinetic solo tiene
    un destino visual para esto, a diferencia de Bento. Reemplaza los
    campos sueltos kinetic_banner_* que tenía ConfiguracionCatalogo (un
    solo banner posible) — ver migración de datos que preserva el banner
    ya cargado al pasar de campo único a esta tabla.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='banners_kinetic',
    )
    imagen = models.ImageField('Imagen (opcional)', upload_to=_catalogo_banner_kinetic_path, blank=True, null=True)
    titulo = models.CharField('Título', max_length=120, blank=True)
    texto = models.CharField('Texto (opcional)', max_length=240, blank=True)
    color_fondo = models.CharField(
        'Color de fondo', max_length=7, blank=True,
        help_text='Código hex. Vacío = usa el fondo oscuro estándar de Kinetic. Solo se ve si el banner no tiene imagen.',
    )
    cta_texto = models.CharField('Texto del botón (opcional)', max_length=40, blank=True)
    cta_url = models.CharField(
        'Link del botón (opcional)', max_length=300, blank=True,
        help_text='Sin texto Y link del botón cargados los dos, el banner no muestra botón.',
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name        = 'Banner (Kinetic)'
        verbose_name_plural  = 'Banners (Kinetic)'
        ordering             = ['orden', 'id']

    def __str__(self):
        return self.titulo or f'Banner #{self.pk}'

    @property
    def muestra_cta(self):
        return bool(self.cta_texto and self.cta_url)


class EntradaBitacoraKineticCatalogo(models.Model):
    """Novedad breve presentada como registro operativo en la home Kinetic."""
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='bitacora_kinetic',
    )
    codigo = models.CharField('Etiqueta', max_length=20, blank=True)
    titulo = models.CharField('Titulo', max_length=100)
    texto = models.CharField('Detalle (opcional)', max_length=280, blank=True)
    enlace_texto = models.CharField('Texto del enlace (opcional)', max_length=40, blank=True)
    url = models.CharField('Link (opcional)', max_length=300, blank=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Entrada de bitacora (Kinetic)'
        verbose_name_plural = 'Entradas de bitacora (Kinetic)'
        ordering = ['orden', 'id']

    def __str__(self):
        return self.titulo

    @property
    def muestra_enlace(self):
        return bool(self.enlace_texto and self.url)


class ConsultaKineticCatalogo(models.Model):
    """Pregunta y respuesta desplegable exclusiva de la home Kinetic."""
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='consultas_kinetic',
    )
    pregunta = models.CharField('Pregunta', max_length=140)
    respuesta = models.TextField('Respuesta', max_length=700)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Consulta frecuente (Kinetic)'
        verbose_name_plural = 'Consultas frecuentes (Kinetic)'
        ordering = ['orden', 'id']

    def __str__(self):
        return self.pregunta


class TipoSeleccionEditorial(models.TextChoices):
    CATEGORIA = 'categoria', 'Categoría'
    PRODUCTO = 'producto', 'Producto'


class SeleccionEditorialCatalogo(models.Model):
    """Capítulo visual opcional y exclusivo de Editorial.

    La selección siempre apunta a contenido real del catálogo. El dueño puede
    sumar una portada y textos propios, pero nunca necesita duplicar productos:
    sin imagen se reutiliza la primera foto disponible del producto/categoría.
    """
    configuracion = models.ForeignKey(
        ConfiguracionCatalogo, on_delete=models.CASCADE, related_name='selecciones_editorial',
    )
    tipo = models.CharField(
        'Contenido', max_length=12, choices=TipoSeleccionEditorial.choices,
        default=TipoSeleccionEditorial.CATEGORIA,
    )
    categoria = models.ForeignKey(
        'productos.CategoriaProducto', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='selecciones_catalogo_editorial',
    )
    producto = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='selecciones_catalogo_editorial',
    )
    etiqueta = models.CharField('Etiqueta (opcional)', max_length=32, blank=True)
    titulo = models.CharField('Título (opcional)', max_length=100, blank=True)
    texto = models.CharField('Bajada (opcional)', max_length=240, blank=True)
    imagen = models.ImageField(
        'Portada (opcional)', upload_to=_catalogo_coleccion_editorial_path, blank=True, null=True,
    )
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Selección de la edición (Editorial)'
        verbose_name_plural = 'Selecciones de la edición (Editorial)'
        ordering = ['orden', 'id']

    def __str__(self):
        return self.titulo or (
            self.producto.nombre if self.producto_id else
            self.categoria.nombre if self.categoria_id else f'Selección #{self.pk}'
        )


class DatoDemo(models.Model):
    """
    Registro de qué fila creó la herramienta de datos de prueba del
    catálogo (ver catalogo/seed.py — "Cargar datos de prueba" para
    admins). Sirve solo para poder borrar después exactamente lo que
    plantó esa herramienta, sin tocar nada cargado a mano.
    """
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField()
    contenido    = GenericForeignKey('content_type', 'object_id')
    creado_el    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Dato de prueba (catálogo)'
        verbose_name_plural  = 'Datos de prueba (catálogo)'
        unique_together      = [('content_type', 'object_id')]

    def __str__(self):
        return f'{self.content_type.model} #{self.object_id}'


class EstadoPedido(models.TextChoices):
    PENDIENTE  = 'pendiente',  'Pendiente'
    VENDIDO    = 'vendido',    'Convertido a venta'
    DESCARTADO = 'descartado', 'Descartado'


class Pedido(models.Model):
    """
    Un pedido armado por un visitante del catálogo público (sin cuenta,
    sin login). No es una Venta — es solo la intención de compra + el
    contacto para coordinar por WhatsApp. El equipo lo revisa desde la
    campanita de notificaciones (ver core/base.html) y, si se confirma,
    lo convierte en una Venta real con el botón "Vender" (crea un
    borrador y reusa el mecanismo ?editar=<pk> de Nueva Venta).
    """
    contacto_nombre    = models.CharField('Nombre', max_length=150, blank=True)
    contacto_telefono  = models.CharField('WhatsApp / teléfono', max_length=40)
    notas              = models.TextField('Notas del cliente', blank=True)
    estado             = models.CharField(max_length=15, choices=EstadoPedido.choices, default=EstadoPedido.PENDIENTE)

    # — Descuento global (oferta por monto mínimo de compra) —
    # Mismo mecanismo que Venta.descuento_global_pct: se resuelve una sola
    # vez al crear el pedido (ver CrearPedidoAjax) y se arrastra tal cual
    # a la Venta al convertir el pedido — así el monto que ve el cliente
    # en el catálogo es el mismo que termina cobrándose, en vez de que el
    # descuento "aparezca" recién al vender.
    descuento_global_pct = models.DecimalField(
        'Descuento global (%)', max_digits=5, decimal_places=2, default=0,
    )
    oferta_global_nombre = models.CharField(
        'Oferta global aplicada', max_length=100, blank=True,
        help_text='Nombre de la Oferta (tipo=umbral) que originó el descuento global, si la hay.',
    )
    leido = models.BooleanField(
        default=False,
        help_text='Se marca solo al abrir la campanita de notificaciones — no requiere acción manual.',
    )
    venta = models.ForeignKey(
        'ventas.Venta', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedido_origen',
        help_text='Borrador de venta creado al tocar "Vender". Null hasta ese momento.',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Pedido del catálogo'
        verbose_name_plural  = 'Pedidos del catálogo'
        ordering             = ['-fecha_alta']

    def __str__(self):
        return f'Pedido #{self.pk} — {self.contacto_nombre or self.contacto_telefono}'

    @property
    def subtotal(self):
        return sum((it.precio_unitario * it.cantidad for it in self.items.all()), start=0)

    @property
    def total(self):
        subtotal = self.subtotal
        if self.descuento_global_pct:
            subtotal = subtotal * (1 - self.descuento_global_pct / 100)
        return subtotal


class ItemPedido(models.Model):
    pedido   = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='items')
    producto = models.ForeignKey(
        'productos.Producto', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    # Variante elegida (opcional) — mismo mecanismo que ItemVenta.combinacion
    # (ventas/models.py), incluido el snapshot en texto para que el pedido
    # siga siendo legible aunque la combinación se borre/desactive después.
    combinacion = models.ForeignKey(
        'productos.CombinacionVariante', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    combinacion_descripcion = models.CharField(max_length=300, blank=True)
    # Snapshot: el pedido tiene que seguir siendo legible aunque el
    # producto se borre o cambie de nombre/precio después.
    producto_nombre = models.CharField(max_length=255, blank=True)
    cantidad        = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name        = 'Ítem de pedido'
        verbose_name_plural  = 'Ítems de pedido'
        ordering             = ['id']

    def __str__(self):
        combinacion = f' [{self.combinacion_descripcion}]' if self.combinacion_descripcion else ''
        return f'{self.producto_nombre}{combinacion} x{self.cantidad}'

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.producto and not self.producto_nombre:
                self.producto_nombre = self.producto.nombre
            if self.combinacion and not self.combinacion_descripcion:
                self.combinacion_descripcion = self.combinacion.descripcion_legible() or ''
        super().save(*args, **kwargs)
