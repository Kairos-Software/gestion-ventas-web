from django.db import models
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from productos.models import Producto, Moneda, CondicionPago, CombinacionVariante
from core.models import Cliente


# ══════════════════════════════════════════════════════════════════
#  CHOICES
# ══════════════════════════════════════════════════════════════════

class EstadoVenta(models.TextChoices):
    BORRADOR   = 'borrador',   'Borrador'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


class MedioPago(models.TextChoices):
    EFECTIVO      = 'efectivo',      'Efectivo'
    TRANSFERENCIA = 'transferencia', 'Transferencia'
    DEBITO        = 'debito',        'Débito'
    CREDITO       = 'credito',       'Crédito'
    QR            = 'qr',            'QR'


# ══════════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _restar_stock_item(item):
    """
    Resta el stock correspondiente a un ítem al confirmar una venta.
    - Si el producto gestiona variantes Y el ítem tiene una combinación
      asignada: resta en CombinacionVariante y sincroniza el total del producto.
    - Si no: resta directamente en Producto.stock_actual.
    """
    producto = item.producto
    if producto is None or not producto.gestiona_stock:
        return

    if producto.gestiona_variantes and item.combinacion is not None:
        combinacion = item.combinacion
        combinacion.stock_actual -= item.cantidad
        combinacion.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_combinaciones()
    else:
        producto.stock_actual -= item.cantidad
        producto.save(update_fields=['stock_actual'])


def _sumar_stock_item(item):
    """
    Suma el stock correspondiente a un ítem al anular/eliminar una venta.
    Misma lógica de despacho que _restar_stock_item.
    """
    producto = item.producto
    if producto is None or not producto.gestiona_stock:
        return

    if producto.gestiona_variantes and item.combinacion is not None:
        combinacion = item.combinacion
        combinacion.stock_actual += item.cantidad
        combinacion.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_combinaciones()
    else:
        producto.stock_actual += item.cantidad
        producto.save(update_fields=['stock_actual'])


# ══════════════════════════════════════════════════════════════════
#  VENTA  (cabecera)
# ══════════════════════════════════════════════════════════════════

class Venta(models.Model):
    """
    Cabecera de una orden de venta.

    Flujo de estados:
        BORRADOR ──confirmar──→ CONFIRMADA  (resta stock)
        CONFIRMADA ──anular───→ ANULADA     (revierte stock)
        ANULADA ──editar_completa──→ CONFIRMADA (re-confirma)

    Auditoría completa:
        creado_por       / fecha_alta         → quién creó el borrador
        confirmado_por   / fecha_confirmacion → quién confirmó
        anulado_por      / fecha_anulacion    → quién anuló
        editado_por      / fecha_edicion      → quién editó (re-confirmó)
    """

    numero = models.CharField(max_length=20, unique=True, blank=True,
                 help_text='Se genera automáticamente: VTA-00001')
    fecha  = models.DateField()
    estado = models.CharField(max_length=20, choices=EstadoVenta.choices,
                 default=EstadoVenta.BORRADOR)

    # — Medio de pago —
    medio_pago = models.CharField(
        'Medio de pago',
        max_length=20,
        choices=MedioPago.choices,
        default=MedioPago.EFECTIVO,
        blank=True,
    )

    # — Totales (calculados al confirmar) —
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # — Notas —
    notas = models.TextField(blank=True)

    # ── Auditoría ────────────────────────────────────────────────
    # Creación del borrador
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ventas_creadas',
        verbose_name='Creado por',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)

    # Confirmación
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ventas_confirmadas',
        verbose_name='Confirmado por',
    )
    fecha_confirmacion = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Fecha de confirmación',
    )

    # Anulación
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ventas_anuladas',
        verbose_name='Anulado por',
    )
    fecha_anulacion = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Fecha de anulación',
    )

    # Edición (re-confirmación desde historial)
    editado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ventas_editadas',
        verbose_name='Editado por',
    )
    fecha_edicion = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Fecha de última edición',
    )

    # Modificación general (auto)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Venta'
        verbose_name_plural = 'Ventas'
        ordering            = ['-fecha', '-fecha_alta']

    def __str__(self):
        return self.numero or f'Venta #{self.pk}'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = _generar_numero_venta()
        super().save(*args, **kwargs)

    # ── override delete() ────────────────────────────────────────
    def delete(self, *args, **kwargs):
        with transaction.atomic():
            if self.estado == EstadoVenta.CONFIRMADA:
                for item in self.items.select_related('producto', 'combinacion'):
                    _sumar_stock_item(item)
            # Sincronizar movimiento de caja grande antes de borrar
            from caja.models import sincronizar_movimiento_venta
            sincronizar_movimiento_venta(self)
            super().delete(*args, **kwargs)

    # ── Métodos de negocio ───────────────────────────────────────

    def calcular_total(self):
        self.total = sum(item.subtotal for item in self.items.all())
        self.save(update_fields=['total'])

    def editar_cabecera(self, fecha, notas=''):
        self.fecha = fecha
        self.notas = notas
        self.save(update_fields=['fecha', 'notas'])

    @transaction.atomic
    def confirmar(self, confirmado_por=None, medio_pago=None, pagos=None):
        """
        Confirma la venta: resta stock y pasa a CONFIRMADA.
        Registra quién confirmó, cuándo, el medio de pago principal
        y, si se pasan, las líneas de pago dividido (PagoVenta).

        pagos: lista de dicts [{'medio': 'efectivo', 'monto': 3000}, ...]
               Si se pasa, reemplaza cualquier PagoVenta previo de
               esta venta (relevante en re-confirmaciones vía editar_completa).
        """
        if self.estado != EstadoVenta.BORRADOR:
            raise ValueError('Solo se pueden confirmar ventas en estado Borrador.')

        for item in self.items.select_related('producto', 'combinacion'):
            _restar_stock_item(item)

        self.calcular_total()
        self.estado            = EstadoVenta.CONFIRMADA
        self.fecha_confirmacion = timezone.now()

        if confirmado_por is not None:
            self.confirmado_por = confirmado_por
        if medio_pago is not None:
            self.medio_pago = medio_pago

        self.save(update_fields=[
            'estado', 'total', 'confirmado_por', 'fecha_confirmacion', 'medio_pago',
        ])

        if pagos is not None:
            self.pagos.all().delete()
            for p in pagos:
                monto = p.get('monto')
                if not monto or float(monto) <= 0:
                    continue
                PagoVenta.objects.create(
                    venta = self,
                    medio = p.get('medio', MedioPago.EFECTIVO),
                    monto = monto,
                )

        # Sincronizar movimiento de caja grande
        from caja.models import sincronizar_movimiento_venta
        sincronizar_movimiento_venta(self)

    @transaction.atomic
    def anular(self, anulado_por=None):
        """Anula la venta y revierte el stock. Solo desde CONFIRMADA."""
        if self.estado == EstadoVenta.ANULADA:
            raise ValueError('La venta ya está anulada.')
        if self.estado == EstadoVenta.BORRADOR:
            raise ValueError('Las ventas en borrador no se anulan — simplemente no se confirman.')

        for item in self.items.select_related('producto', 'combinacion'):
            _sumar_stock_item(item)

        self.estado         = EstadoVenta.ANULADA
        self.anulado_por    = anulado_por
        self.fecha_anulacion = timezone.now()
        self.save(update_fields=['estado', 'anulado_por', 'fecha_anulacion'])

        # Sincronizar movimiento de caja grande
        from caja.models import sincronizar_movimiento_venta
        sincronizar_movimiento_venta(self)

    @transaction.atomic
    def reactivar(self):
        """Reactiva una venta ANULADA devolviéndola a BORRADOR."""
        if self.estado != EstadoVenta.ANULADA:
            raise ValueError('Solo se pueden reactivar ventas anuladas.')

        self.estado = EstadoVenta.BORRADOR
        self.save(update_fields=['estado'])

    @transaction.atomic
    def editar_completa(self, fecha, notas='', items_data=None, medio_pago=None, editado_por=None, pagos=None):
        """
        Edita una venta ANULADA: reemplaza sus ítems y la re-confirma.
        Registra quién editó y cuándo. Si se pasan pagos, reemplaza
        las líneas de pago dividido existentes.
        """
        if self.estado != EstadoVenta.ANULADA:
            raise ValueError('Solo se pueden editar ventas anuladas.')

        self.items.all().delete()

        for d in (items_data or []):
            ItemVenta.objects.create(
                venta           = self,
                producto        = d['producto'],
                cliente         = d.get('cliente'),
                combinacion     = d.get('combinacion'),
                cantidad        = d['cantidad'],
                precio_unitario = d['precio_unitario'],
                moneda          = d.get('moneda', 'ARS'),
                descuento_pct   = d.get('descuento_pct', 0),
                condicion_pago  = d.get('condicion_pago', 'contado'),
                referencia      = d.get('referencia', ''),
                notas           = d.get('notas', ''),
            )

        self.fecha        = fecha
        self.notas        = notas
        self.editado_por  = editado_por
        self.fecha_edicion = timezone.now()
        if medio_pago:
            self.medio_pago = medio_pago
        self.estado = EstadoVenta.BORRADOR
        self.save(update_fields=[
            'fecha', 'notas', 'medio_pago', 'estado', 'editado_por', 'fecha_edicion',
        ])

        # Re-confirma propagando quien editó como confirmador y los pagos
        self.confirmar(confirmado_por=editado_por, medio_pago=medio_pago, pagos=pagos)
        # La sincronización de caja ya ocurre dentro de confirmar()


# ══════════════════════════════════════════════════════════════════
#  ÍTEM DE VENTA
# ══════════════════════════════════════════════════════════════════

class ItemVenta(models.Model):
    """
    Línea de una venta. Un ítem = un producto (+ combinación opcional) + cantidad + precio.

    Snapshots: producto_nombre, producto_codigo, cliente_nombre y combinacion_descripcion
    se autocompletan al crear el ítem y nunca se modifican.
    """

    venta    = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='items')

    producto = models.ForeignKey(
                   Producto, on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='items_venta')

    cliente  = models.ForeignKey(
                   Cliente, on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='items_venta')

    # ── Variante genérica (opcional) ─────────────────────────────
    combinacion = models.ForeignKey(
                   CombinacionVariante, on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='items_venta',
                   verbose_name='Combinación de variantes')

    # ── Snapshots ────────────────────────────────────────────────
    producto_nombre  = models.CharField(max_length=255, blank=True)
    producto_codigo  = models.CharField(max_length=50,  blank=True)
    cliente_nombre   = models.CharField(max_length=200, blank=True)
    combinacion_descripcion = models.CharField(max_length=300, blank=True)

    # — Cantidades y precios —
    cantidad        = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField('Precio unitario', max_digits=12, decimal_places=2)
    moneda          = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)

    # — Descuento opcional —
    descuento_pct   = models.DecimalField('Descuento (%)', max_digits=5, decimal_places=2, default=0)

    # — Condición de pago del ítem —
    condicion_pago  = models.CharField(max_length=20, choices=CondicionPago.choices,
                          default=CondicionPago.CONTADO, blank=True)

    # — Referencia / notas de línea —
    referencia = models.CharField('Factura / Nº Referencia', max_length=100, blank=True)
    notas      = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name        = 'Ítem de venta'
        verbose_name_plural = 'Ítems de venta'
        ordering            = ['id']

    def __str__(self):
        nombre = self.producto_nombre or (str(self.producto) if self.producto else '(producto eliminado)')
        combinacion = f' [{self.combinacion_descripcion}]' if self.combinacion_descripcion else ''
        return f'{nombre}{combinacion} x{self.cantidad}'

    def save(self, *args, **kwargs):
        """Solo al crear: captura snapshots de producto, cliente y combinación."""
        if not self.pk:
            if self.producto and not self.producto_nombre:
                self.producto_nombre = self.producto.nombre or ''
                self.producto_codigo = self.producto.codigo or ''
            if self.cliente and not self.cliente_nombre:
                self.cliente_nombre = self.cliente.nombre or self.cliente.razon_social or ''
            if self.combinacion and not self.combinacion_descripcion:
                self.combinacion_descripcion = self.combinacion.descripcion_legible() or ''
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        base = self.cantidad * self.precio_unitario
        if self.descuento_pct:
            base = base * (1 - self.descuento_pct / 100)
        return round(base, 2)

    @property
    def nombre_producto_display(self):
        if self.producto:
            return str(self.producto)
        if self.producto_nombre:
            codigo = f'[{self.producto_codigo}] ' if self.producto_codigo else ''
            return f'{codigo}{self.producto_nombre} (eliminado)'
        return '(producto eliminado)'

    @property
    def nombre_cliente_display(self):
        if self.cliente:
            return self.cliente.nombre or self.cliente.razon_social or str(self.cliente)
        if self.cliente_nombre:
            return f'{self.cliente_nombre} (eliminado)'
        return '(sin cliente)'

    @property
    def nombre_combinacion_display(self):
        if self.combinacion:
            return self.combinacion.descripcion_legible()
        if self.combinacion_descripcion:
            return f'{self.combinacion_descripcion} (eliminado)'
        return ''


# ══════════════════════════════════════════════════════════════════
#  PAGO DE VENTA — soporta pago dividido (ej: mitad efectivo, mitad transferencia)
# ══════════════════════════════════════════════════════════════════

class PagoVenta(models.Model):
    """
    Una línea de pago de una venta. Una venta puede tener varias
    líneas (pago dividido entre distintos medios). La suma de
    montos de todas las líneas debe igualar venta.total al confirmar.
    """
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='pagos')
    medio = models.CharField(max_length=20, choices=MedioPago.choices, default=MedioPago.EFECTIVO)
    monto = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        verbose_name        = 'Pago de venta'
        verbose_name_plural = 'Pagos de venta'
        ordering            = ['id']

    def __str__(self):
        return f'{self.venta.numero} — {self.get_medio_display()}: {self.monto}'


# ══════════════════════════════════════════════════════════════════
#  DOCUMENTOS / ADJUNTOS DE VENTA
# ══════════════════════════════════════════════════════════════════

import os as _os

def _venta_doc_path(instance, filename):
    numero = instance.venta.numero or f'tmp-{instance.venta.pk}'
    nombre_limpio = _os.path.basename(filename)
    return f'ventas/{numero}/{nombre_limpio}'


class VentaDocumento(models.Model):

    TIPOS = [
        ('factura', 'Factura'),
        ('remito',  'Remito'),
        ('recibo',  'Recibo'),
        ('otro',    'Otro'),
    ]

    venta       = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='documentos')
    archivo     = models.FileField(upload_to=_venta_doc_path)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='otro')
    descripcion = models.CharField(max_length=200, blank=True)
    subido_el   = models.DateTimeField(auto_now_add=True)
    subido_por  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                      null=True, blank=True, related_name='+')

    class Meta:
        verbose_name        = 'Documento de venta'
        verbose_name_plural = 'Documentos de venta'
        ordering            = ['subido_el']

    def __str__(self):
        return f'{self.venta.numero} — {self.get_tipo_display()} — {_os.path.basename(self.archivo.name)}'

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

def _generar_numero_venta():
    ultimo = Venta.objects.order_by('-id').first()
    if not ultimo or not ultimo.numero:
        numero = 1
    else:
        try:
            numero = int(ultimo.numero.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = Venta.objects.count() + 1
    return f'VTA-{numero:05d}'