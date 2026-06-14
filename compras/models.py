from django.db import models
from django.conf import settings
from django.db import transaction

from productos.models import Producto, Proveedor, Moneda, CondicionPago, ProductoColor


# ══════════════════════════════════════════════════════════════════
#  CHOICES
# ══════════════════════════════════════════════════════════════════

class EstadoCompra(models.TextChoices):
    BORRADOR   = 'borrador',   'Borrador'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


# ══════════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _sumar_stock_item(item):
    """
    Suma el stock correspondiente a un ítem al confirmar una compra.

    - Si el producto gestiona variantes de color Y el ítem tiene un color
      asignado: suma en ProductoColor y sincroniza el total del producto.
    - Si el producto gestiona variantes de color pero el ítem NO tiene color
      (caso raro / migración): suma directamente en Producto.stock_actual.
    - Si el producto no gestiona variantes de color: suma en Producto.stock_actual.
    """
    producto = item.producto
    if producto is None or not producto.gestiona_stock:
        return

    if producto.tiene_variantes_color and item.color is not None:
        color = item.color
        nuevo_stock = color.stock_actual + item.cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para color {color.nombre}: {nuevo_stock}')
        color.stock_actual = nuevo_stock
        color.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_colores()
    else:
        nuevo_stock = producto.stock_actual + item.cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para producto {producto.nombre}: {nuevo_stock}')
        producto.stock_actual = nuevo_stock
        producto.save(update_fields=['stock_actual'])


def _restar_stock_item(item):
    """
    Resta el stock correspondiente a un ítem al anular/eliminar una compra.
    Misma lógica de despacho que _sumar_stock_item.
    """
    producto = item.producto
    if producto is None or not producto.gestiona_stock:
        return

    if producto.tiene_variantes_color and item.color is not None:
        color = item.color
        nuevo_stock = color.stock_actual - item.cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para color {color.nombre}: {nuevo_stock}')
        color.stock_actual = nuevo_stock
        color.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_colores()
    else:
        nuevo_stock = producto.stock_actual - item.cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para producto {producto.nombre}: {nuevo_stock}')
        producto.stock_actual = nuevo_stock
        producto.save(update_fields=['stock_actual'])


# ══════════════════════════════════════════════════════════════════
#  COMPRA  (cabecera)
# ══════════════════════════════════════════════════════════════════

class Compra(models.Model):
    """
    Cabecera de una orden de compra.
    Cada ítem tiene su propio proveedor, por eso el proveedor
    vive en ItemCompra, no aquí.

    Flujo de estados:
        BORRADOR ──confirmar──→ CONFIRMADA  (suma stock)
        CONFIRMADA ──anular───→ ANULADA     (revierte stock)
        ANULADA ──reactivar───→ BORRADOR    (sin tocar stock)
        BORRADOR ──confirmar──→ CONFIRMADA  (re-confirma)

    Eliminar:
        CONFIRMADA → revierte stock + borra
        ANULADA    → borra directo (stock ya fue revertido al anular)
    """

    numero     = models.CharField(max_length=20, unique=True, blank=True,
                     help_text='Se genera automáticamente: CMP-00001')
    fecha      = models.DateField()
    estado     = models.CharField(max_length=20, choices=EstadoCompra.choices,
                     default=EstadoCompra.BORRADOR)

    # — Totales (calculados al confirmar) —
    total      = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # — Notas —
    notas      = models.TextField(blank=True)

    # — Auditoría —
    creado_por         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                             null=True, blank=True, related_name='compras_creadas')
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Compra'
        verbose_name_plural = 'Compras'
        ordering            = ['-fecha', '-fecha_alta']

    def __str__(self):
        return self.numero or f'Compra #{self.pk}'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = _generar_numero_compra()
        super().save(*args, **kwargs)

    # ── override delete() ────────────────────────────────────────
    def delete(self, *args, **kwargs):
        """
        Elimina la compra:
        - Si estaba CONFIRMADA: revierte el stock de cada ítem antes de borrar,
          respetando variantes de color si corresponde.
        - Si el producto fue eliminado (producto=None): se omite silenciosamente.
        - Si estaba ANULADA: borra directo (stock ya fue revertido al anular).
        """
        with transaction.atomic():
            if self.estado == EstadoCompra.CONFIRMADA:
                for item in self.items.select_related('producto', 'color'):
                    _restar_stock_item(item)
            super().delete(*args, **kwargs)

    # ── Métodos de negocio ───────────────────────────────────────

    def calcular_total(self):
        """Recalcula el total sumando todos los ítems."""
        self.total = sum(item.subtotal for item in self.items.all())
        self.save(update_fields=['total'])

    @transaction.atomic
    def confirmar(self):
        """
        Confirma la compra: suma stock (respetando variantes de color)
        y pasa a CONFIRMADA. Solo disponible desde BORRADOR.
        """
        if self.estado != EstadoCompra.BORRADOR:
            raise ValueError('Solo se pueden confirmar compras en estado Borrador.')

        for item in self.items.select_related('producto', 'color'):
            _sumar_stock_item(item)

        self.calcular_total()
        self.estado = EstadoCompra.CONFIRMADA
        self.save(update_fields=['estado', 'total'])

    @transaction.atomic
    def anular(self):
        """
        Anula la compra y revierte el stock si estaba CONFIRMADA,
        respetando variantes de color. Solo disponible desde CONFIRMADA.
        Si el producto fue eliminado (producto=None): se omite silenciosamente.
        """
        if self.estado == EstadoCompra.ANULADA:
            raise ValueError('La compra ya está anulada.')
        if self.estado == EstadoCompra.BORRADOR:
            raise ValueError('Las compras en borrador no se anulan — simplemente no se confirman.')

        for item in self.items.select_related('producto', 'color'):
            _restar_stock_item(item)

        self.estado = EstadoCompra.ANULADA
        self.save(update_fields=['estado'])

    @transaction.atomic
    def reactivar(self):
        """
        Reactiva una compra ANULADA devolviéndola a BORRADOR.
        No toca el stock (fue revertido al anular).
        Desde BORRADOR se puede editar y volver a confirmar.
        """
        if self.estado != EstadoCompra.ANULADA:
            raise ValueError('Solo se pueden reactivar compras anuladas.')

        self.estado = EstadoCompra.BORRADOR
        self.save(update_fields=['estado'])

    @transaction.atomic
    def editar_completa(self, fecha, notas, items_data):
        """
        Edita una compra ANULADA: reemplaza todos sus ítems y la re-confirma.

        Flujo:
          1. Valida que esté ANULADA (el stock ya fue revertido al anular).
          2. Borra los ítems viejos.
          3. Crea los ítems nuevos.
          4. Suma el stock de los nuevos ítems (respetando colores).
          5. Recalcula el total.
          6. Pasa a CONFIRMADA.

        items_data: lista de dicts con claves:
            producto (instancia Producto),
            proveedor (instancia|None),
            color (instancia ProductoColor|None),   ← nuevo
            cantidad, costo_unitario, moneda, descuento_pct,
            condicion_pago, referencia, notas
        """
        if self.estado != EstadoCompra.ANULADA:
            raise ValueError('Solo se pueden editar compras que estén anuladas.')

        if not items_data:
            raise ValueError('La compra debe tener al menos un ítem.')

        # — Reemplazar ítems —
        self.items.all().delete()

        for d in items_data:
            ItemCompra.objects.create(
                compra         = self,
                producto       = d['producto'],
                proveedor      = d.get('proveedor'),
                color          = d.get('color'),          # ← nuevo
                cantidad       = d['cantidad'],
                costo_unitario = d['costo_unitario'],
                moneda         = d.get('moneda', 'ARS'),
                descuento_pct  = d.get('descuento_pct', 0),
                condicion_pago = d.get('condicion_pago', 'contado'),
                referencia     = d.get('referencia', ''),
                notas          = d.get('notas', ''),
            )

        # — Actualizar cabecera —
        self.fecha = fecha
        self.notas = notas
        self.save(update_fields=['fecha', 'notas'])

        # — Sumar stock de los nuevos ítems —
        for item in self.items.select_related('producto', 'color'):
            _sumar_stock_item(item)

        # — Recalcular total y confirmar —
        self.total  = sum(item.subtotal for item in self.items.all())
        self.estado = EstadoCompra.CONFIRMADA
        self.save(update_fields=['total', 'estado'])

    @transaction.atomic
    def editar_cabecera(self, fecha, notas):
        """
        Edita fecha y notas. Solo disponible en BORRADOR.
        """
        if self.estado != EstadoCompra.BORRADOR:
            raise ValueError('Solo se pueden editar compras en estado Borrador.')

        self.fecha = fecha
        self.notas = notas
        self.save(update_fields=['fecha', 'notas'])


# ══════════════════════════════════════════════════════════════════
#  ÍTEM DE COMPRA  (línea del carrito)
# ══════════════════════════════════════════════════════════════════

class ItemCompra(models.Model):
    """
    Una línea dentro de una Compra.
    Cada ítem tiene su propio proveedor y condiciones comerciales.

    Variantes de color:
        Si el producto tiene tiene_variantes_color=True, el campo `color`
        apunta al ProductoColor específico. El stock se suma/resta en ese
        color y el total del producto se sincroniza automáticamente.
        Si el producto no gestiona colores, `color` queda en None.

    Snapshots: producto_nombre, producto_codigo, proveedor_nombre y
    color_nombre se autocompletan al crear el ítem y nunca se modifican.
    Sirven para mostrar el historial aunque el producto, proveedor o color
    hayan sido eliminados posteriormente.
    """

    compra    = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name='items')

    producto  = models.ForeignKey(
                    Producto, on_delete=models.SET_NULL,
                    null=True, blank=True,
                    related_name='items_compra')

    proveedor = models.ForeignKey(
                    Proveedor, on_delete=models.SET_NULL,
                    null=True, blank=True,
                    related_name='items_compra')

    # ── Variante de color (opcional) ─────────────────────────────
    # Solo se completa cuando Producto.tiene_variantes_color = True.
    # SET_NULL para conservar el ítem histórico si se elimina el color.
    color     = models.ForeignKey(
                    ProductoColor, on_delete=models.SET_NULL,
                    null=True, blank=True,
                    related_name='items_compra',
                    verbose_name='Color / variante')

    # ── campos snapshot ──────────────────────────────────────────
    producto_nombre  = models.CharField(max_length=255, blank=True,
                           help_text='Snapshot del nombre del producto al momento de la compra.')
    producto_codigo  = models.CharField(max_length=50, blank=True,
                           help_text='Snapshot del código del producto al momento de la compra.')
    proveedor_nombre = models.CharField(max_length=200, blank=True,
                           help_text='Snapshot del nombre del proveedor al momento de la compra.')
    color_nombre     = models.CharField(max_length=50, blank=True,
                           help_text='Snapshot del nombre del color al momento de la compra.')

    # — Cantidades y costos —
    cantidad        = models.DecimalField(max_digits=12, decimal_places=3)
    costo_unitario  = models.DecimalField('Costo unitario', max_digits=12, decimal_places=2)
    moneda          = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)

    # — Descuento opcional —
    descuento_pct   = models.DecimalField('Descuento (%)', max_digits=5, decimal_places=2, default=0)

    # — Condición de pago del ítem —
    condicion_pago  = models.CharField(max_length=20, choices=CondicionPago.choices,
                          default=CondicionPago.CONTADO, blank=True)

    # — Número de remito / factura del proveedor (opcional) —
    referencia      = models.CharField('Remito / Nº Factura', max_length=100, blank=True)

    # — Notas de línea —
    notas           = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name        = 'Ítem de compra'
        verbose_name_plural = 'Ítems de compra'
        ordering            = ['id']

    def __str__(self):
        nombre = self.producto_nombre or (str(self.producto) if self.producto else '(producto eliminado)')
        color  = f' [{self.color_nombre}]' if self.color_nombre else ''
        return f'{nombre}{color} x{self.cantidad}'

    def save(self, *args, **kwargs):
        """
        Solo al crear: captura snapshots de producto, proveedor y color.
        En ediciones posteriores los snapshots NO se tocan.
        """
        if not self.pk:
            if self.producto and not self.producto_nombre:
                self.producto_nombre = self.producto.nombre or ''
                self.producto_codigo = self.producto.codigo or ''
            if self.proveedor and not self.proveedor_nombre:
                self.proveedor_nombre = self.proveedor.nombre or ''
            if self.color and not self.color_nombre:
                self.color_nombre = self.color.nombre or ''
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        """Subtotal aplicando descuento."""
        base = self.cantidad * self.costo_unitario
        if self.descuento_pct:
            base = base * (1 - self.descuento_pct / 100)
        return round(base, 2)

    @property
    def nombre_producto_display(self):
        """Devuelve el nombre del producto usando snapshot si fue eliminado."""
        if self.producto:
            return str(self.producto)
        if self.producto_nombre:
            codigo = f'[{self.producto_codigo}] ' if self.producto_codigo else ''
            return f'{codigo}{self.producto_nombre} (eliminado)'
        return '(producto eliminado)'

    @property
    def nombre_proveedor_display(self):
        """Devuelve el nombre del proveedor usando snapshot si fue eliminado."""
        if self.proveedor:
            return str(self.proveedor)
        if self.proveedor_nombre:
            return f'{self.proveedor_nombre} (eliminado)'
        return '(sin proveedor)'

    @property
    def nombre_color_display(self):
        """Devuelve el nombre del color usando snapshot si fue eliminado."""
        if self.color:
            return self.color.nombre
        if self.color_nombre:
            return f'{self.color_nombre} (eliminado)'
        return ''


# ══════════════════════════════════════════════════════════════════
#  DOCUMENTOS / ADJUNTOS DE COMPRA
# ══════════════════════════════════════════════════════════════════

import os as _os

def _compra_doc_path(instance, filename):
    """
    Ruta: compras/<numero_compra>/<filename>
    Ej:   compras/CMP-00001/factura.pdf
    """
    numero = instance.compra.numero or f'tmp-{instance.compra.pk}'
    nombre_limpio = _os.path.basename(filename)
    return f'compras/{numero}/{nombre_limpio}'


class CompraDocumento(models.Model):
    """
    Archivo adjunto a una compra (imagen de factura, remito en PDF, etc.).
    Se almacena en media/compras/<numero_compra>/.
    """

    TIPOS = [
        ('factura',  'Factura'),
        ('remito',   'Remito'),
        ('recibo',   'Recibo'),
        ('otro',     'Otro'),
    ]

    compra      = models.ForeignKey(Compra, on_delete=models.CASCADE,
                      related_name='documentos')
    archivo     = models.FileField(upload_to=_compra_doc_path)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='otro')
    descripcion = models.CharField(max_length=200, blank=True)
    subido_el   = models.DateTimeField(auto_now_add=True)
    subido_por  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                      null=True, blank=True, related_name='+')

    class Meta:
        verbose_name        = 'Documento de compra'
        verbose_name_plural = 'Documentos de compra'
        ordering            = ['subido_el']

    def __str__(self):
        return f'{self.compra.numero} — {self.get_tipo_display()} — {_os.path.basename(self.archivo.name)}'

    @property
    def nombre_archivo(self):
        return _os.path.basename(self.archivo.name) if self.archivo else ''

    @property
    def es_imagen(self):
        ext = _os.path.splitext(self.archivo.name)[1].lower() if self.archivo else ''
        return ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif')

    @property
    def es_pdf(self):
        ext = _os.path.splitext(self.archivo.name)[1].lower() if self.archivo else ''
        return ext == '.pdf'


# ══════════════════════════════════════════════════════════════════
#  HELPER — número correlativo
# ══════════════════════════════════════════════════════════════════

def _generar_numero_compra():
    ultimo = Compra.objects.order_by('-id').first()
    if not ultimo or not ultimo.numero:
        numero = 1
    else:
        try:
            numero = int(ultimo.numero.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = Compra.objects.count() + 1
    return f'CMP-{numero:05d}'