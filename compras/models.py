from django.db import models
from django.conf import settings
from django.db import transaction

from productos.models import Producto, Proveedor, Moneda, CondicionPago, CombinacionVariante


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

    - Si el producto gestiona variantes Y el ítem tiene una combinación
      asignada: suma en CombinacionVariante y sincroniza el total del producto.
    - Si el producto gestiona variantes pero el ítem NO tiene combinación
      (caso raro / migración): suma directamente en Producto.stock_actual.
    - Si el producto no gestiona variantes: suma en Producto.stock_actual.
    """
    producto = item.producto
    if producto is None or not producto.gestiona_stock:
        return

    if producto.gestiona_variantes and item.combinacion is not None:
        combinacion = item.combinacion
        nuevo_stock = combinacion.stock_actual + item.cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para combinación {combinacion.descripcion_legible()}: {nuevo_stock}')
        combinacion.stock_actual = nuevo_stock
        combinacion.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_combinaciones()
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

    if producto.gestiona_variantes and item.combinacion is not None:
        combinacion = item.combinacion
        nuevo_stock = combinacion.stock_actual - item.cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para combinación {combinacion.descripcion_legible()}: {nuevo_stock}')
        combinacion.stock_actual = nuevo_stock
        combinacion.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_combinaciones()
    else:
        nuevo_stock = producto.stock_actual - item.cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para producto {producto.nombre}: {nuevo_stock}')
        producto.stock_actual = nuevo_stock
        producto.save(update_fields=['stock_actual'])


def _crear_lote_desde_item(item, fecha_compra):
    """
    Crea un lote de compra a partir de un ítem de compra.
    Valida que si el producto es perecedero, tenga fecha de vencimiento.
    """
    if item.producto is None:
        return

    # Validar fecha de vencimiento para productos perecederos
    if item.producto.es_perecedero and not item.fecha_vencimiento:
        raise ValueError(
            f'El producto "{item.producto.nombre}" es perecedero. '
            f'Debe especificar una fecha de vencimiento.'
        )

    LoteCompra.objects.create(
        item_compra=item,
        producto=item.producto,
        combinacion=item.combinacion,
        cantidad_inicial=int(item.cantidad),
        cantidad_actual=int(item.cantidad),
        costo_unitario=item.costo_unitario,
        fecha_vencimiento=item.fecha_vencimiento,
        fecha_compra=fecha_compra,
    )


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
          respetando variantes si corresponde.
        - Si el producto fue eliminado (producto=None): se omite silenciosamente.
        - Si estaba ANULADA: borra directo (stock ya fue revertido al anular).
        """
        with transaction.atomic():
            if self.estado == EstadoCompra.CONFIRMADA:
                for item in self.items.select_related('producto', 'combinacion'):
                    _restar_stock_item(item)
            # Sincronizar movimiento de caja grande antes de borrar
            from caja.models import sincronizar_movimiento_compra
            sincronizar_movimiento_compra(self)
            super().delete(*args, **kwargs)

    # ── Métodos de negocio ───────────────────────────────────────

    def calcular_total(self):
        """Recalcula el total sumando todos los ítems."""
        self.total = sum(item.subtotal for item in self.items.all())
        self.save(update_fields=['total'])

    @transaction.atomic
    def confirmar(self):
        """
        Confirma la compra: suma stock (respetando variantes),
        crea lotes para trazabilidad de costos y vencimientos,
        y pasa a CONFIRMADA. Solo disponible desde BORRADOR.
        """
        if self.estado != EstadoCompra.BORRADOR:
            raise ValueError('Solo se pueden confirmar compras en estado Borrador.')

        for item in self.items.select_related('producto', 'combinacion'):
            _sumar_stock_item(item)
            # Crear lote para trazabilidad
            _crear_lote_desde_item(item, self.fecha)

        self.calcular_total()
        self.estado = EstadoCompra.CONFIRMADA
        self.save(update_fields=['estado', 'total'])

        # Sincronizar movimiento de caja grande
        from caja.models import sincronizar_movimiento_compra
        sincronizar_movimiento_compra(self)

    @transaction.atomic
    def anular(self):
        """
        Anula la compra y revierte el stock si estaba CONFIRMADA,
        respetando variantes. Desactiva los lotes asociados.
        Solo disponible desde CONFIRMADA.
        Si el producto fue eliminado (producto=None): se omite silenciosamente.
        """
        if self.estado == EstadoCompra.ANULADA:
            raise ValueError('La compra ya está anulada.')
        if self.estado == EstadoCompra.BORRADOR:
            raise ValueError('Las compras en borrador no se anulan — simplemente no se confirman.')

        for item in self.items.select_related('producto', 'combinacion'):
            _restar_stock_item(item)
            # Desactivar lotes asociados a este ítem
            item.lotes.update(activo=False)

        self.estado = EstadoCompra.ANULADA
        self.save(update_fields=['estado'])

        # Sincronizar movimiento de caja grande
        from caja.models import sincronizar_movimiento_compra
        sincronizar_movimiento_compra(self)

    @transaction.atomic
    def reactivar(self):
        """
        Reactiva una compra ANULADA devolviéndola a BORRADOR.
        No toca el stock (fue revertido al anular).
        Reactiva los lotes asociados.
        Desde BORRADOR se puede editar y volver a confirmar.
        """
        if self.estado != EstadoCompra.ANULADA:
            raise ValueError('Solo se pueden reactivar compras anuladas.')

        # Reactivar lotes asociados
        for item in self.items.all():
            item.lotes.update(activo=True)

        self.estado = EstadoCompra.BORRADOR
        self.save(update_fields=['estado'])

    @transaction.atomic
    def editar_completa(self, fecha, notas, items_data):
        """
        Edita una compra ANULADA: reemplaza todos sus ítems y la re-confirma.

        Flujo:
          1. Valida que esté ANULADA (el stock ya fue revertido al anular).
          2. Borra los ítems viejos (y sus lotes asociados en cascada).
          3. Crea los ítems nuevos.
          4. Suma el stock de los nuevos ítems (respetando variantes).
          5. Crea lotes para los nuevos ítems.
          6. Recalcula el total.
          7. Pasa a CONFIRMADA.

        items_data: lista de dicts con claves:
            producto (instancia Producto),
            proveedor (instancia|None),
            combinacion (instancia CombinacionVariante|None),
            cantidad, costo_unitario, moneda, descuento_pct,
            condicion_pago, referencia, notas, fecha_vencimiento
        """
        if self.estado != EstadoCompra.ANULADA:
            raise ValueError('Solo se pueden editar compras que estén anuladas.')

        if not items_data:
            raise ValueError('La compra debe tener al menos un ítem.')

        # — Reemplazar ítems (los lotes se borran en cascada) —
        self.items.all().delete()

        for d in items_data:
            ItemCompra.objects.create(
                compra         = self,
                producto       = d['producto'],
                proveedor      = d.get('proveedor'),
                combinacion    = d.get('combinacion'),
                cantidad       = d['cantidad'],
                costo_unitario = d['costo_unitario'],
                moneda         = d.get('moneda', 'ARS'),
                descuento_pct  = d.get('descuento_pct', 0),
                condicion_pago = d.get('condicion_pago', 'contado'),
                referencia     = d.get('referencia', ''),
                notas          = d.get('notas', ''),
                fecha_vencimiento = d.get('fecha_vencimiento'),
            )

        # — Actualizar cabecera —
        self.fecha = fecha
        self.notas = notas
        self.save(update_fields=['fecha', 'notas'])

        # — Sumar stock de los nuevos ítems y crear lotes —
        for item in self.items.select_related('producto', 'combinacion'):
            _sumar_stock_item(item)
            _crear_lote_desde_item(item, self.fecha)

        # — Recalcular total y confirmar —
        self.total  = sum(item.subtotal for item in self.items.all())
        self.estado = EstadoCompra.CONFIRMADA
        self.save(update_fields=['total', 'estado'])

        # Sincronizar movimiento de caja grande
        from caja.models import sincronizar_movimiento_compra
        sincronizar_movimiento_compra(self)

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

    Variantes genéricas:
        Si el producto tiene gestiona_variantes=True, el campo `combinacion`
        apunta al CombinacionVariante específico. El stock se suma/resta en esa
        combinación y el total del producto se sincroniza automáticamente.
        Si el producto no gestiona variantes, `combinacion` queda en None.

    Snapshots: producto_nombre, producto_codigo, proveedor_nombre y
    combinacion_descripcion se autocompletan al crear el ítem y nunca se modifican.
    Sirven para mostrar el historial aunque el producto, proveedor o combinación
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

    # ── Variante genérica (opcional) ─────────────────────────────
    # Solo se completa cuando Producto.gestiona_variantes = True.
    # SET_NULL para conservar el ítem histórico si se elimina la combinación.
    combinacion = models.ForeignKey(
                    CombinacionVariante, on_delete=models.SET_NULL,
                    null=True, blank=True,
                    related_name='items_compra',
                    verbose_name='Combinación de variantes')

    # ── campos snapshot ──────────────────────────────────────────
    producto_nombre  = models.CharField(max_length=255, blank=True,
                           help_text='Snapshot del nombre del producto al momento de la compra.')
    producto_codigo  = models.CharField(max_length=50, blank=True,
                           help_text='Snapshot del código del producto al momento de la compra.')
    proveedor_nombre = models.CharField(max_length=200, blank=True,
                           help_text='Snapshot del nombre del proveedor al momento de la compra.')
    combinacion_descripcion = models.CharField(max_length=300, blank=True,
                           help_text='Snapshot de la descripción de la combinación al momento de la compra.')

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

    # — Fecha de vencimiento (para productos perecederos) —
    fecha_vencimiento = models.DateField(
        'Fecha de vencimiento',
        null=True,
        blank=True,
        help_text='Requerido para productos perecederos.'
    )

    class Meta:
        verbose_name        = 'Ítem de compra'
        verbose_name_plural = 'Ítems de compra'
        ordering            = ['id']

    def __str__(self):
        nombre = self.producto_nombre or (str(self.producto) if self.producto else '(producto eliminado)')
        combinacion = f' [{self.combinacion_descripcion}]' if self.combinacion_descripcion else ''
        return f'{nombre}{combinacion} x{self.cantidad}'

    def save(self, *args, **kwargs):
        """
        Solo al crear: captura snapshots de producto, proveedor y combinación.
        En ediciones posteriores los snapshots NO se tocan.
        """
        if not self.pk:
            if self.producto and not self.producto_nombre:
                self.producto_nombre = self.producto.nombre or ''
                self.producto_codigo = self.producto.codigo or ''
            if self.proveedor and not self.proveedor_nombre:
                self.proveedor_nombre = self.proveedor.nombre or ''
            if self.combinacion and not self.combinacion_descripcion:
                self.combinacion_descripcion = self.combinacion.descripcion_legible() or ''
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
    def nombre_combinacion_display(self):
        """Devuelve la descripción de la combinación usando snapshot si fue eliminado."""
        if self.combinacion:
            return self.combinacion.descripcion_legible()
        if self.combinacion_descripcion:
            return f'{self.combinacion_descripcion} (eliminado)'
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


# ══════════════════════════════════════════════════════════════════
#  LOTE DE COMPRA
# ══════════════════════════════════════════════════════════════════

def _generar_codigo_lote():
    """
    Genera un código único para el lote que se puede escanear.
    Formato: LT-AAAA-XXXXX donde AAAA es el año y XXXXX es un número correlativo.
    """
    from django.utils import timezone
    anio = timezone.now().year
    ultimo = LoteCompra.objects.filter(codigo__startswith=f'LT-{anio}').order_by('-id').first()
    if not ultimo:
        numero = 1
    else:
        try:
            numero = int(ultimo.codigo.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = LoteCompra.objects.count() + 1
    return f'LT-{anio}-{numero:05d}'


class LoteCompra(models.Model):
    """
    Lote de compra que representa una entrada específica de stock.
    Cada lote tiene su propio costo, fecha de vencimiento y código único escaneable.
    Permite calcular ganancias reales al vender productos de diferentes lotes.
    """

    # — Identificación —
    codigo = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        help_text='Se genera automáticamente: LT-2025-00001'
    )

    # — Referencia al ítem de compra —
    item_compra = models.ForeignKey(
        ItemCompra,
        on_delete=models.CASCADE,
        related_name='lotes',
        verbose_name='Ítem de compra'
    )

    # — Producto y variante (snapshots para trazabilidad) —
    producto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lotes',
        verbose_name='Producto'
    )
    combinacion = models.ForeignKey(
        CombinacionVariante,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lotes',
        verbose_name='Combinación de variante'
    )

    # — Datos del lote —
    cantidad_inicial = models.PositiveIntegerField(
        'Cantidad inicial',
        help_text='Cantidad de productos en este lote al momento de la compra.'
    )
    cantidad_actual = models.PositiveIntegerField(
        'Cantidad actual',
        help_text='Cantidad disponible actualmente en este lote.'
    )
    costo_unitario = models.DecimalField(
        'Costo unitario',
        max_digits=12,
        decimal_places=2,
        help_text='Costo unitario de este lote (para cálculo de ganancias).'
    )

    # — Fecha de vencimiento —
    fecha_vencimiento = models.DateField(
        'Fecha de vencimiento',
        null=True,
        blank=True,
        help_text='Fecha de vencimiento del lote (requerido para productos perecederos).'
    )

    # — Fecha de compra —
    fecha_compra = models.DateField(
        'Fecha de compra',
        help_text='Fecha en que se realizó la compra de este lote.'
    )

    # — Estado —
    activo = models.BooleanField(
        default=True,
        help_text='Desactivar en lugar de eliminar para preservar trazabilidad.'
    )

    # — Auditoría —
    fecha_alta = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Lote de compra'
        verbose_name_plural = 'Lotes de compra'
        ordering = ['-fecha_compra', '-fecha_alta']

    def __str__(self):
        return f'{self.codigo} - {self.producto.nombre if self.producto else "N/A"} ({self.cantidad_actual}/{self.cantidad_inicial})'

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = _generar_codigo_lote()
        super().save(*args, **kwargs)

    @property
    def stock_disponible(self):
        """Cantidad disponible en este lote."""
        return self.cantidad_actual

    @property
    def porcentaje_restante(self):
        """Porcentaje de stock restante en el lote."""
        if self.cantidad_inicial == 0:
            return 0
        return round((self.cantidad_actual / self.cantidad_inicial) * 100, 2)

    def descontar_stock(self, cantidad):
        """Descuenta stock del lote. Lanza ValueError si no hay suficiente."""
        if cantidad > self.cantidad_actual:
            raise ValueError(f'No hay suficiente stock en el lote {self.codigo}. Disponible: {self.cantidad_actual}, requerido: {cantidad}')
        self.cantidad_actual -= cantidad
        self.save(update_fields=['cantidad_actual', 'fecha_modificacion'])

    def agregar_stock(self, cantidad):
        """Agrega stock al lote (para devoluciones, correcciones, etc.)."""
        self.cantidad_actual += cantidad
        self.save(update_fields=['cantidad_actual', 'fecha_modificacion'])