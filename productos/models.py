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
#  PROVEEDOR  (sin cambios respecto al original)
# ══════════════════════════════════════════════════════════════════

class Proveedor(models.Model):

    # — Identidad —
    nombre      = models.CharField(max_length=200)
    cuit        = models.CharField(max_length=20, blank=True)
    tipo        = models.CharField(max_length=20, choices=TipoProveedor.choices,
                                   default=TipoProveedor.NACIONAL)
    activo      = models.BooleanField(default=True)
    sitio_web   = models.URLField(blank=True)
    descripcion = models.TextField(blank=True, help_text="Descripción interna del proveedor")

    # — Contacto —
    email           = models.EmailField(blank=True)
    telefono        = models.CharField(max_length=30, blank=True)
    contacto_nombre = models.CharField(max_length=150, blank=True, verbose_name="Nombre del contacto")
    contacto_cargo  = models.CharField(max_length=100, blank=True, verbose_name="Cargo del contacto")

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
                         help_text="Días hábiles promedio de entrega")
    notas          = models.TextField(blank=True, help_text="Notas internas / condiciones especiales")

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
    EXENTO   = '0',    'Exento (0%)'
    REDUCIDO = '10.5', 'Reducido (10,5%)'
    GENERAL  = '21',   'General (21%)'
    ESPECIAL = '27',   'Especial (27%)'


class EstadoProducto(models.TextChoices):
    ACTIVO   = 'activo',        'Activo'
    INACTIVO = 'inactivo',      'Inactivo'
    DESCONT  = 'discontinuado', 'Discontinuado'
    AGOTADO  = 'agotado',       'Agotado (sin reposición)'


# ══════════════════════════════════════════════════════════════════
#  CATEGORÍA DE PRODUCTO  (dinámica — usuario crea/elimina)
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
#  TIPO DE PRODUCTO  (dinámica — usuario crea/elimina)
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
    """media/productos/<codigo>/filename — replica patrón clientes/<codigo>/filename"""
    import os
    producto      = instance.producto
    carpeta       = producto.codigo if producto.codigo else str(producto.pk)
    nombre_limpio = os.path.basename(filename)
    return f'productos/{carpeta}/{nombre_limpio}'


def _generar_codigo_producto():
    """Genera código correlativo: PRD-00001"""
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
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL,
                    null=True, blank=True, related_name='productos',
                    verbose_name='Proveedor principal')

    # — Unidad y presentación —
    unidad_medida  = models.CharField(max_length=20, choices=UnidadMedida.choices,
                         default=UnidadMedida.UNIDAD)
    contenido_neto = models.DecimalField(max_digits=10, decimal_places=3,
                         null=True, blank=True)

    # — Dimensiones —
    peso_kg        = models.DecimalField('Peso (kg)', max_digits=8, decimal_places=3, null=True, blank=True)
    alto_cm        = models.DecimalField('Alto (cm)', max_digits=7, decimal_places=2, null=True, blank=True)
    ancho_cm       = models.DecimalField('Ancho (cm)', max_digits=7, decimal_places=2, null=True, blank=True)
    profundidad_cm = models.DecimalField('Profundidad (cm)', max_digits=7, decimal_places=2, null=True, blank=True)

    # — Precios —
    precio_venta     = models.DecimalField('Precio de venta', max_digits=12, decimal_places=2, null=True, blank=True)
    precio_mayorista = models.DecimalField('Precio mayorista', max_digits=12, decimal_places=2, null=True, blank=True)
    precio_oferta    = models.DecimalField('Precio oferta', max_digits=12, decimal_places=2, null=True, blank=True)

    # — Impuestos —
    alicuota_iva       = models.CharField('Alícuota IVA', max_length=5,
                             choices=AlicuotaIVA.choices, default=AlicuotaIVA.GENERAL)
    precio_incluye_iva = models.BooleanField('Precio incluye IVA', default=True)

    # — Stock —
    stock_actual           = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    stock_minimo           = models.DecimalField('Stock mínimo', max_digits=12, decimal_places=3, default=0)
    stock_maximo           = models.DecimalField('Stock máximo', max_digits=12, decimal_places=3, null=True, blank=True)
    permite_stock_negativo = models.BooleanField(default=False)
    gestiona_stock         = models.BooleanField('Gestiona stock', default=True)

    # — Estado y visibilidad —
    estado    = models.CharField(max_length=20, choices=EstadoProducto.choices,
                    default=EstadoProducto.ACTIVO)
    publicado = models.BooleanField(default=False, help_text='Visible en catálogo público.')
    destacado = models.BooleanField(default=False)

    # — Logística —
    requiere_refrigeracion = models.BooleanField('Requiere refrigeración', default=False)
    es_fragil              = models.BooleanField('Es frágil', default=False)
    es_peligroso           = models.BooleanField('Es peligroso / Hazmat', default=False)
    posicion_deposito      = models.CharField('Posición en depósito', max_length=50, blank=True)

    # — Notas —
    notas = models.TextField(blank=True)
    tags  = models.CharField(max_length=500, blank=True,
                help_text='Etiquetas separadas por coma.')

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
        super().save(*args, **kwargs)

    @property
    def stock_bajo(self):
        return self.gestiona_stock and self.stock_actual <= self.stock_minimo

    @property
    def imagen_principal(self):
        return self.imagenes.filter(es_portada=True).first() or self.imagenes.first()

    @property
    def precio_final(self):
        return self.precio_oferta if self.precio_oferta else self.precio_venta

    @property
    def precio_con_iva(self):
        if not self.precio_venta:
            return None
        if self.precio_incluye_iva:
            return self.precio_venta
        factor = 1 + (float(self.alicuota_iva) / 100)
        return round(float(self.precio_venta) * factor, 2)

    def get_tags_lista(self):
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]


# ══════════════════════════════════════════════════════════════════
#  IMÁGENES DEL PRODUCTO
# ══════════════════════════════════════════════════════════════════

class ProductoImagen(models.Model):
    """Replica patrón ClienteImagen. Ruta: media/productos/<codigo>/filename"""
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
    COMPRA        = 'compra',        'Compra a proveedor'
    AJUSTE_POS    = 'ajuste_pos',    'Ajuste positivo (corrección)'
    DEVOLUCION_V  = 'devolucion_v',  'Devolución de venta'
    TRANSFERENCIA_E = 'transf_e',   'Transferencia (entrada)'
    INVENTARIO_E  = 'inventario_e',  'Inventario inicial'
    # Salidas
    VENTA         = 'venta',         'Venta'
    AJUSTE_NEG    = 'ajuste_neg',    'Ajuste negativo (corrección)'
    DEVOLUCION_C  = 'devolucion_c',  'Devolución a proveedor'
    TRANSFERENCIA_S = 'transf_s',   'Transferencia (salida)'
    MERMA         = 'merma',         'Merma / Pérdida'
    USO_INTERNO   = 'uso_interno',   'Uso interno'


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
    Registra cada entrada o salida de stock de un producto.
    El stock_actual del Producto se actualiza automáticamente
    en el método save() de esta clase (y en delete()).
    """

    producto        = models.ForeignKey(
                          Producto, on_delete=models.CASCADE,
                          related_name='movimientos_stock')
    tipo            = models.CharField(
                          max_length=20, choices=TipoMovimiento.choices)
    cantidad        = models.DecimalField(
                          max_digits=12, decimal_places=3,
                          help_text='Siempre positivo. El tipo determina si es entrada o salida.')
    stock_anterior  = models.DecimalField(
                          max_digits=12, decimal_places=3,
                          help_text='Stock antes del movimiento (se completa automáticamente).')
    stock_posterior = models.DecimalField(
                          max_digits=12, decimal_places=3,
                          help_text='Stock después del movimiento (se completa automáticamente).')
    motivo          = models.CharField(max_length=300, blank=True,
                          help_text='Descripción libre del motivo.')
    referencia      = models.CharField(max_length=100, blank=True,
                          help_text='N° de compra, orden, remito, etc.')
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+')
    fecha           = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Movimiento de stock'
        verbose_name_plural = 'Movimientos de stock'
        ordering            = ['-fecha']

    def __str__(self):
        signo = '+' if self.tipo in MOVIMIENTOS_ENTRADA else '-'
        return f'{self.producto.codigo} | {signo}{self.cantidad} | {self.get_tipo_display()} | {self.fecha:%d/%m/%Y}'

    @property
    def es_entrada(self):
        return self.tipo in MOVIMIENTOS_ENTRADA

    def save(self, *args, **kwargs):
        """
        Al crear un movimiento nuevo:
          1. Registra el stock actual como stock_anterior.
          2. Calcula el stock_posterior.
          3. Actualiza el stock_actual del Producto.
        No se permite editar movimientos ya guardados (solo crear o eliminar).
        """
        if self.pk:
            # No permitir edición directa de movimientos ya guardados
            raise ValueError(
                'Los movimientos de stock no pueden editarse. '
                'Cree uno nuevo o elimine este para corregir.'
            )

        from django.db import transaction
        with transaction.atomic():
            # Bloquear el producto para evitar condiciones de carrera
            producto = Producto.objects.select_for_update().get(pk=self.producto_id)

            self.stock_anterior = producto.stock_actual

            if self.tipo in MOVIMIENTOS_ENTRADA:
                nuevo_stock = producto.stock_actual + self.cantidad
            else:
                nuevo_stock = producto.stock_actual - self.cantidad
                if nuevo_stock < 0 and not producto.permite_stock_negativo:
                    raise ValueError(
                        f'Stock insuficiente. Disponible: {producto.stock_actual}, '
                        f'solicitado: {self.cantidad}.'
                    )

            self.stock_posterior = nuevo_stock
            super().save(*args, **kwargs)

            # Actualizar el campo en el producto
            Producto.objects.filter(pk=producto.pk).update(stock_actual=nuevo_stock)

    def delete(self, *args, **kwargs):
        """Revertir el stock al eliminar un movimiento."""
        from django.db import transaction
        with transaction.atomic():
            producto = Producto.objects.select_for_update().get(pk=self.producto_id)
            # Revertir: si era entrada, restamos; si era salida, sumamos
            if self.tipo in MOVIMIENTOS_ENTRADA:
                stock_revertido = producto.stock_actual - self.cantidad
            else:
                stock_revertido = producto.stock_actual + self.cantidad
            super().delete(*args, **kwargs)
            Producto.objects.filter(pk=producto.pk).update(stock_actual=stock_revertido)