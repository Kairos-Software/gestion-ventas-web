from decimal import Decimal

from django.conf import settings
from django.db import models, transaction

from productos.models import Producto, CombinacionVariante, cantidad_valida_para_unidad
from core.models import Cliente


def _generar_numero_presupuesto():
    """Mismo patrón que Venta._generar_numero_venta(): PRE-00001, PRE-00002..."""
    ultimo = Presupuesto.objects.order_by('-id').first()
    if not ultimo or not ultimo.numero:
        numero = 1
    else:
        try:
            numero = int(ultimo.numero.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = Presupuesto.objects.count() + 1
    return f'PRE-{numero:05d}'


class Presupuesto(models.Model):
    """
    Cotización informal para un cliente (típicamente uno que revende y
    quiere saber cuánto le costaría llevar cierta cantidad de varios
    productos a precio mayorista). NUNCA toca stock ni caja — es puro
    texto/números para imprimir y entregar. No tiene vencimiento (solo
    fecha de emisión) ni valor fiscal.

    Sí se puede editar (ver actualizar_presupuesto()) — a diferencia de
    Devolución/Pérdida, acá no hay ningún movimiento de stock/caja que
    revertir, así que reemplazar los ítems de uno ya guardado es
    seguro: solo se pisan filas de texto/números.
    """
    numero = models.CharField(max_length=20, unique=True, blank=True,
                 help_text='Se genera automáticamente: PRE-00001')
    fecha = models.DateField(help_text='Fecha de emisión del presupuesto.')

    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True,
                 related_name='presupuestos')
    cliente_nombre = models.CharField('Cliente', max_length=200, blank=True,
                 help_text='Snapshot del nombre del cliente elegido, o un nombre libre '
                            'si todavía no está registrado como Cliente (ej. un posible '
                            'revendedor nuevo que solo está averiguando precios).')

    notas = models.TextField(blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                 null=True, blank=True, related_name='presupuestos_creados')
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_alta']

    def __str__(self):
        return self.numero

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = _generar_numero_presupuesto()
        super().save(*args, **kwargs)

    def calcular_total(self):
        total = sum((item.subtotal for item in self.items.all()), Decimal('0'))
        self.total = round(total, 2)
        self.save(update_fields=['total'])


class ItemPresupuesto(models.Model):
    presupuesto = models.ForeignKey(Presupuesto, on_delete=models.CASCADE, related_name='items')

    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True,
                 related_name='items_presupuesto')
    combinacion = models.ForeignKey(CombinacionVariante, on_delete=models.SET_NULL, null=True, blank=True,
                 related_name='items_presupuesto')
    producto_nombre = models.CharField(max_length=255, blank=True)
    combinacion_descripcion = models.CharField(max_length=300, blank=True)

    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField('Precio unitario', max_digits=12, decimal_places=2)
    descuento_pct = models.DecimalField('Descuento (%)', max_digits=8, decimal_places=4, default=0)
    lista_descuento_nombre = models.CharField('Lista de descuento aplicada', max_length=100, blank=True)

    stock_al_emitir = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True,
                 help_text='Stock disponible visto al momento de armar el presupuesto '
                            '(solo informativo — no se reserva ni se descuenta nada).')

    class Meta:
        ordering = ['id']

    def save(self, *args, **kwargs):
        if not self.pk:
            if self.producto_id and not self.producto_nombre:
                self.producto_nombre = self.producto.nombre
            if self.combinacion_id and not self.combinacion_descripcion:
                self.combinacion_descripcion = self.combinacion.descripcion_legible()
        super().save(*args, **kwargs)

    @property
    def nombre_producto_display(self):
        return self.producto_nombre or (self.producto.nombre if self.producto_id else '(producto eliminado)')

    @property
    def subtotal(self):
        base = self.cantidad * self.precio_unitario
        if self.descuento_pct:
            base = base * (1 - self.descuento_pct / 100)
        return round(base, 2)


def _validar_items(items_data):
    """items_data: [{'producto': Producto, 'combinacion': CombinacionVariante|None,
                     'cantidad': Decimal, 'precio_unitario': Decimal,
                     'descuento_pct': Decimal, 'lista_descuento_nombre': str,
                     'stock_al_emitir': Decimal|None}, ...]"""
    if not items_data:
        raise ValueError('El presupuesto necesita al menos un ítem.')

    for idx, data in enumerate(items_data, start=1):
        producto = data.get('producto')
        if not producto:
            raise ValueError(f'Ítem {idx}: falta el producto.')
        cantidad = data.get('cantidad')
        if not cantidad or cantidad <= 0:
            raise ValueError(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
        if not cantidad_valida_para_unidad(producto.unidad_medida, cantidad):
            raise ValueError(
                f'Ítem {idx}: "{producto.nombre}" se vende por {producto.get_unidad_medida_display()} '
                f'— la cantidad tiene que ser un número entero.'
            )
        if data.get('precio_unitario') is None or data['precio_unitario'] < 0:
            raise ValueError(f'Ítem {idx}: el precio no puede ser negativo.')


def _crear_items(presupuesto, items_data):
    for data in items_data:
        ItemPresupuesto.objects.create(
            presupuesto=presupuesto,
            producto=data['producto'],
            combinacion=data.get('combinacion'),
            cantidad=data['cantidad'],
            precio_unitario=data['precio_unitario'],
            descuento_pct=data.get('descuento_pct') or 0,
            lista_descuento_nombre=data.get('lista_descuento_nombre', ''),
            stock_al_emitir=data.get('stock_al_emitir'),
        )


@transaction.atomic
def crear_presupuesto(fecha, items_data, cliente=None, cliente_nombre='', notas='', usuario=None):
    """Todo o nada: si algún ítem falla la validación no se crea nada.
    No toca stock ni caja en ningún punto."""
    _validar_items(items_data)
    presupuesto = Presupuesto.objects.create(
        fecha=fecha, cliente=cliente, cliente_nombre=cliente_nombre,
        notas=notas, creado_por=usuario,
    )
    _crear_items(presupuesto, items_data)
    presupuesto.calcular_total()
    return presupuesto


@transaction.atomic
def actualizar_presupuesto(presupuesto, items_data, cliente=None, cliente_nombre='', notas=None):
    """Reemplaza por completo los ítems de un presupuesto ya guardado
    (mismo patrón "borrar todo y recrear" que ActualizarBorradorAjax en
    ventas). La fecha de emisión original NO se toca — editar corrige
    una línea, no vuelve a emitir el documento."""
    _validar_items(items_data)
    presupuesto.items.all().delete()
    presupuesto.cliente = cliente
    presupuesto.cliente_nombre = cliente_nombre
    if notas is not None:
        presupuesto.notas = notas
    presupuesto.save()
    _crear_items(presupuesto, items_data)
    presupuesto.calcular_total()
    return presupuesto
