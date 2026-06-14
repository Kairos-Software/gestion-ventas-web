from django.db import models
from django.conf import settings
from django.db import transaction

from productos.models import Producto, Moneda, CondicionPago, ProductoColor
from core.models import Cliente


# ══════════════════════════════════════════════════════════════════
#  CHOICES
# ══════════════════════════════════════════════════════════════════

class EstadoVenta(models.TextChoices):
    BORRADOR   = 'borrador',   'Borrador'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


class MedioPago(models.TextChoices):
    EFECTIVO     = 'efectivo',     'Efectivo'
    TRANSFERENCIA = 'transferencia', 'Transferencia'
    DEBITO       = 'debito',       'Débito'
    CREDITO      = 'credito',      'Crédito'
    QR           = 'qr',           'QR'


# ══════════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _restar_stock_item(item):
    """
    Resta el stock correspondiente a un ítem al confirmar una venta.
    - Si el producto gestiona variantes de color Y el ítem tiene un color
      asignado: resta en ProductoColor y sincroniza el total del producto.
    - Si no: resta directamente en Producto.stock_actual.
    """
    producto = item.producto
    if producto is None or not producto.gestiona_stock:
        return

    if producto.tiene_variantes_color and item.color is not None:
        color = item.color
        color.stock_actual -= item.cantidad
        color.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_colores()
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

    if producto.tiene_variantes_color and item.color is not None:
        color = item.color
        color.stock_actual += item.cantidad
        color.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_colores()
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
        ANULADA ──reactivar───→ BORRADOR    (sin tocar stock)
        BORRADOR ──confirmar──→ CONFIRMADA  (re-confirma)

    Eliminar:
        CONFIRMADA → revierte stock + borra
        ANULADA    → borra directo (stock ya revertido al anular)

    Medio de pago:
        Se registra al confirmar. Puede ser mixto (varios métodos),
        pero para esta etapa es un único campo en la cabecera.
        Cuando se implemente la caja, cada VentaPago sumará al turno activo.
    """

    numero = models.CharField(max_length=20, unique=True, blank=True,
                 help_text='Se genera automáticamente: VTA-00001')
    fecha  = models.DateField()
    estado = models.CharField(max_length=20, choices=EstadoVenta.choices,
                 default=EstadoVenta.BORRADOR)

    # — Medio de pago —
    # Se completa al confirmar la venta. blank=True para que el borrador
    # pueda existir sin medio de pago aún definido.
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

    # — Auditoría —
    # creado_por: quien creó el borrador (puede ser distinto al que confirmó)
    # confirmado_por: quien apretó "Confirmar venta" — es el dato relevante
    #                 para el control de caja y turnos.
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ventas_creadas',
    )
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ventas_confirmadas',
        verbose_name='Confirmado por',
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
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
                for item in self.items.select_related('producto', 'color'):
                    _sumar_stock_item(item)
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
    def confirmar(self, confirmado_por=None, medio_pago=None):
        """
        Confirma la venta: resta stock y pasa a CONFIRMADA.
        Registra quién confirmó y el medio de pago.
        Solo disponible desde BORRADOR.
        """
        if self.estado != EstadoVenta.BORRADOR:
            raise ValueError('Solo se pueden confirmar ventas en estado Borrador.')

        for item in self.items.select_related('producto', 'color'):
            _restar_stock_item(item)

        self.calcular_total()
        self.estado = EstadoVenta.CONFIRMADA

        if confirmado_por is not None:
            self.confirmado_por = confirmado_por
        if medio_pago is not None:
            self.medio_pago = medio_pago

        self.save(update_fields=['estado', 'total', 'confirmado_por', 'medio_pago'])

    @transaction.atomic
    def anular(self):
        """Anula la venta y revierte el stock. Solo desde CONFIRMADA."""
        if self.estado == EstadoVenta.ANULADA:
            raise ValueError('La venta ya está anulada.')
        if self.estado == EstadoVenta.BORRADOR:
            raise ValueError('Las ventas en borrador no se anulan — simplemente no se confirman.')

        for item in self.items.select_related('producto', 'color'):
            _sumar_stock_item(item)

        self.estado = EstadoVenta.ANULADA
        self.save(update_fields=['estado'])

    @transaction.atomic
    def reactivar(self):
        """Reactiva una venta ANULADA devolviéndola a BORRADOR."""
        if self.estado != EstadoVenta.ANULADA:
            raise ValueError('Solo se pueden reactivar ventas anuladas.')

        self.estado = EstadoVenta.BORRADOR
        self.save(update_fields=['estado'])

    @transaction.atomic
    def editar_completa(self, fecha, notas='', items_data=None):
        """
        Edita una venta ANULADA: reemplaza sus ítems y la re-confirma.
        El medio_pago y confirmado_por NO se tocan aquí — se pasan
        por separado desde la view si es necesario.
        """
        if self.estado != EstadoVenta.ANULADA:
            raise ValueError('Solo se pueden editar ventas anuladas.')

        self.items.all().delete()

        for d in (items_data or []):
            ItemVenta.objects.create(
                venta           = self,
                producto        = d['producto'],
                cliente         = d.get('cliente'),
                color           = d.get('color'),
                cantidad        = d['cantidad'],
                precio_unitario = d['precio_unitario'],
                moneda          = d.get('moneda', 'ARS'),
                descuento_pct   = d.get('descuento_pct', 0),
                condicion_pago  = d.get('condicion_pago', 'contado'),
                referencia      = d.get('referencia', ''),
                notas           = d.get('notas', ''),
            )

        self.fecha = fecha
        self.notas = notas
        self.estado = EstadoVenta.BORRADOR
        self.save(update_fields=['fecha', 'notas', 'estado'])

        self.confirmar()


# ══════════════════════════════════════════════════════════════════
#  ÍTEM DE VENTA
# ══════════════════════════════════════════════════════════════════

class ItemVenta(models.Model):
    """
    Línea de una venta. Un ítem = un producto (+ color opcional) + cantidad + precio.

    Snapshots: producto_nombre, producto_codigo, cliente_nombre y color_nombre
    se autocompletan al crear el ítem y nunca se modifican.
    """

    venta    = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='items')

    producto = models.ForeignKey(
                   Producto, on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='items_venta')

    cliente  = models.ForeignKey(
                   Cliente, on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='items_venta')

    # ── Variante de color (opcional) ─────────────────────────────
    color    = models.ForeignKey(
                   ProductoColor, on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='items_venta',
                   verbose_name='Color / variante')

    # ── Snapshots ────────────────────────────────────────────────
    producto_nombre = models.CharField(max_length=255, blank=True)
    producto_codigo = models.CharField(max_length=50,  blank=True)
    cliente_nombre  = models.CharField(max_length=200, blank=True)
    color_nombre    = models.CharField(max_length=50,  blank=True)

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
        color  = f' [{self.color_nombre}]' if self.color_nombre else ''
        return f'{nombre}{color} x{self.cantidad}'

    def save(self, *args, **kwargs):
        """Solo al crear: captura snapshots de producto, cliente y color."""
        if not self.pk:
            if self.producto and not self.producto_nombre:
                self.producto_nombre = self.producto.nombre or ''
                self.producto_codigo = self.producto.codigo or ''
            if self.cliente and not self.cliente_nombre:
                self.cliente_nombre = self.cliente.nombre or self.cliente.razon_social or ''
            if self.color and not self.color_nombre:
                self.color_nombre = self.color.nombre or ''
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
    def nombre_color_display(self):
        if self.color:
            return self.color.nombre
        if self.color_nombre:
            return f'{self.color_nombre} (eliminado)'
        return ''


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