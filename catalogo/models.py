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


class PlantillaCatalogo(models.TextChoices):
    ALMACEN = 'almacen', 'Almacén'
    BENTO   = 'bento',   'Bento'
    KINETIC = 'kinetic', 'Kinetic'


class ConfiguracionCatalogo(models.Model):
    """
    Contenido editable del catálogo público — no diseño, sino los textos
    e imagen que cambian según el negocio (título del hero, bajada,
    sobre nosotros, contacto). Editable desde Configuración → Catálogo
    público (ver core/views.py:configuracion), con vista previa en vivo.
    Mismo patrón singleton que DatosEmpresa (ver core/models.py).
    hero_titulo/hero_imagen son exclusivos de la plantilla "almacen" (esa
    no tiene carrusel). hero_subtitulo y hero_producto los usan las DOS
    plantillas — en "bento", hero_subtitulo es el texto de respaldo hasta
    que se carga el primer slide (ver SlideHeroCatalogo) y hero_producto
    arma la tarjeta lateral del hero, con o sin carrusel.
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
    sobre_nosotros = models.TextField('Sobre nosotros', blank=True)
    contacto_texto = models.TextField(
        'Texto de contacto', blank=True,
        help_text='Se muestra junto a los datos de contacto en el pie de página.',
    )
    # — Personalización visual/textual de la plantilla "almacen" —
    color_marca = models.CharField(
        'Color de marca', max_length=7, blank=True,
        help_text='Código hex, ej: #ff9343. Vacío = color por defecto. Botones, precios y detalles.',
    )
    color_marca_secundario = models.CharField(
        'Color secundario', max_length=7, blank=True,
        help_text='Código hex, ej: #111e2f. Vacío = color por defecto. Encabezado, hero y pie de página.',
    )
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
    # "kinetic" no lee estos colores todavía (paleta fija en kinetic.css,
    # ver plantillas/kinetic/base.html) — quedan acá solo para el día que
    # se sume personalización de marca a esa plantilla, mismo criterio que
    # las de arriba.
    DEFAULT_COLOR_MARCA_KINETIC = '#ff3366'
    DEFAULT_COLOR_MARCA_SECUNDARIO_KINETIC = '#00e699'
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
        return f'{self.producto_nombre} x{self.cantidad}'

    def save(self, *args, **kwargs):
        if not self.pk and self.producto and not self.producto_nombre:
            self.producto_nombre = self.producto.nombre
        super().save(*args, **kwargs)
