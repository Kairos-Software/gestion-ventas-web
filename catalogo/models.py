from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


def _catalogo_hero_path(instance, filename):
    import os
    ext = os.path.splitext(filename)[1].lower()
    return f'catalogo/hero{ext}'


class PlantillaCatalogo(models.TextChoices):
    ALMACEN = 'almacen', 'Almacén'
    BENTO   = 'bento',   'Bento'


class ConfiguracionCatalogo(models.Model):
    """
    Contenido editable del catálogo público — no diseño, sino los textos
    e imagen que cambian según el negocio (título del hero, bajada,
    sobre nosotros, contacto). Editable desde Configuración → Catálogo
    público (ver core/views.py:configuracion), con vista previa en vivo.
    Mismo patrón singleton que DatosEmpresa (ver core/models.py).
    hero_titulo/hero_subtitulo/hero_imagen son exclusivos de la plantilla
    "almacen" — la plantilla "bento" usa SlideHeroCatalogo en su lugar.
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
    sobre_nosotros = models.TextField('Sobre nosotros', blank=True)
    contacto_texto = models.TextField(
        'Texto de contacto', blank=True,
        help_text='Se muestra junto a los datos de contacto en el pie de página.',
    )
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
