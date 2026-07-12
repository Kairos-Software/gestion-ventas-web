from datetime import date
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from productos.models import Producto, Proveedor, Moneda, CondicionPago, CombinacionVariante


# ══════════════════════════════════════════════════════════════════
#  CHOICES
# ══════════════════════════════════════════════════════════════════

class EstadoCompra(models.TextChoices):
    BORRADOR   = 'borrador',   'Borrador'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


class MedioPagoCompra(models.TextChoices):
    """
    CREDITO ('crédito con tarjeta') no impacta caja al confirmar la
    compra: genera una Deuda con cuotas (ver caja.models.Deuda) que
    se van confirmando y debitando una por una. El resto de los
    medios sigue impactando caja grande de inmediato, como siempre.
    """
    EFECTIVO      = 'efectivo',      'Efectivo'
    TRANSFERENCIA = 'transferencia', 'Transferencia'
    DEBITO        = 'debito',        'Débito'
    QR            = 'qr',            'QR'
    CREDITO       = 'credito',       'Crédito (tarjeta)'


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


def _resolver_pagos_compra(compra, pagos):
    """
    Valida y resuelve la cuenta real de cada línea de pago de una
    compra. Devuelve una lista de dicts [{'medio', 'monto', 'cuenta',
    'cuotas', 'interes_pct', 'fecha_inicio_debito'}] lista para crear
    PagoCompra (los últimos 3 campos son None salvo medio=CREDITO), o
    None si `pagos` es None (no se tocan los pagos existentes).

    Usado por Compra.confirmar() y Compra.editar_completa() — misma
    validación en los dos lugares donde se puede confirmar una compra.
    """
    if pagos is None:
        return None

    from caja.models import CuentaCaja, TipoCaja
    moneda_compra = compra.items.values_list('moneda', flat=True).first() or 'ARS'
    labels_medio = dict(MedioPagoCompra.choices)

    pagos_resueltos = []
    for p in pagos:
        monto = p.get('monto')
        if not monto or float(monto) <= 0:
            continue
        medio = p.get('medio', MedioPagoCompra.EFECTIVO)
        if medio not in MedioPagoCompra.values:
            raise ValueError(f'Medio de pago inválido: {medio}')

        es_credito = medio == MedioPagoCompra.CREDITO
        cuenta = CuentaCaja.objects.filter(
            pk=p.get('cuenta_pk'), caja=TipoCaja.GRANDE, activa=True,
            es_credito=es_credito, moneda=moneda_compra,
        ).first()
        if not cuenta:
            raise ValueError(
                f'Elegí una cuenta válida para el pago con '
                f'{labels_medio.get(medio, medio)}.'
            )

        cuotas = interes_pct = fecha_inicio_debito = None
        if es_credito:
            try:
                cuotas = int(p.get('cuotas', 0))
            except (TypeError, ValueError):
                cuotas = 0
            if cuotas < 1:
                raise ValueError('Indicá la cantidad de cuotas para el pago con crédito.')
            try:
                interes_pct = Decimal(str(p.get('interes_pct', 0) or 0))
            except Exception:
                raise ValueError('Porcentaje de interés inválido.')
            if interes_pct < 0:
                raise ValueError('El porcentaje de interés no puede ser negativo.')
            fecha_inicio_raw = p.get('fecha_inicio_debito')
            if not fecha_inicio_raw:
                raise ValueError('Indicá la fecha de inicio de débito de la tarjeta.')
            try:
                fecha_inicio_debito = date.fromisoformat(str(fecha_inicio_raw))
            except ValueError:
                raise ValueError('Fecha de inicio de débito inválida.')

        pagos_resueltos.append({
            'medio': medio, 'monto': monto, 'cuenta': cuenta,
            'cuotas': cuotas, 'interes_pct': interes_pct,
            'fecha_inicio_debito': fecha_inicio_debito,
        })

    return pagos_resueltos


def _guardar_pagos_compra(compra, pagos_resueltos):
    """
    Reemplaza las líneas de pago de una compra con las ya resueltas.
    Devuelve la lista de PagoCompra creados (mismo orden que
    pagos_resueltos) para poder linkear Deuda a la línea de crédito.
    """
    if pagos_resueltos is None:
        return None
    compra.pagos.all().delete()
    creados = []
    for p in pagos_resueltos:
        creados.append(PagoCompra.objects.create(
            compra = compra,
            medio  = p['medio'],
            monto  = p['monto'],
            cuenta = p['cuenta'],
        ))
    return creados


def _crear_deudas_desde_pagos(compra, pagos_resueltos, pagos_creados):
    """
    Para cada línea de pago con medio=CREDITO, crea la Deuda (con su
    plan de cuotas) vinculada a esa línea. Se llama después de
    _guardar_pagos_compra(), que ya devolvió los PagoCompra reales.
    """
    if not pagos_resueltos:
        return

    from caja.models import Deuda, TipoDeuda
    moneda_compra = compra.items.values_list('moneda', flat=True).first() or 'ARS'

    for p, pago_obj in zip(pagos_resueltos, pagos_creados):
        if p['medio'] != MedioPagoCompra.CREDITO:
            continue
        Deuda.crear_con_cuotas(
            tipo=TipoDeuda.COMPRA_CREDITO,
            pago_compra=pago_obj,
            cuenta_tarjeta=p['cuenta'],
            monto_original=p['monto'],
            porcentaje_interes=p['interes_pct'],
            cantidad_cuotas=p['cuotas'],
            fecha_inicio=p['fecha_inicio_debito'],
            moneda=moneda_compra,
            descripcion=f'Compra {compra.numero}',
            creado_por=compra.creado_por,
        )


def _anular_deudas_de_compra(compra):
    """
    Anula las Deudas activas vinculadas a las líneas de crédito de esta
    compra. Deuda.anular() ya bloquea si hay cuotas confirmadas — el
    ValueError se propaga tal cual, mismo criterio que el resto de las
    validaciones de este archivo (fail fast, antes de tocar stock).
    """
    from caja.models import Deuda, EstadoDeuda
    for deuda in Deuda.objects.filter(pago_compra__compra=compra, estado=EstadoDeuda.ACTIVA):
        deuda.anular()


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

    # — Medio de pago (principal — el detalle real vive en PagoCompra) —
    medio_pago = models.CharField(
        'Medio de pago',
        max_length=20,
        choices=MedioPagoCompra.choices,
        default=MedioPagoCompra.EFECTIVO,
        blank=True,
    )

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
            # Falla rápido: bloquea el borrado si hay cuotas ya confirmadas.
            _anular_deudas_de_compra(self)
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
    def confirmar(self, medio_pago=None, pagos=None):
        """
        Confirma la compra: suma stock (respetando variantes),
        crea lotes para trazabilidad de costos y vencimientos,
        y pasa a CONFIRMADA. Solo disponible desde BORRADOR.

        pagos: lista de dicts [{'medio': 'efectivo', 'monto': 3000},
               {'medio': 'transferencia', 'monto': 999.97, 'cuenta_pk': 5}, ...]
               Si se pasa, reemplaza cualquier PagoCompra previo.

               Todas las líneas (incluida efectivo) necesitan una
               cuenta real, activa, sin crédito y en la moneda de la
               compra — acá no hay turno que la resuelva más tarde
               como en Ventas, compras siempre impactó caja grande
               al confirmar.
        """
        if self.estado != EstadoCompra.BORRADOR:
            raise ValueError('Solo se pueden confirmar compras en estado Borrador.')

        # Resolver la cuenta real de cada línea de pago ANTES de tocar
        # stock/estado: si alguna es inválida, falla rápido.
        pagos_resueltos = _resolver_pagos_compra(self, pagos)

        for item in self.items.select_related('producto', 'combinacion'):
            _sumar_stock_item(item)
            # Crear lote para trazabilidad
            _crear_lote_desde_item(item, self.fecha)

        self.calcular_total()
        self.estado = EstadoCompra.CONFIRMADA
        if medio_pago is not None:
            self.medio_pago = medio_pago
        self.save(update_fields=['estado', 'total', 'medio_pago'])

        pagos_creados = _guardar_pagos_compra(self, pagos_resueltos)
        _crear_deudas_desde_pagos(self, pagos_resueltos, pagos_creados)

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

        # Falla rápido: si alguna cuota de una deuda por crédito ya fue
        # confirmada, no se puede anular la compra sin antes resolver esa deuda.
        _anular_deudas_de_compra(self)

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
    def editar_completa(self, fecha, notas, items_data, medio_pago=None, pagos=None):
        """
        Edita una compra ANULADA: reemplaza todos sus ítems y la re-confirma.

        Flujo:
          1. Valida que esté ANULADA (el stock ya fue revertido al anular).
          2. Borra los ítems viejos (y sus lotes asociados en cascada).
          3. Crea los ítems nuevos.
          4. Resuelve las cuentas de pago (ver Compra.confirmar), ya
             con la moneda de los ítems nuevos.
          5. Suma el stock de los nuevos ítems (respetando variantes).
          6. Crea lotes para los nuevos ítems.
          7. Recalcula el total.
          8. Pasa a CONFIRMADA.

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
                lista_descuento_nombre = d.get('lista_descuento_nombre', ''),
                condicion_pago = d.get('condicion_pago', 'contado'),
                referencia     = d.get('referencia', ''),
                notas          = d.get('notas', ''),
                fecha_vencimiento = d.get('fecha_vencimiento'),
            )

        # Resolver cuentas de pago con la moneda de los ítems ya nuevos
        pagos_resueltos = _resolver_pagos_compra(self, pagos)

        # — Actualizar cabecera —
        self.fecha = fecha
        self.notas = notas
        if medio_pago is not None:
            self.medio_pago = medio_pago
        self.save(update_fields=['fecha', 'notas', 'medio_pago'])

        # — Sumar stock de los nuevos ítems y crear lotes —
        for item in self.items.select_related('producto', 'combinacion'):
            _sumar_stock_item(item)
            _crear_lote_desde_item(item, self.fecha)

        # — Recalcular total y confirmar —
        self.total  = sum(item.subtotal for item in self.items.all())
        self.estado = EstadoCompra.CONFIRMADA
        self.save(update_fields=['total', 'estado'])

        pagos_creados = _guardar_pagos_compra(self, pagos_resueltos)
        _crear_deudas_desde_pagos(self, pagos_resueltos, pagos_creados)

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
    lista_descuento_nombre = models.CharField(
        'Lista de descuento aplicada', max_length=100, blank=True,
        help_text='Nombre de la lista si el % vino de ahí (ver ListaDescuento); '
                   'vacío si se escribió el % a mano.',
    )

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
#  PAGO DE COMPRA — soporta pago dividido (ej: mitad efectivo, mitad
#  transferencia). Mismo patrón que ventas.PagoVenta.
# ══════════════════════════════════════════════════════════════════

class PagoCompra(models.Model):
    """
    Una línea de pago de una compra. Una compra puede tener varias
    líneas (pago dividido entre distintos medios). La suma de montos
    de todas las líneas debe igualar compra.total al confirmar.

    A diferencia de Ventas, acá no hay turno/caja diaria de por
    medio: TODA línea (incluido efectivo) impacta caja grande al
    confirmar, en su cuenta real — Compras siempre lo hizo así, esto
    solo agrega DE QUÉ cuenta sale la plata en vez de asumir Efectivo.

    `cuenta`: para medio=CREDITO apunta a la tarjeta (CuentaCaja con
    es_credito=True) usada, no a una cuenta real de caja — esa línea
    no impacta caja al confirmar, genera una Deuda con cuotas (ver
    `deuda` en el related_name de caja.models.Deuda.pago_compra) que
    van impactando de a una a medida que se confirman.
    """
    compra = models.ForeignKey(Compra, on_delete=models.CASCADE, related_name='pagos')
    medio  = models.CharField(max_length=20, choices=MedioPagoCompra.choices,
                 default=MedioPagoCompra.EFECTIVO)
    monto  = models.DecimalField(max_digits=14, decimal_places=2)
    cuenta = models.ForeignKey(
        'caja.CuentaCaja', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pagos_compra',
    )

    class Meta:
        verbose_name        = 'Pago de compra'
        verbose_name_plural = 'Pagos de compra'
        ordering            = ['id']

    def __str__(self):
        return f'{self.compra.numero} — {self.get_medio_display()}: {self.monto}'


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
    # Nulo cuando el lote se generó desde un ajuste manual de stock
    # (ver productos/views_stock.py) en vez de una Compra real: no
    # pasó por compras, así que no hay ítem de compra al que atarlo.
    item_compra = models.ForeignKey(
        ItemCompra,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
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


# ══════════════════════════════════════════════════════════════════
#  PÉRDIDAS — control real de mermas (vencimiento, rotura, otro)
# ══════════════════════════════════════════════════════════════════

class MotivoPerdida(models.TextChoices):
    VENCIMIENTO = 'vencimiento', 'Vencimiento'
    ROTURA      = 'rotura',      'Rotura / daño'
    OTRO        = 'otro',        'Otro'


class Perdida(models.Model):
    """
    Registro de una pérdida de stock, siempre atada a un lote puntual
    (así se sabe qué costo se perdió realmente, no solo "bajó el
    stock"). Dos orígenes:

    - Automática: al vencer un lote (ver procesar_lotes_vencidos,
      que se dispara solo al visitar Inventario).
    - Manual: rotura, extravío o cualquier otro motivo, registrada
      desde Inventario sobre un lote específico.

    Snapshots (lote_codigo, producto_nombre, costo_unitario): igual
    que ConsumoLoteVenta — si el lote o el producto se borran/
    desactivan más adelante, el historial de pérdidas no se rompe.
    """
    lote = models.ForeignKey(
        LoteCompra, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='perdidas',
    )
    lote_codigo_snapshot = models.CharField(max_length=20, blank=True)

    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='perdidas',
    )
    producto_nombre_snapshot = models.CharField(max_length=255, blank=True)
    combinacion = models.ForeignKey(
        CombinacionVariante, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='perdidas',
    )
    combinacion_desc_snapshot = models.CharField(max_length=300, blank=True)

    cantidad = models.PositiveIntegerField()
    costo_unitario_snapshot = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    motivo = models.CharField(max_length=20, choices=MotivoPerdida.choices)
    motivo_detalle = models.CharField(max_length=300, blank=True)
    automatica = models.BooleanField(
        default=False,
        help_text='True si la generó el sistema al vencer el lote; False si se registró a mano.',
    )

    fecha = models.DateField(help_text='Fecha en que se detectó/registró la pérdida.')
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='perdidas_registradas',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Pérdida'
        verbose_name_plural = 'Pérdidas'
        ordering            = ['-fecha', '-fecha_alta']

    def __str__(self):
        return f'{self.producto_nombre_snapshot} — {self.cantidad}u ({self.get_motivo_display()})'

    @property
    def costo_total(self):
        return self.cantidad * self.costo_unitario_snapshot


@transaction.atomic
def registrar_perdida(lote, cantidad, motivo, motivo_detalle='', usuario=None,
                       automatica=False, fecha=None):
    """
    Da de baja `cantidad` unidades de `lote` por pérdida y deja
    registro en Perdida. Mantiene todo sincronizado en el mismo lugar:
    lote.cantidad_actual, Producto/CombinacionVariante.stock_actual, y
    un MovimientoStock (tipo=MERMA) para que quede también en el
    historial de stock que ya existe en Productos.
    """
    cantidad = int(cantidad)
    if cantidad <= 0:
        raise ValueError('La cantidad debe ser mayor a 0.')
    if cantidad > lote.cantidad_actual:
        raise ValueError(
            f'El lote {lote.codigo} solo tiene {lote.cantidad_actual} unidad(es) disponibles.'
        )
    if motivo not in MotivoPerdida.values:
        raise ValueError(f'Motivo de pérdida inválido: {motivo}')

    from productos.models import MovimientoStock, TipoMovimiento

    lote.descontar_stock(cantidad)

    producto    = lote.producto
    combinacion = lote.combinacion

    if producto is not None:
        mov = MovimientoStock(
            producto = producto,
            tipo     = TipoMovimiento.MERMA,
            cantidad = cantidad,
            motivo   = motivo_detalle or dict(MotivoPerdida.choices).get(motivo, motivo),
            usuario  = usuario,
        )
        mov.save()  # ajusta Producto.stock_actual internamente

        if combinacion is not None:
            combinacion.stock_actual -= cantidad
            combinacion.save(update_fields=['stock_actual'])
            producto.sincronizar_stock_desde_combinaciones()

    return Perdida.objects.create(
        lote                       = lote,
        lote_codigo_snapshot       = lote.codigo,
        producto                   = producto,
        producto_nombre_snapshot   = producto.nombre if producto else '',
        combinacion                = combinacion,
        combinacion_desc_snapshot  = combinacion.descripcion_legible() if combinacion else '',
        cantidad                   = cantidad,
        costo_unitario_snapshot    = lote.costo_unitario,
        motivo                     = motivo,
        motivo_detalle             = motivo_detalle,
        automatica                 = automatica,
        fecha                      = fecha or timezone.now().date(),
        registrado_por             = usuario,
    )


def procesar_lotes_vencidos():
    """
    Recorre lotes activos con stock cuya fecha_vencimiento ya pasó y
    los da de baja automáticamente como pérdida por vencimiento, por
    el total que les quedaba.

    No hay un scheduler corriendo dentro de Django, así que esto se
    llama "perezosamente" cada vez que se visita Inventario (ver
    views_inventario.py) — igual que asegurar_cuentas_efectivo() en
    caja/models.py. Si hace falta precisión real (que se procese
    aunque nadie abra la pantalla ese día), este mismo trabajo está
    expuesto como comando: `manage.py procesar_lotes_vencidos`, para
    programarlo con el Task Scheduler de Windows.
    """
    hoy = timezone.now().date()
    vencidos = LoteCompra.objects.filter(
        activo=True, cantidad_actual__gt=0, fecha_vencimiento__lt=hoy,
    )
    return [
        registrar_perdida(
            lote            = lote,
            cantidad        = lote.cantidad_actual,
            motivo          = MotivoPerdida.VENCIMIENTO,
            motivo_detalle  = 'Vencimiento automático',
            usuario         = None,
            automatica      = True,
            fecha           = hoy,
        )
        for lote in vencidos
    ]