from datetime import timedelta
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from productos.models import Moneda


# ══════════════════════════════════════════════════════════════════
#  CHOICES
# ══════════════════════════════════════════════════════════════════

class TipoCaja(models.TextChoices):
    """
    Distingue a qué libro pertenece un movimiento.
    GRANDE: contabilidad general del negocio (todo: ventas, compras,
            depósitos, extracciones, gastos, etc.)
    DIARIA: lo que se factura/cobra en el día a día (caja chica).
    """
    GRANDE = 'grande', 'Caja grande'
    DIARIA = 'diaria', 'Caja diaria'


class TipoCuenta(models.TextChoices):
    EFECTIVO = 'efectivo', 'Efectivo'
    BANCO    = 'banco',    'Cuenta bancaria'
    OTRA     = 'otra',     'Otra'


class TipoMovimientoCaja(models.TextChoices):
    INGRESO = 'ingreso', 'Ingreso'
    EGRESO  = 'egreso',  'Egreso'


class OrigenMovimiento(models.TextChoices):
    """De dónde sale el movimiento. Sirve para trazabilidad y para
    saber si fue generado automáticamente o cargado a mano."""
    VENTA   = 'venta',   'Venta'
    COMPRA  = 'compra',  'Compra'
    MANUAL  = 'manual',  'Carga manual'
    AJUSTE  = 'ajuste',  'Ajuste'
    TRANSACCION = 'transaccion', 'Transacción interna'
    DEUDA       = 'deuda',       'Deuda (acreditación de préstamo)'
    CUOTA_DEUDA = 'cuota_deuda', 'Cuota de deuda'
    CHEQUE      = 'cheque',      'Cheque'


# ══════════════════════════════════════════════════════════════════
#  CUENTA DE CAJA
#  (Efectivo, Banco Santander ARS, Banco USD, etc.)
# ══════════════════════════════════════════════════════════════════

class CuentaCaja(models.Model):
    """
    Una "cuenta" dentro de la caja grande: efectivo, banco, etc.
    Cada cuenta opera en UNA moneda. Si el negocio maneja efectivo
    en ARS y en USD, son dos cuentas distintas (ej: "Efectivo ARS",
    "Efectivo USD"), igual que pasaría con bancos.

    El saldo NO se almacena: se calcula en caliente sumando los
    movimientos (igual que el stock se reconstruye a partir de
    MovimientoStock, pero acá preferimos no cachear el total para
    evitar inconsistencias mientras el modelo de caja es nuevo;
    se puede optimizar con un campo cacheado más adelante si hace
    falta por performance).
    """

    nombre  = models.CharField(max_length=100)
    tipo    = models.CharField(max_length=20, choices=TipoCuenta.choices,
                  default=TipoCuenta.EFECTIVO)
    moneda  = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)
    caja    = models.CharField(max_length=10, choices=TipoCaja.choices,
                  default=TipoCaja.GRANDE,
                  help_text='A qué libro pertenece esta cuenta (grande o diaria).')

    # ── Identificación de la cuenta (tarjetas, billeteras, bancos) ──
    titular      = models.CharField(max_length=150, blank=True,
                       help_text='Solo si difiere del titular del negocio.')
    terminada_en = models.CharField(max_length=20, blank=True,
                       help_text='Últimos 4 dígitos, alias o CBU corto. Nunca el número completo.')

    # ── Crédito ──────────────────────────────────────────────────
    # Es el único atributo que cambia comportamiento real: una compra
    # con es_credito=True no descuenta el total de inmediato, genera
    # cuotas que impactan la cuenta a medida que se pagan (ver Fase 3).
    es_credito       = models.BooleanField(default=False)
    dia_cierre       = models.PositiveSmallIntegerField(null=True, blank=True,
                           help_text='Día del mes en que cierra el resumen (1-31). Solo si es_credito.')
    dia_vencimiento  = models.PositiveSmallIntegerField(null=True, blank=True,
                           help_text='Día del mes en que vence el pago (1-31). Solo si es_credito.')

    activa  = models.BooleanField(default=True)
    notas   = models.CharField(max_length=300, blank=True)
    orden   = models.PositiveSmallIntegerField(default=0)

    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Cuenta de caja'
        verbose_name_plural = 'Cuentas de caja'
        ordering            = ['caja', 'orden', 'nombre']
        unique_together     = [('nombre', 'caja', 'moneda')]

    def __str__(self):
        return f'{self.nombre} ({self.get_moneda_display()})'

    @property
    def saldo(self):
        """Saldo actual = suma de ingresos - suma de egresos, en esta cuenta."""
        agregados = self.movimientos.aggregate(
            ingresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.INGRESO)),
            egresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.EGRESO)),
        )
        ingresos = agregados['ingresos'] or 0
        egresos  = agregados['egresos'] or 0
        return ingresos - egresos


# ══════════════════════════════════════════════════════════════════
#  CONCEPTO DE MOVIMIENTO (categoría configurable)
# ══════════════════════════════════════════════════════════════════

class ConceptoMovimiento(models.Model):
    """
    Categoría de un movimiento de caja: Venta, Compra, Gasto fijo,
    Retiro de socio, Aporte de capital, Depósito bancario, etc.

    tipo_default determina si, al elegir este concepto en la carga
    manual, el monto se sugiere como ingreso o egreso (el usuario
    puede igual elegir lo contrario si hiciera falta).

    es_sistema=True marca los conceptos que usa el propio sistema
    para generar movimientos automáticos (Venta/Compra) y que no
    deberían poder borrarse desde la UI.
    """

    nombre        = models.CharField(max_length=100, unique=True)
    tipo_default  = models.CharField(max_length=10, choices=TipoMovimientoCaja.choices,
                        default=TipoMovimientoCaja.EGRESO)
    descripcion   = models.CharField(max_length=300, blank=True)
    activo        = models.BooleanField(default=True)
    es_sistema    = models.BooleanField(default=False,
                        help_text='Concepto usado internamente por el sistema (Venta/Compra). No editable desde la UI.')
    orden         = models.PositiveSmallIntegerField(default=0)

    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Concepto de movimiento'
        verbose_name_plural = 'Conceptos de movimiento'
        ordering            = ['orden', 'nombre']

    def __str__(self):
        return self.nombre


# ══════════════════════════════════════════════════════════════════
#  MOVIMIENTO DE CAJA
# ══════════════════════════════════════════════════════════════════

class MovimientoCaja(models.Model):
    """
    Registro de un movimiento de caja (ingreso o egreso).

    Dos orígenes posibles:
    - Automático: generado por Venta.confirmar()/anular()/editar_completa()
      o Compra.confirmar()/anular()/reactivar()/editar_completa(), usando
      GenericForeignKey hacia el objeto que lo originó (venta o compra).
      Estos movimientos quedan vinculados 1 a 1 con su origen mediante
      (origen, origen_id) para poder sincronizarlos si la venta/compra
      se edita o anula (ver helpers sincronizar_movimiento_* más abajo).
    - Manual: cargado a mano (depósito, extracción, gasto, etc.), sin
      objeto origen.

    Es semi-inmutable: no se "edita" un movimiento generado por una
    venta/compra (se reemplaza completo cuando la venta/compra cambia,
    igual que MovimientoStock no se edita sino que se recrea). Los
    movimientos manuales sí pueden editarse desde la UI mientras no
    tengan origen automático.
    """

    caja    = models.CharField(max_length=10, choices=TipoCaja.choices,
                  default=TipoCaja.GRANDE)
    cuenta  = models.ForeignKey(CuentaCaja, on_delete=models.PROTECT,
                  related_name='movimientos')
    concepto = models.ForeignKey(ConceptoMovimiento, on_delete=models.PROTECT,
                  related_name='movimientos')

    tipo    = models.CharField(max_length=10, choices=TipoMovimientoCaja.choices)
    monto   = models.DecimalField(max_digits=14, decimal_places=2,
                  help_text='Siempre positivo. El campo "tipo" determina si suma o resta.')
    moneda  = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)

    fecha   = models.DateField(help_text='Fecha contable del movimiento (puede diferir de fecha_alta).')
    descripcion = models.CharField(max_length=300, blank=True)
    referencia  = models.CharField(max_length=100, blank=True,
                      help_text='N° de venta, compra, comprobante, etc.')

    # ── Trazabilidad: origen automático (opcional) ─────────────────
    origen    = models.CharField(max_length=15, choices=OrigenMovimiento.choices,
                    default=OrigenMovimiento.MANUAL)
    origen_app  = models.CharField(max_length=20, blank=True,
                      help_text="App del objeto origen, ej. 'ventas' o 'compras'.")
    origen_id   = models.PositiveIntegerField(null=True, blank=True,
                      help_text='PK de la Venta/Compra que generó este movimiento.')

    # ── Auditoría ────────────────────────────────────────────────
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='movimientos_caja_creados',
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Movimiento de caja'
        verbose_name_plural = 'Movimientos de caja'
        ordering            = ['-fecha', '-fecha_alta']
        indexes = [
            models.Index(fields=['origen', 'origen_app', 'origen_id']),
            models.Index(fields=['caja', 'fecha']),
        ]

    def __str__(self):
        signo = '+' if self.tipo == TipoMovimientoCaja.INGRESO else '-'
        return f'{self.get_caja_display()} | {signo}{self.monto} {self.moneda} | {self.concepto} | {self.fecha:%d/%m/%Y}'

    def save(self, *args, **kwargs):
        if not self.moneda and self.cuenta_id:
            self.moneda = self.cuenta.moneda
        super().save(*args, **kwargs)

    @property
    def es_automatico(self):
        return self.origen != OrigenMovimiento.MANUAL

    @property
    def es_editable(self):
        """Solo los movimientos manuales se editan/eliminan libremente desde la UI."""
        return self.origen == OrigenMovimiento.MANUAL


# ══════════════════════════════════════════════════════════════════
#  HELPERS DE SINCRONIZACIÓN — usados por Venta y Compra
# ══════════════════════════════════════════════════════════════════
#
# Patrón: cada vez que una Venta/Compra cambia de estado de forma que
# afecta el balance (confirmar, anular, reactivar, editar_completa),
# llama a sincronizar_movimiento_venta()/sincronizar_movimiento_compra().
# La función borra el movimiento previo asociado a ese objeto (si existía)
# y crea el nuevo según el estado actual. Así el movimiento de caja
# siempre refleja el estado real de la venta/compra, sin duplicarse.
#
# Esto requiere una CuentaCaja y un ConceptoMovimiento "default" para
# automáticos. Se resuelven por convención (ver _cuenta_efectivo_default
# y _concepto_default) y son configurables vía CuentaCaja/ConceptoMovimiento
# (es_sistema=True para los conceptos).

CONCEPTO_VENTA_NOMBRE  = 'Venta'
CONCEPTO_COMPRA_NOMBRE = 'Compra'
CUENTA_EFECTIVO_DEFAULT_NOMBRE = 'Efectivo'


def _cuenta_default(moneda=Moneda.ARS, caja=TipoCaja.GRANDE):
    """
    Cuenta a la que se imputan los movimientos automáticos de Venta/Compra
    cuando no se especifica una cuenta puntual (ej: no hay todavía mapeo
    medio_pago → cuenta). Por ahora siempre es "Efectivo" en la moneda
    del movimiento. Se crea sola la primera vez que hace falta.
    """
    cuenta, _creada = CuentaCaja.objects.get_or_create(
        nombre=CUENTA_EFECTIVO_DEFAULT_NOMBRE,
        caja=caja,
        moneda=moneda,
        defaults={'tipo': TipoCuenta.EFECTIVO},
    )
    return cuenta


def asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE):
    """
    Garantiza que la cuenta Efectivo exista en las tres monedas
    (ARS/USD/EUR) para esa caja. Hay que llamarla en TODO lugar que
    arma un selector de "a qué cuenta se paga/cobra" (Ventas, Compras,
    Gastos, Transacciones) — si no, en una base de datos nueva el
    selector aparece vacío hasta que por casualidad algo más
    (ej: visitar Caja Grande) termine creando Efectivo primero.
    """
    for moneda, _label in Moneda.choices:
        _cuenta_default(moneda=moneda, caja=caja)


def _concepto_default(nombre, tipo_default):
    concepto, _creado = ConceptoMovimiento.objects.get_or_create(
        nombre=nombre,
        defaults={'tipo_default': tipo_default, 'es_sistema': True},
    )
    return concepto


def _cuenta_grande_para_medio_pago(medio_codigo, medio_label, moneda=Moneda.ARS):
    """
    Resuelve la CuentaCaja de caja GRANDE donde debe aterrizar el dinero
    de un medio de pago al cerrar un turno.

    - 'efectivo' → la cuenta "Efectivo" de siempre (misma que usan
      compras, gastos y turnos para no fragmentar el efectivo).
    - Cualquier otro medio (transferencia, débito, QR, etc.) → una
      cuenta tipo BANCO nombrada igual que el medio de pago. Se crea
      sola la primera vez que aparece ese medio.
    """
    if medio_codigo == 'efectivo':
        return _cuenta_default(moneda=moneda, caja=TipoCaja.GRANDE)

    cuenta, _creada = CuentaCaja.objects.get_or_create(
        nombre=medio_label,
        caja=TipoCaja.GRANDE,
        moneda=moneda,
        defaults={'tipo': TipoCuenta.BANCO},
    )
    return cuenta


@transaction.atomic
def _borrar_movimiento_origen(origen_app, origen_tipo, origen_id):
    MovimientoCaja.objects.filter(
        origen=origen_tipo, origen_app=origen_app, origen_id=origen_id,
    ).delete()


@transaction.atomic
def sincronizar_movimiento_venta(venta):
    """
    Sincroniza los MovimientoCaja asociados a una Venta con su estado actual.

    - BORRADOR: no genera movimiento (no es plata real todavía).
    - CONFIRMADA: un ingreso en CAJA GRANDE por cada línea de pago que
      NO sea efectivo (transferencia/débito/crédito/QR), cada una en
      su cuenta real (PagoVenta.cuenta) — esa plata ya está o no está
      en la cuenta digital en el momento del cobro, no hay nada que
      contar físicamente, así que no tiene sentido esperar al cierre
      de turno para que aparezca. Un negocio abierto 24hs vería su
      Mercado Pago/banco desactualizado por horas si no fuera así.
    - El pago en EFECTIVO es la excepción: no genera nada acá. Sigue
      esperando al cierre de turno (ver TurnoCaja.cerrar), que es el
      único momento en que se concilia contra lo contado físicamente
      — por eso "caja diaria" existe como concepto, solo para eso.
    - ANULADA: no debe quedar ningún movimiento (la venta no se concretó).

    Se llama desde Venta.confirmar(), Venta.anular() y
    Venta.editar_completa() (que internamente re-confirma).
    """
    _borrar_movimiento_origen('ventas', OrigenMovimiento.VENTA, venta.pk)

    # Import local para evitar dependencia circular a nivel de módulo
    from ventas.models import EstadoVenta, MedioPago

    if venta.estado != EstadoVenta.CONFIRMADA:
        return []

    concepto = _concepto_default(CONCEPTO_VENTA_NOMBRE, TipoMovimientoCaja.INGRESO)

    pagos_no_efectivo = (
        venta.pagos
        .exclude(medio=MedioPago.EFECTIVO)
        .exclude(cuenta__isnull=True)
        .select_related('cuenta')
    )

    movimientos = []
    for pago in pagos_no_efectivo:
        movimientos.append(MovimientoCaja.objects.create(
            caja        = TipoCaja.GRANDE,
            cuenta      = pago.cuenta,
            concepto    = concepto,
            tipo        = TipoMovimientoCaja.INGRESO,
            monto       = pago.monto,
            moneda      = pago.cuenta.moneda,
            fecha       = venta.fecha,
            descripcion = f'Venta {venta.numero} ({pago.get_medio_display()})',
            referencia  = venta.numero,
            origen      = OrigenMovimiento.VENTA,
            origen_app  = 'ventas',
            origen_id   = venta.pk,
            creado_por  = venta.confirmado_por,
        ))
    return movimientos


@transaction.atomic
def sincronizar_movimiento_compra(compra):
    """
    Sincroniza los MovimientoCaja asociados a una Compra con su estado
    actual.

    - BORRADOR: no genera movimiento.
    - CONFIRMADA: un egreso en CAJA GRANDE por cada línea de pago
      (PagoCompra), cada una en su cuenta real. A diferencia de
      Ventas, acá no hay turno de por medio — toda línea (incluida
      efectivo) impacta caja grande de inmediato, como siempre lo
      hizo Compras. Excepción: las líneas pagadas con tarjeta de
      crédito (medio=CREDITO) NO generan egreso acá — esa plata no
      sale de la caja al confirmar la compra, sale de a poco cuando
      se confirma cada CuotaDeuda de la Deuda asociada (ver
      sincronizar_movimiento_cuota).
    - ANULADA: no debe quedar movimiento (se revirtió, no hubo gasto neto).

    Se llama desde Compra.confirmar(), Compra.anular(), Compra.reactivar()
    y Compra.editar_completa().
    """
    _borrar_movimiento_origen('compras', OrigenMovimiento.COMPRA, compra.pk)

    from compras.models import EstadoCompra, MedioPagoCompra

    if compra.estado != EstadoCompra.CONFIRMADA:
        return []

    concepto = _concepto_default(CONCEPTO_COMPRA_NOMBRE, TipoMovimientoCaja.EGRESO)

    movimientos = []
    pagos_caja = (
        compra.pagos
        .exclude(cuenta__isnull=True)
        .exclude(medio=MedioPagoCompra.CREDITO)
        .select_related('cuenta')
    )
    for pago in pagos_caja:
        movimientos.append(MovimientoCaja.objects.create(
            caja        = TipoCaja.GRANDE,
            cuenta      = pago.cuenta,
            concepto    = concepto,
            tipo        = TipoMovimientoCaja.EGRESO,
            monto       = pago.monto,
            moneda      = pago.cuenta.moneda,
            fecha       = compra.fecha,
            descripcion = f'Compra {compra.numero} ({pago.get_medio_display()})',
            referencia  = compra.numero,
            origen      = OrigenMovimiento.COMPRA,
            origen_app  = 'compras',
            origen_id   = compra.pk,
            creado_por  = compra.creado_por,
        ))
    return movimientos


def _normalizar_cajas(cajas):
    """
    Normaliza el parámetro `cajas` de TurnoCaja.abrir()/cerrar() a una
    lista de dicts [{'nombre': ..., 'monto': ..., 'id': <opcional>}, ...].

    Acepta:
    - Un número (Decimal/int/float/str): compatibilidad con negocios de
      una sola caja — se guarda como una única caja llamada "Caja 1".
    - Una lista de dicts [{'nombre': 'Caja 1', 'monto': 100}, ...]: para
      negocios con varias cajas físicas abiertas en simultáneo. El 'id'
      es opcional y se usa en el cierre para saber a qué CajaFisicaTurno
      de la apertura corresponde cada monto declarado.
    """
    if isinstance(cajas, (list, tuple)):
        normalizado = []
        for i, c in enumerate(cajas):
            nombre = (c.get('nombre') or f'Caja {i + 1}').strip() or f'Caja {i + 1}'
            normalizado.append({
                'nombre': nombre,
                'monto': c.get('monto', 0) or 0,
                'id': c.get('id'),
            })
        return normalizado or [{'nombre': 'Caja 1', 'monto': 0, 'id': None}]
    # Compatibilidad: se pasó un solo número en vez de una lista
    return [{'nombre': 'Caja 1', 'monto': cajas, 'id': None}]


class EstadoTurno(models.TextChoices):
    ABIERTO = 'abierto', 'Abierto'
    CERRADO = 'cerrado', 'Cerrado'


class TurnoCaja(models.Model):
    """
    Representa un turno de caja diaria.
    
    - Al abrir un turno, se especifica el monto inicial en efectivo que se toma
      de la caja grande. Esto genera un egreso en caja grande y un ingreso en
      caja diaria.
    - Al cerrar un turno, el monto inicial se devuelve a caja grande (ingreso
      en caja grande, egreso en caja diaria).
    - Solo se permite efectivo para apertura/cierre (lo que se contabiliza a mano).
    - Las ventas requieren un turno abierto para poder realizarse.
    """
    
    numero = models.PositiveIntegerField()
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=10, choices=EstadoTurno.choices, default=EstadoTurno.ABIERTO)
    
    # Monto inicial en efectivo (tomado de caja grande)
    monto_inicial_efectivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    # Monto final en efectivo al cierre (declarado por el cajero)
    monto_final_efectivo = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    
    # Diferencia entre lo que debería haber y lo que hay (para control)
    diferencia_efectivo = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Snapshot de los totales al momento del cierre (por medio de pago,
    # total recaudado, ganancia). Se guarda para que el historial de un
    # turno ya cerrado NUNCA cambie si después se edita/anula una venta
    # vieja: el historial contable debe quedar congelado en el tiempo.
    # Mientras el turno está ABIERTO, los totales se siguen calculando
    # en caliente (ver propiedad totales_medio_pago).
    totales_cierre = models.JSONField(null=True, blank=True, default=None,
                        help_text='Snapshot de totales_medio_pago/total_recaudado/ganancia al cerrar el turno.')

    # Auditoría
    abierto_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='turnos_abiertos',
    )
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='turnos_cerrados',
    )
    
    notas = models.TextField(blank=True, help_text='Notas del turno')
    
    class Meta:
        verbose_name = 'Turno de caja'
        verbose_name_plural = 'Turnos de caja'
        ordering = ['-fecha_apertura']
        constraints = [
            # Garantiza a nivel de base de datos que nunca haya dos
            # turnos ABIERTOS a la vez, incluso si dos requests de
            # "abrir turno" pasan el chequeo de turno_actual() casi al
            # mismo tiempo (índice único parcial: solo restringe filas
            # con estado=ABIERTO, no afecta a los turnos cerrados).
            models.UniqueConstraint(
                fields=['estado'],
                condition=Q(estado=EstadoTurno.ABIERTO),
                name='unico_turno_abierto',
            ),
        ]
    
    def __str__(self):
        return f'Turno #{self.numero} - {self.fecha_apertura:%d/%m/%Y %H:%M}'
    
    @property
    def totales_medio_pago(self):
        """
        Totales recaudados por medio de pago.

        Si el turno ya está CERRADO y tiene snapshot guardado, se
        devuelve ese snapshot congelado (para que el historial no
        cambie retroactivamente). Si está ABIERTO (o por algún motivo
        no tiene snapshot todavía), se calcula en caliente.
        """
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return {
                k: Decimal(str(v))
                for k, v in self.totales_cierre.get('totales_medio_pago', {}).items()
            }
        if not hasattr(self, '_totales_medio_pago'):
            self._totales_medio_pago = self.calcular_totales_por_medio_pago()
        return self._totales_medio_pago

    @property
    def total_recaudado(self):
        return sum(self.totales_medio_pago.values())

    @property
    def efectivo_ventas(self):
        return self.totales_medio_pago.get('efectivo', 0)

    @property
    def efectivo_total(self):
        return (self.monto_inicial_efectivo or 0) + self.efectivo_ventas

    @property
    def ganancia_turno(self):
        return self.total_recaudado - (self.monto_inicial_efectivo or 0)

    @property
    def alerta_diferencia(self):
        """True si al cerrar hubo una diferencia entre lo esperado y lo declarado."""
        return self.diferencia_efectivo is not None and abs(self.diferencia_efectivo) >= Decimal('0.01')

    @property
    def mensaje_alerta(self):
        if not self.alerta_diferencia:
            return None
        signo = 'sobra' if self.diferencia_efectivo > 0 else 'falta'
        return (
            f'¡Atención! En el turno #{self.numero} {signo} '
            f'{abs(self.diferencia_efectivo)} en efectivo respecto de lo esperado. '
            f'Revisar con urgencia.'
        )

    
    @classmethod
    def turno_actual(cls):
        """Devuelve el turno abierto actual, o None si no hay ninguno."""
        return cls.objects.filter(estado=EstadoTurno.ABIERTO).first()
    
    @classmethod
    def obtener_siguiente_numero(cls):
        """Obtiene el siguiente número de turno."""
        ultimo = cls.objects.order_by('-numero').first()
        return (ultimo.numero + 1) if ultimo else 1

    @classmethod
    def turno_que_contiene(cls, momento):
        """
        Devuelve el turno (abierto o cerrado) cuya ventana de tiempo
        contiene `momento`, o None si no cae en ningún turno (ej: dato
        viejo previo a la existencia de turnos). Se usa para saber si
        una venta puntual pertenece a un turno ya cerrado y así decidir
        si se la puede eliminar o solo anular (ver Venta.delete()).
        """
        return cls.objects.filter(
            fecha_apertura__lte=momento,
        ).filter(
            Q(fecha_cierre__isnull=True) | Q(fecha_cierre__gte=momento)
        ).order_by('-fecha_apertura').first()
    
    @classmethod
    def abrir(cls, cajas, usuario):
        """
        Abre un nuevo turno.

        `cajas`: lista de dicts [{'nombre': 'Caja 1', 'monto': 100}, ...]
        — una fila por caja física declarada. También acepta un número
        simple por compatibilidad (negocio de una sola caja).

        El monto que se resta de caja grande y el que queda en
        monto_inicial_efectivo es SIEMPRE la SUMA de todas las cajas
        declaradas. El resto del sistema (ventas, cierre, alertas, caja
        grande) sigue viendo un único total, exactamente como antes —
        el desglose por caja es puramente declarativo/informativo (ver
        CajaFisicaTurno).
        """
        from django.db import transaction, IntegrityError

        cajas = _normalizar_cajas(cajas)
        monto_inicial_total = sum(Decimal(str(c['monto'])) for c in cajas)

        with transaction.atomic():
            # Verificar que no haya un turno abierto (mensaje de error
            # rápido en el caso común). La garantía real contra dos
            # aperturas simultáneas es el índice único parcial
            # 'unico_turno_abierto' en Meta.constraints: si dos
            # requests pasan este chequeo casi al mismo tiempo, el
            # segundo turno.save() de abajo va a fallar con
            # IntegrityError en vez de crear un segundo turno abierto.
            if cls.turno_actual():
                raise ValueError('Ya existe un turno abierto')

            # Crear el turno
            turno = cls(
                numero=cls.obtener_siguiente_numero(),
                monto_inicial_efectivo=monto_inicial_total,
                estado=EstadoTurno.ABIERTO,
                abierto_por=usuario,
            )
            try:
                turno.save()
            except IntegrityError:
                raise ValueError('Ya existe un turno abierto')

            CajaFisicaTurno.objects.bulk_create([
                CajaFisicaTurno(
                    turno=turno, nombre=c['nombre'], orden=i,
                    monto_inicial=Decimal(str(c['monto'])),
                )
                for i, c in enumerate(cajas)
            ])
            
            # Registrar egreso en caja grande (dinero que sale para iniciar turno)
            if monto_inicial_total > 0:
                cuenta_efectivo = _cuenta_default(moneda=Moneda.ARS, caja=TipoCaja.GRANDE)
                concepto = _concepto_default('Apertura de turno', TipoMovimientoCaja.EGRESO)

                detalle_cajas = (
                    ' (' + ', '.join(f"{c['nombre']}: {c['monto']}" for c in cajas) + ')'
                    if len(cajas) > 1 else ''
                )
                
                MovimientoCaja.objects.create(
                    caja=TipoCaja.GRANDE,
                    cuenta=cuenta_efectivo,
                    concepto=concepto,
                    tipo=TipoMovimientoCaja.EGRESO,
                    monto=monto_inicial_total,
                    moneda=Moneda.ARS,
                    fecha=turno.fecha_apertura.date(),
                    descripcion=f'Apertura turno #{turno.numero}' + detalle_cajas,
                    referencia=f'Turno #{turno.numero}',
                    origen=OrigenMovimiento.AJUSTE,
                    origen_app='caja',
                    origen_id=turno.pk,
                    creado_por=usuario,
                )
            
            return turno
    
    def _ventas_en_turno(self):
        """Ventas confirmadas dentro de la ventana horaria de este turno."""
        from ventas.models import Venta
        return Venta.objects.filter(
            estado='confirmada',
            fecha_alta__gte=self.fecha_apertura,
            fecha_alta__lte=self.fecha_cierre if self.fecha_cierre else timezone.now()
        )

    def calcular_totales_por_medio_pago(self):
        """
        Calcula los totales de ventas agrupados por medio de pago
        para este turno (informativo — para el desglose que se muestra
        en pantalla y se congela en totales_cierre). Usa PagoVenta para
        soportar pagos divididos (ej: mitad efectivo, mitad transferencia).
        """
        from ventas.models import MedioPago, PagoVenta

        pagos_en_turno = PagoVenta.objects.filter(venta__in=self._ventas_en_turno())

        totales = {}
        for medio, label in MedioPago.choices:
            totales[medio] = pagos_en_turno.filter(medio=medio).aggregate(
                total=Sum('monto')
            )['total'] or 0

        return totales
    
    def cerrar(self, cajas, usuario, notas=''):
        """
        Cierra el turno. Es el momento en que el EFECTIVO de un turno
        "aparece" en caja grande — el resto de medios de pago (no
        efectivo) ya impactaron caja grande al confirmarse cada venta
        (ver sincronizar_movimiento_venta): no requieren conteo físico,
        así que no tiene sentido hacerlos esperar al cierre.

        `cajas`: lista de dicts [{'id': <CajaFisicaTurno.pk opcional>,
        'nombre': 'Caja 1', 'monto': 2000}, ...] — lo que el cajero
        declara en CADA caja física al cerrar. También acepta un
        número simple (compatibilidad, una sola caja). El 'id' es
        opcional: si viene, se usa para emparejar con la caja física
        declarada en la apertura; si no, se empareja por nombre; si no
        existía ninguna con ese nombre/id (se agregó una caja nueva
        recién al cierre), se crea la fila en ese momento.

        monto_final_efectivo SIEMPRE es la SUMA de todas las cajas
        declaradas — todo el resto de la lógica (esperado, diferencia,
        alerta, transferencia a caja grande) sigue operando sobre ese
        total único, exactamente como antes. El desglose por caja es
        puramente declarativo (ver CajaFisicaTurno): el sistema nunca
        supo en qué caja física se hizo cada venta, así que no existe
        una "diferencia" individual por caja, solo la del total.

        1. Congela (snapshot) los totales por medio de pago, para que
           el historial de este turno no cambie más adelante aunque se
           edite/anule una venta vieja.
        2. Efectivo: se transfiere a caja grande el MONTO REAL
           declarado por el cajero (lo contado físicamente), no el
           teórico. Esto reemplaza de una sola vez tanto la devolución
           del monto inicial como lo vendido en efectivo, evitando
           doble conteo. Si hay diferencia entre lo esperado
           (monto_inicial + ventas en efectivo) y lo declarado, queda
           registrada en diferencia_efectivo y se expone una alerta
           (ver alerta_diferencia / mensaje_alerta) — no se "esconde"
           la diferencia ni se ajusta silenciosamente.
        3. Resto de medios de pago (transferencia, débito, QR, etc.):
           nada que hacer acá — ya están en caja grande desde que se
           confirmó cada venta.
        """
        from django.db import transaction

        cajas = _normalizar_cajas(cajas)
        monto_final_efectivo = sum(Decimal(str(c['monto'])) for c in cajas)

        with transaction.atomic():
            # select_for_update() + re-chequeo de estado: si dos cierres
            # del mismo turno llegan casi al mismo tiempo (doble clic),
            # el segundo espera acá bloqueado y, al destrabarse, ya
            # encuentra el turno CERRADO por el primero — evita
            # duplicar el movimiento de "Cierre de turno - Efectivo" y
            # pisar diferencia_efectivo/totales_cierre dos veces.
            turno_bloqueado = TurnoCaja.objects.select_for_update().get(pk=self.pk)
            if turno_bloqueado.estado != EstadoTurno.ABIERTO:
                raise ValueError(
                    f'El turno #{turno_bloqueado.numero} ya está '
                    f'{turno_bloqueado.get_estado_display().lower()}.'
                )

            # Calcular totales por medio de pago (en caliente, todavía
            # no está cerrado el turno en este punto)
            totales = self.calcular_totales_por_medio_pago()
            total_recaudado = sum(totales.values())

            efectivo_ventas = totales.get('efectivo', 0)
            esperado = self.monto_inicial_efectivo + efectivo_ventas

            # ── Congelar estado del turno ───────────────────────────
            self.monto_final_efectivo = monto_final_efectivo
            self.diferencia_efectivo = monto_final_efectivo - esperado
            self.fecha_cierre = timezone.now()
            self.estado = EstadoTurno.CERRADO
            self.cerrado_por = usuario
            self.notas = notas
            self.totales_cierre = {
                'totales_medio_pago': {k: str(v) for k, v in totales.items()},
                'total_recaudado': str(total_recaudado),
                'ganancia_turno': str(total_recaudado - (self.monto_inicial_efectivo or 0)),
                'esperado_efectivo': str(esperado),
                'declarado_efectivo': str(monto_final_efectivo),
            }
            self.save()

            # ── Volcar lo declarado a las cajas físicas de este turno ──
            existentes_por_id = {cf.pk: cf for cf in self.cajas_fisicas.all()}
            existentes_por_nombre = {cf.nombre: cf for cf in existentes_por_id.values()}
            siguiente_orden = len(existentes_por_id)

            for c in cajas:
                cf = None
                if c['id'] and c['id'] in existentes_por_id:
                    cf = existentes_por_id[c['id']]
                elif c['nombre'] in existentes_por_nombre:
                    cf = existentes_por_nombre[c['nombre']]

                if cf:
                    cf.monto_final = Decimal(str(c['monto']))
                    cf.save(update_fields=['monto_final'])
                else:
                    # Caja declarada recién al cierre (no existía en la apertura)
                    CajaFisicaTurno.objects.create(
                        turno=self, nombre=c['nombre'], orden=siguiente_orden,
                        monto_inicial=Decimal('0'), monto_final=Decimal(str(c['monto'])),
                    )
                    siguiente_orden += 1

            fecha_cierre = self.fecha_cierre.date()

            # ── 1. Efectivo: se transfiere lo REALMENTE contado ─────
            cuenta_efectivo = _cuenta_grande_para_medio_pago('efectivo', 'Efectivo', moneda=Moneda.ARS)
            concepto_cierre_efectivo = _concepto_default('Cierre de turno - Efectivo', TipoMovimientoCaja.INGRESO)

            if monto_final_efectivo and monto_final_efectivo > 0:
                detalle_cajas = (
                    ' (' + ', '.join(f"{c['nombre']}: {c['monto']}" for c in cajas) + ')'
                    if len(cajas) > 1 else ''
                )
                MovimientoCaja.objects.create(
                    caja=TipoCaja.GRANDE,
                    cuenta=cuenta_efectivo,
                    concepto=concepto_cierre_efectivo,
                    tipo=TipoMovimientoCaja.INGRESO,
                    monto=monto_final_efectivo,
                    moneda=Moneda.ARS,
                    fecha=fecha_cierre,
                    descripcion=(
                        f'Cierre turno #{self.numero} — efectivo declarado '
                        f'(esperado {esperado}, diferencia {self.diferencia_efectivo})'
                        + detalle_cajas
                    ),
                    referencia=f'Turno #{self.numero}',
                    origen=OrigenMovimiento.AJUSTE,
                    origen_app='caja',
                    origen_id=self.pk,
                    creado_por=usuario,
                )

            # ── 2. Resto de medios de pago: YA NO se tocan acá. Desde que
            #      sincronizar_movimiento_venta() postea cada pago no
            #      efectivo a caja grande en el momento de confirmar la
            #      venta (ver caja/models.py), volver a acreditarlos acá
            #      los duplicaría. El cierre de turno solo liquida lo
            #      único que de verdad necesita esperar: el efectivo,
            #      porque recién ahí existe un conteo físico contra el
            #      cual conciliar.


class CajaFisicaTurno(models.Model):
    """
    Desglose DECLARATIVO de un turno en varias cajas físicas, para
    negocios con más de una caja registradora abierta en simultáneo
    durante un mismo turno.

    Es puramente informativo: el sistema NUNCA supo en qué caja física
    se hizo cada venta (decisión de diseño a propósito — llevar ese
    registro exigiría tocar Ventas, y en la práctica el efectivo
    circula entre cajas igual, así que ese nivel de detalle se
    desactualizaría solo). Por eso:

    - monto_inicial / monto_final son lo que el cajero DECLARA para
      cada caja, no algo que el sistema valide o calcule por sí solo.
    - No existe una "diferencia" individual por caja — la única
      diferencia real (sobra/falta) sigue siendo la del TURNO completo
      (TurnoCaja.diferencia_efectivo), que suma todas las cajas.
    - TurnoCaja.monto_inicial_efectivo / monto_final_efectivo son
      SIEMPRE la suma de estas filas. El resto del sistema (ventas,
      cierre, alertas, historial a nivel total, caja grande) no sabe
      que existe más de una caja física — ve un único número, exacto
      como funcionaba antes de este modelo.
    """
    turno = models.ForeignKey(TurnoCaja, on_delete=models.CASCADE, related_name='cajas_fisicas')
    nombre = models.CharField(max_length=50, default='Caja 1')
    orden = models.PositiveIntegerField(default=0)
    monto_inicial = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    monto_final = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = 'Caja física de turno'
        verbose_name_plural = 'Cajas físicas de turno'
        ordering = ['orden', 'id']

    def __str__(self):
        return f'{self.nombre} — Turno #{self.turno.numero}'


# ══════════════════════════════════════════════════════════════════
#  GASTO
# ══════════════════════════════════════════════════════════════════

class Gasto(models.Model):
    """
    Movimiento manual de caja grande: ingreso o egreso libre (sueldo,
    herencia, regalo, alquiler, mecánico, luz, etc. — la descripción
    queda libre a propósito, no hay catálogo de categorías).

    El nombre de la clase quedó como "Gasto" por compatibilidad con
    el resto del código (tabla, permisos, FKs) aunque ahora también
    representa ingresos — ver `tipo`. Cada instancia genera un
    MovimientoCaja en la caja grande contra la `cuenta` elegida
    (nunca forzado a Efectivo). Al editar/eliminar, se sincroniza el
    movimiento de caja correspondiente.
    """

    tipo = models.CharField(max_length=10, choices=TipoMovimientoCaja.choices,
               default=TipoMovimientoCaja.EGRESO)
    cuenta = models.ForeignKey(CuentaCaja, on_delete=models.PROTECT,
                 related_name='gastos',
                 help_text='Cuenta que se acredita o debita con este movimiento.')

    fecha = models.DateField(help_text='Fecha del movimiento')
    hora = models.TimeField(help_text='Hora del movimiento (automática)')
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)
    descripcion = models.CharField(max_length=300, help_text='Ej: alquiler, mecánico, luz, sueldo, herencia, regalo')

    # ── Auditoría ────────────────────────────────────────────────
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='gastos_creados',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Ingreso o egreso manual'
        verbose_name_plural = 'Ingresos y egresos manuales'
        ordering = ['-fecha', '-hora']

    def __str__(self):
        signo = '+' if self.tipo == TipoMovimientoCaja.INGRESO else '-'
        return f'{signo}{self.monto} {self.moneda} — {self.descripcion} ({self.fecha})'
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            # Establecer hora automáticamente al crear
            if not self.hora:
                self.hora = timezone.now().time()
        super().save(*args, **kwargs)
        
        # Sincronizar movimiento de caja
        if is_new:
            sincronizar_movimiento_gasto(self)
    
    def delete(self, *args, **kwargs):
        # Eliminar movimiento de caja asociado antes de borrar el gasto
        movimiento = MovimientoCaja.objects.filter(
            origen='manual',
            origen_app='caja',
            origen_id=self.pk,
        ).first()
        if movimiento:
            movimiento.delete()
        super().delete(*args, **kwargs)


@transaction.atomic
def sincronizar_movimiento_gasto(gasto):
    """
    Sincroniza el MovimientoCaja asociado a un Gasto (ingreso o egreso
    manual) con su cuenta y tipo actuales.

    - Si el gasto existe: crea/actualiza el movimiento de caja contra
      `gasto.cuenta`, como ingreso o egreso según `gasto.tipo`.
    - Si el gasto se elimina: borra el movimiento de caja asociado.
    """
    # Buscar movimiento existente asociado a este gasto
    movimiento = MovimientoCaja.objects.filter(
        origen='manual',
        origen_app='caja',
        origen_id=gasto.pk,
    ).first()

    # Si el gasto ya no existe (se está borrando), eliminar el movimiento
    if not Gasto.objects.filter(pk=gasto.pk).exists():
        if movimiento:
            movimiento.delete()
        return

    # Crear o actualizar el movimiento
    moneda = gasto.moneda
    cuenta = gasto.cuenta
    nombre_concepto = 'Ingreso' if gasto.tipo == TipoMovimientoCaja.INGRESO else 'Gasto'
    concepto = _concepto_default(nombre_concepto, gasto.tipo)

    if movimiento:
        # Actualizar movimiento existente
        movimiento.cuenta = cuenta
        movimiento.concepto = concepto
        movimiento.tipo = gasto.tipo
        movimiento.monto = gasto.monto
        movimiento.moneda = moneda
        movimiento.fecha = gasto.fecha
        movimiento.descripcion = gasto.descripcion
        movimiento.save()
    else:
        # Crear nuevo movimiento
        MovimientoCaja.objects.create(
            caja = TipoCaja.GRANDE,
            cuenta = cuenta,
            concepto = concepto,
            tipo = gasto.tipo,
            monto = gasto.monto,
            moneda = moneda,
            fecha = gasto.fecha,
            descripcion = gasto.descripcion,
            referencia = f'Gasto #{gasto.pk}',
            origen = OrigenMovimiento.MANUAL,
            origen_app = 'caja',
            origen_id = gasto.pk,
            creado_por = gasto.creado_por,
        )


# ══════════════════════════════════════════════════════════════════
#  DEUDAS (créditos con tarjeta y préstamos)
#
#  Una Deuda es dinero que el negocio debe pagar (compra a crédito) o
#  ya recibió y debe devolver (préstamo). Se paga/devuelve en cuotas
#  (CuotaDeuda), cada una con su propia fecha de vencimiento. Nada
#  impacta la caja grande hasta que la cuota se confirma a mano — ni
#  siquiera al vencer la fecha (no hay débito automático).
#
#  Compra a crédito: nace desde compras._crear_deudas_desde_pagos()
#  cuando una línea de PagoCompra usa medio=CREDITO, o se carga manual
#  acá mismo para gastos con tarjeta que no son mercadería (ej. una
#  notebook). No genera movimiento propio al crearse — el costo real
#  ya quedó reflejado en la Compra (si la hay); acá solo se generan
#  egresos a medida que se confirman las cuotas.
#
#  Préstamo: genera un ingreso inmediato en `cuenta_acreditacion` al
#  crearse (el dinero ya entró), y luego un egreso por cada cuota de
#  devolución confirmada.
# ══════════════════════════════════════════════════════════════════

class TipoDeuda(models.TextChoices):
    COMPRA_CREDITO = 'compra_credito', 'Compra con tarjeta de crédito'
    PRESTAMO       = 'prestamo',       'Préstamo'


class EstadoDeuda(models.TextChoices):
    ACTIVA  = 'activa',  'Activa'
    ANULADA = 'anulada', 'Anulada'


class EstadoCuota(models.TextChoices):
    PENDIENTE  = 'pendiente',  'Pendiente'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


def _sumar_meses(fecha, n):
    """
    Suma `n` meses a una fecha, clampeando el día si el mes de destino
    es más corto (ej: 31/01 + 1 mes → 28/02, no 03/03).
    """
    import calendar

    mes_total = fecha.month - 1 + n
    anio = fecha.year + mes_total // 12
    mes  = mes_total % 12 + 1
    dia  = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return fecha.replace(year=anio, month=mes, day=dia)


class Deuda(models.Model):
    """
    Cabecera de una deuda (compra a crédito o préstamo). El detalle de
    pago vive en CuotaDeuda — ver comentario de sección más arriba.
    """

    tipo = models.CharField(max_length=20, choices=TipoDeuda.choices)

    # — Origen (compra a crédito desde el checkout de Compras) —
    pago_compra = models.OneToOneField(
        'compras.PagoCompra', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deuda',
        help_text='Solo si esta deuda nació de una línea de pago con tarjeta en una compra.',
    )
    descripcion = models.CharField(max_length=300, blank=True,
                      help_text='Obligatoria si no viene de una compra (ej: "Notebook oficina", "Préstamo Banco Nación").')

    # — Cuentas involucradas —
    cuenta_tarjeta = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='deudas_tarjeta',
        help_text='Tarjeta (CuentaCaja con es_credito=True) usada. Solo para compra_credito.',
    )
    cuenta_acreditacion = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='deudas_acreditadas',
        help_text='Cuenta que recibe el dinero del préstamo. Solo para prestamo.',
    )

    monto_original     = models.DecimalField(max_digits=14, decimal_places=2,
                              help_text='Capital, sin interés.')
    porcentaje_interes  = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    moneda              = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)
    cantidad_cuotas     = models.PositiveSmallIntegerField()
    fecha_inicio        = models.DateField(help_text='Vencimiento de la primera cuota. Las siguientes son mensuales a partir de acá.')

    estado = models.CharField(max_length=10, choices=EstadoDeuda.choices, default=EstadoDeuda.ACTIVA)
    notas  = models.CharField(max_length=300, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='deudas_creadas',
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Deuda'
        verbose_name_plural = 'Deudas'
        ordering             = ['-fecha_alta']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.descripcion or self.pk} ({self.monto_total} {self.moneda})'

    @property
    def monto_total(self):
        """Suma de las cuotas ya generadas (capital + interés). No se cachea."""
        return self.cuotas.aggregate(total=models.Sum('monto'))['total'] or Decimal('0')

    @property
    def cuotas_pagadas(self):
        return self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).count()

    @property
    def saldo_pendiente(self):
        return self.cuotas.filter(estado=EstadoCuota.PENDIENTE).aggregate(
            total=models.Sum('monto'))['total'] or Decimal('0')

    @classmethod
    @transaction.atomic
    def crear_con_cuotas(cls, *, tipo, monto_original, porcentaje_interes, cantidad_cuotas,
                          fecha_inicio, moneda=Moneda.ARS, descripcion='', notas='',
                          pago_compra=None, cuenta_tarjeta=None, cuenta_acreditacion=None,
                          creado_por=None):
        """
        Crea la Deuda y su plan de cuotas. Si tipo=PRESTAMO, además
        genera de inmediato el ingreso a `cuenta_acreditacion`.
        """
        if cantidad_cuotas < 1:
            raise ValueError('La cantidad de cuotas debe ser al menos 1.')
        if monto_original <= 0:
            raise ValueError('El monto debe ser mayor a 0.')
        if tipo == TipoDeuda.COMPRA_CREDITO and not cuenta_tarjeta:
            raise ValueError('Elegí la tarjeta con la que se pagó.')
        if tipo == TipoDeuda.PRESTAMO and not cuenta_acreditacion:
            raise ValueError('Elegí la cuenta que recibe el préstamo.')
        if not pago_compra and not descripcion:
            raise ValueError('La descripción es obligatoria cuando la deuda no viene de una compra.')

        deuda = cls.objects.create(
            tipo=tipo, pago_compra=pago_compra, descripcion=descripcion,
            cuenta_tarjeta=cuenta_tarjeta, cuenta_acreditacion=cuenta_acreditacion,
            monto_original=monto_original, porcentaje_interes=porcentaje_interes,
            moneda=moneda, cantidad_cuotas=cantidad_cuotas, fecha_inicio=fecha_inicio,
            notas=notas, creado_por=creado_por,
        )
        generar_cuotas(deuda)

        if tipo == TipoDeuda.PRESTAMO:
            sincronizar_movimiento_deuda(deuda)

        return deuda

    @transaction.atomic
    def anular(self):
        if self.estado == EstadoDeuda.ANULADA:
            raise ValueError('La deuda ya está anulada.')
        if self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).exists():
            raise ValueError('No se puede anular: ya hay cuotas confirmadas de esta deuda.')

        self.estado = EstadoDeuda.ANULADA
        self.save(update_fields=['estado'])
        self.cuotas.filter(estado=EstadoCuota.PENDIENTE).update(estado=EstadoCuota.ANULADA)

        sincronizar_movimiento_deuda(self)

    def delete(self, *args, **kwargs):
        if self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).exists():
            raise ValueError('No se puede eliminar: ya hay cuotas confirmadas de esta deuda.')
        with transaction.atomic():
            movimiento = MovimientoCaja.objects.filter(
                origen=OrigenMovimiento.DEUDA, origen_app='caja', origen_id=self.pk,
            ).first()
            if movimiento:
                movimiento.delete()
            super().delete(*args, **kwargs)


DIAS_HABILITACION_CUOTA = 2


class CuotaDeuda(models.Model):
    """
    Una cuota del plan de pago/devolución de una Deuda. Se habilita
    para confirmar recién DIAS_HABILITACION_CUOTA días antes de su
    vencimiento (no tiene sentido habilitarla el mismo día) — una vez
    habilitada, sigue estándolo aunque se pase la fecha.
    """

    deuda   = models.ForeignKey(Deuda, on_delete=models.CASCADE, related_name='cuotas')
    numero  = models.PositiveSmallIntegerField()
    monto   = models.DecimalField(max_digits=14, decimal_places=2)
    fecha_vencimiento = models.DateField()

    estado  = models.CharField(max_length=10, choices=EstadoCuota.choices, default=EstadoCuota.PENDIENTE)
    cuenta_pago = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cuotas_pagadas',
        help_text='Cuenta real (banco/efectivo) de donde sale la plata al confirmar. Nunca una tarjeta.',
    )
    fecha_confirmacion = models.DateTimeField(null=True, blank=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cuotas_deuda_confirmadas',
    )

    class Meta:
        verbose_name        = 'Cuota de deuda'
        verbose_name_plural = 'Cuotas de deuda'
        ordering            = ['deuda', 'numero']
        unique_together     = [('deuda', 'numero')]

    def __str__(self):
        return f'{self.deuda} — cuota {self.numero}/{self.deuda.cantidad_cuotas}'

    @property
    def habilitada(self):
        """True desde DIAS_HABILITACION_CUOTA días antes del vencimiento en adelante."""
        return timezone.now().date() >= self.fecha_vencimiento - timedelta(days=DIAS_HABILITACION_CUOTA)

    @transaction.atomic
    def confirmar(self, cuenta_pk, usuario):
        # select_for_update(): mismo guard que en Venta/Compra.confirmar()
        # — un doble clic en "Pagar cuota" no debe generar dos egresos.
        if CuotaDeuda.objects.select_for_update().get(pk=self.pk).estado != EstadoCuota.PENDIENTE:
            raise ValueError('Solo se pueden confirmar cuotas pendientes.')
        if not self.habilitada:
            fecha_habilitacion = self.fecha_vencimiento - timedelta(days=DIAS_HABILITACION_CUOTA)
            raise ValueError(
                f'Esta cuota se habilita para pagar a partir del {fecha_habilitacion.strftime("%d/%m/%Y")}.'
            )

        cuenta = CuentaCaja.objects.filter(
            pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True,
            es_credito=False, moneda=self.deuda.moneda,
        ).first()
        if not cuenta:
            raise ValueError('Elegí una cuenta válida para pagar la cuota.')

        self.cuenta_pago = cuenta
        self.estado = EstadoCuota.CONFIRMADA
        self.fecha_confirmacion = timezone.now()
        self.confirmado_por = usuario
        self.save(update_fields=['cuenta_pago', 'estado', 'fecha_confirmacion', 'confirmado_por'])

        sincronizar_movimiento_cuota(self)


def generar_cuotas(deuda):
    """
    Genera el plan de CuotaDeuda de una Deuda recién creada: interés
    simple sobre el monto original, repartido en partes iguales entre
    `cantidad_cuotas` (la última absorbe el resto del redondeo).
    """
    monto_total = (deuda.monto_original * (Decimal('1') + deuda.porcentaje_interes / Decimal('100'))) \
        .quantize(Decimal('0.01'))
    cuota_base = (monto_total / deuda.cantidad_cuotas).quantize(Decimal('0.01'))

    acumulado = Decimal('0')
    for i in range(1, deuda.cantidad_cuotas + 1):
        if i < deuda.cantidad_cuotas:
            monto_cuota = cuota_base
            acumulado += monto_cuota
        else:
            monto_cuota = monto_total - acumulado

        CuotaDeuda.objects.create(
            deuda=deuda, numero=i, monto=monto_cuota,
            fecha_vencimiento=_sumar_meses(deuda.fecha_inicio, i - 1),
        )


@transaction.atomic
def sincronizar_movimiento_deuda(deuda):
    """
    Sincroniza el MovimientoCaja de acreditación de un préstamo (no
    aplica a compra_credito, que nunca genera movimiento propio — solo
    sus cuotas lo hacen).
    """
    movimiento = MovimientoCaja.objects.filter(
        origen=OrigenMovimiento.DEUDA, origen_app='caja', origen_id=deuda.pk,
    ).first()

    if deuda.tipo != TipoDeuda.PRESTAMO or deuda.estado != EstadoDeuda.ACTIVA:
        if movimiento:
            movimiento.delete()
        return

    concepto = _concepto_default('Préstamo recibido', TipoMovimientoCaja.INGRESO)

    if movimiento:
        movimiento.cuenta = deuda.cuenta_acreditacion
        movimiento.concepto = concepto
        movimiento.tipo = TipoMovimientoCaja.INGRESO
        movimiento.monto = deuda.monto_original
        movimiento.moneda = deuda.moneda
        movimiento.fecha = deuda.fecha_alta.date()
        movimiento.descripcion = f'Préstamo — {deuda.descripcion}'
        movimiento.save()
    else:
        MovimientoCaja.objects.create(
            caja=TipoCaja.GRANDE, cuenta=deuda.cuenta_acreditacion, concepto=concepto,
            tipo=TipoMovimientoCaja.INGRESO, monto=deuda.monto_original, moneda=deuda.moneda,
            fecha=deuda.fecha_alta.date(), descripcion=f'Préstamo — {deuda.descripcion}',
            referencia=f'Deuda #{deuda.pk}', origen=OrigenMovimiento.DEUDA,
            origen_app='caja', origen_id=deuda.pk, creado_por=deuda.creado_por,
        )


@transaction.atomic
def sincronizar_movimiento_cuota(cuota):
    """Sincroniza el MovimientoCaja (egreso) de una CuotaDeuda con su estado actual."""
    movimiento = MovimientoCaja.objects.filter(
        origen=OrigenMovimiento.CUOTA_DEUDA, origen_app='caja', origen_id=cuota.pk,
    ).first()

    if cuota.estado != EstadoCuota.CONFIRMADA:
        if movimiento:
            movimiento.delete()
        return

    deuda = cuota.deuda
    entidad = deuda.descripcion or (deuda.cuenta_tarjeta.nombre if deuda.cuenta_tarjeta else '')
    concepto = _concepto_default('Pago de cuota (deuda)', TipoMovimientoCaja.EGRESO)
    descripcion = f'Cuota {cuota.numero}/{deuda.cantidad_cuotas} — {entidad}'.strip(' —')

    if movimiento:
        movimiento.cuenta = cuota.cuenta_pago
        movimiento.concepto = concepto
        movimiento.tipo = TipoMovimientoCaja.EGRESO
        movimiento.monto = cuota.monto
        movimiento.moneda = deuda.moneda
        movimiento.fecha = cuota.fecha_confirmacion.date()
        movimiento.descripcion = descripcion
        movimiento.save()
    else:
        MovimientoCaja.objects.create(
            caja=TipoCaja.GRANDE, cuenta=cuota.cuenta_pago, concepto=concepto,
            tipo=TipoMovimientoCaja.EGRESO, monto=cuota.monto, moneda=deuda.moneda,
            fecha=cuota.fecha_confirmacion.date(), descripcion=descripcion,
            referencia=f'Deuda #{deuda.pk}', origen=OrigenMovimiento.CUOTA_DEUDA,
            origen_app='caja', origen_id=cuota.pk, creado_por=cuota.confirmado_por,
        )


# ══════════════════════════════════════════════════════════════════
#  CHEQUES (a cobrar / a pagar)
#
#  A_PAGAR: cheque propio, librado contra una cuenta bancaria PROPIA
#  (la chequera) — esa cuenta es fija desde que se carga el cheque, el
#  egreso siempre sale de ahí.
#
#  A_COBRAR: cheque de terceros, librado contra la cuenta del que lo
#  entregó (banco ajeno, solo informativo — no se modela como
#  CuentaCaja). El negocio elige en cuál de SUS PROPIAS cuentas lo
#  deposita/cobra recién al confirmarlo, no al cargarlo.
#
#  En ambos casos: nada impacta caja hasta que se confirma a mano —
#  mismo patrón que CuotaDeuda. Un cheque puede además "rechazarse"
#  (rebotar) — si ya estaba confirmado, revierte el movimiento.
# ══════════════════════════════════════════════════════════════════

class TipoCheque(models.TextChoices):
    A_COBRAR = 'a_cobrar', 'A cobrar (de terceros)'
    A_PAGAR  = 'a_pagar',  'A pagar (propio)'


class EstadoCheque(models.TextChoices):
    PENDIENTE  = 'pendiente',  'Pendiente'
    CONFIRMADO = 'confirmado', 'Confirmado'
    RECHAZADO  = 'rechazado',  'Rechazado'
    ANULADO    = 'anulado',    'Anulado'


class Cheque(models.Model):
    """Un cheque a cobrar (de terceros) o a pagar (propio)."""

    tipo = models.CharField(max_length=10, choices=TipoCheque.choices)

    numero_cheque = models.CharField(max_length=30, blank=True,
                        help_text='Opcional, ayuda a evitar duplicados.')
    monto  = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)

    fecha_emision = models.DateField(help_text='Fecha en que se emitió/recibió el cheque.')
    fecha_cobro   = models.DateField(help_text='Fecha en que se puede/debe cobrar (cubre cheque común y de pago diferido).')

    # — A_PAGAR: chequera propia, fija desde que se carga —
    cuenta_origen = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cheques_a_pagar',
        help_text='Cuenta bancaria propia (la chequera). Solo para A_PAGAR.',
    )

    # — A_COBRAR: datos del que lo entregó (informativos) + cuenta propia
    # de destino, que se elige recién al confirmar —
    banco_librador   = models.CharField(max_length=100, blank=True,
                            help_text='Banco del cheque de terceros. Solo informativo.')
    titular_librador = models.CharField(max_length=150, blank=True,
                            help_text='Quién entregó el cheque. Solo para A_COBRAR.')
    cuenta_destino = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cheques_a_cobrar',
        help_text='Cuenta propia donde se deposita/cobra. Se completa al confirmar, no antes.',
    )

    contraparte = models.CharField(max_length=150, blank=True,
                      help_text='A quién se le paga (A_PAGAR) o quién lo entregó (A_COBRAR).')

    estado = models.CharField(max_length=10, choices=EstadoCheque.choices, default=EstadoCheque.PENDIENTE)
    notas  = models.CharField(max_length=300, blank=True)

    fecha_confirmacion = models.DateTimeField(null=True, blank=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cheques_confirmados',
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cheques_creados',
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Cheque'
        verbose_name_plural = 'Cheques'
        ordering             = ['-fecha_alta']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.numero_cheque or "s/n"} — {self.monto} {self.moneda}'

    @transaction.atomic
    def confirmar(self, usuario, cuenta_pk=None):
        # select_for_update(): un doble clic en "Confirmar" no debe
        # depositar el cheque dos veces.
        if Cheque.objects.select_for_update().get(pk=self.pk).estado != EstadoCheque.PENDIENTE:
            raise ValueError('Solo se pueden confirmar cheques pendientes.')

        if self.tipo == TipoCheque.A_COBRAR:
            cuenta = CuentaCaja.objects.filter(
                pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True,
                es_credito=False, moneda=self.moneda,
            ).first()
            if not cuenta:
                raise ValueError('Elegí una cuenta válida para depositar el cheque.')
            self.cuenta_destino = cuenta

        self.estado = EstadoCheque.CONFIRMADO
        self.fecha_confirmacion = timezone.now()
        self.confirmado_por = usuario
        self.save(update_fields=['estado', 'fecha_confirmacion', 'confirmado_por', 'cuenta_destino'])

        sincronizar_movimiento_cheque(self)

    @transaction.atomic
    def rechazar(self):
        """Un cheque puede rebotar recién al intentar cobrarlo, ya confirmado."""
        if Cheque.objects.select_for_update().get(pk=self.pk).estado not in (EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO):
            raise ValueError('Solo se pueden rechazar cheques pendientes o confirmados.')

        self.estado = EstadoCheque.RECHAZADO
        self.save(update_fields=['estado'])

        sincronizar_movimiento_cheque(self)

    @transaction.atomic
    def anular(self):
        if Cheque.objects.select_for_update().get(pk=self.pk).estado != EstadoCheque.PENDIENTE:
            raise ValueError('Solo se pueden anular cheques pendientes (si ya se confirmó, hay que rechazarlo).')

        self.estado = EstadoCheque.ANULADO
        self.save(update_fields=['estado'])

    def delete(self, *args, **kwargs):
        if self.estado == EstadoCheque.CONFIRMADO:
            raise ValueError('No se puede eliminar un cheque confirmado — hay que rechazarlo primero.')
        with transaction.atomic():
            movimiento = MovimientoCaja.objects.filter(
                origen=OrigenMovimiento.CHEQUE, origen_app='caja', origen_id=self.pk,
            ).first()
            if movimiento:
                movimiento.delete()
            super().delete(*args, **kwargs)


@transaction.atomic
def sincronizar_movimiento_cheque(cheque):
    """Sincroniza el MovimientoCaja de un Cheque con su estado actual."""
    movimiento = MovimientoCaja.objects.filter(
        origen=OrigenMovimiento.CHEQUE, origen_app='caja', origen_id=cheque.pk,
    ).first()

    if cheque.estado != EstadoCheque.CONFIRMADO:
        if movimiento:
            movimiento.delete()
        return

    if cheque.tipo == TipoCheque.A_PAGAR:
        tipo_mov = TipoMovimientoCaja.EGRESO
        cuenta = cheque.cuenta_origen
        concepto = _concepto_default('Cheque emitido', TipoMovimientoCaja.EGRESO)
    else:
        tipo_mov = TipoMovimientoCaja.INGRESO
        cuenta = cheque.cuenta_destino
        concepto = _concepto_default('Cheque cobrado', TipoMovimientoCaja.INGRESO)

    descripcion = f'Cheque {cheque.numero_cheque or "s/n"} — {cheque.contraparte}'.strip(' —')

    if movimiento:
        movimiento.cuenta = cuenta
        movimiento.concepto = concepto
        movimiento.tipo = tipo_mov
        movimiento.monto = cheque.monto
        movimiento.moneda = cheque.moneda
        movimiento.fecha = cheque.fecha_confirmacion.date()
        movimiento.descripcion = descripcion
        movimiento.save()
    else:
        MovimientoCaja.objects.create(
            caja=TipoCaja.GRANDE, cuenta=cuenta, concepto=concepto,
            tipo=tipo_mov, monto=cheque.monto, moneda=cheque.moneda,
            fecha=cheque.fecha_confirmacion.date(), descripcion=descripcion,
            referencia=f'Cheque #{cheque.pk}', origen=OrigenMovimiento.CHEQUE,
            origen_app='caja', origen_id=cheque.pk, creado_por=cheque.confirmado_por,
        )


# ══════════════════════════════════════════════════════════════════
#  TRANSACCIONES DE CAJA GRANDE
#  Agregar este bloque al final de models.py (antes de los helpers
#  de sincronización si querés, o al final del archivo).
#
#  También agregar 'TRANSACCION' a OrigenMovimiento:
#
#  class OrigenMovimiento(models.TextChoices):
#      VENTA       = 'venta',       'Venta'
#      COMPRA      = 'compra',      'Compra'
#      MANUAL      = 'manual',      'Carga manual'
#      AJUSTE      = 'ajuste',      'Ajuste'
#      TRANSACCION = 'transaccion', 'Transacción interna'   ← AGREGAR
# ══════════════════════════════════════════════════════════════════


class TipoTransaccion(models.TextChoices):
    DEPOSITO      = 'deposito',      'Depósito bancario'
    EXTRACCION    = 'extraccion',    'Extracción bancaria'
    COMPRA_DIVISA = 'compra_divisa', 'Compra de divisa'
    VENTA_DIVISA  = 'venta_divisa',  'Venta de divisa'


class TransaccionCaja(models.Model):
    """
    Registra un movimiento entre dos cuentas de la caja grande.

    Tipos soportados:
    - DEPOSITO:      Efectivo → Banco (misma moneda)
    - EXTRACCION:    Banco → Efectivo (misma moneda)
    - COMPRA_DIVISA: Cuenta en moneda A → Cuenta en moneda B,
                     con tipo de cambio y costos opcionales.
    - VENTA_DIVISA:  Lo inverso de compra_divisa.

    Genera atómicamente dos MovimientoCaja:
    - mov_egreso:  egreso en cuenta_origen  por monto_origen
    - mov_ingreso: ingreso en cuenta_destino por monto_destino

    Los costos extra (impuestos, comisiones) se registran como un
    tercer egreso opcional en cuenta_origen, también linkeado aquí.

    La transacción es el "objeto padre"; los movimientos son sus
    consecuencias y no deben editarse directamente.
    """

    tipo = models.CharField(
        max_length=20,
        choices=TipoTransaccion.choices,
    )

    cuenta_origen  = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT,
        related_name='transacciones_como_origen',
        help_text='Cuenta desde la que sale el dinero.',
    )
    cuenta_destino = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT,
        related_name='transacciones_como_destino',
        help_text='Cuenta hacia la que entra el dinero.',
    )

    # Montos
    monto_origen   = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text='Monto que sale de cuenta_origen (en la moneda de esa cuenta).',
    )
    monto_destino  = models.DecimalField(
        max_digits=14, decimal_places=2,
        help_text='Monto que entra en cuenta_destino (en la moneda de esa cuenta). '
                  'Para depósito/extracción es igual a monto_origen. '
                  'Para compra/venta de divisa es monto_origen / tipo_cambio.',
    )

    # Solo para operaciones de cambio de divisa
    tipo_cambio = models.DecimalField(
        max_digits=14, decimal_places=6,
        null=True, blank=True,
        help_text='Precio de 1 unidad de la divisa destino en moneda origen. '
                  'Ej: si comprás USD a 1.200 ARS, tipo_cambio=1200. '
                  'Solo aplica para compra/venta de divisa.',
    )

    # Costo extra opcional (impuestos, comisiones bancarias, etc.)
    costo_extra = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True,
        help_text='Monto adicional cobrado (impuesto, comisión, etc.), '
                  'en la moneda de cuenta_origen.',
    )
    descripcion_costo = models.CharField(
        max_length=200,
        blank=True,
        help_text='Descripción del costo extra. Ej: "Impuesto PAIS 30%", "Comisión bancaria".',
    )
    # Si hay costo extra, puede salir de la misma cuenta origen u otra cuenta.
    # Por simplicidad asumimos que siempre sale de cuenta_origen.
    # mov_costo referencia ese tercer movimiento.
    mov_costo = models.OneToOneField(
        'MovimientoCaja',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transaccion_como_costo',
    )

    # Metadata
    fecha       = models.DateField(help_text='Fecha contable de la transacción.')
    descripcion = models.CharField(max_length=300, blank=True)

    # Referencias a los movimientos generados (se setean en ejecutar())
    mov_egreso = models.OneToOneField(
        'MovimientoCaja',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transaccion_como_egreso',
    )
    mov_ingreso = models.OneToOneField(
        'MovimientoCaja',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transaccion_como_ingreso',
    )

    # Auditoría
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='transacciones_caja_creadas',
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Transacción de caja'
        verbose_name_plural = 'Transacciones de caja'
        ordering            = ['-fecha', '-fecha_alta']

    def __str__(self):
        return (
            f'{self.get_tipo_display()} | '
            f'{self.monto_origen} {self.cuenta_origen.moneda} → '
            f'{self.monto_destino} {self.cuenta_destino.moneda} | '
            f'{self.fecha:%d/%m/%Y}'
        )

    # ──────────────────────────────────────────────────────────────
    #  LÓGICA DE NEGOCIO
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def calcular_monto_destino(monto_origen, tipo_cambio):
        """
        Calcula el monto que llega a destino dados el monto origen
        y el tipo de cambio.
        Fórmula: monto_destino = monto_origen / tipo_cambio
        Ej: 15.000 ARS / 1.200 (ARS por USD) = 12,5 USD
        """
        if not tipo_cambio or tipo_cambio == 0:
            return monto_origen
        from decimal import Decimal, ROUND_HALF_UP
        return (Decimal(str(monto_origen)) / Decimal(str(tipo_cambio))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @transaction.atomic
    def ejecutar(self):
        """
        Crea los MovimientoCaja correspondientes y los linkea a esta
        transacción. Debe llamarse justo después de crear la instancia
        (save() sin ejecutar() deja la transacción incompleta).

        Flujo:
        1. Egreso en cuenta_origen por monto_origen
        2. Ingreso en cuenta_destino por monto_destino
        3. (Opcional) Egreso en cuenta_origen por costo_extra
        """
        concepto_egreso  = _concepto_default('Transacción - Egreso',  TipoMovimientoCaja.EGRESO)
        concepto_ingreso = _concepto_default('Transacción - Ingreso', TipoMovimientoCaja.INGRESO)
        concepto_costo   = _concepto_default('Transacción - Costo',   TipoMovimientoCaja.EGRESO)

        desc = self.descripcion or self.get_tipo_display()

        # 1. Egreso en origen
        mov_egreso = MovimientoCaja.objects.create(
            caja        = TipoCaja.GRANDE,
            cuenta      = self.cuenta_origen,
            concepto    = concepto_egreso,
            tipo        = TipoMovimientoCaja.EGRESO,
            monto       = self.monto_origen,
            moneda      = self.cuenta_origen.moneda,
            fecha       = self.fecha,
            descripcion = f'{desc} [origen]',
            referencia  = f'Transacción #{self.pk}',
            origen      = 'transaccion',
            origen_app  = 'caja',
            origen_id   = self.pk,
            creado_por  = self.creado_por,
        )

        # 2. Ingreso en destino
        mov_ingreso = MovimientoCaja.objects.create(
            caja        = TipoCaja.GRANDE,
            cuenta      = self.cuenta_destino,
            concepto    = concepto_ingreso,
            tipo        = TipoMovimientoCaja.INGRESO,
            monto       = self.monto_destino,
            moneda      = self.cuenta_destino.moneda,
            fecha       = self.fecha,
            descripcion = f'{desc} [destino]',
            referencia  = f'Transacción #{self.pk}',
            origen      = 'transaccion',
            origen_app  = 'caja',
            origen_id   = self.pk,
            creado_por  = self.creado_por,
        )

        self.mov_egreso  = mov_egreso
        self.mov_ingreso = mov_ingreso

        # 3. Costo extra opcional
        if self.costo_extra and self.costo_extra > 0:
            mov_costo = MovimientoCaja.objects.create(
                caja        = TipoCaja.GRANDE,
                cuenta      = self.cuenta_origen,
                concepto    = concepto_costo,
                tipo        = TipoMovimientoCaja.EGRESO,
                monto       = self.costo_extra,
                moneda      = self.cuenta_origen.moneda,
                fecha       = self.fecha,
                descripcion = self.descripcion_costo or f'Costo extra: {desc}',
                referencia  = f'Transacción #{self.pk}',
                origen      = 'transaccion',
                origen_app  = 'caja',
                origen_id   = self.pk,
                creado_por  = self.creado_por,
            )
            self.mov_costo = mov_costo

        self.save(update_fields=['mov_egreso', 'mov_ingreso', 'mov_costo'])

    @transaction.atomic
    def revertir(self):
        """
        Elimina todos los movimientos asociados a esta transacción
        y luego elimina la transacción misma.
        Úsalo para "anular" una transacción registrada por error.
        """
        MovimientoCaja.objects.filter(
            origen='transaccion',
            origen_app='caja',
            origen_id=self.pk,
        ).delete()
        self.delete()