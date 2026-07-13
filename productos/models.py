from decimal import Decimal

from django.db import models
from django.utils.text import slugify
from django.conf import settings


# ══════════════════════════════════════════════════════════════════
#  CHOICES — PROVEEDOR
# ══════════════════════════════════════════════════════════════════

class TipoProveedor(models.TextChoices):
    NACIONAL       = 'nacional',     'Nacional'
    INTERNACIONAL  = 'internacional','Internacional'
    MONOTRIBUTISTA = 'monotributo',  'Monotributista'
    OTRO           = 'otro',         'Otro'


class CondicionPago(models.TextChoices):
    CONTADO    = 'contado',  'Contado'
    DIAS_15    = '15',       '15 días'
    DIAS_30    = '30',       '30 días'
    DIAS_60    = '60',       '60 días'
    DIAS_90    = '90',       '90 días'
    A_CONVENIR = 'convenir', 'A convenir'


class Moneda(models.TextChoices):
    ARS = 'ARS', 'Peso argentino'
    USD = 'USD', 'Dólar estadounidense'
    EUR = 'EUR', 'Euro'


# ══════════════════════════════════════════════════════════════════
#  PROVEEDOR
# ══════════════════════════════════════════════════════════════════

class Proveedor(models.Model):

    # — Identidad —
    nombre      = models.CharField(max_length=200)
    cuit        = models.CharField(max_length=20, blank=True)
    tipo        = models.CharField(max_length=20, choices=TipoProveedor.choices,
                                   default=TipoProveedor.NACIONAL)
    activo      = models.BooleanField(default=True)
    sitio_web   = models.URLField(blank=True)
    descripcion = models.TextField(blank=True, help_text='Descripción interna del proveedor')

    # — Contacto —
    email           = models.EmailField(blank=True)
    telefono        = models.CharField(max_length=30, blank=True)
    contacto_nombre = models.CharField(max_length=150, blank=True, verbose_name='Nombre del contacto')
    contacto_cargo  = models.CharField(max_length=100, blank=True, verbose_name='Cargo del contacto')

    # — Dirección —
    calle     = models.CharField(max_length=200, blank=True)
    ciudad    = models.CharField(max_length=100, blank=True)
    provincia = models.CharField(max_length=100, blank=True)
    pais      = models.CharField(max_length=100, blank=True, default='Argentina')

    # — Comercial —
    condicion_pago = models.CharField(max_length=20, choices=CondicionPago.choices,
                                      default=CondicionPago.CONTADO)
    moneda         = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)
    dias_entrega   = models.PositiveSmallIntegerField(null=True, blank=True,
                         help_text='Días hábiles promedio de entrega')
    notas          = models.TextField(blank=True, help_text='Notas internas / condiciones especiales')

    # — Auditoría —
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Proveedor'
        verbose_name_plural = 'Proveedores'
        ordering            = ['nombre']

    def __str__(self):
        return self.nombre

    @property
    def direccion_completa(self):
        partes = filter(None, [self.calle, self.ciudad, self.provincia, self.pais])
        return ', '.join(partes)


# ══════════════════════════════════════════════════════════════════
#  CHOICES — PRODUCTO
# ══════════════════════════════════════════════════════════════════

class UnidadMedida(models.TextChoices):
    UNIDAD = 'unidad', 'Unidad'
    KG     = 'kg',     'Kilogramo'
    GR     = 'gr',     'Gramo'
    LT     = 'lt',     'Litro'
    ML     = 'ml',     'Mililitro'
    MT     = 'mt',     'Metro'
    CM     = 'cm',     'Centímetro'
    MT2    = 'mt2',    'Metro cuadrado'
    MT3    = 'mt3',    'Metro cúbico'
    CAJA   = 'caja',   'Caja'
    PACK   = 'pack',   'Pack / Set'
    PAR    = 'par',    'Par'
    DOCENA = 'docena', 'Docena'
    ROLLO  = 'rollo',  'Rollo'
    BOLSA  = 'bolsa',  'Bolsa'
    OTRO   = 'otro',   'Otro'


class AlicuotaIVA(models.TextChoices):
    """
    Alícuotas de IVA vigentes en Argentina.
    Se almacena el porcentaje como string para evitar problemas de punto flotante.
    Uso: float(producto.alicuota_iva) / 100  →  factor multiplicador.
    El precio de venta es siempre el precio FINAL (con IVA incluido).
    Para obtener el neto: precio / (1 + alicuota)
    Para obtener el IVA: precio - (precio / (1 + alicuota))
    """
    EXENTO   = '0',    'Exento (0%)'
    REDUCIDO = '10.5', 'Reducido (10,5%)'
    GENERAL  = '21',   'General (21%)'
    ESPECIAL = '27',   'Especial (27%)'


class ModoPrecio(models.TextChoices):
    """
    MANUAL: precio_venta se carga y edita a mano, como siempre.
    AUTOMATICO: precio_venta se recalcula solo a partir de costo_actual
    (el costo del lote activo más reciente) + porcentaje_ganancia, cada
    vez que se confirma/anula una compra de este producto — nunca al
    vender (ver Producto.actualizar_costo_y_precio()).
    """
    MANUAL     = 'manual',     'Manual'
    AUTOMATICO = 'automatico', 'Automático (costo + % ganancia)'


class EstadoProducto(models.TextChoices):
    ACTIVO   = 'activo',        'Activo'
    INACTIVO = 'inactivo',      'Inactivo'
    DESCONT  = 'discontinuado', 'Discontinuado'
    AGOTADO  = 'agotado',       'Agotado (sin reposición)'


# ══════════════════════════════════════════════════════════════════
#  CATEGORÍA DE PRODUCTO
# ══════════════════════════════════════════════════════════════════

class CategoriaProducto(models.Model):
    nombre      = models.CharField(max_length=100, unique=True)
    slug        = models.SlugField(max_length=110, unique=True, blank=True)
    descripcion = models.CharField(max_length=300, blank=True)
    activo      = models.BooleanField(default=True)
    orden       = models.PositiveSmallIntegerField(default=0)
    fecha_alta  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Categoría de producto'
        verbose_name_plural = 'Categorías de producto'
        ordering            = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    @property
    def total_productos(self):
        return self.productos.count()


# ══════════════════════════════════════════════════════════════════
#  LISTA DE DESCUENTO
#  Porcentajes predefinidos ("Lista 1", "Mayorista", etc.) que se
#  pueden elegir desde un desplegable al cargar una compra o una
#  venta, en vez de escribir el % a mano cada vez. El campo de texto
#  manual sigue existiendo igual — esto es un atajo, no un reemplazo.
# ══════════════════════════════════════════════════════════════════

class ListaDescuento(models.Model):
    nombre     = models.CharField(max_length=100, unique=True)
    porcentaje = models.DecimalField(
        'Porcentaje', max_digits=5, decimal_places=2,
        help_text='Ej: 10 = 10% de descuento.',
    )
    activa     = models.BooleanField(default=True)
    orden      = models.PositiveSmallIntegerField(default=0)
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Lista de descuento'
        verbose_name_plural = 'Listas de descuento'
        ordering            = ['orden', 'nombre']

    def __str__(self):
        return f'{self.nombre} ({self.porcentaje}%)'


# ══════════════════════════════════════════════════════════════════
#  TIPO DE PRODUCTO
# ══════════════════════════════════════════════════════════════════

class TipoProducto(models.Model):
    nombre      = models.CharField(max_length=100, unique=True)
    slug        = models.SlugField(max_length=110, unique=True, blank=True)
    descripcion = models.CharField(max_length=300, blank=True)
    activo      = models.BooleanField(default=True)
    orden       = models.PositiveSmallIntegerField(default=0)
    fecha_alta  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Tipo de producto'
        verbose_name_plural = 'Tipos de producto'
        ordering            = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nombre)
        super().save(*args, **kwargs)

    @property
    def total_productos(self):
        return self.productos.count()


# ══════════════════════════════════════════════════════════════════
#  HELPERS — rutas de archivos de producto
# ══════════════════════════════════════════════════════════════════

def _producto_imagen_path(instance, filename):
    import os
    producto      = instance.producto
    carpeta       = producto.codigo if producto.codigo else str(producto.pk)
    nombre_limpio = os.path.basename(filename)
    return f'productos/{carpeta}/{nombre_limpio}'


def _generar_codigo_producto():
    ultimo = Producto.objects.order_by('-id').first()
    if not ultimo or not ultimo.codigo:
        numero = 1
    else:
        try:
            numero = int(ultimo.codigo.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = Producto.objects.count() + 1
    return f'PRD-{numero:05d}'


# ══════════════════════════════════════════════════════════════════
#  PRODUCTO
# ══════════════════════════════════════════════════════════════════

class Producto(models.Model):

    # — Identificación —
    codigo        = models.CharField(max_length=50, unique=True, blank=True,
                        help_text='Se genera automáticamente (PRD-00001).')
    sku           = models.CharField('SKU', max_length=100, blank=True)
    codigo_barras = models.CharField(max_length=100, blank=True)
    nombre        = models.CharField(max_length=255)
    nombre_corto  = models.CharField(max_length=80, blank=True,
                        help_text='Para tickets y etiquetas.')
    descripcion         = models.TextField(blank=True)
    descripcion_publica = models.TextField(blank=True,
                              help_text='Para catálogo público / e-commerce.')

    # — Clasificación (dinámica) —
    categoria = models.ForeignKey(CategoriaProducto, on_delete=models.SET_NULL,
                    null=True, blank=True, related_name='productos')
    tipo      = models.ForeignKey(TipoProducto, on_delete=models.SET_NULL,
                    null=True, blank=True, related_name='productos')

    # — Marca / Fabricante —
    marca       = models.CharField(max_length=100, blank=True)
    modelo      = models.CharField(max_length=100, blank=True)
    fabricante  = models.CharField(max_length=150, blank=True)
    pais_origen = models.CharField('País de origen', max_length=100, blank=True)

    # — Proveedor principal —
    # El proveedor habitual de este producto. Puede quedar vacío si se compra
    # a distintos proveedores según la ocasión. El detalle por compra vive en
    # el modelo Compra / ItemCompra (sprint futuro).
    proveedor = models.ForeignKey('Proveedor', on_delete=models.SET_NULL,
                    null=True, blank=True, related_name='productos',
                    verbose_name='Proveedor principal')

    # — Unidad y presentación —
    # unidad_medida: define cómo se cuenta/mide el producto (unidad, kg, lt, etc.)
    # contenido_neto: el contenido de cada unidad (ej: 500 ml, 1.5 lt, 6 unidades en un pack).
    #   Es DecimalField porque puede ser 1.5 lt, 2.5 kg, etc.
    #   La cantidad comprada/vendida (stock) siempre es un entero — se compran/venden
    #   N unidades enteras de ese producto, sin importar qué contenga cada una.
    unidad_medida  = models.CharField(max_length=20, choices=UnidadMedida.choices,
                         default=UnidadMedida.UNIDAD)
    contenido_neto = models.DecimalField(max_digits=10, decimal_places=3,
                         null=True, blank=True,
                         help_text='Contenido por unidad (ej: 500 para una botella de 500 ml).')

    # — Dimensiones físicas —
    # Útiles para logística, embalaje y cálculo de flete.
    peso_kg        = models.DecimalField('Peso (kg)', max_digits=8, decimal_places=3, null=True, blank=True)
    alto_cm        = models.DecimalField('Alto (cm)', max_digits=7, decimal_places=2, null=True, blank=True)
    ancho_cm       = models.DecimalField('Ancho (cm)', max_digits=7, decimal_places=2, null=True, blank=True)
    profundidad_cm = models.DecimalField('Profundidad (cm)', max_digits=7, decimal_places=2, null=True, blank=True)

    # — Precio —
    # Solo se almacena el precio de venta final (con IVA incluido).
    # El neto y el monto de IVA se calculan en runtime a partir de alicuota_iva.
    # Precios alternativos (mayorista, oferta, listas de precio) vivirán en
    # tablas separadas cuando se implemente el módulo de ventas:
    #   - ListaPrecio + ListaPrecioItem  → precios por segmento (minorista, mayorista, etc.)
    #   - Oferta + OfertaItem            → promociones con vigencia temporal
    #   - ItemVenta.descuento            → descuento manual al momento de la venta
    precio_venta = models.DecimalField('Precio de venta', max_digits=12, decimal_places=2,
                       null=True, blank=True,
                       help_text='Precio final de venta al público (IVA incluido).')

    # — Precio automático (costo + % de ganancia) —
    # MANUAL (default): precio_venta se carga a mano, como siempre.
    # AUTOMATICO: precio_venta se recalcula solo cada vez que cambia
    # costo_actual (ver actualizar_costo_y_precio(), disparado desde
    # compras al confirmar/anular una compra de este producto).
    modo_precio = models.CharField('Modo de precio', max_length=10,
                       choices=ModoPrecio.choices, default=ModoPrecio.MANUAL)
    porcentaje_ganancia = models.DecimalField('% de ganancia', max_digits=6, decimal_places=2,
                       null=True, blank=True,
                       help_text='Solo si modo_precio=automático. Ej: 35 → precio = costo × 1.35.')
    costo_actual = models.DecimalField('Costo actual', max_digits=12, decimal_places=2,
                       null=True, blank=True, editable=False,
                       help_text='Costo del lote activo más reciente. Se recalcula solo desde '
                                  'compras — nunca se edita a mano.')

    # — Impuestos —
    # Se guarda la alícuota porque es un dato del producto (varía según rubro).
    # El precio siempre es con IVA incluido; la alícuota permite desdoblar
    # neto e impuesto en facturas, reportes y cálculos de rentabilidad.
    alicuota_iva = models.CharField('Alícuota IVA', max_length=5,
                       choices=AlicuotaIVA.choices, default=AlicuotaIVA.GENERAL)

    # — Stock —
    # stock_actual: unidades disponibles en este momento.
    #   - Si tiene_variantes_color=False: se actualiza directamente por MovimientoStock.
    #   - Si tiene_variantes_color=True:  es la suma de stock de todos los colores activos.
    #     Se sincroniza automáticamente vía sincronizar_stock_desde_colores().
    # stock_minimo: umbral de alerta. Cuando stock_actual <= stock_minimo se muestra ⚠.
    #   Se aplica al total del producto (suma de todos los colores si los tiene).
    # stock_maximo: límite superior opcional. Útil para no sobrecomprar productos
    #   de baja rotación o con restricciones de almacenamiento.
    #   No se valida automáticamente — es orientativo para el equipo de compras.
    # PositiveIntegerField porque siempre se compran/venden unidades enteras.
    stock_actual  = models.PositiveIntegerField(default=0)
    stock_minimo  = models.PositiveIntegerField('Stock mínimo', default=0,
                        help_text='Alerta de stock bajo cuando el total cae por debajo de este valor.')
    stock_maximo  = models.PositiveIntegerField('Stock máximo', null=True, blank=True,
                        help_text='Límite sugerido de stock. Orientativo para compras.')

    permite_stock_negativo = models.BooleanField(default=False,
                                 help_text='Permite registrar ventas aunque no haya stock disponible.')
    gestiona_stock         = models.BooleanField('Gestiona stock', default=True,
                                 help_text='Desactivar para productos de tipo servicio o sin control de inventario.')

    # — Variantes genéricas —
    # gestiona_variantes=True: el producto tiene variantes (color, sabor, talle, etc.)
    #   stock_actual del producto = suma de stock de todas sus combinaciones activas.
    # gestiona_variantes=False: producto sin variantes (stock único).
    gestiona_variantes = models.BooleanField(
        'Gestiona variantes',
        default=False,
        help_text='Activar si el producto tiene variantes (color, sabor, talle, aroma, etc.) con stock independiente.',
    )

    # — Estado y visibilidad —
    estado    = models.CharField(max_length=20, choices=EstadoProducto.choices,
                    default=EstadoProducto.ACTIVO)
    publicado = models.BooleanField(default=False,
                    help_text='Visible en catálogo público / e-commerce.')
    destacado = models.BooleanField(default=False,
                    help_text='Producto destacado en catálogo.')

    # — Logística —
    requiere_refrigeracion = models.BooleanField('Requiere refrigeración', default=False)
    es_fragil              = models.BooleanField('Es frágil', default=False)
    es_peligroso           = models.BooleanField('Es peligroso / Hazmat', default=False)
    es_perecedero          = models.BooleanField('Es perecedero', default=False,
                                 help_text='Producto con fecha de vencimiento.')
    posicion_deposito      = models.CharField('Posición en depósito', max_length=50, blank=True,
                                 help_text='Ej: A3-P2. Ubicación física en el depósito.')

    # — Notas y etiquetas —
    notas = models.TextField(blank=True, help_text='Notas internas del equipo.')
    tags  = models.CharField(max_length=500, blank=True,
                help_text='Etiquetas separadas por coma (ej: importado, liquidación).')

    # — Auditoría —
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Producto'
        verbose_name_plural = 'Productos'
        ordering            = ['nombre']

    def __str__(self):
        return f'[{self.codigo}] {self.nombre}' if self.codigo else self.nombre

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = _generar_codigo_producto()
        if self.pk and self.gestiona_variantes:
            total = (
                self.combinaciones.filter(activo=True)
                .aggregate(total=models.Sum('stock_actual'))['total']
                or 0
            )
            self.stock_actual = total
        super().save(*args, **kwargs)

    def sincronizar_stock_desde_combinaciones(self):
        """
        Recalcula y persiste stock_actual como suma de combinaciones activas.
        Llamar después de modificar el stock de cualquier CombinacionVariante.
        No hacer nada si gestiona_variantes=False.
        """
        if not self.gestiona_variantes:
            return
        total = (
            self.combinaciones.filter(activo=True)
            .aggregate(total=models.Sum('stock_actual'))['total']
            or 0
        )
        Producto.objects.filter(pk=self.pk).update(stock_actual=total)
        self.stock_actual = total

    def actualizar_costo_y_precio(self):
        """
        Recalcula costo_actual desde el lote ACTIVO más reciente del
        producto, y si modo_precio=AUTOMATICO, recalcula precio_venta a
        partir de ese costo + porcentaje_ganancia. Se llama únicamente
        desde compras (confirmar/anular/reactivar/editar_completa/delete
        de una Compra) — nunca al vender, nunca en el momento de la venta.
        """
        from compras.models import LoteCompra  # import diferido, evita circularidad

        ultimo_lote = LoteCompra.objects.filter(
            producto=self, activo=True,
        ).order_by('-fecha_compra', '-fecha_alta').first()

        nuevo_costo = ultimo_lote.costo_unitario if ultimo_lote else None
        update_fields = []

        if nuevo_costo != self.costo_actual:
            self.costo_actual = nuevo_costo
            update_fields.append('costo_actual')

        if self.modo_precio == ModoPrecio.AUTOMATICO and self.costo_actual is not None:
            margen = self.porcentaje_ganancia or Decimal('0')
            nuevo_precio = (self.costo_actual * (Decimal('1') + margen / Decimal('100'))).quantize(Decimal('0.01'))
            if nuevo_precio != self.precio_venta:
                self.precio_venta = nuevo_precio
                update_fields.append('precio_venta')

        if update_fields:
            self.save(update_fields=update_fields)

    def delete(self, *args, **kwargs):
        """
        Elimina el producto y sus movimientos de stock en bloque.
        Se usa queryset.delete() para los movimientos para evitar que cada
        MovimientoStock.delete() intente revertir stock de un producto que
        ya no existe. Los ProductoColor se eliminan en cascada automáticamente.
        """
        from django.db import transaction
        with transaction.atomic():
            self.movimientos_stock.all().delete()
            super().delete(*args, **kwargs)

    # — Properties de utilidad —

    @property
    def stock_bajo(self):
        """True si el stock total está en o por debajo del mínimo configurado."""
        return self.gestiona_stock and self.stock_minimo > 0 and self.stock_actual <= self.stock_minimo

    @property
    def imagen_principal(self):
        return self.imagenes.filter(es_portada=True).first() or self.imagenes.first()

    @property
    def precio_neto(self):
        """Precio sin IVA, calculado a partir del precio de venta final."""
        if not self.precio_venta:
            return None
        alicuota = float(self.alicuota_iva)
        if alicuota == 0:
            return self.precio_venta
        return round(float(self.precio_venta) / (1 + alicuota / 100), 2)

    @property
    def monto_iva(self):
        """Monto de IVA contenido en el precio de venta."""
        if not self.precio_venta:
            return None
        neto = self.precio_neto
        return round(float(self.precio_venta) - neto, 2)

    def get_tags_lista(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]


# ══════════════════════════════════════════════════════════════════
#  SISTEMA DE VARIANTES GENÉRICAS
# ══════════════════════════════════════════════════════════════════

class Variante(models.Model):
    """
    Tipo de variante genérica (ej: Color, Sabor, Talle, Aroma, Tamaño).
    Estas variantes se crean una vez y se reutilizan en todos los productos.
    """
    nombre      = models.CharField(max_length=50, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    activo      = models.BooleanField(default=True)
    orden       = models.PositiveSmallIntegerField(default=0)
    fecha_alta  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Variante'
        verbose_name_plural = 'Variantes'
        ordering            = ['orden', 'nombre']

    def __str__(self):
        return self.nombre

    @property
    def total_opciones(self):
        return self.opciones.count()


class OpcionVariante(models.Model):
    """
    Opción específica de una variante (ej: Rojo, Verde, S, M, L, Naranja, Manzana).
    Estas opciones se crean una vez y se reutilizan en todos los productos.
    """
    variante    = models.ForeignKey(Variante, on_delete=models.CASCADE, related_name='opciones')
    nombre      = models.CharField(max_length=50)
    descripcion = models.CharField(max_length=200, blank=True)
    activo      = models.BooleanField(default=True)
    orden       = models.PositiveSmallIntegerField(default=0)
    fecha_alta  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Opción de variante'
        verbose_name_plural = 'Opciones de variantes'
        ordering            = ['orden', 'nombre']
        unique_together     = [('variante', 'nombre')]

    def __str__(self):
        return f'{self.variante.nombre}: {self.nombre}'


class CombinacionVariante(models.Model):
    """
    Combinación específica de opciones para un producto.
    Ejemplo: Producto "Remera" → Color:Rojo + Talle:M
    Cada combinación tiene su propio código de barras y stock independiente.
    """
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name='combinaciones',
        verbose_name='Producto',
    )

    # — Identificación —
    descripcion_combinacion = models.CharField(
        'Descripción de combinación',
        max_length=200,
        blank=True,
        help_text='Generada automáticamente a partir de las opciones seleccionadas.',
    )
    codigo_barras = models.CharField(
        'Código de barras',
        max_length=100,
        blank=True,
        help_text='Código de barras específico para esta combinación.',
    )
    sku_variante = models.CharField(
        'SKU variante',
        max_length=100,
        blank=True,
        help_text='SKU específico de esta combinación. Si está vacío se usa el SKU del producto.',
    )

    # — Stock —
    stock_actual = models.PositiveIntegerField('Stock actual', default=0)

    # — Control —
    activo = models.BooleanField(
        default=True,
        help_text='Desactivar en lugar de eliminar para preservar trazabilidad.',
    )

    # — Auditoría —
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Combinación de variante'
        verbose_name_plural = 'Combinaciones de variantes'
        ordering            = ['pk']

    def __str__(self):
        opciones = self.opciones.all()
        nombres = [f"{op.variante.nombre}:{op.nombre}" for op in opciones]
        return f'{self.producto.codigo} — {", ".join(nombres)}'

    @property
    def sku_efectivo(self):
        """SKU de la combinación o, si está vacío, el del producto padre."""
        return self.sku_variante or self.producto.sku

    def construir_descripcion_desde_opciones(self):
        """Descripción legible a partir de las opciones vinculadas."""
        opciones = (
            self.opciones
            .select_related('opcion__variante')
            .order_by('opcion__variante__orden', 'opcion__orden')
        )
        partes = [
            f'{rel.opcion.variante.nombre}: {rel.opcion.nombre}'
            for rel in opciones
        ]
        return ' | '.join(partes)

    def descripcion_legible(self):
        """Descripción persistida o generada desde las opciones."""
        return self.descripcion_combinacion or self.construir_descripcion_desde_opciones()

    def sincronizar_descripcion(self):
        """Persiste descripcion_combinacion según las opciones actuales."""
        desc = self.construir_descripcion_desde_opciones()
        if desc and desc != self.descripcion_combinacion:
            self.descripcion_combinacion = desc
            CombinacionVariante.objects.filter(pk=self.pk).update(
                descripcion_combinacion=desc,
            )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.producto.sincronizar_stock_desde_combinaciones()


class CombinacionVarianteOpcion(models.Model):
    """
    Tabla intermedia que relaciona una combinación con sus opciones específicas.
    Permite que una combinación tenga múltiples opciones (ej: Color:Rojo + Talle:M).
    """
    combinacion = models.ForeignKey(
        CombinacionVariante,
        on_delete=models.CASCADE,
        related_name='opciones',
    )
    opcion = models.ForeignKey(
        OpcionVariante,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name        = 'Opción de combinación'
        verbose_name_plural = 'Opciones de combinación'
        unique_together     = [('combinacion', 'opcion')]

    def __str__(self):
        return f'{self.combinacion.producto.codigo} — {self.opcion}'


# ══════════════════════════════════════════════════════════════════
#  IMÁGENES DEL PRODUCTO
# ══════════════════════════════════════════════════════════════════

class ProductoImagen(models.Model):
    producto    = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='imagenes')
    imagen      = models.ImageField(upload_to=_producto_imagen_path)
    es_portada  = models.BooleanField(default=False)
    descripcion = models.CharField(max_length=200, blank=True)
    orden       = models.PositiveIntegerField(default=0)
    subida_el   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['-es_portada', 'orden', 'subida_el']
        verbose_name        = 'Imagen de producto'
        verbose_name_plural = 'Imágenes de producto'

    def __str__(self):
        return f'Imagen de {self.producto}{" [PORTADA]" if self.es_portada else ""}'

    def save(self, *args, **kwargs):
        if self.es_portada:
            ProductoImagen.objects.filter(
                producto=self.producto, es_portada=True
            ).exclude(pk=self.pk).update(es_portada=False)
        super().save(*args, **kwargs)


# ══════════════════════════════════════════════════════════════════
#  CHOICES — MOVIMIENTO DE STOCK
# ══════════════════════════════════════════════════════════════════

class TipoMovimiento(models.TextChoices):
    # Entradas
    COMPRA          = 'compra',       'Compra a proveedor'
    AJUSTE_POS      = 'ajuste_pos',   'Ajuste positivo (corrección)'
    DEVOLUCION_V    = 'devolucion_v', 'Devolución de venta'
    TRANSFERENCIA_E = 'transf_e',     'Transferencia (entrada)'
    INVENTARIO_E    = 'inventario_e', 'Inventario inicial'
    # Salidas
    VENTA           = 'venta',        'Venta'
    AJUSTE_NEG      = 'ajuste_neg',   'Ajuste negativo (corrección)'
    DEVOLUCION_C    = 'devolucion_c', 'Devolución a proveedor'
    TRANSFERENCIA_S = 'transf_s',     'Transferencia (salida)'
    MERMA           = 'merma',        'Merma / Pérdida'
    USO_INTERNO     = 'uso_interno',  'Uso interno'


MOVIMIENTOS_ENTRADA = {
    TipoMovimiento.COMPRA,
    TipoMovimiento.AJUSTE_POS,
    TipoMovimiento.DEVOLUCION_V,
    TipoMovimiento.TRANSFERENCIA_E,
    TipoMovimiento.INVENTARIO_E,
}


# ══════════════════════════════════════════════════════════════════
#  MOVIMIENTO DE STOCK
# ══════════════════════════════════════════════════════════════════

class MovimientoStock(models.Model):
    """
    Registro inmutable de cada entrada o salida de stock.

    Reglas:
    - cantidad siempre positiva; el tipo determina si es entrada o salida.
    - stock_anterior y stock_posterior se calculan automáticamente en save().
    - No se pueden editar movimientos ya guardados (solo crear o eliminar).
    - Al eliminar un movimiento individual, se revierte el stock del producto.
    - Al eliminar un Producto, sus movimientos se borran en bloque con
      queryset.delete() sin disparar este delete() individual (intencional).

    FUTURO (sprint de compras/ventas):
      - La FK a CombinacionVariante ya está implementada.
      - Agregar FK a Compra / Venta para trazabilidad completa.
    """

    producto = models.ForeignKey(
        Producto, on_delete=models.CASCADE,
        related_name='movimientos_stock',
    )
    # FK a combinación: null cuando el producto no tiene variantes,
    # o cuando el movimiento afecta al stock general sin distinguir combinación.
    combinacion = models.ForeignKey(
        'CombinacionVariante', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='movimientos',
        help_text='Combinación afectada. Null si el producto no tiene variantes.',
    )
    tipo            = models.CharField(max_length=20, choices=TipoMovimiento.choices)
    cantidad        = models.PositiveIntegerField(
                          help_text='Siempre positivo. El tipo determina si es entrada o salida.')
    stock_anterior  = models.PositiveIntegerField(
                          help_text='Stock total del producto antes del movimiento (calculado automáticamente).')
    stock_posterior = models.PositiveIntegerField(
                          help_text='Stock total del producto después del movimiento (calculado automáticamente).')
    motivo          = models.CharField(max_length=300, blank=True,
                          help_text='Descripción libre del motivo.')
    referencia      = models.CharField(max_length=100, blank=True,
                          help_text='N° de compra, venta, remito, etc.')
    usuario         = models.ForeignKey(
                          settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                          null=True, blank=True, related_name='+')
    fecha           = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Movimiento de stock'
        verbose_name_plural = 'Movimientos de stock'
        ordering            = ['-fecha']

    def __str__(self):
        signo = '+' if self.tipo in MOVIMIENTOS_ENTRADA else '-'
        return (
            f'{self.producto.codigo} | {signo}{self.cantidad} | '
            f'{self.get_tipo_display()} | {self.fecha:%d/%m/%Y}'
        )

    @property
    def es_entrada(self):
        return self.tipo in MOVIMIENTOS_ENTRADA

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError(
                'Los movimientos de stock no pueden editarse. '
                'Eliminá este registro y creá uno nuevo para corregir.'
            )

        from django.db import transaction
        with transaction.atomic():
            producto = Producto.objects.select_for_update().get(pk=self.producto_id)

            self.stock_anterior = producto.stock_actual

            if self.tipo in MOVIMIENTOS_ENTRADA:
                nuevo_stock = producto.stock_actual + self.cantidad
            else:
                nuevo_stock = producto.stock_actual - self.cantidad
                if nuevo_stock < 0 and not producto.permite_stock_negativo:
                    raise ValueError(
                        f'Stock insuficiente. '
                        f'Disponible: {producto.stock_actual}, solicitado: {self.cantidad}.'
                    )

            self.stock_posterior = nuevo_stock
            super().save(*args, **kwargs)
            Producto.objects.filter(pk=producto.pk).update(stock_actual=nuevo_stock)

    def delete(self, *args, **kwargs):
        """Revierte el stock al eliminar un movimiento individual."""
        from django.db import transaction
        with transaction.atomic():
            producto = Producto.objects.select_for_update().get(pk=self.producto_id)
            if self.tipo in MOVIMIENTOS_ENTRADA:
                stock_revertido = producto.stock_actual - self.cantidad
            else:
                stock_revertido = producto.stock_actual + self.cantidad
            super().delete(*args, **kwargs)
            Producto.objects.filter(pk=producto.pk).update(stock_actual=stock_revertido)