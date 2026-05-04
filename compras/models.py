from django.db import models
from django.conf import settings
from django.db import transaction

from productos.models import Producto, Proveedor, Moneda, CondicionPago


# ══════════════════════════════════════════════════════════════════
#  CHOICES
# ══════════════════════════════════════════════════════════════════

class EstadoCompra(models.TextChoices):
    BORRADOR   = 'borrador',   'Borrador'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


# ══════════════════════════════════════════════════════════════════
#  COMPRA  (cabecera)
# ══════════════════════════════════════════════════════════════════

class Compra(models.Model):
    """
    Cabecera de una orden de compra.
    Cada ítem tiene su propio proveedor, por eso el proveedor
    vive en ItemCompra, no aquí.
    """

    numero         = models.CharField(max_length=20, unique=True, blank=True,
                         help_text='Se genera automáticamente: CMP-00001')
    fecha          = models.DateField()
    estado         = models.CharField(max_length=20, choices=EstadoCompra.choices,
                         default=EstadoCompra.BORRADOR)

    # — Totales (calculados al confirmar) —
    total          = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # — Notas —
    notas          = models.TextField(blank=True)

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

    # ── Métodos de negocio ───────────────────────────────────────

    def calcular_total(self):
        """Recalcula el total sumando todos los ítems."""
        self.total = sum(item.subtotal for item in self.items.all())
        self.save(update_fields=['total'])

    @transaction.atomic
    def confirmar(self):
        """
        Confirma la compra:
          1. Actualiza stock_actual de cada producto.
          2. Marca la compra como CONFIRMADA.
        """
        if self.estado != EstadoCompra.BORRADOR:
            raise ValueError('Solo se pueden confirmar compras en estado Borrador.')

        for item in self.items.select_related('producto'):
            producto = item.producto
            if producto.gestiona_stock:
                producto.stock_actual += item.cantidad
                producto.save(update_fields=['stock_actual'])

        self.calcular_total()
        self.estado = EstadoCompra.CONFIRMADA
        self.save(update_fields=['estado', 'total'])

    @transaction.atomic
    def anular(self):
        """
        Anula la compra y revierte el stock si estaba confirmada.
        """
        if self.estado == EstadoCompra.ANULADA:
            raise ValueError('La compra ya está anulada.')

        if self.estado == EstadoCompra.CONFIRMADA:
            for item in self.items.select_related('producto'):
                producto = item.producto
                if producto.gestiona_stock:
                    producto.stock_actual -= item.cantidad
                    producto.save(update_fields=['stock_actual'])

        self.estado = EstadoCompra.ANULADA
        self.save(update_fields=['estado'])


# ══════════════════════════════════════════════════════════════════
#  ÍTEM DE COMPRA  (línea del carrito)
# ══════════════════════════════════════════════════════════════════

class ItemCompra(models.Model):
    """
    Una línea dentro de una Compra.
    Cada ítem tiene su propio proveedor y condiciones comerciales.
    """

    compra     = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name='items')
    producto   = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='items_compra')
    proveedor  = models.ForeignKey(Proveedor, on_delete=models.SET_NULL,
                     null=True, blank=True, related_name='items_compra')

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
        return f'{self.producto} x{self.cantidad}'

    @property
    def subtotal(self):
        """Subtotal aplicando descuento."""
        base = self.cantidad * self.costo_unitario
        if self.descuento_pct:
            base = base * (1 - self.descuento_pct / 100)
        return round(base, 2)


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