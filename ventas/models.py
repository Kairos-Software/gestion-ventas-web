from datetime import date, timedelta
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from productos.models import Producto, Moneda, CondicionPago, CombinacionVariante, AlicuotaIVA
from core.models import Cliente, AmbienteArca
from compras.models import LoteCompra


# ══════════════════════════════════════════════════════════════════
#  CHOICES
# ══════════════════════════════════════════════════════════════════

class EstadoVenta(models.TextChoices):
    BORRADOR   = 'borrador',   'Borrador'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


class MedioPago(models.TextChoices):
    """
    CUOTAS ('venta financiada por el propio comercio') no impacta caja
    al confirmar la venta: genera una CuentaPorCobrar con cuotas (ver
    caja.models.CuentaPorCobrar) que se van confirmando y acreditando
    una por una a medida que el cliente paga. Requiere que la venta
    tenga un cliente vinculado (ver Venta.cliente_unico) — no se le
    puede vender en cuotas a un Consumidor Final anónimo. El resto de
    los medios sigue impactando caja grande de inmediato, como siempre.
    """
    EFECTIVO      = 'efectivo',      'Efectivo'
    TRANSFERENCIA = 'transferencia', 'Transferencia'
    DEBITO        = 'debito',        'Débito'
    CREDITO       = 'credito',       'Crédito'
    QR            = 'qr',            'QR'
    CUOTAS        = 'cuotas',        'Cuotas'
    CHEQUE        = 'cheque',        'Cheque'


class TipoResolucionLote(models.TextChoices):
    """
    Cómo se determinó de qué lote sale el stock de un ítem.

    NORMAL           → se escaneó/buscó el producto por su código habitual.
                        El lote se resuelve recién al CONFIRMAR la venta,
                        tomando el lote activo con stock más VIEJO (FIFO)
                        (igual que un sistema sin trazabilidad de lotes,
                        pero dejando registro de cuál se usó).
    LOTE_ESPECIFICO  → se escaneó el código de lote (LT-AAAA-XXXXX) que
                        genera/muestra el módulo de inventario. El lote
                        queda fijado desde que se agrega el ítem al carrito.
    """
    NORMAL          = 'normal',          'Código normal (último lote disponible)'
    LOTE_ESPECIFICO = 'lote_especifico', 'Código de lote específico'


# ══════════════════════════════════════════════════════════════════
#  HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _lotes_candidatos(producto, combinacion):
    """
    Lotes activos con stock para un producto/combinación, en el orden
    en que se deben descontar al vender:

    - Producto perecedero: FEFO — primero el que vence antes (First
      Expired, First Out), para no perder mercadería por vencimiento.
      Los lotes sin fecha de vencimiento cargada (ej: ajustes manuales
      de stock, que no tienen esa información) quedan al final.
    - Producto no perecedero: FIFO — primero el más viejo por fecha
      de compra, como antes.
    """
    # select_for_update: bloquea las filas de lote elegidas hasta que la
    # transacción de la venta termine, para que dos ventas concurrentes
    # sobre el mismo lote no lean el mismo cantidad_actual y descuenten
    # las dos de más (lost update / sobreventa).
    qs = LoteCompra.objects.select_for_update().filter(activo=True, cantidad_actual__gt=0, producto=producto)
    qs = qs.filter(combinacion=combinacion) if combinacion is not None else qs.filter(combinacion__isnull=True)
    if producto.es_perecedero:
        return list(qs.order_by(F('fecha_vencimiento').asc(nulls_last=True), 'fecha_compra', 'fecha_alta'))
    return list(qs.order_by('fecha_compra', 'fecha_alta'))


def _resolver_y_consumir_lotes(item, producto=None, combinacion=None, cantidad=None, nombre_desc=None):
    """
    Determina de qué lote(s) sale el descuento y los consume. Por
    default opera sobre `item.producto`/`item.combinacion`/
    `item.cantidad` (el caso normal) — pero un paquete necesita
    descontar de VARIOS productos distintos con el mismo ItemVenta
    como destino de los ConsumoLoteVenta, así que estos tres se pueden
    pisar explícitamente (ver _descontar_stock_paquete).

    - tipo_escaneo NORMAL: arranca por el lote activo más VIEJO (FIFO).
    - tipo_escaneo LOTE_ESPECIFICO: arranca por item.lote_escaneado
      (solo aplica al producto principal del item, nunca a componentes
      de un paquete).

    Si el lote elegido no alcanza para cubrir la cantidad pedida, completa
    automáticamente con el/los siguiente(s) lote(s) disponibles y agrega
    un aviso legible para mostrarle al vendedor.

    Devuelve (lista_de_ConsumoLoteVenta_creados, lista_de_avisos:str).
    Lanza ValueError si no hay stock suficiente en ningún lote.
    """
    es_llamada_normal = producto is None
    if es_llamada_normal:
        producto = item.producto
    if producto is None or not producto.gestiona_stock:
        return [], []

    combinacion = combinacion if combinacion is not None else (item.combinacion if es_llamada_normal else None)
    cantidad    = cantidad if cantidad is not None else item.cantidad

    if nombre_desc is None:
        nombre_desc = item.producto_nombre or (producto.nombre if producto else '')
        if item.combinacion_descripcion:
            nombre_desc = f'{nombre_desc} [{item.combinacion_descripcion}]'

    lotes = _lotes_candidatos(producto, combinacion)

    if es_llamada_normal and item.tipo_escaneo == TipoResolucionLote.LOTE_ESPECIFICO and item.lote_escaneado_id:
        prioritario = next((l for l in lotes if l.pk == item.lote_escaneado_id), None)
        if prioritario is None:
            lp = LoteCompra.objects.filter(pk=item.lote_escaneado_id).first()
            codigo = lp.codigo if lp else '(lote eliminado)'
            raise ValueError(
                f'El lote {codigo} escaneado para "{nombre_desc}" ya no tiene stock disponible. '
                f'Volvé a escanear un código de lote válido.'
            )
        lotes = [prioritario] + [l for l in lotes if l.pk != prioritario.pk]

    if not lotes:
        raise ValueError(f'No hay lotes con stock disponible para "{nombre_desc}".')

    restante   = cantidad
    consumos   = []
    avisos     = []
    es_primero = True

    for lote in lotes:
        if restante <= 0:
            break
        disponible = lote.cantidad_actual
        if disponible <= 0:
            continue

        tomar = min(restante, disponible)

        if es_primero and tomar < restante:
            avisos.append(
                f'"{nombre_desc}": el lote {lote.codigo} solo tenía {disponible} unidad(es) disponibles; '
                f'se completó la cantidad descontando del siguiente lote.'
            )
        es_primero = False

        lote.descontar_stock(tomar)
        # Un lote sin Compra real detrás (item_compra=None — nace de un
        # ajuste manual de stock, ver StockAjusteAjax) siempre tiene
        # costo_unitario=$0: no hay ninguna compra que lo respalde. Si el
        # producto tiene un costo de referencia cargado a mano
        # (Producto.costo, para stock migrado que ya se pagó antes de usar
        # el sistema), la ganancia real de esta venta se calcula con ESE
        # costo en vez de $0 — sino cualquier venta de stock migrado se
        # vería como 100% de ganancia en los reportes.
        costo_unitario_venta = lote.costo_unitario
        if lote.item_compra_id is None and producto.costo is not None:
            costo_unitario_venta = producto.costo
        consumos.append(ConsumoLoteVenta.objects.create(
            item_venta              = item,
            lote                    = lote,
            cantidad                = tomar,
            lote_codigo_snapshot    = lote.codigo,
            costo_unitario_snapshot = costo_unitario_venta,
        ))
        restante -= tomar

    if restante > 0:
        raise ValueError(
            f'Stock insuficiente en todos los lotes disponibles para "{nombre_desc}". '
            f'Faltan {restante} unidad(es) para completar la venta.'
        )

    return consumos, avisos


def _descontar_stock_directo(producto, combinacion, cantidad, nombre_desc):
    """
    Resta `cantidad` del stock cacheado de producto/combinación (después
    de ya haber consumido los lotes), respetando permite_stock_negativo.

    Vuelve a leer la fila con select_for_update() antes de restar: los
    objetos `producto`/`combinacion` recibidos pueden venir de una
    lectura hecha antes de tomar el lock (ej: select_related al armar
    la venta), y si dos ventas descuentan el mismo producto a la vez,
    ambas verían el mismo stock_actual "viejo" y una de las dos
    resta se perdería (lost update) sin este refresh bloqueado.
    """
    if producto.gestiona_variantes and combinacion is not None:
        combinacion = CombinacionVariante.objects.select_for_update().get(pk=combinacion.pk)
        nuevo_stock = combinacion.stock_actual - cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para "{nombre_desc}": {nuevo_stock}')
        combinacion.stock_actual = nuevo_stock
        combinacion.save(update_fields=['stock_actual'])
        producto.sincronizar_stock_desde_combinaciones()
    else:
        producto = Producto.objects.select_for_update().get(pk=producto.pk)
        nuevo_stock = producto.stock_actual - cantidad
        if nuevo_stock < 0 and not producto.permite_stock_negativo:
            raise ValueError(f'Stock resultaría negativo para "{nombre_desc}": {nuevo_stock}')
        producto.stock_actual = nuevo_stock
        producto.save(update_fields=['stock_actual'])


def _descontar_stock_paquete(item):
    """
    Un paquete (Producto.es_paquete=True) no tiene lotes propios: al
    venderlo, se descuenta en el momento de los lotes reales de cada
    componente (mismo FIFO/FEFO de siempre — ver PaqueteComponente en
    productos/models.py). Todos los ConsumoLoteVenta quedan atados a
    ESTE ItemVenta (el del paquete, no uno por componente), así
    item.consumos ya muestra de dónde salió todo y
    _revertir_stock_venta_item funciona sin cambios adicionales.
    """
    consumos_totales, avisos_totales = [], []
    for comp in item.producto.componentes.select_related('producto', 'combinacion').all():
        comp_producto = comp.producto
        if not comp_producto.gestiona_stock:
            continue

        cantidad_necesaria = comp.cantidad * item.cantidad
        nombre_comp = comp.combinacion.descripcion_legible() if comp.combinacion_id else comp_producto.nombre
        nombre_desc = f'{nombre_comp} (componente de "{item.producto_nombre}")'

        consumos, avisos = _resolver_y_consumir_lotes(
            item, producto=comp_producto, combinacion=comp.combinacion,
            cantidad=cantidad_necesaria, nombre_desc=nombre_desc,
        )
        consumos_totales.extend(consumos)
        avisos_totales.extend(avisos)
        _descontar_stock_directo(comp_producto, comp.combinacion, cantidad_necesaria, nombre_desc)

    return consumos_totales, avisos_totales


def _descontar_stock_venta_item(item):
    """
    Descuenta stock al confirmar una venta: consume lote(s) existentes
    (no crea lotes nuevos, a diferencia de compras) y sincroniza
    stock_actual del producto/combinación. Devuelve (consumos, avisos).
    """
    producto = item.producto
    if producto is None:
        return [], []
    if producto.es_paquete:
        return _descontar_stock_paquete(item)
    if not producto.gestiona_stock:
        return [], []

    consumos, avisos = _resolver_y_consumir_lotes(item)
    nombre_desc = item.producto_nombre or producto.nombre
    _descontar_stock_directo(producto, item.combinacion, item.cantidad, nombre_desc)
    return consumos, avisos


def _revertir_stock_venta_item(item):
    """
    Revierte el descuento de stock al anular/eliminar una venta.
    Devuelve cada porción consumida a su lote de origen (usa el
    historial de ConsumoLoteVenta, así que funciona igual si el ítem
    se completó con más de un lote) y sincroniza el stock cacheado de
    CADA producto/combinación involucrado — no necesariamente el del
    item en sí: si era un paquete, los consumos vienen de varios
    productos componente distintos, cada lote ya sabe de cuál.
    """
    producto = item.producto
    if producto is None:
        return
    if not producto.es_paquete and not producto.gestiona_stock:
        return

    totales = {}  # (producto_id, combinacion_id) -> cantidad a devolver
    for consumo in item.consumos.select_related('lote'):
        if consumo.lote is None:
            continue
        consumo.lote.agregar_stock(consumo.cantidad)
        clave = (consumo.lote.producto_id, consumo.lote.combinacion_id)
        totales[clave] = totales.get(clave, 0) + consumo.cantidad

    for (producto_id, combinacion_id), cantidad in totales.items():
        if producto_id is None:
            continue
        if combinacion_id is not None:
            combinacion = CombinacionVariante.objects.select_for_update().filter(pk=combinacion_id).first()
            if combinacion is None:
                continue
            combinacion.stock_actual = combinacion.stock_actual + cantidad
            combinacion.save(update_fields=['stock_actual'])
            prod = Producto.objects.filter(pk=producto_id).first()
            if prod is not None:
                prod.sincronizar_stock_desde_combinaciones()
        else:
            prod = Producto.objects.select_for_update().filter(pk=producto_id).first()
            if prod is None:
                continue
            prod.stock_actual = prod.stock_actual + cantidad
            prod.save(update_fields=['stock_actual'])


def _anular_cuentas_por_cobrar_de_venta(venta):
    """
    Elimina las CuentaPorCobrar activas vinculadas a las líneas de cuotas
    de esta venta. CuentaPorCobrar.anular() ya bloquea si hay cuotas
    cobradas — el ValueError se propaga tal cual, mismo criterio que
    _anular_deudas_de_compra en compras/models.py (fail fast, antes de
    tocar stock). Una vez anulada, se borra del todo (CuentaPorCobrar.
    delete() ya limpia sus propios movimientos) en vez de dejarla como
    fantasma sin ninguna venta real detrás.
    """
    from caja.models import CuentaPorCobrar, EstadoDeuda
    for cxc in CuentaPorCobrar.objects.filter(pago_venta__venta=venta, estado=EstadoDeuda.ACTIVA):
        cxc.anular()
        cxc.delete(_permitir_con_origen=True)


def _anular_cheques_de_venta(venta):
    """
    Elimina los cheques PENDIENTES vinculados a las líneas de pago con
    cheque de esta venta. Si alguno ya está CONFIRMADO (depositado), no
    se puede anular la venta sin resolver eso antes — mismo criterio
    fail-fast que _anular_cuentas_por_cobrar_de_venta. Una vez anulado,
    se borra del todo en vez de dejarlo como fantasma.
    """
    from caja.models import Cheque, EstadoCheque
    for cheque in Cheque.objects.filter(pago_venta__venta=venta).exclude(estado=EstadoCheque.ANULADO):
        if cheque.estado == EstadoCheque.PENDIENTE:
            cheque.anular()
            cheque.delete(_permitir_con_origen=True)
        elif cheque.estado == EstadoCheque.CONFIRMADO:
            raise ValueError(
                f'El cheque {cheque.numero_cheque or "s/n"} de esta venta ya está confirmado '
                f'(depositado) — rechazalo desde Cheques antes de anular la venta.'
            )


def _bloquear_si_tiene_devoluciones(venta):
    """
    Falla rápido si esta venta tiene alguna DevolucionVenta registrada —
    ni anular() ni delete() saben de las devoluciones: revierten stock
    usando la cantidad ORIGINAL de cada ConsumoLoteVenta, así que si una
    porción ya se devolvió, sumarían stock de más al lote (doble conteo).
    No hay forma de "deshacer" una devolución hoy (mismo criterio que
    Perdida, tampoco anulable) — si hace falta corregir un error, se hace
    un ajuste de stock manual.
    """
    if venta.devoluciones.exists():
        raise ValueError(
            'Esta venta tiene devoluciones registradas — no se puede anular ni eliminar '
            '(el stock de los lotes ya se ajustó por esas devoluciones; anularla ahora '
            'sumaría stock de más). Si hace falta corregirla, hacé un ajuste de stock manual.'
        )


def _bloquear_si_tiene_comprobante_arca(venta):
    """
    Falla rápido si esta venta ya tiene un comprobante ARCA (CAE real,
    emitido de verdad ante AFIP) asociado. Ni anular() ni delete() saben
    nada de facturación electrónica — revertirían stock/caja acá adentro
    mientras ARCA sigue teniendo ese comprobante registrado como válido y
    vigente. El camino típico que esto evita: anular una venta facturada
    de 5 ítems, editarla a 3 y volver a confirmar — la Venta queda con el
    total nuevo pero el ComprobanteArca sigue siendo el de los 5 ítems
    originales (facturar_venta() ni siquiera pide un CAE nuevo, ver
    core/services_arca/facturacion.py), así que el sistema termina
    mostrando datos que ya no coinciden con lo declarado ante ARCA — y no
    hay forma de corregir un comprobante ya emitido desde acá, porque no
    existe todavía un mecanismo de Nota de Crédito.

    Si el cliente devolvió parte de la compra, el camino correcto es
    "Registrar devolución": no toca la Venta ni el ComprobanteArca
    original, así que la factura sigue coincidiendo exactamente con lo
    que ARCA tiene en su base.
    """
    comprobante = getattr(venta, 'comprobante_arca', None)
    if comprobante is not None:
        raise ValueError(
            f'Esta venta ya tiene un comprobante ARCA emitido ({comprobante}) — no se puede '
            f'anular ni eliminar. ARCA ya tiene ese comprobante registrado como válido y no hay '
            f'forma de corregirlo desde acá (no está implementada la Nota de Crédito); anular y '
            f'editar la venta la dejaría con datos que no coinciden con lo facturado. Si el '
            f'cliente devolvió parte de la compra, registrá una devolución en su lugar — no '
            f'toca la venta ni el comprobante.'
        )


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

    # — Descuento global (oferta por monto mínimo de compra) —
    # A diferencia de descuento_pct en ItemVenta (por línea), este se
    # aplica una sola vez sobre el total de TODA la venta — ver
    # productos.models.Oferta (tipo=umbral) y calcular_total() más abajo.
    descuento_global_pct = models.DecimalField(
        'Descuento global (%)', max_digits=5, decimal_places=2, default=0,
    )
    oferta_global_nombre = models.CharField(
        'Oferta global aplicada', max_length=100, blank=True,
        help_text='Nombre de la Oferta (tipo=umbral) que originó el descuento global, si la hay.',
    )

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

    @property
    def cliente_unico(self):
        """
        Cliente de la venta, si todos sus ítems apuntan al mismo — None
        si ningún ítem tiene cliente cargado o si hay más de uno
        distinto (venta mixta). Ver `cliente_display` para el texto
        listo para mostrar en pantalla/ticket/factura.
        """
        ids = {item.cliente_id for item in self.items.all() if item.cliente_id}
        if len(ids) == 1:
            return Cliente.objects.filter(pk=ids.pop()).first()
        return None

    @property
    def cliente_display(self):
        """Nombre de cliente a mostrar — 'Consumidor Final' si no hay uno solo vinculado."""
        cliente = self.cliente_unico
        return cliente.get_nombre_display() if cliente else 'Consumidor Final'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = _generar_numero_venta()
        super().save(*args, **kwargs)

    # ── override delete() ────────────────────────────────────────
    def delete(self, *args, **kwargs):
        with transaction.atomic():
            # select_for_update(): si dos requests intentan eliminar la
            # misma venta a la vez, el segundo espera acá; cuando el
            # primero ya la borró, este SELECT ya no encuentra la fila
            # y no hay nada más que hacer (evita revertir el stock dos
            # veces por un doble clic en "Eliminar").
            try:
                estado_actual = Venta.objects.select_for_update().get(pk=self.pk).estado
            except Venta.DoesNotExist:
                return
            # Falla rápido: bloquea el borrado si hay cuotas ya cobradas,
            # devoluciones registradas, o un comprobante ARCA emitido.
            _bloquear_si_tiene_devoluciones(self)
            _bloquear_si_tiene_comprobante_arca(self)
            _anular_cuentas_por_cobrar_de_venta(self)
            _anular_cheques_de_venta(self)

            if estado_actual in (EstadoVenta.CONFIRMADA, EstadoVenta.ANULADA):
                # No permitir el borrado físico de una venta que perteneció a
                # un turno ya cerrado: el turno guardó una foto congelada de
                # sus totales al cerrar (ver TurnoCaja.totales_cierre) para
                # que el historial contable no cambie retroactivamente.
                # Aplica sin importar el estado ACTUAL — anular primero y
                # eliminar después no es una forma válida de esquivar esto:
                # el turno ya la contó en su momento, haya sido anulada
                # recién o no. Acá sí se puede anular sin problema — anular
                # no toca el efectivo ya conciliado de un turno viejo, solo
                # revierte stock y cualquier movimiento no-efectivo asociado.
                from caja.models import TurnoCaja, EstadoTurno
                turno = TurnoCaja.turno_que_contiene(self.fecha_alta)
                if turno and turno.estado == EstadoTurno.CERRADO:
                    if estado_actual == EstadoVenta.CONFIRMADA:
                        detalle = (
                            'Anulala en su lugar (revierte el stock y el movimiento de caja, '
                            'sin reescribir el historial de ese turno).'
                        )
                    else:
                        detalle = 'Ya está anulada — queda así, como registro de lo que pasó ese turno.'
                    raise ValueError(
                        f'No se puede eliminar: esta venta perteneció al turno #{turno.numero}, '
                        f'que ya está cerrado. {detalle}'
                    )

            if estado_actual == EstadoVenta.CONFIRMADA:
                for item in self.items.select_related('producto', 'combinacion'):
                    _revertir_stock_venta_item(item)
                    etiqueta = EtiquetaBalanza.objects.filter(
                        item_venta=item, estado=EstadoEtiquetaBalanza.VENDIDA,
                    ).first()
                    if etiqueta:
                        etiqueta.estado = EstadoEtiquetaBalanza.DISPONIBLE
                        etiqueta.save(update_fields=['estado'])
            # Borrar el movimiento de caja asociado (si lo hay). OJO: NO usar
            # sincronizar_movimiento_venta acá — esa función decide si recrea
            # el movimiento mirando self.estado, que en este punto sigue siendo
            # CONFIRMADA (delete() nunca lo cambia), así que lo recrearía justo
            # antes de que la Venta desaparezca. Como MovimientoCaja no tiene
            # una FK real hacia Venta (se vincula por origen_app/origen_id), el
            # cascade del delete no lo alcanza y queda huérfano para siempre.
            from caja.models import _borrar_movimiento_origen, OrigenMovimiento
            _borrar_movimiento_origen('ventas', OrigenMovimiento.VENTA, self.pk)
            super().delete(*args, **kwargs)

    # ── Métodos de negocio ───────────────────────────────────────

    def calcular_total(self):
        subtotal = sum(item.subtotal for item in self.items.all())
        if self.descuento_global_pct:
            subtotal = subtotal * (1 - self.descuento_global_pct / 100)
        self.total = round(subtotal, 2)
        self.save(update_fields=['total'])

    def calcular_iva_por_alicuota(self):
        """
        Agrupa los ítems por alícuota de IVA (snapshot en ItemVenta.alicuota_iva)
        y calcula neto/IVA reales de cada grupo — para Factura A/B, que a
        diferencia de la C sí tienen que declarar el IVA discriminado ante
        ARCA. Aplica el mismo descuento_global_pct que calcular_total()
        para que neto_total + iva_total cierren EXACTO con self.total
        (WSFEv1 rechaza el comprobante si no cierra).

        Devuelve {'grupos': [{'alicuota': '21', 'neto': Decimal, 'iva': Decimal}, ...],
                  'neto_total': Decimal, 'iva_total': Decimal}.
        """
        factor = (1 - self.descuento_global_pct / 100) if self.descuento_global_pct else Decimal('1')
        acumulado = {}
        for item in self.items.all():
            alicuota = item.alicuota_iva or AlicuotaIVA.GENERAL
            acumulado[alicuota] = acumulado.get(alicuota, Decimal('0')) + item.subtotal * factor

        grupos = []
        for alicuota, base_mas_iva in acumulado.items():
            neto = base_mas_iva / (1 + Decimal(alicuota) / 100)
            grupos.append({
                'alicuota': alicuota,
                'neto': round(neto, 2),
                'iva': round(base_mas_iva - neto, 2),
            })

        neto_total = sum(g['neto'] for g in grupos)
        iva_total  = sum(g['iva']  for g in grupos)

        # El redondeo por grupo puede dejar un centavo de diferencia con
        # self.total — se absorbe en el neto del grupo más grande, mismo
        # criterio que usan los sistemas de facturación reales.
        diferencia = self.total - (neto_total + iva_total)
        if diferencia and grupos:
            mas_grande = max(grupos, key=lambda g: g['neto'] + g['iva'])
            mas_grande['neto'] = round(mas_grande['neto'] + diferencia, 2)
            neto_total = sum(g['neto'] for g in grupos)

        return {'grupos': grupos, 'neto_total': neto_total, 'iva_total': iva_total}

    def aplicar_descuento_global(self, pct, oferta_nombre=''):
        """Fija el descuento global (oferta por monto mínimo) y recalcula el total."""
        self.descuento_global_pct = pct or 0
        self.oferta_global_nombre = oferta_nombre or ''
        self.save(update_fields=['descuento_global_pct', 'oferta_global_nombre'])
        self.calcular_total()

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

        pagos: lista de dicts [{'medio': 'efectivo', 'monto': 3000},
               {'medio': 'transferencia', 'monto': 999.97, 'cuenta_pk': 5,
                'cotizacion': 1200}, ...]
               Si se pasa, reemplaza cualquier PagoVenta previo de
               esta venta (relevante en re-confirmaciones vía editar_completa).

               La venta en sí siempre está en pesos. Para medio=efectivo
               la cuenta se resuelve sola (Efectivo en pesos — el
               efectivo físico no admite otra moneda, ver PagoVenta);
               para el resto, 'cuenta_pk' es obligatorio y puede ser
               una cuenta en cualquier moneda. Si esa cuenta no es en
               pesos, 'cotizacion' es obligatoria (pesos por unidad de
               esa moneda) para poder validar que los pagos cubren el
               total.
        """
        # select_for_update(): vuelve a leer y bloquea esta fila antes
        # de decidir. No alcanza con confiar en que el caller (la vista)
        # ya la haya traído con lock — este método puede llamarse desde
        # otros lugares (editar_completa, shell, etc.) y self.estado
        # puede venir de una lectura vieja. Bloqueando ACÁ adentro, un
        # segundo confirmar() sobre la misma venta (doble clic,
        # reintento de red, doble llamada) se queda esperando a que la
        # primera transacción termine y, al destrabarse, ya la
        # encuentra CONFIRMADA — sin descontar stock ni generar pagos
        # dos veces.
        if Venta.objects.select_for_update().get(pk=self.pk).estado != EstadoVenta.BORRADOR:
            raise ValueError('Solo se pueden confirmar ventas en estado Borrador.')

        # Compatibilidad hacia atrás real (antes solo estaba documentada,
        # no implementada): si no se manda "pagos", se asumía "pago
        # completo con medio_pago" pero en los hechos no se creaba ningún
        # PagoVenta ni movimiento de caja — la venta quedaba CONFIRMADA
        # con el stock ya descontado pero sin ningún rastro de cobro,
        # sin ningún error. Para efectivo hay una cuenta por defecto
        # segura (Efectivo ARS) así que se sintetiza un único pago por el
        # total. Para el resto de los medios no hay ninguna cuenta que
        # se pueda adivinar sin riesgo (¿qué banco? ¿qué tarjeta?) — ahí
        # se rechaza explícito en vez de confirmar en silencio sin cobro.
        # El frontend real (nueva_venta.js) siempre manda "pagos", así
        # que esto solo se activa por una llamada directa (shell, un
        # caller externo, o un bypass del frontend).
        if pagos is None and medio_pago:
            if medio_pago == MedioPago.EFECTIVO:
                self.calcular_total()
                pagos = [{'medio': MedioPago.EFECTIVO, 'monto': self.total}]
            else:
                raise ValueError(
                    'Para confirmar con un medio de pago que no sea efectivo hace falta indicar '
                    'la cuenta real de cobro — mandá el array "pagos" con la cuenta correspondiente.'
                )

        # Resolver la cuenta real de cada línea de pago ANTES de tocar
        # stock/estado: si alguna es inválida, falla rápido sin dejar
        # nada a medio hacer (igual está todo en @transaction.atomic,
        # pero así evitamos descontar stock para nada).
        pagos_resueltos = None
        if pagos is not None:
            from caja.models import CuentaCaja, TipoCaja, TipoCuenta, _cuenta_default, ModoCuotas
            labels_medio = dict(MedioPago.choices)

            pagos_resueltos = []
            for p in pagos:
                monto = p.get('monto')
                if not monto or float(monto) <= 0:
                    continue
                medio = p.get('medio', MedioPago.EFECTIVO)

                cuotas_info = None
                cheques_info = None
                if medio == MedioPago.EFECTIVO:
                    cuenta = _cuenta_default(moneda=Moneda.ARS, caja=TipoCaja.GRANDE)
                    cotizacion = None
                elif medio == MedioPago.CHEQUE:
                    # Igual que CUOTAS: sin cuenta ni cotización acá — no
                    # entra plata a caja al confirmar la venta, cada
                    # cheque se crea PENDIENTE y solo impacta caja cuando
                    # se confirma individualmente (deposita) desde la
                    # pantalla de Cheques.
                    cuenta = None
                    cotizacion = None
                    cliente_venta = self.cliente_unico
                    if cliente_venta is None:
                        raise ValueError(
                            'Para cobrar con cheque la venta necesita un único cliente vinculado '
                            '(no se le puede cobrar con cheque a Consumidor Final).'
                        )
                    cheques_raw = p.get('cheques') or []
                    if not cheques_raw:
                        raise ValueError('Cargá al menos un cheque para esta línea de pago.')
                    cheques_info = []
                    for ch in cheques_raw:
                        try:
                            monto_cheque = Decimal(str(ch.get('monto')))
                            if monto_cheque <= 0:
                                raise ValueError
                        except Exception:
                            raise ValueError('Uno de los cheques cargados tiene un monto inválido.')
                        if (ch.get('moneda') or Moneda.ARS) != Moneda.ARS:
                            raise ValueError(
                                'Por ahora los cheques de una venta deben ser en pesos.'
                            )
                        fecha_emision_raw = ch.get('fecha_emision')
                        fecha_cobro_raw = ch.get('fecha_cobro')
                        if not fecha_emision_raw or not fecha_cobro_raw:
                            raise ValueError('Cada cheque necesita fecha de emisión y de cobro.')
                        try:
                            fecha_emision_ch = date.fromisoformat(str(fecha_emision_raw))
                            fecha_cobro_ch = date.fromisoformat(str(fecha_cobro_raw))
                        except ValueError:
                            raise ValueError('Fecha de cheque inválida.')
                        cheques_info.append({
                            'numero_cheque': str(ch.get('numero_cheque', '') or '').strip(),
                            'monto': monto_cheque,
                            'fecha_emision': fecha_emision_ch,
                            'fecha_cobro': fecha_cobro_ch,
                            'emisor': str(ch.get('emisor', '') or '').strip(),
                            'receptor': str(ch.get('receptor', '') or '').strip(),
                            'banco': str(ch.get('banco', '') or '').strip(),
                            'notas': str(ch.get('notas', '') or '').strip(),
                        })
                    # El monto de la línea es la suma de los cheques
                    # cargados, no un valor tipeado aparte — así nunca
                    # pueden desincronizarse.
                    monto = sum(c['monto'] for c in cheques_info)
                elif medio == MedioPago.CUOTAS:
                    # Sin cuenta ni cotización: no entra plata a caja
                    # todavía, solo se genera la CuentaPorCobrar (ver
                    # más abajo, después de guardar los PagoVenta).
                    cuenta = None
                    cotizacion = None
                    cliente_venta = self.cliente_unico
                    if cliente_venta is None:
                        raise ValueError(
                            'Para vender en cuotas la venta necesita un único cliente vinculado '
                            '(no se le puede vender en cuotas a Consumidor Final).'
                        )
                    modo_cuotas = p.get('modo_cuotas', ModoCuotas.FIJAS)
                    if modo_cuotas not in ModoCuotas.values:
                        modo_cuotas = ModoCuotas.FIJAS
                    es_libre = modo_cuotas == ModoCuotas.LIBRE

                    try:
                        interes_pct = Decimal(str(p.get('interes_pct', 0) or 0))
                    except Exception:
                        raise ValueError('Porcentaje de interés inválido.')
                    if interes_pct < 0:
                        raise ValueError('El porcentaje de interés no puede ser negativo.')

                    cantidad_cuotas = None
                    if es_libre:
                        # Modo libre: no hay plan que armar, así que no hace
                        # falta pedirle cantidad de cuotas ni fecha de la
                        # primera al vendedor — la fecha de origen es
                        # directamente la de la venta (mismo criterio que
                        # Compras usa la fecha de la compra en compra_credito
                        # libre).
                        fecha_inicio_cobro = self.fecha
                    else:
                        try:
                            cantidad_cuotas = int(p.get('cuotas', 0))
                        except (TypeError, ValueError):
                            cantidad_cuotas = 0
                        if cantidad_cuotas < 1:
                            raise ValueError('Indicá la cantidad de cuotas para el pago financiado.')
                        fecha_inicio_raw = p.get('fecha_inicio_cobro')
                        if not fecha_inicio_raw:
                            raise ValueError('Indicá la fecha de la primera cuota.')
                        try:
                            fecha_inicio_cobro = date.fromisoformat(str(fecha_inicio_raw))
                        except ValueError:
                            raise ValueError('Fecha de inicio de cobro inválida.')
                    cuotas_info = {
                        'cliente': cliente_venta, 'modo_cuotas': modo_cuotas, 'cantidad_cuotas': cantidad_cuotas,
                        'interes_pct': interes_pct, 'fecha_inicio_cobro': fecha_inicio_cobro,
                    }
                else:
                    cuenta = CuentaCaja.objects.filter(
                        pk=p.get('cuenta_pk'), caja=TipoCaja.GRANDE, activa=True,
                        es_credito=False,
                    ).exclude(tipo=TipoCuenta.EFECTIVO).first()
                    if not cuenta:
                        raise ValueError(
                            f'Elegí una cuenta válida para el pago con '
                            f'{labels_medio.get(medio, medio)}.'
                        )
                    cotizacion = None
                    if cuenta.moneda != Moneda.ARS:
                        try:
                            cotizacion = Decimal(str(p.get('cotizacion')))
                            if cotizacion <= 0:
                                raise ValueError
                        except Exception:
                            raise ValueError(
                                f'Ingresá la cotización usada para el pago en '
                                f'{cuenta.get_moneda_display()}.'
                            )

                # Recargo (débito/crédito/QR/transferencia — no aplica a
                # efectivo ni a cuotas de financiación propia): `monto` acá
                # sigue siendo la porción del precio de venta que cubre
                # esta línea (igual que siempre — no cambia la validación
                # de que la suma cubra venta.total, ver vista de confirmar).
                # El recargo se calcula ENCIMA de esa base y se snapshotea;
                # abajo se suma a `monto` para guardar en PagoVenta lo que
                # realmente se acredita en la cuenta.
                #
                # `tarjeta` es la TarjetaPago con la que pagó el CLIENTE
                # (Visa, Mercado Pago, Personal Pay...) — un dato aparte de
                # `cuenta` (a cuál de MIS cuentas entra la plata). Es
                # opcional: si la venta no necesita trazabilidad de recargo,
                # se puede confirmar sin elegir tarjeta (recargo 0).
                tarjeta = None
                recargo_pct = Decimal('0')
                cantidad_pagos = 1
                nombre_plan = ''
                recargo_monto = Decimal('0')
                if medio in RecargoMedioPago.MEDIOS_CON_RECARGO:
                    if p.get('tarjeta_pk'):
                        tarjeta = TarjetaPago.objects.filter(pk=p.get('tarjeta_pk'), activa=True).first()
                    try:
                        recargo_pct = Decimal(str(p.get('recargo_pct', 0) or 0))
                    except Exception:
                        raise ValueError('Porcentaje de recargo inválido.')
                    if recargo_pct < 0:
                        raise ValueError('El porcentaje de recargo no puede ser negativo.')
                    if medio == MedioPago.CREDITO:
                        try:
                            cantidad_pagos = max(1, int(p.get('cantidad_pagos', 1) or 1))
                        except (TypeError, ValueError):
                            cantidad_pagos = 1
                        nombre_plan = str(p.get('nombre_plan', '') or '').strip()[:60]
                    recargo_monto = (Decimal(str(monto)) * recargo_pct / 100).quantize(Decimal('0.01'))

                pagos_resueltos.append({
                    'medio': medio, 'monto': monto, 'cuenta': cuenta, 'tarjeta': tarjeta,
                    'cotizacion': cotizacion,
                    'cuotas_info': cuotas_info, 'cheques_info': cheques_info,
                    'recargo_pct': recargo_pct,
                    'cantidad_pagos': cantidad_pagos, 'nombre_plan': nombre_plan,
                    'recargo_monto': recargo_monto,
                })

        # Validar las etiquetas de balanza ANTES de tocar stock: si
        # alguna ya no está disponible (se vendió o se anuló mientras
        # esta venta seguía en borrador), falla rápido sin descontar nada.
        etiquetas_a_marcar = []
        for item in self.items.all():
            etiqueta = EtiquetaBalanza.objects.filter(item_venta=item).first()
            if etiqueta is None:
                continue
            if etiqueta.estado != EstadoEtiquetaBalanza.DISPONIBLE:
                raise ValueError(
                    f'La etiqueta {etiqueta.codigo} ("{etiqueta.producto_nombre_snapshot}") '
                    f'ya no está disponible ({etiqueta.get_estado_display()}). Sacala de la venta.'
                )
            etiquetas_a_marcar.append(etiqueta)

        avisos = []
        for item in self.items.select_related('producto', 'combinacion'):
            _consumos, avisos_item = _descontar_stock_venta_item(item)
            avisos.extend(avisos_item)

        for etiqueta in etiquetas_a_marcar:
            etiqueta.estado = EstadoEtiquetaBalanza.VENDIDA
            etiqueta.save(update_fields=['estado'])

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

        if pagos_resueltos is not None:
            self.pagos.all().delete()
            for p in pagos_resueltos:
                pago = PagoVenta.objects.create(
                    venta          = self,
                    medio          = p['medio'],
                    monto          = Decimal(str(p['monto'])) + p['recargo_monto'],
                    cuenta         = p['cuenta'],
                    tarjeta        = p['tarjeta'],
                    cotizacion     = p['cotizacion'],
                    cantidad_pagos = p['cantidad_pagos'],
                    nombre_plan    = p['nombre_plan'],
                    recargo_pct    = p['recargo_pct'],
                    recargo_monto  = p['recargo_monto'],
                )
                if p['cuotas_info'] is not None:
                    from caja.models import CuentaPorCobrar
                    info = p['cuotas_info']
                    CuentaPorCobrar.crear_con_cuotas(
                        cliente=info['cliente'],
                        pago_venta=pago,
                        monto_original=Decimal(str(p['monto'])),
                        porcentaje_interes=info['interes_pct'],
                        modo_cuotas=info['modo_cuotas'],
                        cantidad_cuotas=info['cantidad_cuotas'],
                        fecha_inicio=info['fecha_inicio_cobro'],
                        moneda=Moneda.ARS,
                        descripcion=f'Venta {self.numero}',
                        numero_comprobante=self.numero,
                        creado_por=confirmado_por,
                    )
                if p['cheques_info'] is not None:
                    from caja.models import Cheque, TipoCheque
                    for ch in p['cheques_info']:
                        Cheque.objects.create(
                            tipo=TipoCheque.A_COBRAR,
                            numero_cheque=ch['numero_cheque'],
                            numero_factura=self.numero,
                            monto=ch['monto'],
                            moneda=Moneda.ARS,
                            fecha_emision=ch['fecha_emision'],
                            fecha_cobro=ch['fecha_cobro'],
                            emisor=ch['emisor'],
                            receptor=ch['receptor'],
                            banco=ch['banco'],
                            notas=ch['notas'],
                            pago_venta=pago,
                            creado_por=confirmado_por,
                        )

        # Sincronizar movimiento de caja grande
        from caja.models import sincronizar_movimiento_venta
        sincronizar_movimiento_venta(self)

        return avisos

    @transaction.atomic
    def anular(self, anulado_por=None):
        """Anula la venta y revierte el stock. Solo desde CONFIRMADA."""
        estado_actual = Venta.objects.select_for_update().get(pk=self.pk).estado
        if estado_actual == EstadoVenta.ANULADA:
            raise ValueError('La venta ya está anulada.')
        if estado_actual == EstadoVenta.BORRADOR:
            raise ValueError('Las ventas en borrador no se anulan — simplemente no se confirman.')

        # Falla rápido: si alguna cuota de una venta en cuotas ya fue
        # cobrada, hay devoluciones registradas, o ya se emitió un
        # comprobante ARCA, no se puede anular.
        _bloquear_si_tiene_devoluciones(self)
        _bloquear_si_tiene_comprobante_arca(self)
        _anular_cuentas_por_cobrar_de_venta(self)
        _anular_cheques_de_venta(self)

        for item in self.items.select_related('producto', 'combinacion'):
            _revertir_stock_venta_item(item)
            etiqueta = EtiquetaBalanza.objects.filter(
                item_venta=item, estado=EstadoEtiquetaBalanza.VENDIDA,
            ).first()
            if etiqueta:
                etiqueta.estado = EstadoEtiquetaBalanza.DISPONIBLE
                etiqueta.save(update_fields=['estado'])

        self.estado         = EstadoVenta.ANULADA
        self.anulado_por    = anulado_por
        self.fecha_anulacion = timezone.now()
        self.save(update_fields=['estado', 'anulado_por', 'fecha_anulacion'])

        # Sincronizar movimiento de caja grande
        from caja.models import sincronizar_movimiento_venta
        sincronizar_movimiento_venta(self)

    @transaction.atomic
    def reactivar(self):
        """
        Reactiva una venta ANULADA devolviéndola a BORRADOR. Actualiza
        `fecha_modificacion` (aunque no cambia nada más) para poder medir
        después cuánto tiempo lleva abandonada si nadie termina de
        editarla — ver `descartar_borradores_vencidos`.
        """
        if Venta.objects.select_for_update().get(pk=self.pk).estado != EstadoVenta.ANULADA:
            raise ValueError('Solo se pueden reactivar ventas anuladas.')

        self.estado = EstadoVenta.BORRADOR
        self.save(update_fields=['estado', 'fecha_modificacion'])

    @transaction.atomic
    def descartar_edicion(self):
        """
        Descarta un borrador desde "Cancelar" (carrito o detalle). Si
        `fecha_anulacion` está seteada, este borrador viene de reactivar()
        una venta ANULADA real (con ItemVenta/PagoVenta históricos detrás)
        — no se borra, vuelve a ANULADA tal cual estaba. Si no, es un
        borrador nuevo genuino (nunca existió como venta real) y se borra
        directo, no hay nada que revertir.
        """
        if Venta.objects.select_for_update().get(pk=self.pk).estado != EstadoVenta.BORRADOR:
            raise ValueError('Solo se pueden descartar borradores.')

        if self.fecha_anulacion is not None:
            self.estado = EstadoVenta.ANULADA
            self.save(update_fields=['estado'])
            return False  # no se borró, se revirtió
        else:
            self.delete()
            return True  # se borró de verdad

    @transaction.atomic
    def editar_completa(self, fecha, notas='', items_data=None, medio_pago=None, editado_por=None, pagos=None,
                         descuento_global_pct=None, oferta_global_nombre=None):
        """
        Edita una venta ANULADA: reemplaza sus ítems y la re-confirma.
        Registra quién editó y cuándo. Si se pasan pagos, reemplaza
        las líneas de pago dividido existentes.
        """
        if self.estado != EstadoVenta.ANULADA:
            raise ValueError('Solo se pueden editar ventas anuladas.')
        # Defensa en profundidad: anular() ya bloquea esto antes de que una
        # venta facturada llegue a ANULADA, pero por si existe un caso
        # viejo (de antes de este chequeo) que haya quedado ANULADA con un
        # comprobante ARCA todavía asociado, no dejar que editar_completa()
        # reemplace los ítems y re-confirme con un total que ya no
        # coincide con lo facturado.
        _bloquear_si_tiene_comprobante_arca(self)

        self.items.all().delete()

        for d in (items_data or []):
            ItemVenta.objects.create(
                venta           = self,
                producto        = d['producto'],
                cliente         = d.get('cliente'),
                combinacion     = d.get('combinacion'),
                tipo_escaneo    = d.get('tipo_escaneo', TipoResolucionLote.NORMAL),
                lote_escaneado  = d.get('lote_escaneado'),
                cantidad        = d['cantidad'],
                precio_unitario = d['precio_unitario'],
                moneda          = d.get('moneda', 'ARS'),
                descuento_pct   = d.get('descuento_pct', 0),
                lista_descuento_nombre = d.get('lista_descuento_nombre', ''),
                oferta_aplicada_nombre = d.get('oferta_aplicada_nombre', ''),
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
        if descuento_global_pct is not None:
            self.descuento_global_pct = descuento_global_pct
        if oferta_global_nombre is not None:
            self.oferta_global_nombre = oferta_global_nombre
        self.estado = EstadoVenta.BORRADOR
        self.save(update_fields=[
            'fecha', 'notas', 'medio_pago', 'estado', 'editado_por', 'fecha_edicion',
            'descuento_global_pct', 'oferta_global_nombre',
        ])

        # Re-confirma propagando quien editó como confirmador y los pagos
        # La sincronización de caja ya ocurre dentro de confirmar()
        return self.confirmar(confirmado_por=editado_por, medio_pago=medio_pago, pagos=pagos)


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

    # ── Origen del stock (de qué lote sale) ───────────────────────
    tipo_escaneo = models.CharField(
                       max_length=20, choices=TipoResolucionLote.choices,
                       default=TipoResolucionLote.NORMAL)

    lote_escaneado = models.ForeignKey(
                          LoteCompra, on_delete=models.SET_NULL,
                          null=True, blank=True,
                          related_name='items_venta_escaneados',
                          verbose_name='Lote escaneado puntualmente',
                          help_text='Solo se completa si tipo_escaneo=lote_especifico.')

    # ── Snapshots ────────────────────────────────────────────────
    producto_nombre  = models.CharField(max_length=255, blank=True)
    producto_codigo  = models.CharField(max_length=50,  blank=True)
    cliente_nombre   = models.CharField(max_length=200, blank=True)
    combinacion_descripcion = models.CharField(max_length=300, blank=True)
    # Alícuota de IVA del producto AL MOMENTO de vender — se guarda acá
    # (no alcanza con producto.alicuota_iva en runtime) porque si el
    # producto cambia de alícuota después, esta venta ya facturada
    # tiene que seguir reflejando la que tenía en ese momento.
    alicuota_iva = models.CharField('Alícuota IVA', max_length=5,
                       choices=AlicuotaIVA.choices, blank=True)

    # — Cantidades y precios —
    cantidad        = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField('Precio unitario', max_digits=12, decimal_places=2)
    moneda          = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)

    # — Descuento opcional —
    # decimal_places=4 (no 2): ofertas NXM tipo "3x1" dan un % con
    # decimales infinitos (pagar 1 de 3 = 66,6666...%). Con solo 2
    # decimales el redondeo se nota en el subtotal (ver Oferta en
    # productos/models.py); a 4 decimales el error queda por debajo
    # del centavo en cualquier venta real.
    descuento_pct   = models.DecimalField('Descuento (%)', max_digits=8, decimal_places=4, default=0)
    lista_descuento_nombre = models.CharField(
        'Lista de descuento aplicada', max_length=100, blank=True,
        help_text='Nombre de la lista si el % vino de ahí (ver ListaDescuento); '
                   'vacío si se escribió el % a mano.',
    )
    oferta_aplicada_nombre = models.CharField(
        'Oferta aplicada', max_length=100, blank=True,
        help_text='Nombre de la Oferta si el % vino de una promoción vigente '
                   '(automática o elegida a mano); vacío si no aplica.',
    )

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
            if self.producto and not self.alicuota_iva:
                self.alicuota_iva = self.producto.alicuota_iva
            if self.cliente and not self.cliente_nombre:
                self.cliente_nombre = self.cliente.get_nombre_display()
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
    def nombre_ticket_display(self):
        """Nombre para tickets/comprobantes — pensado para el cliente final,
        no para uso interno: sin el [código] (útil en pantalla para el
        personal, pero ruido en un ticket) y usando `nombre_corto` del
        producto si está cargado (existe justamente para esto). Con
        fallback automático al nombre completo si no hay nombre corto."""
        if self.producto:
            return self.producto.nombre_corto or self.producto.nombre
        if self.producto_nombre:
            return self.producto_nombre
        return '(producto eliminado)'

    @property
    def nombre_cliente_display(self):
        if self.cliente:
            return self.cliente.get_nombre_display()
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

    @property
    def lotes_utilizados(self):
        """Códigos de lote de los que efectivamente salió el stock (post-confirmación)."""
        return [c.lote_codigo_snapshot for c in self.consumos.all()]


# ══════════════════════════════════════════════════════════════════
#  CONSUMO DE LOTE — de qué LoteCompra específico salió cada porción
#  de un ItemVenta. Un mismo ítem puede tener más de un consumo si el
#  lote principal no alcanzaba para cubrir la cantidad pedida (se
#  completa automáticamente con el siguiente lote disponible).
# ══════════════════════════════════════════════════════════════════

class ConsumoLoteVenta(models.Model):
    """
    costo_unitario_snapshot queda disponible para que otros módulos
    (caja diaria, caja grande, estadísticas) calculen la ganancia real
    — este módulo de ventas no calcula ganancia.
    """
    item_venta = models.ForeignKey(ItemVenta, on_delete=models.CASCADE, related_name='consumos')
    lote       = models.ForeignKey(LoteCompra, on_delete=models.SET_NULL,
                     null=True, blank=True, related_name='consumos_venta')
    cantidad   = models.DecimalField(max_digits=12, decimal_places=3)

    lote_codigo_snapshot    = models.CharField(max_length=20, blank=True)
    costo_unitario_snapshot = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Consumo de lote (venta)'
        verbose_name_plural = 'Consumos de lote (venta)'
        ordering            = ['id']

    def __str__(self):
        return f'{self.lote_codigo_snapshot} → {self.cantidad}u ({self.item_venta})'


def _generar_numero_devolucion():
    ultimo = DevolucionVenta.objects.order_by('-id').first()
    if not ultimo or not ultimo.numero:
        numero = 1
    else:
        try:
            numero = int(ultimo.numero.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = DevolucionVenta.objects.count() + 1
    return f'DEV-{numero:05d}'


# ══════════════════════════════════════════════════════════════════
#  DEVOLUCIONES — alternativa a editar/reactivar una venta ya
#  confirmada para el caso de "el cliente devuelve algo". La venta
#  original queda intacta (sigue CONFIRMADA); la devolución es un
#  registro aparte que repone stock al LOTE EXACTO de origen (via
#  ConsumoLoteVenta) y, opcionalmente, reembolsa plata de una cuenta
#  elegida. Ver registrar_devolucion() más abajo.
# ══════════════════════════════════════════════════════════════════

class DevolucionVenta(models.Model):
    """
    Cabecera de una devolución. No tiene estado (BORRADOR/ANULADA):
    se registra atómicamente de una sola vez, igual que Perdida — no
    hay forma de "deshacer" una devolución hoy (si hace falta corregir
    un error, se hace un ajuste de stock manual, mismo criterio que ya
    existe para Perdida).
    """
    numero = models.CharField(max_length=20, unique=True, blank=True)
    venta  = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name='devoluciones')
    fecha  = models.DateField(help_text='Fecha contable de la devolución.')
    descripcion = models.CharField(max_length=300, help_text='Motivo/descripción cargada a mano.')

    # — Reembolso (opcional: puede ser un simple cambio, sin devolver plata) —
    cuenta = models.ForeignKey(
        'caja.CuentaCaja', on_delete=models.PROTECT,
        null=True, blank=True, related_name='devoluciones_venta',
        help_text='De qué cuenta sale el reembolso. Vacío si no se devuelve plata.',
    )
    monto = models.DecimalField(max_digits=14, decimal_places=2, default=0,
                       help_text='Lo efectivamente reembolsado, en la moneda de "cuenta".')
    cotizacion = models.DecimalField(
        'Cotización', max_digits=12, decimal_places=4, null=True, blank=True,
        help_text='Pesos por unidad de la moneda de la cuenta. Solo aplica si la cuenta no es en pesos.',
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='devoluciones_venta_creadas',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Devolución de venta'
        verbose_name_plural = 'Devoluciones de venta'
        ordering            = ['-fecha_alta']

    def __str__(self):
        return f'{self.numero} — {self.venta.numero}'

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = _generar_numero_devolucion()
        super().save(*args, **kwargs)


class DevolucionVentaItem(models.Model):
    """
    Una fila por ItemVenta devuelto. Puede haber DOS filas para el
    mismo item_venta en una misma devolución si una porción vuelve al
    stock vendible y otra se marca como pérdida (ej: devolvieron 3,
    2 se revenden, 1 está rota).
    """
    devolucion = models.ForeignKey(DevolucionVenta, on_delete=models.CASCADE, related_name='items')
    item_venta = models.ForeignKey(
        ItemVenta, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='devoluciones',
    )
    producto_nombre_snapshot     = models.CharField(max_length=255, blank=True)
    combinacion_desc_snapshot    = models.CharField(max_length=300, blank=True)

    cantidad = models.DecimalField(max_digits=12, decimal_places=3)

    es_perdida = models.BooleanField(
        default=False,
        help_text='True si la unidad devuelta está rota/no reutilizable — no vuelve al stock '
                   'vendible, se registra como Perdida en su lugar (ver registrar_perdida en '
                   'compras.models).',
    )
    motivo_perdida = models.CharField(
        max_length=20, blank=True,
        help_text='Choices de compras.models.MotivoPerdida. Solo aplica si es_perdida=True.',
    )

    class Meta:
        verbose_name        = 'Ítem de devolución de venta'
        verbose_name_plural = 'Ítems de devolución de venta'

    def __str__(self):
        return f'{self.producto_nombre_snapshot} — {self.cantidad}u'


class DevolucionVentaConsumo(models.Model):
    """
    De qué LoteCompra (vía qué ConsumoLoteVenta original) salió cada
    porción repuesta — el corazón de "reponer al lote exacto". Un
    DevolucionVentaItem puede repartirse entre varios lotes de origen,
    igual que una venta puede haberse completado con más de uno.

    `consumo_origen` es lo que permite saber cuánto de cada consumo
    puntual de la venta original ya se devolvió antes (sumando
    DevolucionVentaConsumo.cantidad por consumo_origen), para no poder
    devolver más de lo que realmente salió de ahí.
    """
    devolucion_item = models.ForeignKey(DevolucionVentaItem, on_delete=models.CASCADE, related_name='consumos')
    consumo_origen  = models.ForeignKey(
        ConsumoLoteVenta, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='devoluciones',
    )
    lote = models.ForeignKey(
        LoteCompra, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='devoluciones_venta',
    )
    lote_codigo_snapshot = models.CharField(max_length=20, blank=True)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)

    fue_perdida = models.BooleanField(default=False)
    perdida = models.ForeignKey(
        'compras.Perdida', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='devolucion_origen',
        help_text='La Perdida que registró esta porción, si fue_perdida=True.',
    )

    class Meta:
        verbose_name        = 'Consumo de devolución (venta)'
        verbose_name_plural = 'Consumos de devolución (venta)'

    def __str__(self):
        return f'{self.lote_codigo_snapshot} ← {self.cantidad}u'


@transaction.atomic
def registrar_devolucion(venta, items_data, descripcion, usuario=None,
                          cuenta=None, monto=None, cotizacion=None, fecha=None):
    """
    Registra una devolución de `venta` sin tocar su estado (sigue
    CONFIRMADA). Por cada entrada de `items_data`
    ({'item_venta': ItemVenta, 'cantidad': Decimal, 'es_perdida': bool,
    'motivo_perdida': str|None}), reparte la cantidad a devolver entre
    los ConsumoLoteVenta del ítem (mismo orden FIFO en que se vendió),
    y por cada porción:
      - siempre repone stock al lote de origen (lote.agregar_stock) y
        sincroniza producto/combinación — igual que anular una venta;
      - si es_perdida, ADEMÁS llama a registrar_perdida() de inmediato
        para esa misma porción, que vuelve a descontarla del lote y
        genera el registro de Perdida + MovimientoStock(MERMA). El
        resultado neto es stock sin cambios (nunca volvió a estar
        vendible), pero con el registro de auditoría/costo correcto.

    Lanza ValueError si la venta no está confirmada, si falta algún
    dato requerido, o si se intenta devolver más de lo que un ítem
    realmente vendió (descontando devoluciones previas).
    """
    from compras.models import registrar_perdida, MotivoPerdida

    if venta.estado != EstadoVenta.CONFIRMADA:
        if venta.estado == EstadoVenta.BORRADOR:
            raise ValueError('No se puede devolver una venta que todavía no se confirmó.')
        raise ValueError('No se puede devolver una venta anulada.')

    descripcion = (descripcion or '').strip()
    if not descripcion:
        raise ValueError('La descripción de la devolución es obligatoria.')
    if not items_data:
        raise ValueError('Elegí al menos un ítem a devolver.')

    monto = Decimal(str(monto)) if monto else Decimal('0')
    if monto < 0:
        raise ValueError('El monto a reembolsar no puede ser negativo.')
    if monto > 0:
        if cuenta is None:
            raise ValueError('Elegí de qué cuenta sale el reembolso.')
        if cuenta.moneda != Moneda.ARS and not cotizacion:
            raise ValueError('Indicá la cotización — la cuenta elegida no está en pesos.')
    else:
        cuenta = None
        cotizacion = None

    devolucion = DevolucionVenta.objects.create(
        venta=venta, fecha=fecha or timezone.now().date(), descripcion=descripcion,
        cuenta=cuenta, monto=monto, cotizacion=cotizacion, creado_por=usuario,
    )

    for data in items_data:
        item_venta = data['item_venta']
        if item_venta.venta_id != venta.pk:
            raise ValueError('Uno de los ítems no pertenece a esta venta.')

        cantidad = Decimal(str(data['cantidad']))
        if cantidad <= 0:
            raise ValueError('La cantidad a devolver debe ser mayor a 0.')

        es_perdida = bool(data.get('es_perdida'))
        motivo_perdida = data.get('motivo_perdida') or MotivoPerdida.ROTURA
        if es_perdida and motivo_perdida not in MotivoPerdida.values:
            raise ValueError(f'Motivo de pérdida inválido: {motivo_perdida}')

        nombre_desc = item_venta.producto_nombre or (item_venta.producto.nombre if item_venta.producto else '')

        dev_item = DevolucionVentaItem.objects.create(
            devolucion=devolucion, item_venta=item_venta,
            producto_nombre_snapshot=nombre_desc,
            combinacion_desc_snapshot=item_venta.combinacion_descripcion,
            cantidad=cantidad, es_perdida=es_perdida,
            motivo_perdida=motivo_perdida if es_perdida else '',
        )

        restante = cantidad
        totales = {}  # (producto_id, combinacion_id) -> cantidad a sumar a stock_actual

        # Sin select_related('lote'): `lote` es una FK nullable
        # (SET_NULL) — select_for_update() sobre un LEFT OUTER JOIN no
        # es válido en Postgres ("FOR UPDATE no puede ser aplicado al
        # lado nulable de un outer join"). consumo.lote se resuelve con
        # una query aparte por fila, sin problema (son pocas filas).
        for consumo in item_venta.consumos.select_for_update().order_by('id'):
            if restante <= 0:
                break
            if consumo.lote is None:
                continue

            ya_devuelto = consumo.devoluciones.aggregate(total=models.Sum('cantidad'))['total'] or Decimal('0')
            disponible = consumo.cantidad - ya_devuelto
            if disponible <= 0:
                continue

            tomar = min(restante, disponible)

            consumo.lote.agregar_stock(tomar)
            clave = (consumo.lote.producto_id, consumo.lote.combinacion_id)
            totales[clave] = totales.get(clave, Decimal('0')) + tomar

            perdida = None
            if es_perdida:
                perdida = registrar_perdida(
                    lote=consumo.lote, cantidad=tomar, motivo=motivo_perdida,
                    motivo_detalle=f'Devolución {devolucion.numero}: {descripcion}',
                    usuario=usuario, automatica=False, fecha=devolucion.fecha,
                )

            DevolucionVentaConsumo.objects.create(
                devolucion_item=dev_item, consumo_origen=consumo, lote=consumo.lote,
                lote_codigo_snapshot=consumo.lote_codigo_snapshot, cantidad=tomar,
                fue_perdida=es_perdida, perdida=perdida,
            )
            restante -= tomar

        if restante > 0:
            raise ValueError(
                f'"{nombre_desc}": no se puede devolver esa cantidad — ya se devolvió lo '
                f'disponible de las {item_venta.cantidad} unidades vendidas en esta línea.'
            )

        # Sincronizar stock_actual de producto/combinación — mismo patrón
        # que _revertir_stock_venta_item: lectura fresca con
        # select_for_update() para no pisar cambios que registrar_perdida()
        # ya haya guardado en la misma transacción (ver docstring de arriba).
        for (producto_id, combinacion_id), cant in totales.items():
            if producto_id is None:
                continue
            if combinacion_id is not None:
                combinacion = CombinacionVariante.objects.select_for_update().filter(pk=combinacion_id).first()
                if combinacion is None:
                    continue
                combinacion.stock_actual = combinacion.stock_actual + cant
                combinacion.save(update_fields=['stock_actual'])
                prod = Producto.objects.filter(pk=producto_id).first()
                if prod is not None:
                    prod.sincronizar_stock_desde_combinaciones()
            else:
                prod = Producto.objects.select_for_update().filter(pk=producto_id).first()
                if prod is None:
                    continue
                prod.stock_actual = prod.stock_actual + cant
                prod.save(update_fields=['stock_actual'])

    if devolucion.monto > 0:
        from caja.models import sincronizar_movimiento_devolucion
        sincronizar_movimiento_devolucion(devolucion)

    return devolucion


# ══════════════════════════════════════════════════════════════════
#  ETIQUETA DE BALANZA — para productos que se pesan/miden al momento
#  (carnicería, verdulería, panadería, fiambrería...): el peso real
#  nunca es exacto (pediste 2kg, la bolsa da 2,050kg), así que se pesa,
#  se genera una etiqueta con código de barras ÚNICO que ya trae la
#  cantidad y el precio fijados, se pega en la bolsa, y en caja
#  alcanza con escanearla — no se vuelve a pesar ni tipear nada.
#
#  A diferencia de Fraccionamiento, esto NO mueve stock al generarse:
#  es solo una "reserva de datos" para una única venta. El stock recién
#  se descuenta cuando la venta que contiene esa etiqueta se confirma,
#  exactamente igual que cualquier otro ítem del carrito (FIFO normal
#  sobre los lotes reales del producto).
# ══════════════════════════════════════════════════════════════════

class EstadoEtiquetaBalanza(models.TextChoices):
    DISPONIBLE = 'disponible', 'Disponible'
    VENDIDA    = 'vendida',    'Vendida'
    ANULADA    = 'anulada',    'Anulada'


def _generar_codigo_etiqueta_balanza():
    anio = timezone.now().year
    ultimo = EtiquetaBalanza.objects.filter(codigo__startswith=f'BAL-{anio}').order_by('-id').first()
    if not ultimo:
        numero = 1
    else:
        try:
            numero = int(ultimo.codigo.split('-')[-1]) + 1
        except (ValueError, IndexError):
            numero = EtiquetaBalanza.objects.count() + 1
    return f'BAL-{anio}-{numero:05d}'


class EtiquetaBalanza(models.Model):
    codigo = models.CharField(max_length=20, unique=True, blank=True,
                 help_text='Se genera automáticamente: BAL-2026-00001')

    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='etiquetas_balanza',
    )
    producto_nombre_snapshot = models.CharField(max_length=255, blank=True)
    unidad_medida_snapshot   = models.CharField(max_length=20, blank=True)

    # Pesados/medidos y fijados en el momento de generar la etiqueta —
    # nunca se recalculan después, ni siquiera si cambia el precio del
    # producto: lo que dice la etiqueta impresa es lo que se cobra.
    cantidad        = models.DecimalField(max_digits=12, decimal_places=3)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    precio_total    = models.DecimalField(max_digits=12, decimal_places=2)

    estado = models.CharField(max_length=12, choices=EstadoEtiquetaBalanza.choices,
                 default=EstadoEtiquetaBalanza.DISPONIBLE)

    # Se completa apenas se agrega al carrito (borrador) — el estado
    # sigue en DISPONIBLE hasta que esa venta se confirma de verdad.
    # Si la venta se anula después, vuelve a None y el estado vuelve a
    # DISPONIBLE (ver Venta.anular en este mismo archivo).
    item_venta = models.OneToOneField(
        ItemVenta, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='etiqueta_balanza_origen',
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='etiquetas_balanza_creadas',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)

    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='etiquetas_balanza_anuladas',
    )
    fecha_anulacion  = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name        = 'Etiqueta de balanza'
        verbose_name_plural = 'Etiquetas de balanza'
        ordering             = ['-fecha_alta']

    def __str__(self):
        return f'{self.codigo} — {self.producto_nombre_snapshot} ({self.cantidad})'

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = _generar_codigo_etiqueta_balanza()
        super().save(*args, **kwargs)


# ══════════════════════════════════════════════════════════════════
#  PAGO DE VENTA — soporta pago dividido (ej: mitad efectivo, mitad transferencia)
# ══════════════════════════════════════════════════════════════════

class TarjetaPago(models.Model):
    """
    Tarjeta o billetera con la que puede pagar un CLIENTE (Visa, Mastercard,
    Naranja X, Mercado Pago, Personal Pay, Ualá, etc.) — es el eje real del
    recargo (ver PagoVenta/RecargoMedioPago), independiente de si el
    negocio tiene o no una CuentaCaja propia con ese mismo nombre.

    Por qué está separado de CuentaCaja: `CuentaCaja` es "a cuál de MIS
    cuentas entra la plata de verdad" (para que la caja grande cuadre).
    `TarjetaPago` es "con qué me pagó el cliente" (para saber qué recargo
    corresponde). No son lo mismo — un negocio puede no tener cuenta propia
    en Personal Pay y sin embargo un cliente pagarle desde ahí (la plata cae
    igual en su cuenta bancaria de siempre); y una tarjeta de crédito PROPIA
    del negocio para pagarle a proveedores (`CuentaCaja.es_credito=True`)
    nunca debería poder tener un recargo configurado, porque no recibe
    pagos de clientes — con el viejo modelo (recargo atado a CuentaCaja)
    ambos casos rompían.
    """
    nombre = models.CharField(max_length=100, unique=True)
    acepta_debito       = models.BooleanField(default=True)
    acepta_credito      = models.BooleanField(default=True)
    acepta_qr           = models.BooleanField(default=True)
    acepta_transferencia = models.BooleanField(default=True)
    activa = models.BooleanField(default=True)
    orden  = models.PositiveSmallIntegerField(default=0)
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Tarjeta/billetera de pago'
        verbose_name_plural = 'Tarjetas/billeteras de pago'
        ordering            = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


class PagoVenta(models.Model):
    """
    Una línea de pago de una venta. Una venta puede tener varias
    líneas (pago dividido entre distintos medios). La suma en pesos
    de todas las líneas (ver monto_ars) debe igualar venta.total al
    confirmar — la venta en sí siempre está expresada en pesos.

    `cuenta`: a qué CuentaCaja real se acredita este pago. Para
    medio=efectivo se resuelve sola (la cuenta Efectivo en pesos —
    el cierre de turno en caja diaria todavía cuenta el efectivo como
    un único total en ARS, sin desglose por moneda, así que el
    efectivo físico no admite otra moneda por ahora). Para el resto
    (transferencia/débito/crédito/QR) la elige quien confirma la
    venta, y puede ser una cuenta en dólares o euros — típico caso:
    "en Argentina se acepta cualquier moneda si ambas partes están
    de acuerdo". Sin esto, todo lo que no era efectivo terminaba en
    una cuenta genérica por nombre de medio al cerrar el turno (ver
    TurnoCaja.cerrar en caja/models.py).

    `tarjeta`: con qué TarjetaPago pagó el CLIENTE — un dato aparte de
    `cuenta` (ver TarjetaPago.__doc__). Define el recargo. Puede quedar
    vacío si esa venta no tuvo recargo asociado.

    `cotizacion`: solo se completa cuando `cuenta` NO es en pesos —
    cuántos pesos vale 1 unidad de esa moneda, según lo acordado en
    el momento del cobro (no hay ninguna fuente automática de tipo de
    cambio en el sistema). `monto` queda siempre en la moneda de
    `cuenta` (lo que realmente se acreditó ahí); `monto_ars` es el
    equivalente en pesos usado para validar que los pagos cubren
    venta.total.
    """
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='pagos')
    medio = models.CharField(max_length=20, choices=MedioPago.choices, default=MedioPago.EFECTIVO)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    cuenta = models.ForeignKey(
        'caja.CuentaCaja', on_delete=models.PROTECT,
        null=True, blank=True, related_name='pagos_venta',
    )
    tarjeta = models.ForeignKey(
        TarjetaPago, on_delete=models.PROTECT,
        null=True, blank=True, related_name='pagos_venta',
    )
    cotizacion = models.DecimalField(
        'Cotización', max_digits=12, decimal_places=4, null=True, blank=True,
        help_text='Pesos por unidad de la moneda de la cuenta. Solo aplica si la cuenta no es en pesos.',
    )

    # ── Recargo por medio de pago (débito/crédito/QR/transferencia) ──
    # Snapshot del recargo vigente en RecargoMedioPago al momento de
    # cobrar (mismo criterio que ItemVenta.alicuota_iva: si el recargo
    # configurado cambia después, este pago ya cobrado no debe cambiar).
    # `monto` de arriba YA incluye `recargo_monto` — es lo que
    # realmente se acredita en `cuenta` (ver sincronizar_movimiento_venta
    # en caja/models.py, que usa `monto` tal cual). `monto_base` es la
    # porción que corresponde al precio de venta en sí.
    cantidad_pagos = models.PositiveSmallIntegerField(
        'Cantidad de pagos', default=1,
        help_text='Plan de pagos de la tarjeta de crédito (1, 3, 6...). Siempre 1 para los demás medios.',
    )
    nombre_plan = models.CharField(
        'Nombre del plan', max_length=60, blank=True,
        help_text='Nombre comercial del plan (ej. "Plan Z"), snapshot de RecargoMedioPago.nombre_plan.',
    )
    recargo_pct = models.DecimalField(
        'Recargo %', max_digits=5, decimal_places=2, default=Decimal('0'),
        help_text='Porcentaje de recargo aplicado a esta línea, snapshot de RecargoMedioPago.',
    )
    recargo_monto = models.DecimalField(
        'Recargo', max_digits=14, decimal_places=2, default=Decimal('0'),
        help_text='Monto de recargo (en la moneda de `cuenta`), ya incluido en `monto`.',
    )

    class Meta:
        verbose_name        = 'Pago de venta'
        verbose_name_plural = 'Pagos de venta'
        ordering            = ['id']

    def __str__(self):
        return f'{self.venta.numero} — {self.get_medio_display()}: {self.monto}'

    @property
    def monto_base(self):
        """Porción de `monto` que corresponde al precio de venta, sin el recargo."""
        return self.monto - self.recargo_monto

    @property
    def etiqueta_plan(self):
        """"Plan Z (3 pagos)" si tiene nombre, si no simplemente "3 pagos"."""
        pagos = f'{self.cantidad_pagos} pago{"" if self.cantidad_pagos == 1 else "s"}'
        return f'{self.nombre_plan} ({pagos})' if self.nombre_plan else pagos

    @property
    def monto_ars(self):
        """Equivalente en pesos de este pago (monto tal cual si ya es en pesos)."""
        if self.cotizacion and self.cuenta_id and self.cuenta.moneda != Moneda.ARS:
            return (self.monto * self.cotizacion).quantize(Decimal('0.01'))
        return self.monto


class RecargoMedioPago(models.Model):
    """
    Recargo que cobra una TarjetaPago (Posnet, Mercado Pago, Naranja X,
    Personal Pay, etc.) por medio de pago — ver TarjetaPago.__doc__ para
    por qué esto vive sobre la tarjeta/billetera del CLIENTE y no sobre
    una CuentaCaja propia del negocio. Dentro de una tarjeta, el recargo
    varía por medio y, si es crédito, por la cantidad de pagos (plan).
    Por eso se configura por (tarjeta, medio, cantidad_pagos).

    `cantidad_pagos` solo tiene sentido > 1 para medio=CREDITO (planes de
    pago tipo "3 pagos", "6 pagos" — a propósito NO se llama "cuotas" acá:
    ese nombre ya lo usa MedioPago.CUOTAS para la financiación propia del
    comercio, un concepto sin relación con esto). Para débito/QR/
    transferencia siempre es 1: un único recargo fijo por tarjeta.
    """
    MEDIOS_CON_RECARGO = ['debito', 'credito', 'qr', 'transferencia']

    tarjeta = models.ForeignKey(
        TarjetaPago, on_delete=models.CASCADE, related_name='recargos',
    )
    medio = models.CharField(
        max_length=20,
        choices=[(v, l) for v, l in MedioPago.choices if v in ['debito', 'credito', 'qr', 'transferencia']],
    )
    cantidad_pagos = models.PositiveSmallIntegerField(
        'Cantidad de pagos', default=1,
        help_text='Solo aplica a Crédito. Para los demás medios siempre es 1.',
    )
    # Nombre comercial del plan (ej. "Plan Z", "Ahora 12") — opcional.
    # Muchas tarjetas venden sus planes de cuotas con un nombre propio
    # que el dueño del negocio conoce, pero no necesariamente sabe (ni
    # necesita saber) a cuántos pagos exactos corresponde ese nombre en
    # todos los casos — `cantidad_pagos` sigue siendo el dato que se usa
    # para calcular/mostrar, esto es solo una etiqueta más reconocible.
    nombre_plan = models.CharField('Nombre del plan', max_length=60, blank=True)
    recargo_pct = models.DecimalField('Recargo %', max_digits=5, decimal_places=2)
    activo = models.BooleanField(default=True)
    orden  = models.PositiveSmallIntegerField(default=0)

    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Recargo por medio de pago'
        verbose_name_plural = 'Recargos por medio de pago'
        ordering            = ['tarjeta', 'medio', 'cantidad_pagos']
        unique_together     = [('tarjeta', 'medio', 'cantidad_pagos')]

    def __str__(self):
        plan = f' ({self.etiqueta_plan})' if self.medio == MedioPago.CREDITO else ''
        return f'{self.tarjeta.nombre} — {self.get_medio_display()}{plan}: {self.recargo_pct}%'

    @property
    def etiqueta_plan(self):
        """"Plan Z (3 pagos)" si tiene nombre, si no simplemente "3 pagos"."""
        pagos = f'{self.cantidad_pagos} pago{"" if self.cantidad_pagos == 1 else "s"}'
        return f'{self.nombre_plan} ({pagos})' if self.nombre_plan else pagos


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
#  FACTURACIÓN ELECTRÓNICA (ARCA)
# ══════════════════════════════════════════════════════════════════

class TipoComprobante(models.IntegerChoices):
    """Códigos de comprobante de ARCA (los que exige WSFEv1, no inventados)."""
    FACTURA_A = 1, 'Factura A'
    FACTURA_B = 6, 'Factura B'
    FACTURA_C = 11, 'Factura C'


class ComprobanteArca(models.Model):
    """
    Comprobante fiscal (CAE) obtenido de ARCA para una Venta. 1-a-1: cada
    venta facturada electrónicamente tiene, a lo sumo, un comprobante.
    Se crea únicamente después de que Venta.confirmar() ya hizo commit (ver
    core/services_arca/wsfe.py) — nunca dentro de la misma transacción que
    descuenta stock, porque un CAE no se puede "deshacer" si algo más falla.
    """
    venta = models.OneToOneField(
        Venta, on_delete=models.PROTECT, related_name='comprobante_arca',
    )
    tipo_comprobante = models.PositiveSmallIntegerField(choices=TipoComprobante.choices)
    punto_venta = models.PositiveIntegerField()
    numero = models.PositiveIntegerField()

    cae = models.CharField(max_length=20)
    cae_vencimiento = models.DateField()
    ambiente = models.CharField(max_length=12, choices=AmbienteArca.choices)

    # — Receptor (comprador), snapshot al momento de facturar —
    doc_tipo = models.PositiveSmallIntegerField(help_text='Código AFIP: 80=CUIT, 96=DNI, 99=Consumidor Final, etc.')
    doc_nro = models.CharField(max_length=20, blank=True)
    condicion_iva_receptor_id = models.PositiveSmallIntegerField(
        help_text='Código de FEParamGetCondicionIvaReceptor (5=Consumidor Final, etc.)',
    )

    # — Importes (snapshot, no recalcular desde la Venta más adelante) —
    importe_total = models.DecimalField(max_digits=14, decimal_places=2)
    importe_neto = models.DecimalField(max_digits=14, decimal_places=2)
    importe_iva = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    creado_el = models.DateTimeField(auto_now_add=True)
    respuesta_json = models.JSONField(
        blank=True, null=True,
        help_text='Respuesta cruda de ARCA (FECAESolicitar), para auditoría/debug.',
    )

    class Meta:
        verbose_name = 'Comprobante ARCA'
        verbose_name_plural = 'Comprobantes ARCA'

    def __str__(self):
        return f'{self.get_tipo_comprobante_display()} {self.punto_venta:04d}-{self.numero:08d} (CAE {self.cae})'


# ══════════════════════════════════════════════════════════════════
#  HELPER — número correlativo
# ══════════════════════════════════════════════════════════════════

HORAS_DESCARTE_BORRADOR = 24


def descartar_borradores_vencidos(excluir_pk=None):
    """
    Limpia los borradores abandonados hace más de HORAS_DESCARTE_BORRADOR
    horas. Dos casos, tratados distinto:

    1. Borrador nuevo genuino (`fecha_anulacion` vacía — nunca fue una
       venta real): el caso típico es alguien que salió de la pantalla de
       detalle sin tocar "Cancelar venta". Nunca tocó stock ni caja, así
       que borrarlo directo es seguro.
    2. Venta ANULADA reactivada para editar (ver `reactivar()`, que sí
       tiene `fecha_anulacion`) y abandonada sin terminar — por ejemplo,
       alguien tocó "Editar" en el Historial y después cerró la pestaña
       en vez de guardar o cancelar. Acá NO se borra (tiene ItemVenta/
       PagoVenta históricos reales detrás) — se revierte a ANULADA, tal
       como estaba antes de tocar "Editar", para que vuelva a aparecer en
       el Historial. Se mide el tiempo abandonado con `fecha_modificacion`
       (que `reactivar()` actualiza a propósito), no `fecha_alta` (que es
       la fecha original de la venta, de hace semanas quizás).

    `excluir_pk` es el borrador que se está por editar en esta misma
    request (ver NuevaVentaView) — nunca hay que tocar el que el usuario
    está a punto de retomar, aunque esté vencido.

    No hay scheduler corriendo dentro de Django, así que esto se llama
    perezosamente al entrar a "Nueva venta" — mismo criterio que
    procesar_lotes_vencidos() en compras/models.py.
    """
    umbral = timezone.now() - timedelta(hours=HORAS_DESCARTE_BORRADOR)

    nuevos = Venta.objects.filter(
        estado=EstadoVenta.BORRADOR, fecha_alta__lt=umbral, fecha_anulacion__isnull=True
    )
    reactivados_abandonados = Venta.objects.filter(
        estado=EstadoVenta.BORRADOR, fecha_modificacion__lt=umbral, fecha_anulacion__isnull=False
    )
    if excluir_pk:
        nuevos = nuevos.exclude(pk=excluir_pk)
        reactivados_abandonados = reactivados_abandonados.exclude(pk=excluir_pk)

    for venta in nuevos:
        venta.delete()
    for venta in reactivados_abandonados:
        venta.estado = EstadoVenta.ANULADA
        venta.save(update_fields=['estado'])


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