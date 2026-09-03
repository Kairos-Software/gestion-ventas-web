from datetime import timedelta, date, datetime as dt
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Q, F, ExpressionWrapper, DecimalField
from django.utils import timezone

from productos.models import Moneda
from core.models import Cliente, recalcular_scoring_cliente


def _fmt_cantidad(d):
    """Decimal → texto sin ceros de más: 3.000 → '3', 1.500 → '1.5'."""
    s = f'{Decimal(d):f}'
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s or '0'


# ══════════════════════════════════════════════════════════════════
#  SCORING — recálculo diferido al commit
#  El scoring de riesgo de pago del cliente (ver core/scoring.py) se
#  recalcula cada vez que cambia algo que lo afecta: cobro/rechazo de
#  una cuota, cheque rebotado, alta/baja de una cuenta por cobrar.
#  Se difiere con transaction.on_commit para que un problema en el
#  cálculo nunca rompa la operación real (y para no recalcular si la
#  transacción termina revirtiéndose).
# ══════════════════════════════════════════════════════════════════

def _recalcular_scoring_pk(cliente_id):
    """Programa el recálculo del scoring de un cliente para después del
    commit de la transacción actual."""
    if cliente_id:
        transaction.on_commit(lambda cid=cliente_id: recalcular_scoring_cliente(cid))


def _recalcular_scoring_de_cxc(cuenta_por_cobrar_id):
    """Igual, resolviendo el cliente desde la cuenta por cobrar."""
    if not cuenta_por_cobrar_id:
        return
    cliente_id = (
        CuentaPorCobrar.objects
        .filter(pk=cuenta_por_cobrar_id)
        .values_list('cliente_id', flat=True)
        .first()
    )
    _recalcular_scoring_pk(cliente_id)


def _recalcular_scoring_de_cheque(cheque):
    """Resuelve el cliente de un cheque A_COBRAR (vía la cuota que cobra
    o la venta que lo originó) y le programa el recálculo. Los cheques
    A_PAGAR (propios) no tienen cliente — se ignoran."""
    if cheque.tipo != TipoCheque.A_COBRAR:
        return
    cliente_id = None
    if cheque.cuota_cobro_id:
        cliente_id = (
            CuotaCobro.objects
            .filter(pk=cheque.cuota_cobro_id)
            .values_list('cuenta_por_cobrar__cliente_id', flat=True)
            .first()
        )
    if not cliente_id and cheque.pago_venta_id:
        from ventas.models import PagoVenta
        venta = (
            PagoVenta.objects
            .filter(pk=cheque.pago_venta_id)
            .select_related('venta')
            .first()
        )
        if venta and venta.venta:
            cli = venta.venta.cliente_unico
            cliente_id = cli.pk if cli else None
    _recalcular_scoring_pk(cliente_id)


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
    DEUDA_TARJETA       = 'deuda_tarjeta',       'Compra con tarjeta (débito en tarjeta)'
    CUOTA_DEUDA_TARJETA = 'cuota_deuda_tarjeta', 'Pago de cuota (capital acreditado a tarjeta)'
    CUOTA_COBRO = 'cuota_cobro', 'Cobro de cuota (venta en cuotas)'
    DEVOLUCION_VENTA = 'devolucion_venta', 'Devolución de venta'


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
    # Obligatorio para todo lo que no sea Efectivo: es lo que permite
    # tener, por ejemplo, dos cuentas "Naranja X" (de dos personas
    # distintas, o débito vs. crédito de la misma persona) sin que se
    # confundan entre sí — ver unique_together y clean() más abajo.
    titular      = models.CharField(max_length=150, blank=True,
                       help_text='Nombre de quien es titular de la tarjeta/cuenta. '
                                  'Obligatorio salvo para Efectivo.')
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

    # ── Medios de cobro que acepta esta cuenta (lado VENTAS) ────────
    # OJO, esto NO es lo mismo que `es_credito` de arriba: `es_credito`
    # es sobre una tarjeta PROPIA del negocio usada para pagar a
    # proveedores (compras a crédito, con día de cierre/vencimiento).
    # Estos 4 campos son al revés: describen qué medios puede COBRARLE
    # esta cuenta a un cliente (ej. el Posnet de un banco cobra débito
    # y crédito; una cuenta bancaria para transferencias solo eso).
    # Sirven para no ofrecer "Crédito" como recargo/medio de pago en
    # cuentas donde no tiene sentido (ver ventas.models.RecargoMedioPago).
    # Default=True en los 4 para no romper cuentas ya cargadas: hasta que
    # el dueño los ajuste a mano en la pantalla de Recargos, se sigue
    # comportando como antes (todos los medios disponibles).
    acepta_debito       = models.BooleanField(default=True)
    acepta_credito      = models.BooleanField(default=True)
    acepta_qr           = models.BooleanField(default=True)
    acepta_transferencia = models.BooleanField(default=True)

    activa  = models.BooleanField(default=True)
    notas   = models.CharField(max_length=300, blank=True)
    orden   = models.PositiveSmallIntegerField(default=0)

    # "Cuenta principal": la que viene preseleccionada en TODOS los
    # selectores de cuenta del sistema (cobros, pagos, compras, gastos,
    # cuotas...). Una sola marcada — lo garantiza el endpoint que la
    # setea (core.views_cuentas.CuentaPrincipalAjax). Es solo un default:
    # siempre se puede elegir otra en el momento. En Ventas, además, un
    # medio de pago con CuentaPredeterminadaMedio propia le gana a esta.
    preferida = models.BooleanField('Cuenta principal', default=False)

    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Cuenta de caja'
        verbose_name_plural = 'Cuentas de caja'
        ordering            = ['caja', 'orden', 'nombre']
        # titular y es_credito entran en la unicidad a propósito: permite
        # tener dos cuentas "Naranja X" en la misma moneda siempre que
        # sean de titulares distintos, o débito/crédito de la misma
        # persona (ver clean() — titular es obligatorio salvo Efectivo,
        # así que esto nunca degenera en dos cuentas iguales con
        # titular vacío de por medio).
        unique_together     = [('nombre', 'caja', 'moneda', 'titular', 'es_credito')]

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if self.tipo != TipoCuenta.EFECTIVO and not self.titular:
            raise ValidationError({'titular': 'El titular es obligatorio para esta cuenta.'})

    def __str__(self):
        titular = f' · {self.titular}' if self.titular else ''
        return f'{self.nombre}{titular} ({self.get_moneda_display()})'

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

    @classmethod
    def principal(cls):
        """La 'cuenta principal' marcada por el dueño (o None). Es la que
        viene preseleccionada en todos los selectores de cuenta. Ver el
        campo `preferida` y core.views_cuentas.CuentaPrincipalAjax."""
        return cls.objects.filter(
            preferida=True, activa=True, caja=TipoCaja.GRANDE, es_credito=False,
        ).first()

    @classmethod
    def principal_pk(cls):
        p = cls.principal()
        return p.pk if p else None


# ══════════════════════════════════════════════════════════════════
#  CUENTA PREDETERMINADA POR MEDIO DE PAGO (sugerencia al cobrar)
# ══════════════════════════════════════════════════════════════════

class CuentaPredeterminadaMedio(models.Model):
    """
    A cuál de las cuentas reales del negocio va, POR DEFECTO, la plata de
    cada medio de pago cuando se cobra una venta (débito/crédito/QR/
    transferencia). Es SOLO una sugerencia para no tener que elegir la
    misma cuenta en cada venta: el <select> del panel de cobro sigue
    mostrando todas las cuentas y el vendedor puede cambiarla en el
    momento (ver ventas/static/ventas/js/detalle_venta.js
    _aplicarMedioALinea). El dueño la configura en Configuración →
    Cuentas de caja.

    Una fila por medio (máximo 4). Efectivo resuelve su cuenta solo,
    cheque no elige "cuenta real" y cuotas es financiación propia: por
    eso no están acá.
    """

    class Medio(models.TextChoices):
        DEBITO        = 'debito',        'Débito'
        CREDITO       = 'credito',       'Crédito'
        QR            = 'qr',            'QR'
        TRANSFERENCIA = 'transferencia', 'Transferencia'

    medio  = models.CharField(max_length=20, choices=Medio.choices, unique=True)
    cuenta = models.ForeignKey('caja.CuentaCaja', on_delete=models.CASCADE,
                               related_name='+')

    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Cuenta predeterminada por medio de pago'
        verbose_name_plural = 'Cuentas predeterminadas por medio de pago'
        ordering            = ['medio']

    def __str__(self):
        return f'{self.get_medio_display()} → {self.cuenta}'

    @classmethod
    def como_dict(cls):
        """{'qr': 5, 'transferencia': 2, ...} — solo con las cuentas que
        sirven de verdad como destino de un cobro (activa, caja GRANDE,
        no es una tarjeta de crédito propia, no es Efectivo). Si una
        cuenta deja de cumplir, su medio simplemente no aparece."""
        out = {}
        for r in cls.objects.select_related('cuenta'):
            c = r.cuenta
            if (c.activa and c.caja == TipoCaja.GRANDE
                    and not c.es_credito and c.tipo != TipoCuenta.EFECTIVO):
                out[r.medio] = c.pk
        return out


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
    origen    = models.CharField(max_length=20, choices=OrigenMovimiento.choices,
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
CONCEPTO_DEVOLUCION_VENTA_NOMBRE = 'Devolución de venta'
CONCEPTO_REDONDEO_VENTA_NOMBRE = 'Redondeo a favor (venta)'
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
      PERO esto solo tiene sentido si existe un turno ABIERTO que
      efectivamente vaya a cerrar y tomar esta venta en su ventana de
      fecha_alta (ver TurnoCaja._ventas_en_turno). Si el turno al que
      pertenece esta venta ya está CERRADO (por ejemplo: se anuló y
      reeditó una venta vieja desde el Historial, después de que su
      turno original ya cerró) — o directamente no hay ningún turno
      que la cubra — ningún cierre futuro va a volver a mirar para
      atrás y contarla: ese efectivo quedaría perdido para siempre en
      Caja Grande. En ese caso se banca acá mismo, de inmediato, igual
      que el resto de los medios.
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
    concepto_redondeo = _concepto_default(CONCEPTO_REDONDEO_VENTA_NOMBRE, TipoMovimientoCaja.INGRESO)

    turno = TurnoCaja.turno_que_contiene(venta.fecha_alta)
    turno_va_a_conciliarla = turno is not None and turno.estado == EstadoTurno.ABIERTO

    pagos_a_sincronizar = venta.pagos.exclude(cuenta__isnull=True).select_related('cuenta')
    if turno_va_a_conciliarla:
        pagos_a_sincronizar = pagos_a_sincronizar.exclude(medio=MedioPago.EFECTIVO)

    movimientos = []
    for pago in pagos_a_sincronizar:
        excedente = pago.redondeo_monto or Decimal('0')
        # El redondeo a favor (lo que el cliente pagó por encima del precio
        # de los productos) va en un movimiento APARTE, con concepto propio
        # — así en Caja Grande queda claro por qué la cuenta tiene unos
        # pesos más que el total de la venta, y se puede sumar/filtrar
        # solo. A ARCA le llega venta.total (nunca el excedente).
        monto_venta = pago.monto - excedente
        if monto_venta > 0:
            movimientos.append(MovimientoCaja.objects.create(
                caja        = TipoCaja.GRANDE,
                cuenta      = pago.cuenta,
                concepto    = concepto,
                tipo        = TipoMovimientoCaja.INGRESO,
                monto       = monto_venta,
                moneda      = pago.cuenta.moneda,
                fecha       = venta.fecha,
                descripcion = f'Venta {venta.numero} ({pago.get_medio_display()})',
                referencia  = venta.numero,
                origen      = OrigenMovimiento.VENTA,
                origen_app  = 'ventas',
                origen_id   = venta.pk,
                creado_por  = venta.confirmado_por,
            ))
        if excedente > 0:
            movimientos.append(MovimientoCaja.objects.create(
                caja        = TipoCaja.GRANDE,
                cuenta      = pago.cuenta,
                concepto    = concepto_redondeo,
                tipo        = TipoMovimientoCaja.INGRESO,
                monto       = excedente,
                moneda      = pago.cuenta.moneda,
                fecha       = venta.fecha,
                descripcion = f'Redondeo a favor — Venta {venta.numero} ({pago.get_medio_display()})',
                referencia  = venta.numero,
                origen      = OrigenMovimiento.VENTA,
                origen_app  = 'ventas',
                origen_id   = venta.pk,
                creado_por  = venta.confirmado_por,
            ))
    return movimientos


@transaction.atomic
def sincronizar_movimiento_devolucion(devolucion):
    """
    Sincroniza el MovimientoCaja (EGRESO) del reembolso de una
    DevolucionVenta. Mismo patrón borrar-y-recrear que
    sincronizar_movimiento_venta, por si en el futuro se agrega poder
    editarla/anularla.

    Mismo criterio de turno abierto/cerrado que las ventas en efectivo,
    pero evaluado sobre el momento en que se REGISTRA la devolución (no
    el de la venta original): si hay un turno ABIERTO que la vaya a
    conciliar, se difiere hasta su cierre (TurnoCaja.cerrar ya resta
    esto del efectivo esperado — ver _devoluciones_en_turno) — el
    cajero entregó el efectivo físico al toque, pero el sistema recién
    lo descuenta de Caja Grande cuando el turno se cierra y se concilia,
    igual que una venta en efectivo. Si no hay turno abierto que la
    cubra, se banca de inmediato, como cualquier otro egreso.

    Se llama desde registrar_devolucion() — no hay forma de editar o
    anular una devolución todavía.
    """
    _borrar_movimiento_origen('ventas', OrigenMovimiento.DEVOLUCION_VENTA, devolucion.pk)

    if not devolucion.cuenta_id or not devolucion.monto:
        return None

    concepto = _concepto_default(CONCEPTO_DEVOLUCION_VENTA_NOMBRE, TipoMovimientoCaja.EGRESO)

    es_efectivo = devolucion.cuenta.tipo == TipoCuenta.EFECTIVO
    turno = TurnoCaja.turno_que_contiene(timezone.now())
    turno_va_a_conciliarla = es_efectivo and turno is not None and turno.estado == EstadoTurno.ABIERTO
    if turno_va_a_conciliarla:
        return None

    return MovimientoCaja.objects.create(
        caja        = TipoCaja.GRANDE,
        cuenta      = devolucion.cuenta,
        concepto    = concepto,
        tipo        = TipoMovimientoCaja.EGRESO,
        monto       = devolucion.monto,
        moneda      = devolucion.cuenta.moneda,
        fecha       = devolucion.fecha,
        descripcion = f'Devolución {devolucion.numero} (venta {devolucion.venta.numero})',
        referencia  = devolucion.venta.numero,
        origen      = OrigenMovimiento.DEVOLUCION_VENTA,
        origen_app  = 'ventas',
        origen_id   = devolucion.pk,
        creado_por  = devolucion.creado_por,
    )


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
      hizo Compras. Excepciones: las líneas pagadas con tarjeta de
      crédito (medio=CREDITO) NO generan egreso acá — esa plata no
      sale de la caja al confirmar la compra, sale de a poco cuando
      se confirma cada CuotaDeuda de la Deuda asociada (ver
      sincronizar_movimiento_cuota). Tampoco las de cheque (medio=CHEQUE):
      aunque sí tienen `cuenta` (la chequera), el egreso real recién
      ocurre cuando se confirma cada Cheque por separado (ver
      sincronizar_movimiento_cheque) — la compra solo deja el cheque
      cargado como PENDIENTE.
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
        .exclude(medio__in=[MedioPagoCompra.CREDITO, MedioPagoCompra.CHEQUE])
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
    - `total_recaudado` es SOLO plata real (efectivo/transferencia/débito/
      crédito/QR). Cheque y cuotas se venden en el turno pero no son plata
      todavía — quedan aparte en `total_financiado_pendiente`, para no
      mostrar como "recaudado" algo que todavía puede no cobrarse nunca.
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

    # Medios de pago que NO meten plata real en caja en el momento de la
    # venta: cheque (hasta que se cobra) y cuotas (financiación propia,
    # hasta que cada cuota se confirma). Ver MedioPago en ventas/models.py.
    MEDIOS_PENDIENTES = {'cheque', 'cuotas'}

    @property
    def totales_medio_pago(self):
        """
        Totales de ventas por medio de pago (TODOS los medios, incluidos
        cheque/cuotas) — desglose completo informativo.

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
    def totales_medio_pago_inmediato(self):
        """Medios que ya son plata real en caja (efectivo, transferencia, débito, crédito, QR)."""
        return {k: v for k, v in self.totales_medio_pago.items() if k not in self.MEDIOS_PENDIENTES}

    @property
    def totales_medio_pago_pendiente(self):
        """Cheque y cuotas: monto vendido pero todavía no cobrado — no es plata real todavía."""
        return {k: v for k, v in self.totales_medio_pago.items() if k in self.MEDIOS_PENDIENTES}

    @property
    def total_recaudado(self):
        """
        Plata real que entró en el turno. NO incluye cheques ni cuotas
        vendidos en el turno pero todavía no cobrados — eso se expone
        aparte en total_financiado_pendiente, para no mezclar una venta
        con el cobro real de esa venta.
        """
        return sum(self.totales_medio_pago_inmediato.values())

    @property
    def total_financiado_pendiente(self):
        """Monto vendido con cheque/cuotas en este turno, todavía sin cobrar."""
        return sum(self.totales_medio_pago_pendiente.values())

    @property
    def correcciones_posteriores(self):
        """
        Ventas que pertenecieron a este turno (por fecha_alta, dentro de
        su ventana de apertura/cierre) y se anularon DESPUÉS de que el
        turno ya había cerrado — algo que el cierre original no podía
        saber en su momento. `totales_cierre` queda intacto a propósito
        (nunca se reescribe retroactivamente); esto es solo para poder
        avisar que existe una corrección posterior, como una nota de
        ajuste que referencia un cierre ya hecho, sin tocarlo.
        """
        if self.estado != EstadoTurno.CERRADO or not self.fecha_cierre:
            from ventas.models import Venta
            return Venta.objects.none()
        from ventas.models import Venta, EstadoVenta
        return Venta.objects.filter(
            fecha_alta__gte=self.fecha_apertura, fecha_alta__lte=self.fecha_cierre,
            estado=EstadoVenta.ANULADA, fecha_anulacion__gt=self.fecha_cierre,
        ).order_by('-fecha_anulacion')

    @property
    def impacto_correcciones_posteriores(self):
        """
        Cuánto del total_recaudado original quedó desactualizado por esas
        correcciones — solo medios inmediatos (cheque/cuotas nunca
        entraron en total_recaudado, así que anularlos no lo cambia).
        """
        total = Decimal('0')
        for venta in self.correcciones_posteriores:
            total += sum(
                (p.monto for p in venta.pagos.all() if p.medio not in self.MEDIOS_PENDIENTES),
                Decimal('0'),
            )
        return total

    @property
    def efectivo_ventas(self):
        """Total cobrado en efectivo en ventas de este turno — INCLUYE el
        redondeo a favor (está dentro de PagoVenta.monto). Para el efectivo
        físico esperado tiene que ser así; el desglose está en
        efectivo_ventas_sin_redondeo + redondeos_efectivo."""
        return self.totales_medio_pago.get('efectivo', 0)

    @property
    def redondeos_turno(self):
        """Suma de TODO el redondeo a favor de ventas de este turno (lo que
        los clientes pagaron por encima del precio de los productos — en
        efectivo y en otros medios). Plata real que entró pero que NO es
        precio de venta: se deja afuera de la Ganancia y se muestra aparte.
        Congelado en el snapshot si el turno ya cerró."""
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return Decimal(self.totales_cierre.get('redondeos_turno', '0'))
        return self.calcular_redondeos_en_turno()

    @property
    def redondeos_efectivo(self):
        """Redondeo a favor que entró en EFECTIVO — al cajón físico, así
        que afecta el arqueo. Congelado si el turno ya cerró."""
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return Decimal(self.totales_cierre.get('redondeos_efectivo', '0'))
        return self.calcular_redondeos_en_turno(solo_efectivo=True)

    @property
    def redondeos_otros_medios(self):
        """Redondeo a favor que entró por un medio que no es efectivo
        (transferencia, QR...). Ya se acreditó en la cuenta bancaria al
        confirmar la venta, no toca el arqueo del cajón."""
        return self.redondeos_turno - self.redondeos_efectivo

    @property
    def efectivo_ventas_sin_redondeo(self):
        """efectivo_ventas menos el redondeo — el precio de venta puro."""
        return self.efectivo_ventas - self.redondeos_efectivo

    @property
    def efectivo_cuotas_cobradas(self):
        """
        Cobrado en efectivo durante este turno por cuotas VIEJAS de CxC
        (deudas de clientes de ventas anteriores) — plata real que entra
        al mismo cajón físico que las ventas de hoy, pero que NO es venta
        de hoy. Se muestra aparte a propósito (ver efectivo_total): que
        quede claro de dónde salió, no que "aparezca" mezclada con lo
        vendido. Si el turno ya cerró, devuelve el valor congelado.
        """
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return Decimal(self.totales_cierre.get('efectivo_cuotas_cobradas', '0'))
        return self.calcular_efectivo_cuotas_cobradas_en_turno()

    @property
    def efectivo_cuotas_pagadas(self):
        """Pagado en efectivo durante este turno por cuotas VIEJAS de
        Deuda (lo que le debíamos a un proveedor) — mismo criterio que
        efectivo_cuotas_cobradas, pero en la dirección contraria (sale
        del cajón, no entra)."""
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return Decimal(self.totales_cierre.get('efectivo_cuotas_pagadas', '0'))
        return self.calcular_efectivo_cuotas_pagadas_en_turno()

    @property
    def ingresos_manuales(self):
        """Ingresos manuales de caja diaria de este turno (plata que entró
        al cajón y no es venta). Congelado si el turno ya cerró."""
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return Decimal(self.totales_cierre.get('ingresos_manuales', '0'))
        return self.calcular_ingresos_manuales_en_turno()

    @property
    def egresos_manuales(self):
        """Egresos manuales de caja diaria de este turno (plata que se
        retiró del cajón). Congelado si el turno ya cerró."""
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return Decimal(self.totales_cierre.get('egresos_manuales', '0'))
        return self.calcular_egresos_manuales_en_turno()

    @property
    def efectivo_total(self):
        """
        Efectivo que se espera encontrar AHORA MISMO en el cajón físico
        de este turno (o el que había al cerrarlo, si ya cerró — usa el
        valor congelado). Mismos 4 componentes que usa cerrar() para
        calcular la diferencia: ver _componentes_efectivo_esperado().
        """
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            return Decimal(self.totales_cierre.get('esperado_efectivo', '0'))
        return self._componentes_efectivo_esperado()['esperado']

    @property
    def ganancia_turno(self):
        """Ganancia BRUTA del turno. Es lo que se ganó con lo vendido en
        este turno, NO la recaudación (eso es total_recaudado). Se arma
        con dos partes:

          1. Margen de la mercadería: por cada producto vendido, el
             precio de venta cobrado (con su descuento) menos el costo
             real del lote del que salió cada unidad (vía
             ConsumoLoteVenta).
          2. Lo que el cliente pagó por encima del precio de lista:
             redondeo a favor + recargo por medio de pago. Es plata que
             entró y que no tiene costo asociado, así que es ganancia.

        Cuenta TODAS las ventas confirmadas del turno, también las de
        cheque/cuotas (la venta ya se hizo; que el cobro esté pendiente
        es otra cosa). No descuenta gastos ni egresos manuales (eso
        sería la ganancia NETA). Congelada en el snapshot si el turno
        ya cerró."""
        if self.estado == EstadoTurno.CERRADO and self.totales_cierre:
            congelado = self.totales_cierre.get('ganancia_bruta_turno')
            if congelado is not None:
                return Decimal(congelado)
        return self.calcular_ganancia_bruta_turno()

    def calcular_ganancia_bruta_turno(self):
        """Margen de la mercadería vendida (precio cobrado − costo real
        del lote) MÁS lo cobrado por encima del precio de lista (redondeo
        a favor + recargo por medio de pago), para las ventas confirmadas
        de este turno. Ver ganancia_turno. Se calcula en caliente; el
        cierre lo congela en totales_cierre."""
        from ventas.models import ItemVenta, ConsumoLoteVenta, PagoVenta
        ventas = self._ventas_en_turno()
        money = DecimalField(max_digits=14, decimal_places=2)
        ingresos = (
            ItemVenta.objects.filter(venta__in=ventas)
            .annotate(_sub=ExpressionWrapper(
                F('cantidad') * F('precio_unitario') * (1 - F('descuento_pct') / 100),
                output_field=money))
            .aggregate(t=Sum('_sub'))['t'] or Decimal('0')
        )
        costo = (
            ConsumoLoteVenta.objects.filter(item_venta__venta__in=ventas)
            .annotate(_c=ExpressionWrapper(
                F('cantidad') * F('costo_unitario_snapshot'), output_field=money))
            .aggregate(t=Sum('_c'))['t'] or Decimal('0')
        )
        extra = PagoVenta.objects.filter(venta__in=ventas).aggregate(
            r=Sum('recargo_monto'), d=Sum('redondeo_monto'))
        extra_cobrado = (extra['r'] or Decimal('0')) + (extra['d'] or Decimal('0'))
        return ingresos - costo + extra_cobrado

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

    def productos_vendidos_sin_stock_pendientes(self):
        """
        Productos/variantes que se vendieron SIN stock en este turno
        (ConsumoLoteVenta sin lote — ver
        core.ConfiguracionVentas.permitir_venta_sin_stock) y que TODAVÍA
        tienen stock negativo. Mientras haya alguno, el turno no se puede
        cerrar: hay que cargar la mercadería que falta (una compra o un
        ajuste de stock) para que el balance del turno cierre.

        Devuelve [{'nombre': str, 'faltante': Decimal}, ...] ordenado por
        nombre. `faltante` es el stock negativo expresado en positivo.
        """
        from ventas.models import ConsumoLoteVenta
        from productos.models import Producto, CombinacionVariante

        consumos = (
            ConsumoLoteVenta.objects
            .filter(item_venta__venta__in=self._ventas_en_turno(), lote__isnull=True)
            .select_related('item_venta')
        )

        # (producto_id, combinacion_id) únicos — un mismo producto puede
        # haberse vendido sin stock en varias ventas del turno.
        claves = set()
        for c in consumos:
            it = c.item_venta
            if it.producto_id is None:
                continue
            claves.add((it.producto_id, it.combinacion_id))

        pendientes = []
        for prod_id, comb_id in claves:
            if comb_id:
                comb = (CombinacionVariante.objects
                        .select_related('producto')
                        .filter(pk=comb_id).first())
                if comb is None or comb.stock_actual >= 0:
                    continue
                nombre = f'{comb.producto.nombre} — {comb.descripcion_legible()}'
                faltante = -comb.stock_actual
            else:
                prod = Producto.objects.filter(pk=prod_id).first()
                if prod is None or prod.stock_actual >= 0:
                    continue
                nombre = prod.nombre
                faltante = -prod.stock_actual
            pendientes.append({'nombre': nombre, 'faltante': faltante})

        pendientes.sort(key=lambda p: p['nombre'].lower())
        return pendientes

    def _devoluciones_en_turno(self):
        """Devoluciones de venta reembolsadas en EFECTIVO dentro de la
        ventana horaria de este turno — ver calcular_efectivo_devuelto_en_turno."""
        from ventas.models import DevolucionVenta
        return DevolucionVenta.objects.filter(
            cuenta__tipo=TipoCuenta.EFECTIVO,
            fecha_alta__gte=self.fecha_apertura,
            fecha_alta__lte=self.fecha_cierre if self.fecha_cierre else timezone.now(),
        )

    def calcular_efectivo_devuelto_en_turno(self):
        """
        Total reembolsado en efectivo durante este turno (ver
        sincronizar_movimiento_devolucion: mientras el turno está
        ABIERTO ese egreso se difiere, igual que las ventas en
        efectivo). Hace falta restarlo del efectivo "esperado" al
        cerrar — el cajero ya entregó ese efectivo físico al cliente,
        así que lo que queda contado en el cajón está de por sí por
        debajo de "inicial + ventas"; si no se resta acá, el cierre
        muestra un faltante que en realidad no es tal.
        """
        return self._devoluciones_en_turno().aggregate(total=Sum('monto'))['total'] or Decimal('0')

    def _cuotas_cobradas_en_turno(self):
        """CuotaCobro (cuotas viejas de clientes) confirmadas en EFECTIVO
        dentro de la ventana horaria de este turno — filtra por la fecha
        en que se confirmó el cobro, no por cuándo nació la cuenta por
        cobrar. Ver calcular_efectivo_cuotas_cobradas_en_turno."""
        return CuotaCobro.objects.filter(
            estado=EstadoCuota.CONFIRMADA,
            cuenta_cobro__tipo=TipoCuenta.EFECTIVO,
            fecha_confirmacion__gte=self.fecha_apertura,
            fecha_confirmacion__lte=self.fecha_cierre if self.fecha_cierre else timezone.now(),
        )

    def _cuotas_pagadas_en_turno(self):
        """CuotaDeuda (cuotas viejas que le debíamos a un proveedor)
        confirmadas en EFECTIVO dentro de la ventana horaria de este
        turno — mismo criterio que _cuotas_cobradas_en_turno, en la
        dirección contraria."""
        return CuotaDeuda.objects.filter(
            estado=EstadoCuota.CONFIRMADA,
            cuenta_pago__tipo=TipoCuenta.EFECTIVO,
            fecha_confirmacion__gte=self.fecha_apertura,
            fecha_confirmacion__lte=self.fecha_cierre if self.fecha_cierre else timezone.now(),
        )

    def calcular_efectivo_cuotas_cobradas_en_turno(self):
        """
        Total cobrado en efectivo durante este turno por cuotas VIEJAS de
        CxC (ver sincronizar_movimiento_cuota_cobro: mientras el turno
        está ABIERTO ese ingreso se difiere, igual que una venta en
        efectivo — el cajero recibe esa plata físicamente en el mismo
        cajón, así que el cierre tiene que esperarla para no mostrar una
        sobra sin explicación).
        """
        return self._cuotas_cobradas_en_turno().aggregate(total=Sum('monto'))['total'] or Decimal('0')

    def calcular_efectivo_cuotas_pagadas_en_turno(self):
        """Total pagado en efectivo durante este turno por cuotas VIEJAS
        de Deuda — mismo criterio que calcular_efectivo_cuotas_cobradas_en_turno,
        pero resta en vez de sumar (sale plata del cajón, no entra)."""
        return self._cuotas_pagadas_en_turno().aggregate(total=Sum('monto'))['total'] or Decimal('0')

    def calcular_ingresos_manuales_en_turno(self):
        """Ingresos manuales cargados en la pantalla de Caja Diaria para
        este turno (Gasto con turno=self, tipo INGRESO) — plata que entró
        al cajón físico y que no es venta (ej: un aporte, una devolución
        de vuelto, plata que trajo el dueño). Suma al efectivo esperado."""
        from .models import Gasto
        return Gasto.objects.filter(
            turno=self, tipo=TipoMovimientoCaja.INGRESO,
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0')

    def calcular_egresos_manuales_en_turno(self):
        """Egresos manuales cargados en la pantalla de Caja Diaria para
        este turno (Gasto con turno=self, tipo EGRESO) — plata que salió
        del cajón físico (ej: se retiró efectivo para pagar algo). Resta
        del efectivo esperado."""
        from .models import Gasto
        return Gasto.objects.filter(
            turno=self, tipo=TipoMovimientoCaja.EGRESO,
        ).aggregate(total=Sum('monto'))['total'] or Decimal('0')

    def _componentes_efectivo_esperado(self):
        """
        Desglose completo de lo que se espera encontrar en el cajón
        físico de este turno: inicial + ventas en efectivo - devoluciones
        en efectivo + cuotas viejas cobradas en efectivo - cuotas viejas
        pagadas en efectivo + ingresos manuales de caja diaria - egresos
        manuales de caja diaria. Usado tanto por efectivo_total (mientras
        el turno sigue abierto) como por cerrar() — un solo lugar con la
        fórmula, para que nunca queden desincronizados.
        """
        efectivo_ventas = self.efectivo_ventas  # incluye el redondeo a favor
        efectivo_redondeos = self.calcular_redondeos_en_turno(solo_efectivo=True)
        efectivo_devuelto = self.calcular_efectivo_devuelto_en_turno()
        efectivo_cuotas_cobradas = self.calcular_efectivo_cuotas_cobradas_en_turno()
        efectivo_cuotas_pagadas = self.calcular_efectivo_cuotas_pagadas_en_turno()
        ingresos_manuales = self.calcular_ingresos_manuales_en_turno()
        egresos_manuales = self.calcular_egresos_manuales_en_turno()
        esperado = (
            (self.monto_inicial_efectivo or 0) + efectivo_ventas - efectivo_devuelto
            + efectivo_cuotas_cobradas - efectivo_cuotas_pagadas
            + ingresos_manuales - egresos_manuales
        )
        return {
            'efectivo_ventas': efectivo_ventas,
            'efectivo_ventas_sin_redondeo': efectivo_ventas - efectivo_redondeos,
            'efectivo_redondeos': efectivo_redondeos,
            'efectivo_devuelto': efectivo_devuelto,
            'efectivo_cuotas_cobradas': efectivo_cuotas_cobradas,
            'efectivo_cuotas_pagadas': efectivo_cuotas_pagadas,
            'ingresos_manuales': ingresos_manuales,
            'egresos_manuales': egresos_manuales,
            'esperado': esperado,
        }

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

    def calcular_redondeos_en_turno(self, solo_efectivo=False):
        """
        Suma de PagoVenta.redondeo_monto de las ventas de este turno —
        lo que los clientes pagaron de más por redondeo. Con
        solo_efectivo=True, únicamente las líneas cobradas en efectivo
        (las que afectan el conteo físico del cajón).
        """
        from ventas.models import MedioPago, PagoVenta

        qs = PagoVenta.objects.filter(venta__in=self._ventas_en_turno())
        if solo_efectivo:
            qs = qs.filter(medio=MedioPago.EFECTIVO)
        return qs.aggregate(total=Sum('redondeo_monto'))['total'] or Decimal('0')

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

            # Ventas sin stock: no se puede cerrar mientras algún producto
            # que se vendió sin stock en este turno siga en negativo — el
            # balance del turno no cerraría (ver ConfiguracionVentas).
            pendientes = self.productos_vendidos_sin_stock_pendientes()
            if pendientes:
                detalle = ' · '.join(
                    f"{p['nombre']} (faltan {_fmt_cantidad(p['faltante'])})"
                    for p in pendientes
                )
                raise ValueError(
                    'No se puede cerrar el turno: hay productos que se vendieron sin stock '
                    'en este turno y todavía están en negativo. Cargá la mercadería que falta '
                    '(una compra o un ajuste de stock) y volvé a cerrar. '
                    f'Pendiente de cargar → {detalle}.'
                )

            # Calcular totales por medio de pago (en caliente, todavía
            # no está cerrado el turno en este punto)
            totales = self.calcular_totales_por_medio_pago()
            total_recaudado = sum(v for k, v in totales.items() if k not in self.MEDIOS_PENDIENTES)
            total_financiado_pendiente = sum(v for k, v in totales.items() if k in self.MEDIOS_PENDIENTES)

            # Mismos 4 componentes que efectivo_total calcula mientras el
            # turno sigue abierto — un solo lugar con la fórmula (ver
            # _componentes_efectivo_esperado), así nunca quedan
            # desincronizados entre lo que se mostró en pantalla y lo que
            # efectivamente se congela acá.
            componentes = self._componentes_efectivo_esperado()
            efectivo_devuelto = componentes['efectivo_devuelto']
            efectivo_cuotas_cobradas = componentes['efectivo_cuotas_cobradas']
            efectivo_cuotas_pagadas = componentes['efectivo_cuotas_pagadas']
            ingresos_manuales = componentes['ingresos_manuales']
            egresos_manuales = componentes['egresos_manuales']
            esperado = componentes['esperado']
            redondeos_turno = self.calcular_redondeos_en_turno()
            redondeos_efectivo = componentes['efectivo_redondeos']

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
                'total_financiado_pendiente': str(total_financiado_pendiente),
                'redondeos_turno': str(redondeos_turno),
                'redondeos_efectivo': str(redondeos_efectivo),
                'ganancia_bruta_turno': str(self.calcular_ganancia_bruta_turno()),
                'esperado_efectivo': str(esperado),
                'declarado_efectivo': str(monto_final_efectivo),
                'efectivo_devuelto': str(efectivo_devuelto),
                'efectivo_cuotas_cobradas': str(efectivo_cuotas_cobradas),
                'efectivo_cuotas_pagadas': str(efectivo_cuotas_pagadas),
                'ingresos_manuales': str(ingresos_manuales),
                'egresos_manuales': str(egresos_manuales),
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

            # ── 1. Efectivo: vuelve a caja grande ───────────────────
            # Se acredita el BRUTO del cajón (lo contado + lo que se
            # retiró como egreso de caja diaria - lo que entró como
            # ingreso de caja diaria) y esos ingresos/egresos se
            # registran aparte, línea por línea (ver más abajo), para
            # que el libro de caja grande muestre a dónde fue cada peso.
            # El neto es idéntico a acreditar solo lo contado:
            #   bruto - egresos_manuales + ingresos_manuales = declarado.
            cuenta_efectivo = _cuenta_grande_para_medio_pago('efectivo', 'Efectivo', moneda=Moneda.ARS)
            concepto_cierre_efectivo = _concepto_default('Cierre de turno - Efectivo', TipoMovimientoCaja.INGRESO)

            bruto_efectivo = monto_final_efectivo + egresos_manuales - ingresos_manuales

            if bruto_efectivo and bruto_efectivo > 0:
                detalle_cajas = (
                    ' (' + ', '.join(f"{c['nombre']}: {c['monto']}" for c in cajas) + ')'
                    if len(cajas) > 1 else ''
                )
                MovimientoCaja.objects.create(
                    caja=TipoCaja.GRANDE,
                    cuenta=cuenta_efectivo,
                    concepto=concepto_cierre_efectivo,
                    tipo=TipoMovimientoCaja.INGRESO,
                    monto=bruto_efectivo,
                    moneda=Moneda.ARS,
                    fecha=fecha_cierre,
                    descripcion=(
                        f'Cierre turno #{self.numero} — efectivo contado {monto_final_efectivo} '
                        f'(esperado {esperado}, diferencia {self.diferencia_efectivo})'
                        + detalle_cajas
                    ),
                    referencia=f'Turno #{self.numero}',
                    origen=OrigenMovimiento.AJUSTE,
                    origen_app='caja',
                    origen_id=self.pk,
                    creado_por=usuario,
                )

            # ── Ingresos/egresos manuales de caja diaria de este turno ──
            # Ya venían "descontados/sumados" del cajón físico durante el
            # turno; recién ahora impactan caja grande, cada uno con su
            # propia línea (mismo criterio que una venta en efectivo, que
            # espera al cierre).
            for g in self.movimientos_manuales.all():
                MovimientoCaja.objects.create(
                    caja=TipoCaja.GRANDE,
                    cuenta=cuenta_efectivo,
                    concepto=_concepto_default(
                        'Ingreso' if g.tipo == TipoMovimientoCaja.INGRESO else 'Gasto',
                        g.tipo,
                    ),
                    tipo=g.tipo,
                    monto=g.monto,
                    moneda=Moneda.ARS,
                    fecha=g.fecha,
                    descripcion=f'{g.descripcion} · Caja diaria turno #{self.numero}',
                    referencia=f'Turno #{self.numero}',
                    origen=OrigenMovimiento.MANUAL,
                    origen_app='caja',
                    origen_id=g.pk,
                    creado_por=g.creado_por,
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
#  CONCEPTO DE GASTO  (rubro de un ingreso/egreso manual)
#
#  Catálogo liviano de conceptos reutilizables para la pantalla de
#  Ingresos y egresos (combustible, luz, agua, sueldos...). OJO: es
#  distinto de ConceptoMovimiento — ese categoriza los asientos de
#  caja grande (Venta/Compra/...). Este solo etiqueta el Gasto para
#  dos cosas: alimentar el autocompletado de la descripción y agrupar
#  en Estadísticas ("¿cuánto gasté en combustible este mes?").
#
#  La descripción del Gasto SIGUE siendo texto libre. El catálogo se
#  puebla solo: cada descripción nueva que se carga queda registrada
#  acá, deduplicada por nombre normalizado (minúsculas + espacios
#  colapsados) — así "Combustible", "combustible " y "COMBUSTIBLE"
#  son el mismo concepto.
# ══════════════════════════════════════════════════════════════════

def _normalizar_concepto_gasto(nombre):
    """'  Combustible   Nafta ' → 'combustible nafta' (para deduplicar)."""
    return ' '.join((nombre or '').split()).lower()[:120]


class ConceptoGasto(models.Model):
    nombre = models.CharField(max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, editable=False)
    tipo = models.CharField(
        max_length=10, choices=TipoMovimientoCaja.choices,
        default=TipoMovimientoCaja.EGRESO,
        help_text='Si suele ser ingreso o egreso — ordena las sugerencias.',
    )
    activo = models.BooleanField(default=True)
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Concepto de ingreso/egreso'
        verbose_name_plural = 'Conceptos de ingresos/egresos'
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    @classmethod
    def resolver(cls, nombre, tipo=None):
        """Get-or-create por nombre normalizado. Devuelve el concepto, o
        None si el nombre viene vacío. No pisa el `tipo` de un concepto
        que ya existía."""
        norm = _normalizar_concepto_gasto(nombre)
        if not norm:
            return None
        obj, _ = cls.objects.get_or_create(
            nombre_normalizado=norm,
            defaults={
                'nombre': ' '.join(nombre.split())[:120],
                'tipo': tipo or TipoMovimientoCaja.EGRESO,
            },
        )
        return obj


# ══════════════════════════════════════════════════════════════════
#  GASTO
# ══════════════════════════════════════════════════════════════════

class Gasto(models.Model):
    """
    Movimiento manual de caja grande: ingreso o egreso libre (sueldo,
    herencia, regalo, alquiler, mecánico, luz, etc.). La descripción
    queda libre a propósito; además se resuelve sola contra un catálogo
    liviano de conceptos (ver ConceptoGasto / campo `concepto`) para el
    autocompletado y para agrupar en Estadísticas.

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

    # ── Movimiento de CAJA DIARIA (efectivo del cajón de un turno) ──
    # Si `turno` está seteado, este ingreso/egreso NO impacta caja grande
    # de inmediato: sale/entra del cajón físico del turno (igual que una
    # venta en efectivo). Ajusta el efectivo esperado del turno mientras
    # está abierto y, al cerrar, se vuelca a caja grande como su propia
    # línea (ver TurnoCaja.cerrar). `cuenta` queda en la cuenta Efectivo
    # por consistencia de FK/serialización, pero no se elige a mano.
    turno = models.ForeignKey(
        'TurnoCaja', on_delete=models.PROTECT,
        null=True, blank=True, related_name='movimientos_manuales',
        help_text='Si viene de la pantalla de Caja Diaria: el turno cuyo cajón afecta.',
    )

    fecha = models.DateField(help_text='Fecha del movimiento')
    hora = models.TimeField(help_text='Hora del movimiento (automática)')
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)
    descripcion = models.CharField(max_length=300, help_text='Ej: alquiler, mecánico, luz, sueldo, herencia, regalo')
    concepto = models.ForeignKey(
        'ConceptoGasto', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='gastos',
        help_text='Concepto del catálogo — se resuelve solo desde la descripción.',
    )

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
    
    @property
    def es_caja_diaria(self):
        return self.turno_id is not None

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            # Establecer hora automáticamente al crear
            if not self.hora:
                self.hora = timezone.localtime().time()

        # Mantener `concepto` en sync con la descripción: si está vacío o
        # ya no coincide con el nombre normalizado del concepto actual,
        # se resuelve de nuevo (get-or-create en el catálogo). Cubre
        # TODAS las vías de alta de Gasto (pantalla de Ingresos y egresos,
        # confirmación de un programado, movimiento de caja diaria).
        update_fields = kwargs.get('update_fields')
        toca_descripcion = update_fields is None or {'descripcion', 'concepto'} & set(update_fields)
        if toca_descripcion:
            norm = _normalizar_concepto_gasto(self.descripcion)
            actual = self.concepto.nombre_normalizado if self.concepto_id else None
            if norm and actual != norm:
                self.concepto = ConceptoGasto.resolver(self.descripcion, self.tipo)
                if update_fields is not None and 'concepto' not in update_fields:
                    kwargs['update_fields'] = list(update_fields) + ['concepto']
            elif not norm and self.concepto_id:
                self.concepto = None

        super().save(*args, **kwargs)

        # Sincronizar movimiento de caja grande — SALVO que sea un
        # movimiento de caja diaria: ese se difiere hasta el cierre del
        # turno (TurnoCaja.cerrar lo vuelca), igual que una venta en
        # efectivo.
        if is_new and not self.turno_id:
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

    Los movimientos de CAJA DIARIA (gasto.turno seteado) no se tocan acá:
    su MovimientoCaja lo genera el cierre del turno (TurnoCaja.cerrar) y no
    se pueden editar una vez cerrado el turno.
    """
    if gasto.turno_id and Gasto.objects.filter(pk=gasto.pk).exists():
        return

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
#  MOVIMIENTOS PROGRAMADOS (ingresos/egresos recurrentes)
#
#  Un MovimientoProgramado es la "plantilla" de algo que se repite en
#  el tiempo (sueldo, alquiler, cuenta de luz). No es un Gasto ni toca
#  la caja por sí solo: cuando llega su próxima_fecha, genera una
#  InstanciaProgramada "pendiente de confirmar" (ver
#  generar_instancias_pendientes(), llamada perezosamente al visitar
#  la pantalla — no hay ningún scheduler corriendo en este proyecto,
#  mismo criterio que procesar_lotes_vencidos en compras). Recién al
#  confirmar esa instancia a mano se crea el Gasto real — igual
#  filosofía que CuotaDeuda: nada mueve la caja solo.
# ══════════════════════════════════════════════════════════════════

class FrecuenciaProgramado(models.TextChoices):
    DIARIO    = 'diario',    'Diario'
    SEMANAL   = 'semanal',   'Semanal'
    QUINCENAL = 'quincenal', 'Quincenal'
    MENSUAL   = 'mensual',   'Mensual'
    BIMESTRAL = 'bimestral', 'Bimestral'
    ANUAL     = 'anual',     'Anual'


class TipoMontoProgramado(models.TextChoices):
    FIJO     = 'fijo',     'Monto fijo (igual cada vez)'
    VARIABLE = 'variable', 'Monto variable (se carga cada vez)'


class EstadoInstanciaProgramada(models.TextChoices):
    PENDIENTE  = 'pendiente',  'Pendiente'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


class MovimientoProgramado(models.Model):
    """Plantilla de un ingreso/egreso recurrente. Ver comentario de sección arriba."""

    tipo = models.CharField(max_length=10, choices=TipoMovimientoCaja.choices)
    descripcion = models.CharField(
        max_length=300,
        help_text='Ej: "Alquiler local", "Sueldo Juan Pérez", "Cuenta de luz".',
    )
    cuenta = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, related_name='programados',
        help_text='Cuenta sugerida al confirmar cada instancia (se puede cambiar en el momento).',
    )
    moneda = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)

    tipo_monto = models.CharField(max_length=10, choices=TipoMontoProgramado.choices)
    monto_fijo = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Solo si tipo_monto=fijo — se precarga en cada instancia (editable al confirmar).',
    )

    frecuencia = models.CharField(max_length=10, choices=FrecuenciaProgramado.choices)
    proxima_fecha = models.DateField(
        help_text='Próxima fecha en la que se genera la siguiente instancia pendiente.',
    )

    activo = models.BooleanField(
        default=True,
        help_text='Si se pausa, no genera más instancias nuevas — las ya generadas se pueden '
                   'seguir confirmando o anulando igual.',
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='programados_creados',
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Movimiento programado'
        verbose_name_plural = 'Movimientos programados'
        ordering             = ['proxima_fecha']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.descripcion}'

    def avanzar_proxima_fecha(self):
        """Corre proxima_fecha un período hacia adelante, según frecuencia."""
        if self.frecuencia == FrecuenciaProgramado.DIARIO:
            self.proxima_fecha = self.proxima_fecha + timedelta(days=1)
        elif self.frecuencia == FrecuenciaProgramado.SEMANAL:
            self.proxima_fecha = self.proxima_fecha + timedelta(days=7)
        elif self.frecuencia == FrecuenciaProgramado.QUINCENAL:
            self.proxima_fecha = self.proxima_fecha + timedelta(days=15)
        elif self.frecuencia == FrecuenciaProgramado.BIMESTRAL:
            self.proxima_fecha = _sumar_meses(self.proxima_fecha, 2)
        elif self.frecuencia == FrecuenciaProgramado.ANUAL:
            self.proxima_fecha = _sumar_meses(self.proxima_fecha, 12)
        else:  # MENSUAL
            self.proxima_fecha = _sumar_meses(self.proxima_fecha, 1)


class InstanciaProgramada(models.Model):
    """
    Una repetición concreta de un MovimientoProgramado, pendiente de
    confirmar. Solo existen instancias de fechas ya vencidas (no se
    pre-generan a futuro) — ver generar_instancias_pendientes().
    """

    programado = models.ForeignKey(
        MovimientoProgramado, on_delete=models.CASCADE, related_name='instancias',
    )
    fecha_vencimiento = models.DateField()
    estado = models.CharField(
        max_length=10, choices=EstadoInstanciaProgramada.choices,
        default=EstadoInstanciaProgramada.PENDIENTE,
    )
    monto = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Precargado si el programado es de monto fijo; vacío si es variable '
                   'hasta que se completa al confirmar.',
    )
    gasto = models.OneToOneField(
        Gasto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='instancia_programada',
    )
    fecha_confirmacion = models.DateTimeField(null=True, blank=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='instancias_programadas_confirmadas',
    )

    class Meta:
        verbose_name        = 'Instancia programada'
        verbose_name_plural = 'Instancias programadas'
        ordering             = ['fecha_vencimiento']
        unique_together      = [('programado', 'fecha_vencimiento')]

    def __str__(self):
        return f'{self.programado.descripcion} — {self.fecha_vencimiento}'

    @transaction.atomic
    def confirmar(self, *, monto, cuenta, fecha, usuario):
        # select_for_update(): mismo guard que CuotaDeuda.confirmar() —
        # un doble clic no debe generar dos Gastos.
        if InstanciaProgramada.objects.select_for_update().get(pk=self.pk).estado != EstadoInstanciaProgramada.PENDIENTE:
            raise ValueError('Solo se pueden confirmar instancias pendientes.')

        monto = Decimal(str(monto))
        if monto <= 0:
            raise ValueError('El monto debe ser mayor a cero.')

        gasto = Gasto.objects.create(
            tipo=self.programado.tipo,
            cuenta=cuenta,
            fecha=fecha,
            monto=monto,
            moneda=self.programado.moneda,
            descripcion=self.programado.descripcion,
            creado_por=usuario,
        )
        self.monto              = monto
        self.gasto               = gasto
        self.estado              = EstadoInstanciaProgramada.CONFIRMADA
        self.fecha_confirmacion  = timezone.now()
        self.confirmado_por      = usuario
        self.save(update_fields=['monto', 'gasto', 'estado', 'fecha_confirmacion', 'confirmado_por'])

    def anular(self):
        if self.estado != EstadoInstanciaProgramada.PENDIENTE:
            raise ValueError('Solo se pueden anular instancias pendientes.')
        self.estado = EstadoInstanciaProgramada.ANULADA
        self.save(update_fields=['estado'])


def generar_instancias_pendientes():
    """
    Genera las InstanciaProgramada que ya vencieron desde la última vez
    que se llamó a esto — mismo criterio perezoso que
    compras.procesar_lotes_vencidos(): no hay scheduler en este
    proyecto, así que se corre cada vez que alguien visita la pantalla
    de Programados. Si nadie entró en un tiempo, se generan de una
    todas las instancias atrasadas (una por período) para que el
    usuario decida cada una: confirmar o anular.
    """
    hoy = timezone.localtime().date()
    creadas = 0
    for programado in MovimientoProgramado.objects.filter(activo=True, proxima_fecha__lte=hoy):
        intentos = 0
        # Tope de seguridad por si proxima_fecha quedó muy atrás: para los
        # mensuales/anuales 60 vueltas son años; para el DIARIO son solo 60
        # días, así que se le da margen de ~1 año. Si el atraso supera el
        # tope, se completa en las siguientes visitas a la pantalla (la
        # próxima_fecha ya quedó avanzada y get_or_create evita duplicados).
        tope = 370 if programado.frecuencia == FrecuenciaProgramado.DIARIO else 60
        while programado.proxima_fecha <= hoy and intentos < tope:
            monto_inicial = programado.monto_fijo if programado.tipo_monto == TipoMontoProgramado.FIJO else None
            _, created = InstanciaProgramada.objects.get_or_create(
                programado=programado,
                fecha_vencimiento=programado.proxima_fecha,
                defaults={'monto': monto_inicial},
            )
            if created:
                creadas += 1
            programado.avanzar_proxima_fecha()
            intentos += 1
        programado.save(update_fields=['proxima_fecha'])
    return creadas


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
#
#  Compra con cheque: igual que compra a crédito (no genera movimiento
#  propio al crearse, ni requiere una cuenta propia — no hay tarjeta ni
#  acreditación), pero pensada para lo que se compró y se va a pagar
#  con uno o varios cheques propios en vez de tarjeta. Cada cuota se
#  paga como cualquier otra: con un cheque real (confirmar_con_cheque)
#  o con una cuenta, ambos ya soportados de forma genérica.
# ══════════════════════════════════════════════════════════════════

class TipoDeuda(models.TextChoices):
    COMPRA_CREDITO = 'compra_credito', 'Compra con tarjeta de crédito'
    PRESTAMO       = 'prestamo',       'Préstamo'
    CHEQUE         = 'cheque',         'Compra con cheque'


class EstadoDeuda(models.TextChoices):
    ACTIVA  = 'activa',  'Activa'
    ANULADA = 'anulada', 'Anulada'


class EstadoCuota(models.TextChoices):
    PENDIENTE  = 'pendiente',  'Pendiente'
    CONFIRMADA = 'confirmada', 'Confirmada'
    ANULADA    = 'anulada',    'Anulada'


class ModoCuotas(models.TextChoices):
    FIJAS = 'fijas', 'Cuotas fijas'
    LIBRE = 'libre', 'Cuotas libres'


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
    modo_cuotas = models.CharField(
        max_length=10, choices=ModoCuotas.choices, default=ModoCuotas.FIJAS,
        help_text='Fijas: plan de N cuotas iguales con vencimiento mensual (como hoy). '
                   'Libre: no hay plan — se van registrando abonos de cualquier monto '
                   '(ver Deuda.registrar_abono) hasta cubrir el total.',
    )
    cantidad_cuotas = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Solo aplica a modo_cuotas=fijas.',
    )
    fecha_inicio = models.DateField(
        help_text='modo_cuotas=fijas: vencimiento de la primera cuota (las siguientes son '
                   'mensuales a partir de acá). modo_cuotas=libre: fecha de origen de la deuda.',
    )

    numero_comprobante = models.CharField(
        max_length=100, blank=True,
        help_text='N° de factura/comprobante del proveedor o entidad, si corresponde.',
    )
    es_carga_inicial = models.BooleanField(
        default=False,
        help_text='Deuda que ya existía antes de empezar a usar el sistema. Las cuotas '
                   'marcadas como ya pagadas al crearla (ver CuotaDeuda.es_historica) no '
                   'generan movimiento de caja, y si es un préstamo tampoco se acredita '
                   'el ingreso — esa plata ya entró/salió antes de tener registro acá.',
    )

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
        """
        Fijas: suma de las cuotas ya generadas (capital + interés) — no se cachea.
        Libre: no hay cuotas pre-generadas, así que el total es directamente el
        objetivo (capital + interés simple), independiente de cuántos abonos
        ya se registraron.
        """
        if self.modo_cuotas == ModoCuotas.LIBRE:
            return (self.monto_original * (Decimal('1') + self.porcentaje_interes / Decimal('100'))) \
                .quantize(Decimal('0.01'))
        return self.cuotas.aggregate(total=models.Sum('monto'))['total'] or Decimal('0')

    @property
    def cuotas_pagadas(self):
        return self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).count()

    @property
    def saldo_pendiente(self):
        if self.modo_cuotas == ModoCuotas.LIBRE:
            # No solo lo ya cobrado (CONFIRMADA): una cuota PENDIENTE con
            # un cheque todavía en trámite (pendiente o ya cobrado, ver
            # CuotaDeuda.confirmar_con_cheque) ya tiene un cheque real
            # emitido por ese monto — si no se descontara acá, "Registrar
            # abono" dejaría cargar OTRO cheque encima por la misma plata.
            comprometido = self.cuotas.filter(
                models.Q(estado=EstadoCuota.CONFIRMADA)
                | models.Q(cheques__estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO))
            ).distinct().aggregate(total=models.Sum('monto'))['total'] or Decimal('0')
            return self.monto_total - comprometido
        return self.cuotas.filter(estado=EstadoCuota.PENDIENTE).aggregate(
            total=models.Sum('monto'))['total'] or Decimal('0')

    @classmethod
    @transaction.atomic
    def crear_con_cuotas(cls, *, tipo, monto_original, porcentaje_interes, cantidad_cuotas=None,
                          fecha_inicio, moneda=Moneda.ARS, descripcion='', notas='',
                          pago_compra=None, cuenta_tarjeta=None, cuenta_acreditacion=None,
                          creado_por=None, numero_comprobante='', modo_cuotas=ModoCuotas.FIJAS,
                          es_carga_inicial=False, cuotas_historicas=None, abonos_historicos=None):
        """
        Crea la Deuda. Si modo_cuotas=FIJAS, genera de una el plan de N
        cuotas iguales (comportamiento original). Si modo_cuotas=LIBRE,
        no genera ninguna cuota — se van creando de a una a medida que
        se llama a `registrar_abono`. Si tipo=PRESTAMO, además genera de
        inmediato el ingreso a `cuenta_acreditacion` — salvo que sea
        carga inicial (ver más abajo).

        `cuotas_historicas` (solo modo_cuotas=FIJAS): lista de
        {'numero': int, 'fecha_pago': date} para deudas preexistentes
        con cuotas ya pagadas ANTES de cargar el sistema.
        `abonos_historicos` (solo modo_cuotas=LIBRE): lista de
        {'monto': Decimal, 'fecha_pago': date}, mismo propósito pero sin
        número fijo (se van creando en orden vía `registrar_abono`).
        En ambos casos, esas cuotas/abonos quedan CONFIRMADA/es_historica=True
        con `cuenta_pago=None`, así que nunca generan el egreso real de
        caja (mismo mecanismo que una cuota pagada con cheque, ver
        sincronizar_movimiento_cuota) — no tenemos registrado el ingreso
        que las bancó, así que no pueden restar de caja grande hoy.
        Solo válidos junto con es_carga_inicial=True.
        """
        if monto_original <= 0:
            raise ValueError('El monto debe ser mayor a 0.')
        if tipo == TipoDeuda.COMPRA_CREDITO and not cuenta_tarjeta:
            raise ValueError('Elegí la tarjeta con la que se pagó.')
        if tipo == TipoDeuda.PRESTAMO and not cuenta_acreditacion:
            raise ValueError('Elegí la cuenta que recibe el préstamo.')
        if not pago_compra and not descripcion:
            raise ValueError('La descripción es obligatoria cuando la deuda no viene de una compra.')

        cuotas_historicas = cuotas_historicas or []
        abonos_historicos = abonos_historicos or []
        if (cuotas_historicas or abonos_historicos) and not es_carga_inicial:
            raise ValueError('Solo se pueden marcar cuotas/abonos ya pagados en una deuda de carga inicial.')
        hoy = timezone.localtime().date()

        if modo_cuotas == ModoCuotas.LIBRE:
            if cuotas_historicas:
                raise ValueError('Una deuda de cuotas libres no usa cuotas_historicas — usá abonos_historicos.')
            for ab in abonos_historicos:
                if ab['monto'] <= 0:
                    raise ValueError('El monto de un abono histórico debe ser mayor a 0.')
                if ab['fecha_pago'] > hoy:
                    raise ValueError('La fecha de pago de un abono histórico no puede ser futura.')
            cantidad_cuotas = None
        else:
            if not cantidad_cuotas or cantidad_cuotas < 1:
                raise ValueError('La cantidad de cuotas debe ser al menos 1.')
            numeros_historicos = [ch['numero'] for ch in cuotas_historicas]
            if len(set(numeros_historicos)) != len(numeros_historicos):
                raise ValueError('Hay cuotas históricas repetidas.')
            for numero in numeros_historicos:
                if numero < 1 or numero > cantidad_cuotas:
                    raise ValueError(f'La cuota {numero} no existe en un plan de {cantidad_cuotas} cuotas.')
            for ch in cuotas_historicas:
                if ch['fecha_pago'] > hoy:
                    raise ValueError('La fecha de pago de una cuota histórica no puede ser futura.')

        deuda = cls.objects.create(
            tipo=tipo, pago_compra=pago_compra, descripcion=descripcion,
            cuenta_tarjeta=cuenta_tarjeta, cuenta_acreditacion=cuenta_acreditacion,
            monto_original=monto_original, porcentaje_interes=porcentaje_interes,
            moneda=moneda, modo_cuotas=modo_cuotas, cantidad_cuotas=cantidad_cuotas,
            fecha_inicio=fecha_inicio, notas=notas, creado_por=creado_por,
            numero_comprobante=numero_comprobante, es_carga_inicial=es_carga_inicial,
        )

        if modo_cuotas == ModoCuotas.LIBRE:
            for ab in abonos_historicos:
                deuda.registrar_abono(
                    monto=ab['monto'], usuario=creado_por, fecha=ab['fecha_pago'], es_historica=True,
                    cuenta_pago_historica=ab.get('cuenta_pago_historica'),
                    medio_pago_historico=ab.get('medio_pago', ''),
                    cheque_historico=ab.get('cheque_historico'),
                )
        else:
            generar_cuotas(deuda)
            for ch in cuotas_historicas:
                cuota = deuda.cuotas.get(numero=ch['numero'])
                deuda._aplicar_pago_historico(
                    cuota, fecha_pago=ch['fecha_pago'], usuario=creado_por,
                    cuenta_pago_historica=ch.get('cuenta_pago_historica'),
                    medio_pago_historico=ch.get('medio_pago', ''),
                    cheque_historico=ch.get('cheque_historico'),
                )

        if tipo == TipoDeuda.PRESTAMO:
            if not es_carga_inicial:
                sincronizar_movimiento_deuda(deuda)
        else:
            sincronizar_movimiento_deuda_tarjeta(deuda)

        return deuda

    def _aplicar_pago_historico(self, cuota, *, fecha_pago, usuario, cuenta_pago_historica=None,
                                 medio_pago_historico='', cheque_historico=None):
        """
        Deja `cuota` como pagada históricamente (antes de cargar el
        sistema): CONFIRMADA/es_historica=True con `cuenta_pago=None` —
        no genera egreso real (ver sincronizar_movimiento_cuota). Cómo
        se pagó queda registrado, a lo sumo, de UNA de tres formas
        (todas opcionales, elegidas por quien carga la deuda):
        `cuenta_pago_historica` (una CuentaCaja real, solo informativa —
        no toca su saldo), `cheque_historico` (crea un Cheque real
        marcado es_historico=True, con todos sus datos), o
        `medio_pago_historico` (nota libre, para lo que no encaja en
        las otras dos).
        """
        if fecha_pago > timezone.localtime().date():
            raise ValueError('La fecha de un pago histórico no puede ser futura.')
        cuota.estado = EstadoCuota.CONFIRMADA
        cuota.es_historica = True
        cuota.fecha_confirmacion = timezone.make_aware(dt.combine(fecha_pago, dt.min.time()))
        cuota.confirmado_por = usuario
        cuota.cuenta_pago_historica = cuenta_pago_historica
        cuota.medio_pago_historico = medio_pago_historico or ''
        cuota.save(update_fields=[
            'estado', 'es_historica', 'fecha_confirmacion', 'confirmado_por',
            'cuenta_pago_historica', 'medio_pago_historico',
        ])
        if self.tipo == TipoDeuda.COMPRA_CREDITO:
            sincronizar_movimiento_cuota_tarjeta(cuota)
        if cheque_historico:
            _crear_cheque_historico(self, cuota, cheque_historico, usuario)
        return cuota

    @transaction.atomic
    def registrar_abono(self, *, monto, usuario, cuenta_pk=None, cheque_data=None,
                         fecha=None, es_historica=False, cuenta_pago_historica=None,
                         medio_pago_historico='', cheque_historico=None):
        """
        Solo para modo_cuotas=LIBRE: registra un pago de monto libre.
        A diferencia de una cuota fija (que se genera de antemano y se
        confirma después), acá la CuotaDeuda se crea recién ahora y
        queda CONFIRMADA al instante — un abono libre no se "programa",
        se registra cuando se paga. `monto_capital` se prorratea según
        la proporción capital/total de la deuda, para que la tarjeta
        (compra_credito) siga acreditándose correctamente por partes.

        `es_historica=True` (solo desde crear_con_cuotas, carga inicial):
        el abono queda CONFIRMADA/es_historica=True con cuenta_pago=None
        — ver `_aplicar_pago_historico` para `cuenta_pago_historica`/
        `medio_pago_historico`/`cheque_historico`.
        """
        if self.modo_cuotas != ModoCuotas.LIBRE:
            raise ValueError('Esta deuda no es de cuotas libres.')
        if self.estado != EstadoDeuda.ACTIVA:
            raise ValueError('La deuda no está activa.')
        if monto <= 0:
            raise ValueError('El monto del abono debe ser mayor a 0.')

        saldo = self.saldo_pendiente
        if monto > saldo:
            raise ValueError(f'El abono no puede superar el saldo pendiente ({saldo}).')

        numero = (self.cuotas.aggregate(models.Max('numero'))['numero__max'] or 0) + 1
        monto_total = self.monto_total
        monto_capital = (monto * self.monto_original / monto_total).quantize(Decimal('0.01')) \
            if monto_total else monto
        fecha_pago = fecha or timezone.localtime().date()

        cuota = CuotaDeuda.objects.create(
            deuda=self, numero=numero, monto=monto, monto_capital=monto_capital,
            fecha_vencimiento=fecha_pago,
        )

        if es_historica:
            self._aplicar_pago_historico(
                cuota, fecha_pago=fecha_pago, usuario=usuario,
                cuenta_pago_historica=cuenta_pago_historica,
                medio_pago_historico=medio_pago_historico,
                cheque_historico=cheque_historico,
            )
        elif cheque_data:
            cuota.confirmar_con_cheque(cheque_data, usuario, adelantar=True)
        else:
            cuota.confirmar(cuenta_pk, usuario, adelantar=True)

        return cuota

    @transaction.atomic
    def editar(self, *, descripcion=None, notas=None, numero_comprobante=None,
               monto_original=None, porcentaje_interes=None, cantidad_cuotas=None,
               fecha_inicio=None, moneda=None, cuenta_tarjeta=None, cuenta_acreditacion=None):
        """
        Edita una deuda existente. `descripcion`/`notas`/`numero_comprobante`
        se pueden tocar siempre. El resto (todo lo que define el plan de
        pago: monto, interés, cuotas, fecha, moneda, cuenta) solo se
        puede tocar si TODAVÍA no se confirmó ninguna cuota — ni real ni
        histórica —, porque cambiar esos datos después desalinearía lo
        que ya se registró (y, en el caso de cuotas reales, lo que ya
        se imprimió/mostró como pagado) — y solo si la deuda no nació de
        una compra real (`pago_compra`): el monto/interés/cuotas de una
        compra a crédito ya confirmada no se tocan a mano, solo los de
        un préstamo o una carga inicial (mismo criterio que
        CuentaPorCobrar.editar() con `pago_venta`).
        """
        toca_plan = any(v is not None for v in (
            monto_original, porcentaje_interes, cantidad_cuotas, fecha_inicio,
            moneda, cuenta_tarjeta, cuenta_acreditacion,
        ))
        if toca_plan:
            if self.estado != EstadoDeuda.ACTIVA:
                raise ValueError('No se puede editar una deuda anulada.')
            if self.pago_compra_id:
                raise ValueError('Esta deuda nació de una compra — no se puede editar su plan de pago.')
            if self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).exists():
                raise ValueError(
                    'Esta deuda ya tiene cuotas confirmadas — no se puede editar el monto, '
                    'interés, cantidad de cuotas, fecha de inicio, moneda ni cuenta.'
                )

        # El N° de comprobante de una Deuda es la factura real del
        # proveedor (a diferencia de CuentaPorCobrar, acá SÍ es editable
        # siempre, aunque haya nacido de una compra) — pero si cambia,
        # hay que corregirlo también en los cheques ya emitidos para
        # cuotas de esta deuda, si no la búsqueda por el número corregido
        # deja de encontrarlos (quedarían con el valor viejo para
        # siempre). Se compara ANTES de pisar self.numero_comprobante.
        cambia_comprobante = (
            numero_comprobante is not None and numero_comprobante != self.numero_comprobante
        )

        if descripcion is not None:
            self.descripcion = descripcion
        if notas is not None:
            self.notas = notas
        if numero_comprobante is not None:
            self.numero_comprobante = numero_comprobante

        if toca_plan:
            if monto_original is not None:
                if monto_original <= 0:
                    raise ValueError('El monto debe ser mayor a 0.')
                self.monto_original = monto_original
            if porcentaje_interes is not None:
                if porcentaje_interes < 0:
                    raise ValueError('El interés no puede ser negativo.')
                self.porcentaje_interes = porcentaje_interes
            if cantidad_cuotas is not None:
                if cantidad_cuotas < 1:
                    raise ValueError('La cantidad de cuotas debe ser al menos 1.')
                self.cantidad_cuotas = cantidad_cuotas
            if fecha_inicio is not None:
                self.fecha_inicio = fecha_inicio
            if moneda is not None:
                self.moneda = moneda
            if cuenta_tarjeta is not None:
                if self.tipo != TipoDeuda.COMPRA_CREDITO:
                    raise ValueError('La tarjeta solo aplica a compras a crédito.')
                self.cuenta_tarjeta = cuenta_tarjeta
            if cuenta_acreditacion is not None:
                if self.tipo != TipoDeuda.PRESTAMO:
                    raise ValueError('La cuenta de acreditación solo aplica a préstamos.')
                self.cuenta_acreditacion = cuenta_acreditacion

        self.save()

        if cambia_comprobante:
            # Mismo fallback que usa CuotaDeuda.confirmar_con_cheque() al
            # crear el cheque por primera vez — para no dejar numero_factura
            # vacío si se borra el comprobante.
            origen_desc = self.pago_compra.compra.numero if self.pago_compra_id else f'Deuda #{self.pk}'
            Cheque.objects.filter(cuota_deuda__deuda=self).update(
                numero_factura=self.numero_comprobante or origen_desc
            )

        if toca_plan:
            # Con 0 cuotas confirmadas, todas las que había eran
            # PENDIENTE y sin movimiento propio — se puede rehacer
            # el plan entero desde cero con los datos nuevos. En modo
            # libre no hay plan que regenerar (0 confirmadas implica 0
            # cuotas, ya que ahí nacen confirmadas al instante).
            self.cuotas.all().delete()
            if self.modo_cuotas != ModoCuotas.LIBRE:
                generar_cuotas(self)
            if self.tipo == TipoDeuda.PRESTAMO:
                if not self.es_carga_inicial:
                    sincronizar_movimiento_deuda(self)
            else:
                sincronizar_movimiento_deuda_tarjeta(self)

    @transaction.atomic
    def anular(self):
        if self.estado == EstadoDeuda.ANULADA:
            raise ValueError('La deuda ya está anulada.')
        # Las cuotas es_historica=True no movieron plata real (ver
        # crear_con_cuotas) — no bloquean, a diferencia de una cuota
        # confirmada de verdad.
        if self.cuotas.filter(estado=EstadoCuota.CONFIRMADA, es_historica=False).exists():
            raise ValueError('No se puede anular: ya hay cuotas confirmadas de esta deuda.')
        # Una cuota PENDIENTE puede tener igual un cheque en trámite o ya
        # cobrado (ver CuotaDeuda.confirmar_con_cheque) — si se anulara la
        # deuda ahora, ese cheque quedaría cobrándose para una deuda que
        # ya no existe.
        if Cheque.objects.filter(
            cuota_deuda__deuda=self, estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO),
        ).exists():
            raise ValueError(
                'No se puede anular: hay un cheque pendiente o cobrado ligado a una cuota de esta '
                'deuda — resolvelo primero (cobralo o rechazalo) desde Cheques.'
            )

        self.estado = EstadoDeuda.ANULADA
        self.save(update_fields=['estado'])
        self.cuotas.filter(estado=EstadoCuota.PENDIENTE).update(estado=EstadoCuota.ANULADA)

        sincronizar_movimiento_deuda(self)
        sincronizar_movimiento_deuda_tarjeta(self)

    def delete(self, *args, _permitir_con_origen=False, **kwargs):
        """
        Se puede eliminar una deuda aunque ya tenga cuotas pagadas (todas
        o algunas), reales o históricas — para poder deshacer una carga
        mal hecha sin dejar basura. Al borrar se limpian TODOS los
        movimientos de caja que haya generado (nivel deuda y nivel cuota)
        y TODOS los cheques asociados a sus cuotas, sin importar su
        estado — la idea es que quede como si la deuda nunca hubiera
        existido. La vista que llama a esto debe advertirle al usuario
        antes.

        Si `pago_compra_id` está seteado (nació de una compra real), NO
        se puede borrar directamente desde acá — dejaría a la compra con
        una línea de pago "a crédito" sin ninguna deuda real detrás
        (mismo problema que ya evitamos en `editar()`, pero para delete).
        La única forma de sacarse de encima una deuda con origen real es
        borrar la compra entera (`Compra.delete()`, que sí la limpia bien
        en cascada). `_permitir_con_origen=True` es solo para ese cascade
        interno — nunca lo use una vista directamente.
        """
        if self.pago_compra_id and not _permitir_con_origen:
            raise ValueError(
                'Esta deuda nació de una compra real — no se puede eliminar directamente. '
                'Si querés deshacerte de ella, eliminá la compra completa desde su historial.'
            )
        with transaction.atomic():
            movimientos = MovimientoCaja.objects.filter(
                origen__in=(OrigenMovimiento.DEUDA, OrigenMovimiento.DEUDA_TARJETA),
                origen_app='caja', origen_id=self.pk,
            )
            for movimiento in movimientos:
                movimiento.delete()
            # Nivel cuota: el egreso real (CUOTA_DEUDA) de una cuota que
            # sí se pagó de verdad, y el crédito de tarjeta (CUOTA_DEUDA_
            # TARJETA) de cualquier cuota confirmada — hay que limpiarlos
            # antes del CASCADE, que borra las CuotaDeuda pero no sabe
            # nada de MovimientoCaja.
            cuota_pks = list(self.cuotas.values_list('pk', flat=True))
            cuota_movimientos = MovimientoCaja.objects.filter(
                origen__in=(OrigenMovimiento.CUOTA_DEUDA, OrigenMovimiento.CUOTA_DEUDA_TARJETA),
                origen_app='caja', origen_id__in=cuota_pks,
            )
            for movimiento in cuota_movimientos:
                movimiento.delete()
            # Cheques que iban a pagar una cuota de esta deuda: si ya
            # están CONFIRMADO (y no es_historico), esa plata salió de
            # verdad con su propio movimiento aparte (origen=CHEQUE) —
            # hay que rechazarlo primero (revierte ese movimiento, ver
            # sincronizar_movimiento_cheque) porque Cheque.delete() se
            # niega a borrar uno confirmado directamente. Un cheque
            # es_historico=True nunca generó movimiento real, así que se
            # borra derecho — Cheque.delete() ya lo permite.
            for cheque in Cheque.objects.filter(cuota_deuda_id__in=cuota_pks):
                if cheque.estado == EstadoCheque.CONFIRMADO and not cheque.es_historico:
                    cheque.rechazar()
                cheque.delete()
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
    monto_capital = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        help_text='Porción de `monto` que es capital (sin interés). El resto '
                   '(monto - monto_capital) es interés. Solo relevante para '
                   'compra_credito: es lo que se acredita a la tarjeta al '
                   'confirmar, para que su saldo vuelva a acercarse a 0.',
    )
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
    es_historica = models.BooleanField(
        default=False,
        help_text='Cuota que ya estaba pagada antes de cargar la deuda al sistema '
                   '(carga inicial). No generó movimiento de caja real: no hay '
                   'registro del ingreso que la bancó.',
    )
    cuenta_pago_historica = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cuotas_pagadas_historicas',
        help_text='Solo para cuotas es_historica: con qué cuenta real se pagó (ej. '
                   'Efectivo, Mercado Pago), a modo de registro/trazabilidad. NUNCA '
                   'genera movimiento ni afecta el saldo de esa cuenta — cuenta_pago '
                   'se deja en None a propósito para esas cuotas (ver '
                   'sincronizar_movimiento_cuota). Si el pago histórico fue con '
                   'cheque, ver Cheque.es_historico en su lugar.',
    )
    medio_pago_historico = models.CharField(
        max_length=100, blank=True,
        help_text='Solo para cuotas es_historica y solo cuando no aplica ni '
                   'cuenta_pago_historica ni un Cheque.es_historico (ej. "permuta", '
                   '"compensación con otra deuda") — nota libre de registro.',
    )

    class Meta:
        verbose_name        = 'Cuota de deuda'
        verbose_name_plural = 'Cuotas de deuda'
        ordering            = ['deuda', 'numero']
        unique_together     = [('deuda', 'numero')]

    def __str__(self):
        return f'{self.deuda} — cuota {self.numero}/{self.deuda.cantidad_cuotas}'

    @property
    def monto_interes(self):
        """Interés de esta cuota: lo que no es capital. No se guarda aparte."""
        return self.monto - self.monto_capital

    @property
    def habilitada(self):
        """True desde DIAS_HABILITACION_CUOTA días antes del vencimiento en adelante."""
        return timezone.localtime().date() >= self.fecha_vencimiento - timedelta(days=DIAS_HABILITACION_CUOTA)

    @transaction.atomic
    def confirmar(self, cuenta_pk, usuario, adelantar=False):
        # Una deuda tipo Cheque se paga SOLO con cheque — no admite
        # ningún otro medio, ni siquiera de una cuenta propia.
        if self.deuda.tipo == TipoDeuda.CHEQUE:
            raise ValueError('Esta deuda se paga solo con cheque — usá "Pagar con cheque".')
        # select_for_update(): mismo guard que en Venta/Compra.confirmar()
        # — un doble clic en "Pagar cuota" no debe generar dos egresos.
        if CuotaDeuda.objects.select_for_update().get(pk=self.pk).estado != EstadoCuota.PENDIENTE:
            raise ValueError('Solo se pueden confirmar cuotas pendientes.')
        if self.cheques.filter(estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO)).exists():
            raise ValueError(
                'Esta cuota ya tiene un cheque en trámite o cobrado — resolvelo antes de pagarla de otra forma.'
            )
        if not self.habilitada and not adelantar:
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
        sincronizar_movimiento_cuota_tarjeta(self)

    @transaction.atomic
    def confirmar_con_cheque(self, cheque_data, usuario, adelantar=False):
        """
        Alternativa a confirmar(): en vez de descontar de una cuenta al
        toque, esta cuota se paga con un cheque propio (A_PAGAR) por su
        monto exacto. La cuota NO queda confirmada acá — sigue PENDIENTE,
        con el cheque ya vinculado (`cuota_deuda`), hasta que ESE cheque
        se cobre/paga de verdad y se confirme por separado desde la
        pantalla de Cheques (ver `_sincronizar_cuota_desde_cheque`, que
        recién ahí la pasa a CONFIRMADA). Si el cheque rebota, la cuota
        nunca llegó a confirmarse — nada que revertir. `cuenta_pago`
        queda vacío a propósito, igual que antes.
        """
        if CuotaDeuda.objects.select_for_update().get(pk=self.pk).estado != EstadoCuota.PENDIENTE:
            raise ValueError('Solo se pueden confirmar cuotas pendientes.')
        if self.cheques.filter(estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO)).exists():
            raise ValueError(
                'Esta cuota ya tiene un cheque en trámite o cobrado — resolvelo antes de pagarla de otra forma.'
            )
        if not self.habilitada and not adelantar:
            fecha_habilitacion = self.fecha_vencimiento - timedelta(days=DIAS_HABILITACION_CUOTA)
            raise ValueError(
                f'Esta cuota se habilita para pagar a partir del {fecha_habilitacion.strftime("%d/%m/%Y")}.'
            )

        cuenta_origen = cuenta_chequera_valida(cheque_data.get('cuenta_origen_pk'), self.deuda.moneda)
        if not cuenta_origen:
            raise ValueError('Elegí la cuenta bancaria (chequera) de la que sale el cheque.')

        try:
            monto_cheque = Decimal(str(cheque_data.get('monto')))
        except Exception:
            raise ValueError('Monto de cheque inválido.')
        if abs(monto_cheque - self.monto) > Decimal('0.01'):
            raise ValueError(f'El cheque tiene que ser por el monto exacto de la cuota: {self.monto}.')

        fecha_emision_raw = cheque_data.get('fecha_emision')
        fecha_cobro_raw = cheque_data.get('fecha_cobro')
        if not fecha_emision_raw or not fecha_cobro_raw:
            raise ValueError('Indicá fecha de emisión y de cobro del cheque.')
        try:
            fecha_emision = date.fromisoformat(str(fecha_emision_raw))
            fecha_cobro = date.fromisoformat(str(fecha_cobro_raw))
        except ValueError:
            raise ValueError('Fecha de cheque inválida.')

        financiadora = None
        if cheque_data.get('cuenta_financiadora_pk'):
            financiadora, error = validar_cuenta_financiadora(
                cheque_data.get('cuenta_financiadora_pk'), cuenta_origen, self.deuda.moneda, monto_cheque,
            )
            if error:
                raise ValueError(error)

        deuda = self.deuda
        origen_desc = deuda.pago_compra.compra.numero if deuda.pago_compra_id else f'Deuda #{deuda.pk}'
        # El N° de factura del proveedor (si se cargó al dar de alta la
        # deuda) es lo que hay que poder buscar después desde Cheques —
        # el código interno (origen_desc) queda solo como referencia en
        # las notas, no reemplaza a la factura real.
        numero_factura = deuda.numero_comprobante or origen_desc
        # En modo LIBRE no hay plan fijo de cuotas (deuda.cantidad_cuotas
        # queda en None) — no tiene sentido mostrar "cuota N/None".
        plan_txt = f'{self.numero}/{deuda.cantidad_cuotas}' if deuda.cantidad_cuotas else str(self.numero)
        notas = f'Cuota {plan_txt} de {origen_desc}'
        notas_usuario = str(cheque_data.get('notas', '') or '').strip()
        if notas_usuario:
            notas += f' — {notas_usuario}'

        cheque = Cheque.objects.create(
            tipo=TipoCheque.A_PAGAR,
            numero_cheque=str(cheque_data.get('numero_cheque', '') or '').strip(),
            numero_factura=numero_factura,
            monto=monto_cheque,
            moneda=deuda.moneda,
            fecha_emision=fecha_emision,
            fecha_cobro=fecha_cobro,
            cuenta_origen=cuenta_origen,
            emisor=str(cheque_data.get('emisor', '') or '').strip(),
            receptor=str(cheque_data.get('receptor', '') or '').strip(),
            banco=str(cheque_data.get('banco', '') or '').strip(),
            notas=notas,
            cuota_deuda=self,
            creado_por=usuario,
        )
        if financiadora:
            fondear_chequera(financiadora, cuenta_origen, monto_cheque, timezone.localtime().date(), cheque, usuario)


def _calcular_plan_cuotas(monto_original, porcentaje_interes, cantidad_cuotas, fecha_inicio):
    """
    Calcula el plan de cuotas SIN tocar la DB: interés simple sobre el
    monto original, repartido en partes iguales entre `cantidad_cuotas`
    (la última absorbe el resto del redondeo). Devuelve una lista de
    dicts {numero, monto, monto_capital, fecha_vencimiento}.

    Función pura reutilizada por `generar_cuotas` (que sí crea las
    CuotaDeuda) y por la previsualización del modal de alta — así el
    cálculo vive en un solo lugar y la previsualización nunca puede
    desincronizarse del monto real que se termina guardando.
    """
    monto_total = (monto_original * (Decimal('1') + porcentaje_interes / Decimal('100'))) \
        .quantize(Decimal('0.01'))
    cuota_base = (monto_total / cantidad_cuotas).quantize(Decimal('0.01'))
    capital_base = (monto_original / cantidad_cuotas).quantize(Decimal('0.01'))

    plan = []
    acumulado = Decimal('0')
    acumulado_capital = Decimal('0')
    for i in range(1, cantidad_cuotas + 1):
        if i < cantidad_cuotas:
            monto_cuota = cuota_base
            monto_capital = capital_base
            acumulado += monto_cuota
            acumulado_capital += monto_capital
        else:
            monto_cuota = monto_total - acumulado
            monto_capital = monto_original - acumulado_capital

        plan.append({
            'numero': i, 'monto': monto_cuota, 'monto_capital': monto_capital,
            'fecha_vencimiento': _sumar_meses(fecha_inicio, i - 1),
        })
    return plan


def generar_cuotas(deuda):
    """Crea las CuotaDeuda de una Deuda recién creada a partir de _calcular_plan_cuotas."""
    plan = _calcular_plan_cuotas(
        deuda.monto_original, deuda.porcentaje_interes, deuda.cantidad_cuotas, deuda.fecha_inicio,
    )
    for c in plan:
        CuotaDeuda.objects.create(
            deuda=deuda, numero=c['numero'], monto=c['monto'], monto_capital=c['monto_capital'],
            fecha_vencimiento=c['fecha_vencimiento'],
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

    # cuenta_pago=None con estado CONFIRMADA es una cuota pagada con
    # cheque (ver confirmar_con_cheque) — el egreso real recién ocurre
    # cuando ESE cheque se confirma por separado, no acá.
    if cuota.estado != EstadoCuota.CONFIRMADA or cuota.cuenta_pago_id is None:
        if movimiento:
            movimiento.delete()
        return

    # Efectivo: igual criterio que una venta o una devolución. Si hay un
    # turno de caja ABIERTO que la vaya a conciliar, el egreso se difiere
    # hasta su cierre — esa plata sale físicamente del mismo cajón que el
    # cajero está manejando ese turno, así que el cierre tiene que
    # esperarla (ver TurnoCaja._componentes_efectivo_esperado) en vez de
    # mostrar un faltante sin explicación. Si no hay turno abierto que la
    # cubra, se banca de inmediato como cualquier otro egreso — igual que
    # sincronizar_movimiento_venta cuando no hay turno.
    if cuota.cuenta_pago.tipo == TipoCuenta.EFECTIVO:
        turno = TurnoCaja.turno_que_contiene(cuota.fecha_confirmacion)
        if turno is not None and turno.estado == EstadoTurno.ABIERTO:
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


@transaction.atomic
def sincronizar_movimiento_deuda_tarjeta(deuda):
    """
    Sincroniza el débito en la tarjeta (cuenta_tarjeta) de una compra
    con crédito: al crearse la deuda, la tarjeta pasa a deber
    `monto_original` (capital, sin interés) — un egreso en ESA cuenta,
    independiente del egreso real de plata que genera cada cuota al
    confirmarse (sincronizar_movimiento_cuota, en cuenta_pago).

    Es el complemento de sincronizar_movimiento_deuda (que hace lo
    mismo pero para el ingreso de un préstamo) — no aplica a préstamo,
    que no tiene cuenta_tarjeta.
    """
    movimiento = MovimientoCaja.objects.filter(
        origen=OrigenMovimiento.DEUDA_TARJETA, origen_app='caja', origen_id=deuda.pk,
    ).first()

    if deuda.tipo != TipoDeuda.COMPRA_CREDITO or deuda.estado != EstadoDeuda.ACTIVA:
        if movimiento:
            movimiento.delete()
        return

    concepto = _concepto_default('Compra con tarjeta de crédito', TipoMovimientoCaja.EGRESO)
    descripcion = f'Tarjeta {deuda.cuenta_tarjeta.nombre} — {deuda.descripcion}'.strip(' —')

    if movimiento:
        movimiento.cuenta = deuda.cuenta_tarjeta
        movimiento.concepto = concepto
        movimiento.tipo = TipoMovimientoCaja.EGRESO
        movimiento.monto = deuda.monto_original
        movimiento.moneda = deuda.moneda
        movimiento.fecha = deuda.fecha_alta.date()
        movimiento.descripcion = descripcion
        movimiento.save()
    else:
        MovimientoCaja.objects.create(
            caja=TipoCaja.GRANDE, cuenta=deuda.cuenta_tarjeta, concepto=concepto,
            tipo=TipoMovimientoCaja.EGRESO, monto=deuda.monto_original, moneda=deuda.moneda,
            fecha=deuda.fecha_alta.date(), descripcion=descripcion,
            referencia=f'Deuda #{deuda.pk}', origen=OrigenMovimiento.DEUDA_TARJETA,
            origen_app='caja', origen_id=deuda.pk, creado_por=deuda.creado_por,
        )


@transaction.atomic
def sincronizar_movimiento_cuota_tarjeta(cuota):
    """
    Sincroniza el crédito en la tarjeta por el CAPITAL de una cuota
    confirmada (no el total: el interés no reduce deuda de tarjeta,
    es el costo de financiar — ver monto_interes). Es el complemento
    en cuenta_tarjeta de sincronizar_movimiento_cuota (que ya registró
    el egreso real por el total en cuenta_pago); no duplica plata, solo
    hace que el saldo de la tarjeta vuelva a acercarse a 0 a medida que
    se paga capital, aunque haya interés de por medio.
    """
    movimiento = MovimientoCaja.objects.filter(
        origen=OrigenMovimiento.CUOTA_DEUDA_TARJETA, origen_app='caja', origen_id=cuota.pk,
    ).first()

    deuda = cuota.deuda
    if deuda.tipo != TipoDeuda.COMPRA_CREDITO or cuota.estado != EstadoCuota.CONFIRMADA:
        if movimiento:
            movimiento.delete()
        return

    concepto = _concepto_default('Pago de cuota (capital tarjeta)', TipoMovimientoCaja.INGRESO)
    descripcion = f'Cuota {cuota.numero}/{deuda.cantidad_cuotas} — {deuda.cuenta_tarjeta.nombre}'

    if movimiento:
        movimiento.cuenta = deuda.cuenta_tarjeta
        movimiento.concepto = concepto
        movimiento.tipo = TipoMovimientoCaja.INGRESO
        movimiento.monto = cuota.monto_capital
        movimiento.moneda = deuda.moneda
        movimiento.fecha = cuota.fecha_confirmacion.date()
        movimiento.descripcion = descripcion
        movimiento.save()
    else:
        MovimientoCaja.objects.create(
            caja=TipoCaja.GRANDE, cuenta=deuda.cuenta_tarjeta, concepto=concepto,
            tipo=TipoMovimientoCaja.INGRESO, monto=cuota.monto_capital, moneda=deuda.moneda,
            fecha=cuota.fecha_confirmacion.date(), descripcion=descripcion,
            referencia=f'Deuda #{deuda.pk}', origen=OrigenMovimiento.CUOTA_DEUDA_TARJETA,
            origen_app='caja', origen_id=cuota.pk, creado_por=cuota.confirmado_por,
        )


# ══════════════════════════════════════════════════════════════════
#  DOCUMENTOS / ADJUNTOS DE DEUDA
# ══════════════════════════════════════════════════════════════════

import os as _os


def _deuda_doc_path(instance, filename):
    """Ruta: deudas/<pk>/<filename>"""
    nombre_limpio = _os.path.basename(filename)
    return f'deudas/{instance.deuda_id}/{nombre_limpio}'


class DeudaDocumento(models.Model):
    """Archivo adjunto a una deuda (factura del proveedor, contrato de préstamo, etc.)."""

    TIPOS = [
        ('factura',  'Factura'),
        ('contrato', 'Contrato'),
        ('recibo',   'Recibo'),
        ('otro',     'Otro'),
    ]

    deuda       = models.ForeignKey(Deuda, on_delete=models.CASCADE, related_name='documentos')
    archivo     = models.FileField(upload_to=_deuda_doc_path)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='otro')
    descripcion = models.CharField(max_length=200, blank=True)
    subido_el   = models.DateTimeField(auto_now_add=True)
    subido_por  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                      null=True, blank=True, related_name='+')

    class Meta:
        verbose_name        = 'Documento de deuda'
        verbose_name_plural = 'Documentos de deuda'
        ordering            = ['subido_el']

    def __str__(self):
        return f'Deuda #{self.deuda_id} — {self.get_tipo_display()} — {_os.path.basename(self.archivo.name)}'

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
#  CUENTAS POR COBRAR (ventas en cuotas)
#
#  Espejo de Deuda/CuotaDeuda, pero en la dirección opuesta: acá el
#  CLIENTE le debe al negocio (no el negocio a un tercero). Nace de una
#  venta financiada por el propio comercio (sin tarjeta de por medio) y
#  nunca genera un movimiento de caja al crearse — la mercadería ya se
#  entregó, pero la plata todavía no llegó. Cada CuotaCobro confirmada
#  SÍ genera un INGRESO real (lo inverso de CuotaDeuda, que genera un
#  EGRESO) cuando el cliente efectivamente paga esa cuota.
# ══════════════════════════════════════════════════════════════════

class CuentaPorCobrar(models.Model):
    """
    Cabecera de una venta financiada en cuotas. El detalle de cobro
    vive en CuotaCobro — ver comentario de sección más arriba.
    """
    pago_venta = models.OneToOneField(
        'ventas.PagoVenta', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cuenta_por_cobrar',
        help_text='Línea de pago (medio=cuotas) de la venta que originó esta cuenta por cobrar.',
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name='cuentas_por_cobrar',
        help_text='A quién hay que cobrarle. Obligatorio: no se puede vender en cuotas a Consumidor Final.',
    )
    descripcion = models.CharField(max_length=300, blank=True)

    monto_original     = models.DecimalField(max_digits=14, decimal_places=2,
                              help_text='Precio de venta, sin interés.')
    porcentaje_interes  = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    moneda              = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)
    modo_cuotas = models.CharField(
        max_length=10, choices=ModoCuotas.choices, default=ModoCuotas.FIJAS,
        help_text='Fijas: plan de N cuotas iguales con vencimiento mensual (como hoy). '
                   'Libre: no hay plan — se van registrando abonos de cualquier monto '
                   '(ver CuentaPorCobrar.registrar_abono) hasta cubrir el total.',
    )
    cantidad_cuotas = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Solo aplica a modo_cuotas=fijas.',
    )
    fecha_inicio        = models.DateField(help_text='Vencimiento de la primera cuota. Las siguientes son mensuales a partir de acá.')

    numero_comprobante = models.CharField(
        max_length=100, blank=True,
        help_text='N° de factura/comprobante que se le dio al cliente, si corresponde.',
    )
    es_carga_inicial = models.BooleanField(
        default=False,
        help_text='Cuenta por cobrar que ya existía antes de empezar a usar el sistema. '
                   'Las cuotas marcadas como ya cobradas al crearla (ver CuotaCobro.es_historica) '
                   'no generan movimiento de caja — esa plata ya entró antes de tener registro acá.',
    )

    estado = models.CharField(max_length=10, choices=EstadoDeuda.choices, default=EstadoDeuda.ACTIVA)
    notas  = models.CharField(max_length=300, blank=True)

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cuentas_por_cobrar_creadas',
    )
    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Cuenta por cobrar'
        verbose_name_plural = 'Cuentas por cobrar'
        ordering             = ['-fecha_alta']

    def __str__(self):
        return f'{self.cliente} — {self.monto_total} {self.moneda}'

    @property
    def monto_total(self):
        """
        Fijas: suma de las cuotas ya generadas (capital + interés) — no se cachea.
        Libre: no hay cuotas pre-generadas, así que el total es directamente el
        objetivo (capital + interés simple), independiente de cuántos abonos
        ya se registraron.
        """
        if self.modo_cuotas == ModoCuotas.LIBRE:
            return (self.monto_original * (Decimal('1') + self.porcentaje_interes / Decimal('100'))) \
                .quantize(Decimal('0.01'))
        return self.cuotas.aggregate(total=models.Sum('monto'))['total'] or Decimal('0')

    @property
    def cuotas_cobradas(self):
        return self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).count()

    @property
    def saldo_pendiente(self):
        if self.modo_cuotas == ModoCuotas.LIBRE:
            cobrado = self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).aggregate(
                total=models.Sum('monto'))['total'] or Decimal('0')
            return self.monto_total - cobrado
        return self.cuotas.filter(estado=EstadoCuota.PENDIENTE).aggregate(
            total=models.Sum('monto'))['total'] or Decimal('0')

    @classmethod
    @transaction.atomic
    def crear_con_cuotas(cls, *, cliente, monto_original, porcentaje_interes, cantidad_cuotas=None,
                          fecha_inicio, moneda=Moneda.ARS, descripcion='', notas='',
                          pago_venta=None, creado_por=None, numero_comprobante='',
                          modo_cuotas=ModoCuotas.FIJAS, es_carga_inicial=False,
                          cuotas_historicas=None, abonos_historicos=None):
        """
        Crea la CuentaPorCobrar. Si modo_cuotas=FIJAS, genera de una el plan
        de N cuotas iguales (comportamiento original). Si modo_cuotas=LIBRE,
        no genera ninguna cuota — se van creando de a una a medida que se
        llama a `registrar_abono`. No genera ningún movimiento de caja: la
        mercadería ya se entregó, pero la plata todavía no llegó.

        `cuotas_historicas`/`abonos_historicos`: mismo mecanismo que en
        Deuda — para cuentas por cobrar de carga inicial (un cliente que ya
        debía plata antes de usar el sistema), cuotas/abonos marcados como
        ya cobrados quedan CONFIRMADA/es_historica=True con `cuenta_cobro=
        None`, así que nunca generan el ingreso real (ver
        sincronizar_movimiento_cuota_cobro). Solo válidos junto con
        es_carga_inicial=True.
        """
        if monto_original <= 0:
            raise ValueError('El monto debe ser mayor a 0.')
        if not cliente:
            raise ValueError('Una venta en cuotas necesita un cliente vinculado.')

        cuotas_historicas = cuotas_historicas or []
        abonos_historicos = abonos_historicos or []
        if (cuotas_historicas or abonos_historicos) and not es_carga_inicial:
            raise ValueError('Solo se pueden marcar cuotas/abonos ya cobrados en una cuenta de carga inicial.')
        hoy = timezone.localtime().date()

        if modo_cuotas == ModoCuotas.LIBRE:
            if cuotas_historicas:
                raise ValueError('Una cuenta de cuotas libres no usa cuotas_historicas — usá abonos_historicos.')
            for ab in abonos_historicos:
                if ab['monto'] <= 0:
                    raise ValueError('El monto de un abono histórico debe ser mayor a 0.')
                if ab['fecha_pago'] > hoy:
                    raise ValueError('La fecha de pago de un abono histórico no puede ser futura.')
            cantidad_cuotas = None
        else:
            if not cantidad_cuotas or cantidad_cuotas < 1:
                raise ValueError('La cantidad de cuotas debe ser al menos 1.')
            numeros_historicos = [ch['numero'] for ch in cuotas_historicas]
            if len(set(numeros_historicos)) != len(numeros_historicos):
                raise ValueError('Hay cuotas históricas repetidas.')
            for numero in numeros_historicos:
                if numero < 1 or numero > cantidad_cuotas:
                    raise ValueError(f'La cuota {numero} no existe en un plan de {cantidad_cuotas} cuotas.')
            for ch in cuotas_historicas:
                if ch['fecha_pago'] > hoy:
                    raise ValueError('La fecha de pago de una cuota histórica no puede ser futura.')

        cuenta_por_cobrar = cls.objects.create(
            cliente=cliente, pago_venta=pago_venta, descripcion=descripcion,
            monto_original=monto_original, porcentaje_interes=porcentaje_interes,
            moneda=moneda, modo_cuotas=modo_cuotas, cantidad_cuotas=cantidad_cuotas,
            fecha_inicio=fecha_inicio, notas=notas, creado_por=creado_por,
            numero_comprobante=numero_comprobante, es_carga_inicial=es_carga_inicial,
        )

        if modo_cuotas == ModoCuotas.LIBRE:
            for ab in abonos_historicos:
                cuenta_por_cobrar.registrar_abono(
                    monto=ab['monto'], usuario=creado_por, fecha=ab['fecha_pago'], es_historica=True,
                    cuenta_pago_historica=ab.get('cuenta_pago_historica'),
                    medio_pago_historico=ab.get('medio_pago', ''),
                    cheque_historico=ab.get('cheque_historico'),
                )
        else:
            generar_cuotas_cobro(cuenta_por_cobrar)
            for ch in cuotas_historicas:
                cuota = cuenta_por_cobrar.cuotas.get(numero=ch['numero'])
                cuenta_por_cobrar._aplicar_pago_historico(
                    cuota, fecha_pago=ch['fecha_pago'], usuario=creado_por,
                    cuenta_pago_historica=ch.get('cuenta_pago_historica'),
                    medio_pago_historico=ch.get('medio_pago', ''),
                    cheque_historico=ch.get('cheque_historico'),
                )

        _recalcular_scoring_pk(cuenta_por_cobrar.cliente_id)
        return cuenta_por_cobrar

    def _aplicar_pago_historico(self, cuota, *, fecha_pago, usuario, cuenta_pago_historica=None,
                                 medio_pago_historico='', cheque_historico=None):
        """
        Deja `cuota` como cobrada históricamente (antes de cargar el sistema):
        CONFIRMADA/es_historica=True con `cuenta_cobro=None` — no genera
        ingreso real (ver sincronizar_movimiento_cuota_cobro). Cómo se cobró
        queda registrado, a lo sumo, de UNA de tres formas (todas opcionales):
        `cuenta_pago_historica` (una CuentaCaja real, solo informativa),
        `cheque_historico` (crea un Cheque real A_COBRAR marcado
        es_historico=True), o `medio_pago_historico` (nota libre).
        """
        if fecha_pago > timezone.localtime().date():
            raise ValueError('La fecha de un pago histórico no puede ser futura.')
        cuota.estado = EstadoCuota.CONFIRMADA
        cuota.es_historica = True
        cuota.fecha_confirmacion = timezone.make_aware(dt.combine(fecha_pago, dt.min.time()))
        cuota.confirmado_por = usuario
        cuota.cuenta_pago_historica = cuenta_pago_historica
        cuota.medio_pago_historico = medio_pago_historico or ''
        cuota.save(update_fields=[
            'estado', 'es_historica', 'fecha_confirmacion', 'confirmado_por',
            'cuenta_pago_historica', 'medio_pago_historico',
        ])
        if cheque_historico:
            _crear_cheque_historico_cobro(self, cuota, cheque_historico, usuario)
        return cuota

    @transaction.atomic
    def registrar_abono(self, *, monto, usuario, cuenta_pk=None, cheque_data=None,
                         fecha=None, es_historica=False, cuenta_pago_historica=None,
                         medio_pago_historico='', cheque_historico=None):
        """
        Solo para modo_cuotas=LIBRE: registra un cobro de monto libre. A
        diferencia de una cuota fija (que se genera de antemano y se
        confirma después), acá la CuotaCobro se crea recién ahora y queda
        CONFIRMADA al instante — un abono libre no se "programa", se
        registra cuando se cobra. `monto_capital` se prorratea según la
        proporción capital/total de la cuenta (informativo, no afecta
        ningún saldo real de tarjeta acá — a diferencia de Deuda).

        `es_historica=True` (solo desde crear_con_cuotas, carga inicial): el
        abono queda CONFIRMADA/es_historica=True con cuenta_cobro=None — ver
        `_aplicar_pago_historico` para `cuenta_pago_historica`/
        `medio_pago_historico`/`cheque_historico`.
        """
        if self.modo_cuotas != ModoCuotas.LIBRE:
            raise ValueError('Esta cuenta no es de cuotas libres.')
        if self.estado != EstadoDeuda.ACTIVA:
            raise ValueError('La cuenta por cobrar no está activa.')
        if monto <= 0:
            raise ValueError('El monto del abono debe ser mayor a 0.')

        saldo = self.saldo_pendiente
        if monto > saldo:
            raise ValueError(f'El abono no puede superar el saldo pendiente ({saldo}).')

        numero = (self.cuotas.aggregate(models.Max('numero'))['numero__max'] or 0) + 1
        monto_total = self.monto_total
        monto_capital = (monto * self.monto_original / monto_total).quantize(Decimal('0.01')) \
            if monto_total else monto
        fecha_pago = fecha or timezone.localtime().date()

        cuota = CuotaCobro.objects.create(
            cuenta_por_cobrar=self, numero=numero, monto=monto, monto_capital=monto_capital,
            fecha_vencimiento=fecha_pago,
        )

        if es_historica:
            self._aplicar_pago_historico(
                cuota, fecha_pago=fecha_pago, usuario=usuario,
                cuenta_pago_historica=cuenta_pago_historica,
                medio_pago_historico=medio_pago_historico,
                cheque_historico=cheque_historico,
            )
        elif cheque_data:
            cuota.confirmar_con_cheque(cheque_data, usuario, adelantar=True)
        else:
            cuota.confirmar(cuenta_pk, usuario, adelantar=True)

        _recalcular_scoring_pk(self.cliente_id)
        return cuota

    @transaction.atomic
    def editar(self, *, descripcion=None, notas=None, numero_comprobante=None,
               monto_original=None, porcentaje_interes=None, cantidad_cuotas=None,
               fecha_inicio=None, moneda=None):
        """
        Edita una cuenta por cobrar existente. `descripcion`/`notas` se
        pueden tocar siempre. `numero_comprobante` también, EXCEPTO si la
        cuenta nació de una venta real: ahí ya lo autocompletó el sistema
        con el número de venta (ver Venta.confirmar()) para poder buscar
        la cuenta y sus cheques por ese número — no tiene sentido de
        negocio que se edite a mano (a diferencia de una Deuda por compra,
        donde ese campo es la factura real del proveedor, tipeada por el
        usuario). El resto (todo lo que define el plan de cobro) solo se
        puede tocar si TODAVÍA no se confirmó ninguna cuota — ni real ni
        histórica — Y la cuenta no nació de una venta real (`pago_venta`):
        el monto/cuotas de una venta ya confirmada no se tocan a mano,
        solo los de una carga inicial.
        """
        if numero_comprobante is not None and self.pago_venta_id:
            raise ValueError(
                'Esta cuenta nació de una venta — su N° de comprobante lo generó el '
                'sistema y no se puede editar.'
            )

        toca_plan = any(v is not None for v in (
            monto_original, porcentaje_interes, cantidad_cuotas, fecha_inicio, moneda,
        ))
        if toca_plan:
            if self.estado != EstadoDeuda.ACTIVA:
                raise ValueError('No se puede editar una cuenta anulada.')
            if self.pago_venta_id:
                raise ValueError('Esta cuenta nació de una venta — no se puede editar su plan de cobro.')
            if self.cuotas.filter(estado=EstadoCuota.CONFIRMADA).exists():
                raise ValueError(
                    'Esta cuenta ya tiene cuotas confirmadas — no se puede editar el monto, '
                    'interés, cantidad de cuotas, fecha de inicio ni moneda.'
                )

        if descripcion is not None:
            self.descripcion = descripcion
        if notas is not None:
            self.notas = notas
        if numero_comprobante is not None:
            self.numero_comprobante = numero_comprobante

        if toca_plan:
            if monto_original is not None:
                if monto_original <= 0:
                    raise ValueError('El monto debe ser mayor a 0.')
                self.monto_original = monto_original
            if porcentaje_interes is not None:
                if porcentaje_interes < 0:
                    raise ValueError('El interés no puede ser negativo.')
                self.porcentaje_interes = porcentaje_interes
            if cantidad_cuotas is not None:
                if cantidad_cuotas < 1:
                    raise ValueError('La cantidad de cuotas debe ser al menos 1.')
                self.cantidad_cuotas = cantidad_cuotas
            if fecha_inicio is not None:
                self.fecha_inicio = fecha_inicio
            if moneda is not None:
                self.moneda = moneda

        self.save()

        if toca_plan:
            # Con 0 cuotas confirmadas, todas las que había eran PENDIENTE y
            # sin movimiento propio — se puede rehacer el plan entero desde
            # cero. En modo libre no hay plan que regenerar (0 confirmadas
            # implica 0 cuotas, ya que ahí nacen confirmadas al instante).
            self.cuotas.all().delete()
            if self.modo_cuotas != ModoCuotas.LIBRE:
                generar_cuotas_cobro(self)

    @transaction.atomic
    def anular(self):
        if self.estado == EstadoDeuda.ANULADA:
            raise ValueError('La cuenta por cobrar ya está anulada.')
        # Las cuotas es_historica=True no movieron plata real — no bloquean,
        # a diferencia de una cuota confirmada de verdad. Este mensaje se ve
        # tal cual en pantalla tanto al anular como al eliminar la venta
        # (Venta.delete() anula la CxC como primer paso) — por eso no dice
        # "anular" a secas, tiene que tener sentido para las dos acciones,
        # nombrar al cliente (para saber cuál es de varias CxC activas) y
        # decir qué hacer, en vez del genérico "esta cuenta" (que se
        # confunde con una CuentaCaja real).
        if self.cuotas.filter(estado=EstadoCuota.CONFIRMADA, es_historica=False).exists():
            raise ValueError(
                f'No se puede anular ni eliminar esta venta: ya se cobró al menos una cuota '
                f'de la cuenta por cobrar de {self.cliente.get_nombre_display()}. '
                f'Resolvé esa cuenta primero desde Cuentas por cobrar.'
            )
        # Una cuota PENDIENTE puede tener igual un cheque en trámite o ya
        # cobrado (ver CuotaCobro.confirmar_con_cheque) — si se anulara la
        # cuenta ahora, ese cheque quedaría cobrándose para una cuenta que
        # ya no existe.
        if Cheque.objects.filter(
            cuota_cobro__cuenta_por_cobrar=self, estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO),
        ).exists():
            raise ValueError(
                f'No se puede anular ni eliminar esta venta: hay un cheque pendiente o cobrado '
                f'ligado a una cuota de la cuenta por cobrar de {self.cliente.get_nombre_display()} '
                f'— resolvelo primero (cobralo o rechazalo) desde Cheques.'
            )

        self.estado = EstadoDeuda.ANULADA
        self.save(update_fields=['estado'])
        self.cuotas.filter(estado=EstadoCuota.PENDIENTE).update(estado=EstadoCuota.ANULADA)
        _recalcular_scoring_pk(self.cliente_id)

    def delete(self, *args, _permitir_con_origen=False, **kwargs):
        """
        Se puede eliminar una cuenta por cobrar aunque ya tenga cuotas
        cobradas (reales o históricas) — para poder deshacer una carga mal
        hecha sin dejar basura. Al borrar se limpian TODOS los movimientos
        de caja que haya generado (a nivel cuota, CxC no genera movimiento
        propio a nivel cabecera) y TODOS los cheques asociados a sus
        cuotas.

        Si `pago_venta_id` está seteado (nació de una venta real), NO se
        puede borrar directamente desde acá — mismo criterio que
        `Deuda.delete()`, ver su docstring. `_permitir_con_origen=True` es
        solo para el cascade interno de `Venta.delete()`.
        """
        if self.pago_venta_id and not _permitir_con_origen:
            raise ValueError(
                'Esta cuenta por cobrar nació de una venta real — no se puede eliminar directamente. '
                'Si querés deshacerte de ella, eliminá la venta completa desde su historial.'
            )
        cliente_id = self.cliente_id
        with transaction.atomic():
            cuota_pks = list(self.cuotas.values_list('pk', flat=True))
            movimientos = MovimientoCaja.objects.filter(
                origen=OrigenMovimiento.CUOTA_COBRO, origen_app='caja', origen_id__in=cuota_pks,
            )
            for movimiento in movimientos:
                movimiento.delete()
            for cheque in Cheque.objects.filter(cuota_cobro_id__in=cuota_pks):
                if cheque.estado == EstadoCheque.CONFIRMADO and not cheque.es_historico:
                    cheque.rechazar()
                cheque.delete()
            super().delete(*args, **kwargs)
            _recalcular_scoring_pk(cliente_id)


class CuotaCobro(models.Model):
    """
    Una cuota del plan de cobro de una CuentaPorCobrar. Se habilita
    para confirmar recién DIAS_HABILITACION_CUOTA días antes de su
    vencimiento — mismo criterio que CuotaDeuda.
    """
    cuenta_por_cobrar = models.ForeignKey(CuentaPorCobrar, on_delete=models.CASCADE, related_name='cuotas')
    numero  = models.PositiveSmallIntegerField()
    monto   = models.DecimalField(max_digits=14, decimal_places=2)
    monto_capital = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0'),
        help_text='Porción de `monto` que es capital (sin interés). El resto es interés — '
                   'informativo, no cambia cuánto ingresa a caja al confirmar (eso es siempre `monto`).',
    )
    fecha_vencimiento = models.DateField()

    estado  = models.CharField(max_length=10, choices=EstadoCuota.choices, default=EstadoCuota.PENDIENTE)
    cuenta_cobro = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cuotas_cobradas',
        help_text='Cuenta real (banco/efectivo) a la que entra la plata al confirmar el cobro.',
    )
    fecha_confirmacion = models.DateTimeField(null=True, blank=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='cuotas_cobro_confirmadas',
    )
    es_historica = models.BooleanField(
        default=False,
        help_text='Cuota que ya estaba cobrada antes de cargar la cuenta al sistema '
                   '(carga inicial). No generó movimiento de caja real: no hay '
                   'registro del ingreso que la originó.',
    )
    cuenta_pago_historica = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cuotas_cobro_historicas',
        help_text='Solo para cuotas es_historica: con qué cuenta real se cobró (ej. '
                   'Efectivo, Mercado Pago), a modo de registro/trazabilidad. NUNCA '
                   'genera movimiento ni afecta el saldo de esa cuenta — cuenta_cobro '
                   'se deja en None a propósito para esas cuotas (ver '
                   'sincronizar_movimiento_cuota_cobro). Si el pago histórico fue con '
                   'cheque, ver Cheque.es_historico en su lugar.',
    )
    medio_pago_historico = models.CharField(
        max_length=100, blank=True,
        help_text='Solo para cuotas es_historica y solo cuando no aplica ni '
                   'cuenta_pago_historica ni un Cheque.es_historico (ej. "permuta", '
                   '"compensación con otra deuda") — nota libre de registro.',
    )

    class Meta:
        verbose_name        = 'Cuota de cobro'
        verbose_name_plural = 'Cuotas de cobro'
        ordering            = ['cuenta_por_cobrar', 'numero']
        unique_together     = [('cuenta_por_cobrar', 'numero')]

    def __str__(self):
        return f'{self.cuenta_por_cobrar} — cuota {self.numero}/{self.cuenta_por_cobrar.cantidad_cuotas}'

    @property
    def monto_interes(self):
        return self.monto - self.monto_capital

    @property
    def habilitada(self):
        return timezone.localtime().date() >= self.fecha_vencimiento - timedelta(days=DIAS_HABILITACION_CUOTA)

    @transaction.atomic
    def confirmar(self, cuenta_pk, usuario, adelantar=False):
        # select_for_update(): mismo guard que CuotaDeuda.confirmar() —
        # un doble clic en "Confirmar cobro" no debe generar dos ingresos.
        if CuotaCobro.objects.select_for_update().get(pk=self.pk).estado != EstadoCuota.PENDIENTE:
            raise ValueError('Solo se pueden confirmar cuotas pendientes.')
        if self.cheques.filter(estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO)).exists():
            raise ValueError(
                'Esta cuota ya tiene un cheque en trámite o cobrado — resolvelo antes de cobrarla de otra forma.'
            )
        if not self.habilitada and not adelantar:
            fecha_habilitacion = self.fecha_vencimiento - timedelta(days=DIAS_HABILITACION_CUOTA)
            raise ValueError(
                f'Esta cuota se habilita para cobrar a partir del {fecha_habilitacion.strftime("%d/%m/%Y")}.'
            )

        cuenta = CuentaCaja.objects.filter(
            pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True,
            es_credito=False, moneda=self.cuenta_por_cobrar.moneda,
        ).first()
        if not cuenta:
            raise ValueError('Elegí una cuenta válida para el cobro de la cuota.')

        self.cuenta_cobro = cuenta
        self.estado = EstadoCuota.CONFIRMADA
        self.fecha_confirmacion = timezone.now()
        self.confirmado_por = usuario
        self.save(update_fields=['cuenta_cobro', 'estado', 'fecha_confirmacion', 'confirmado_por'])

        sincronizar_movimiento_cuota_cobro(self)
        _recalcular_scoring_de_cxc(self.cuenta_por_cobrar_id)

    @transaction.atomic
    def confirmar_con_cheque(self, cheque_data, usuario, adelantar=False):
        """
        Alternativa a confirmar(): esta cuota se cobra con un cheque de
        un tercero (A_COBRAR) por su monto exacto. La cuota NO queda
        confirmada acá — sigue PENDIENTE, con el cheque ya vinculado
        (`cuota_cobro`), hasta que ESE cheque se deposite/confirme de
        verdad por separado desde Cheques (ver
        `_sincronizar_cuota_desde_cheque`, que recién ahí la pasa a
        CONFIRMADA). Si el cheque rebota, la cuota nunca llegó a
        confirmarse — nada que revertir. `cuenta_cobro` queda vacío a
        propósito, igual que antes.
        """
        if CuotaCobro.objects.select_for_update().get(pk=self.pk).estado != EstadoCuota.PENDIENTE:
            raise ValueError('Solo se pueden confirmar cuotas pendientes.')
        if self.cheques.filter(estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO)).exists():
            raise ValueError(
                'Esta cuota ya tiene un cheque en trámite o cobrado — resolvelo antes de cobrarla de otra forma.'
            )
        if not self.habilitada and not adelantar:
            fecha_habilitacion = self.fecha_vencimiento - timedelta(days=DIAS_HABILITACION_CUOTA)
            raise ValueError(
                f'Esta cuota se habilita para cobrar a partir del {fecha_habilitacion.strftime("%d/%m/%Y")}.'
            )

        try:
            monto_cheque = Decimal(str(cheque_data.get('monto')))
        except Exception:
            raise ValueError('Monto de cheque inválido.')
        if abs(monto_cheque - self.monto) > Decimal('0.01'):
            raise ValueError(f'El cheque tiene que ser por el monto exacto de la cuota: {self.monto}.')

        fecha_emision_raw = cheque_data.get('fecha_emision')
        fecha_cobro_raw = cheque_data.get('fecha_cobro')
        if not fecha_emision_raw or not fecha_cobro_raw:
            raise ValueError('Indicá fecha de emisión y de cobro del cheque.')
        try:
            fecha_emision = date.fromisoformat(str(fecha_emision_raw))
            fecha_cobro = date.fromisoformat(str(fecha_cobro_raw))
        except ValueError:
            raise ValueError('Fecha de cheque inválida.')

        cxc = self.cuenta_por_cobrar
        origen_desc = cxc.pago_venta.venta.numero if cxc.pago_venta_id else f'Cuenta por cobrar #{cxc.pk}'

        Cheque.objects.create(
            tipo=TipoCheque.A_COBRAR,
            numero_cheque=str(cheque_data.get('numero_cheque', '') or '').strip(),
            numero_factura=origen_desc,
            monto=monto_cheque,
            moneda=cxc.moneda,
            fecha_emision=fecha_emision,
            fecha_cobro=fecha_cobro,
            emisor=str(cheque_data.get('emisor', '') or '').strip(),
            receptor=str(cheque_data.get('receptor', '') or '').strip(),
            banco=str(cheque_data.get('banco', '') or '').strip(),
            notas=f'Cuota {self.numero}/{cxc.cantidad_cuotas} de {origen_desc}',
            cuota_cobro=self,
            creado_por=usuario,
        )


def generar_cuotas_cobro(cuenta_por_cobrar):
    """
    Genera el plan de CuotaCobro de una CuentaPorCobrar recién creada:
    interés simple sobre el monto original, repartido en partes iguales
    entre `cantidad_cuotas` (la última absorbe el resto del redondeo).
    Misma matemática que generar_cuotas() para Deuda.
    """
    monto_total = (cuenta_por_cobrar.monto_original * (Decimal('1') + cuenta_por_cobrar.porcentaje_interes / Decimal('100'))) \
        .quantize(Decimal('0.01'))
    cuota_base = (monto_total / cuenta_por_cobrar.cantidad_cuotas).quantize(Decimal('0.01'))
    capital_base = (cuenta_por_cobrar.monto_original / cuenta_por_cobrar.cantidad_cuotas).quantize(Decimal('0.01'))

    acumulado = Decimal('0')
    acumulado_capital = Decimal('0')
    for i in range(1, cuenta_por_cobrar.cantidad_cuotas + 1):
        if i < cuenta_por_cobrar.cantidad_cuotas:
            monto_cuota = cuota_base
            monto_capital = capital_base
            acumulado += monto_cuota
            acumulado_capital += monto_capital
        else:
            monto_cuota = monto_total - acumulado
            monto_capital = cuenta_por_cobrar.monto_original - acumulado_capital

        CuotaCobro.objects.create(
            cuenta_por_cobrar=cuenta_por_cobrar, numero=i, monto=monto_cuota, monto_capital=monto_capital,
            fecha_vencimiento=_sumar_meses(cuenta_por_cobrar.fecha_inicio, i - 1),
        )


@transaction.atomic
def sincronizar_movimiento_cuota_cobro(cuota):
    """Sincroniza el MovimientoCaja (ingreso) de una CuotaCobro con su estado actual."""
    movimiento = MovimientoCaja.objects.filter(
        origen=OrigenMovimiento.CUOTA_COBRO, origen_app='caja', origen_id=cuota.pk,
    ).first()

    # cuenta_cobro=None con estado CONFIRMADA es una cuota cobrada con
    # cheque (ver confirmar_con_cheque) — el ingreso real recién ocurre
    # cuando ESE cheque se confirma/deposita por separado, no acá.
    if cuota.estado != EstadoCuota.CONFIRMADA or cuota.cuenta_cobro_id is None:
        if movimiento:
            movimiento.delete()
        return

    # Efectivo: igual criterio que una venta o una devolución — ver el
    # comentario equivalente en sincronizar_movimiento_cuota (misma
    # lógica, acá en la dirección de ingreso).
    if cuota.cuenta_cobro.tipo == TipoCuenta.EFECTIVO:
        turno = TurnoCaja.turno_que_contiene(cuota.fecha_confirmacion)
        if turno is not None and turno.estado == EstadoTurno.ABIERTO:
            if movimiento:
                movimiento.delete()
            return

    cxc = cuota.cuenta_por_cobrar
    concepto = _concepto_default('Cobro de cuota (venta)', TipoMovimientoCaja.INGRESO)
    descripcion = f'Cuota {cuota.numero}/{cxc.cantidad_cuotas} — {cxc.cliente.get_nombre_display()}'

    if movimiento:
        movimiento.cuenta = cuota.cuenta_cobro
        movimiento.concepto = concepto
        movimiento.tipo = TipoMovimientoCaja.INGRESO
        movimiento.monto = cuota.monto
        movimiento.moneda = cxc.moneda
        movimiento.fecha = cuota.fecha_confirmacion.date()
        movimiento.descripcion = descripcion
        movimiento.save()
    else:
        MovimientoCaja.objects.create(
            caja=TipoCaja.GRANDE, cuenta=cuota.cuenta_cobro, concepto=concepto,
            tipo=TipoMovimientoCaja.INGRESO, monto=cuota.monto, moneda=cxc.moneda,
            fecha=cuota.fecha_confirmacion.date(), descripcion=descripcion,
            referencia=f'Cuenta por cobrar #{cxc.pk}', origen=OrigenMovimiento.CUOTA_COBRO,
            origen_app='caja', origen_id=cuota.pk, creado_por=cuota.confirmado_por,
        )


# ══════════════════════════════════════════════════════════════════
#  DOCUMENTOS / ADJUNTOS DE CUENTA POR COBRAR
# ══════════════════════════════════════════════════════════════════

def _cuenta_cobrar_doc_path(instance, filename):
    """Ruta: cuentas_cobrar/<pk>/<filename>"""
    nombre_limpio = _os.path.basename(filename)
    return f'cuentas_cobrar/{instance.cuenta_por_cobrar_id}/{nombre_limpio}'


class CuentaPorCobrarDocumento(models.Model):
    """Archivo adjunto a una cuenta por cobrar (factura, comprobante, etc.) — mirror de DeudaDocumento."""

    TIPOS = [
        ('factura',  'Factura'),
        ('contrato', 'Contrato'),
        ('recibo',   'Recibo'),
        ('otro',     'Otro'),
    ]

    cuenta_por_cobrar = models.ForeignKey(CuentaPorCobrar, on_delete=models.CASCADE, related_name='documentos')
    archivo     = models.FileField(upload_to=_cuenta_cobrar_doc_path)
    tipo        = models.CharField(max_length=20, choices=TIPOS, default='otro')
    descripcion = models.CharField(max_length=200, blank=True)
    subido_el   = models.DateTimeField(auto_now_add=True)
    subido_por  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                      null=True, blank=True, related_name='+')

    class Meta:
        verbose_name        = 'Documento de cuenta por cobrar'
        verbose_name_plural = 'Documentos de cuenta por cobrar'
        ordering            = ['subido_el']

    def __str__(self):
        return f'Cuenta por cobrar #{self.cuenta_por_cobrar_id} — {self.get_tipo_display()} — {_os.path.basename(self.archivo.name)}'

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

    numero_cheque  = models.CharField(max_length=30, blank=True,
                        help_text='Opcional, ayuda a evitar duplicados.')
    numero_factura = models.CharField(max_length=30, blank=True,
                        help_text='N° de factura asociada al cheque, si corresponde.')
    monto  = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)

    fecha_emision = models.DateField(help_text='Fecha en que se emitió/recibió el cheque.')
    fecha_cobro   = models.DateField(help_text='Fecha en que se puede/debe cobrar (cubre cheque común y de pago diferido).')

    # — A_PAGAR: chequera propia (cuenta bancaria real), fija desde que se carga —
    cuenta_origen = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cheques_a_pagar',
        help_text='Cuenta bancaria propia (la chequera). Solo para A_PAGAR.',
    )

    # — Datos impresos en el cheque, válidos para ambos tipos —
    banco   = models.CharField(max_length=100, blank=True,
                  help_text='Banco de la chequera. Informativo.')
    emisor  = models.CharField(max_length=150, blank=True,
                  help_text='Quién emite el cheque (A_PAGAR: nuestra empresa/firmante. A_COBRAR: quién lo entregó).')
    receptor = models.CharField(max_length=150, blank=True,
                   help_text='Quién recibe el cheque (A_PAGAR: a quién se le paga. A_COBRAR: normalmente la propia empresa).')

    # — A_COBRAR: cuenta propia de destino, se elige recién al confirmar —
    cuenta_destino = models.ForeignKey(
        CuentaCaja, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cheques_a_cobrar',
        help_text='Cuenta propia donde se deposita/cobra. Se completa al confirmar, no antes.',
    )

    # — Origen, si nació de un checkout de venta/compra en vez de
    # cargarse a mano desde esta pantalla. Nunca OneToOne: una misma
    # línea de pago puede traer varios cheques (pago dividido). —
    pago_venta = models.ForeignKey(
        'ventas.PagoVenta', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cheques',
        help_text='Línea de pago (medio=cheque) de la venta que originó este cheque, si corresponde.',
    )
    pago_compra = models.ForeignKey(
        'compras.PagoCompra', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cheques',
        help_text='Línea de pago (medio=cheque) de la compra que originó este cheque, si corresponde.',
    )
    # — Origen alternativo: pago de UNA cuota suelta de una deuda/cuenta
    # por cobrar (no de la compra/venta completa) — el registro de la
    # deuda es el mismo en todas sus cuotas, esto distingue cuál cuota
    # puntual pagó/cobró este cheque. —
    cuota_deuda = models.ForeignKey(
        'caja.CuotaDeuda', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cheques',
        help_text='Cuota de deuda que este cheque pagó, si nació de "pagar cuota con cheque".',
    )
    cuota_cobro = models.ForeignKey(
        'caja.CuotaCobro', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cheques',
        help_text='Cuota de cobro que este cheque saldó, si nació de "cobrar cuota con cheque".',
    )

    estado = models.CharField(max_length=10, choices=EstadoCheque.choices, default=EstadoCheque.PENDIENTE)
    notas  = models.CharField(max_length=300, blank=True)
    es_historico = models.BooleanField(
        default=False,
        help_text='Cheque que ya se pagó/cobró antes de cargar la deuda al sistema (carga '
                   'inicial de una CuotaDeuda es_historica). Se guarda CONFIRMADO de una, '
                   'pero nunca genera movimiento de caja real — mismo criterio que '
                   'CuotaDeuda.es_historica (ver sincronizar_movimiento_cheque).',
    )

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
            # Un cheque de terceros se deposita en CUALQUIERA de tus
            # cuentas bancarias propias (no hace falta tener cuenta en
            # el banco librador — tu banco lo cobra por vos a través de
            # la cámara compensadora). Pero sí tiene que ser un banco:
            # no se "deposita" en efectivo ni en una billetera virtual.
            cuenta = CuentaCaja.objects.filter(
                pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True,
                es_credito=False, tipo=TipoCuenta.BANCO, moneda=self.moneda,
            ).first()
            if not cuenta:
                raise ValueError('Elegí una cuenta bancaria propia válida para depositar el cheque.')
            self.cuenta_destino = cuenta

        self.estado = EstadoCheque.CONFIRMADO
        self.fecha_confirmacion = timezone.now()
        self.confirmado_por = usuario
        self.save(update_fields=['estado', 'fecha_confirmacion', 'confirmado_por', 'cuenta_destino'])

        sincronizar_movimiento_cheque(self)
        _sincronizar_cuota_desde_cheque(self)
        _recalcular_scoring_de_cheque(self)

    @transaction.atomic
    def rechazar(self):
        """Un cheque puede rebotar recién al intentar cobrarlo, ya confirmado."""
        if Cheque.objects.select_for_update().get(pk=self.pk).estado not in (EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO):
            raise ValueError('Solo se pueden rechazar cheques pendientes o confirmados.')

        self.estado = EstadoCheque.RECHAZADO
        self.save(update_fields=['estado'])

        sincronizar_movimiento_cheque(self)
        _sincronizar_cuota_desde_cheque(self)
        _recalcular_scoring_de_cheque(self)

    @transaction.atomic
    def anular(self):
        if Cheque.objects.select_for_update().get(pk=self.pk).estado != EstadoCheque.PENDIENTE:
            raise ValueError('Solo se pueden anular cheques pendientes (si ya se confirmó, hay que rechazarlo).')

        self.estado = EstadoCheque.ANULADO
        self.save(update_fields=['estado'])
        _recalcular_scoring_de_cheque(self)

    def delete(self, *args, _permitir_con_origen=False, **kwargs):
        # Un histórico CONFIRMADO nunca generó movimiento real (ver
        # sincronizar_movimiento_cheque) — no hace falta pasar por
        # rechazar() antes, se puede borrar directo como cualquier otro.
        if self.estado == EstadoCheque.CONFIRMADO and not self.es_historico:
            raise ValueError('No se puede eliminar un cheque confirmado — hay que rechazarlo primero.')
        # Si `pago_venta_id`/`pago_compra_id` está seteado (nació de ser el
        # medio de pago de una venta/compra real), no se puede borrar
        # directamente desde acá — la venta/compra quedaría confirmada con
        # una línea de pago "con cheque" sin ningún cheque real detrás,
        # como si esa plata jamás fuera a cobrarse/pagarse pero sin que
        # quede ningún rastro de eso (mismo problema ya evitado en
        # Deuda.delete()/CuentaPorCobrar.delete()). La única forma de
        # sacarse de encima este cheque es anular/eliminar la venta/compra
        # entera (_anular_cheques_de_venta para ventas; en compras un
        # cheque siempre cuelga de una Deuda tipo CHEQUE, se limpia vía
        # Deuda.delete()/_anular_deudas_de_compra). `_permitir_con_origen=True`
        # es solo para ese cascade.
        if (self.pago_venta_id or self.pago_compra_id) and not _permitir_con_origen:
            raise ValueError(
                'Este cheque es el medio de pago de una venta/compra real — no se puede eliminar '
                'directamente. Si querés deshacerte de él, eliminá o anulá la venta/compra completa.'
            )
        with transaction.atomic():
            movimiento = MovimientoCaja.objects.filter(
                origen=OrigenMovimiento.CHEQUE, origen_app='caja', origen_id=self.pk,
            ).first()
            if movimiento:
                movimiento.delete()

            # Si este cheque pagaba/cobraba un ABONO de cuotas libres (no
            # una cuota FIJA, que es un lugar fijo del plan y no se toca),
            # ese abono nace y muere junto con el cheque que lo respalda —
            # al borrar el cheque a mano (en vez de rechazarlo, que sí deja
            # historial), se borra el abono entero, como si nunca hubiera
            # existido, en vez de dejarlo como una fila fantasma pagable.
            cuota_deuda = self.cuota_deuda if self.cuota_deuda_id else None
            cuota_cobro = self.cuota_cobro if self.cuota_cobro_id else None

            super().delete(*args, **kwargs)

            if cuota_deuda and cuota_deuda.deuda.modo_cuotas == ModoCuotas.LIBRE:
                cuota_deuda.delete()
            if cuota_cobro and cuota_cobro.cuenta_por_cobrar.modo_cuotas == ModoCuotas.LIBRE:
                cuota_cobro.delete()


@transaction.atomic
def sincronizar_movimiento_cheque(cheque):
    """Sincroniza el MovimientoCaja de un Cheque con su estado actual."""
    movimiento = MovimientoCaja.objects.filter(
        origen=OrigenMovimiento.CHEQUE, origen_app='caja', origen_id=cheque.pk,
    ).first()

    if cheque.estado != EstadoCheque.CONFIRMADO or cheque.es_historico:
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

    contraparte = cheque.receptor if cheque.tipo == TipoCheque.A_PAGAR else cheque.emisor
    descripcion = f'Cheque {cheque.numero_cheque or "s/n"} — {contraparte}'.strip(' —')

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


def _estado_rechazo_cuota(modo_cuotas):
    """
    Qué le pasa a una cuota cuyo cheque rebotó, según el tipo de plan:
    - FIJAS: la cuota es un lugar fijo del plan (ej. "cuota 2/3") que
      igual hay que terminar de pagar — vuelve a PENDIENTE para poder
      reintentarla con otro medio u otro cheque.
    - LIBRE: un abono no es un lugar fijo, es el registro de un pago
      puntual — si ese pago no se concretó, no tiene sentido "reintentar
      esa misma fila": queda ANULADA (no cuenta, no se puede volver a
      tocar) y para seguir pagando se registra un abono nuevo.
    """
    return EstadoCuota.PENDIENTE if modo_cuotas == ModoCuotas.FIJAS else EstadoCuota.ANULADA


@transaction.atomic
def _sincronizar_cuota_desde_cheque(cheque):
    """
    Cuando un cheque que paga una cuota de Deuda (`cuota_deuda`) o cobra
    una de CuentaPorCobrar (`cuota_cobro`) cambia de estado, la cuota
    tiene que reflejar la realidad: mientras el cheque esté PENDIENTE, la
    cuota sigue PENDIENTE (el pago todavía no es real); recién cuando el
    cheque se CONFIRMA (se cobra/paga de verdad) la cuota pasa a
    CONFIRMADA. Si el cheque se RECHAZA, ver `_estado_rechazo_cuota`. No
    toca cuotas ya ANULADAS (la deuda/cuenta que las contenía se anuló
    por otro lado).
    """
    if cheque.cuota_deuda_id:
        cuota = cheque.cuota_deuda
        nuevo_estado = (
            EstadoCuota.CONFIRMADA if cheque.estado == EstadoCheque.CONFIRMADO
            else _estado_rechazo_cuota(cuota.deuda.modo_cuotas) if cheque.estado == EstadoCheque.RECHAZADO
            else EstadoCuota.PENDIENTE
        )
        if cuota.estado != EstadoCuota.ANULADA and cuota.estado != nuevo_estado:
            cuota.estado = nuevo_estado
            cuota.fecha_confirmacion = cheque.fecha_confirmacion if nuevo_estado == EstadoCuota.CONFIRMADA else None
            cuota.confirmado_por = cheque.confirmado_por if nuevo_estado == EstadoCuota.CONFIRMADA else None
            cuota.save(update_fields=['estado', 'fecha_confirmacion', 'confirmado_por'])
            # Compra a crédito: el capital recién se acredita a la tarjeta
            # cuando el cheque se cobra de verdad, no cuando se emitió.
            sincronizar_movimiento_cuota_tarjeta(cuota)

    if cheque.cuota_cobro_id:
        cuota = cheque.cuota_cobro
        nuevo_estado = (
            EstadoCuota.CONFIRMADA if cheque.estado == EstadoCheque.CONFIRMADO
            else _estado_rechazo_cuota(cuota.cuenta_por_cobrar.modo_cuotas) if cheque.estado == EstadoCheque.RECHAZADO
            else EstadoCuota.PENDIENTE
        )
        if cuota.estado != EstadoCuota.ANULADA and cuota.estado != nuevo_estado:
            cuota.estado = nuevo_estado
            cuota.fecha_confirmacion = cheque.fecha_confirmacion if nuevo_estado == EstadoCuota.CONFIRMADA else None
            cuota.confirmado_por = cheque.confirmado_por if nuevo_estado == EstadoCuota.CONFIRMADA else None
            cuota.save(update_fields=['estado', 'fecha_confirmacion', 'confirmado_por'])


@transaction.atomic
def _crear_cheque_historico(deuda, cuota, datos, usuario):
    """
    Crea un Cheque ya CONFIRMADO/es_historico=True para una CuotaDeuda
    histórica (carga inicial) que se pagó con cheque antes de usar el
    sistema. Nunca genera movimiento de caja (ver sincronizar_movimiento_
    cheque) — es un registro completo con fines de trazabilidad/control,
    a pedido del cliente, no una operación financiera real.
    """
    cuenta_origen = cuenta_chequera_valida(datos.get('cuenta_origen_pk'), deuda.moneda)
    if not cuenta_origen:
        raise ValueError('Elegí la cuenta bancaria (chequera) del cheque histórico.')

    fecha_emision_raw = datos.get('fecha_emision')
    if not fecha_emision_raw:
        raise ValueError('Indicá la fecha de emisión del cheque histórico.')
    try:
        fecha_emision = date.fromisoformat(str(fecha_emision_raw))
    except ValueError:
        raise ValueError('Fecha de emisión del cheque histórico inválida.')
    # cuota.fecha_vencimiento es el vencimiento TEÓRICO del plan (en modo
    # fijas puede no coincidir con la fecha real en que se pagó) —
    # fecha_confirmacion sí es la fecha real de pago que se cargó, ya
    # seteada por _aplicar_pago_historico antes de llamar acá.
    fecha_cobro = cuota.fecha_confirmacion.date()

    origen_desc = deuda.pago_compra.compra.numero if deuda.pago_compra_id else f'Deuda #{deuda.pk}'
    numero_factura = deuda.numero_comprobante or origen_desc

    Cheque.objects.create(
        tipo=TipoCheque.A_PAGAR,
        numero_cheque=str(datos.get('numero_cheque', '') or '').strip(),
        numero_factura=numero_factura,
        monto=cuota.monto, moneda=deuda.moneda,
        fecha_emision=fecha_emision, fecha_cobro=fecha_cobro,
        cuenta_origen=cuenta_origen,
        banco=str(datos.get('banco', '') or '').strip(),
        emisor=str(datos.get('emisor', '') or '').strip(),
        receptor=str(datos.get('receptor', '') or '').strip(),
        notas=f'Cuota histórica {cuota.numero} de {origen_desc}',
        estado=EstadoCheque.CONFIRMADO,
        es_historico=True,
        fecha_confirmacion=cuota.fecha_confirmacion,
        confirmado_por=usuario,
        cuota_deuda=cuota,
        creado_por=usuario,
    )


@transaction.atomic
def _crear_cheque_historico_cobro(cxc, cuota, datos, usuario):
    """
    Crea un Cheque ya CONFIRMADO/es_historico=True para una CuotaCobro
    histórica (carga inicial) que se cobró con un cheque de un cliente
    antes de usar el sistema. Nunca genera movimiento de caja (ver
    sincronizar_movimiento_cheque) — es un registro completo con fines de
    trazabilidad/control, mismo criterio que _crear_cheque_historico pero
    en la dirección opuesta: A_COBRAR (de terceros), no A_PAGAR. No hay
    chequera que validar acá — `cuenta_destino` es opcional y puramente
    informativa (dónde se depositó), tiene que ser un banco propio si se
    indica, igual que exige Cheque.confirmar() para un A_COBRAR real.
    """
    cuenta_destino = None
    if datos.get('cuenta_destino_pk'):
        cuenta_destino = CuentaCaja.objects.filter(
            pk=datos.get('cuenta_destino_pk'), caja=TipoCaja.GRANDE, activa=True,
            es_credito=False, tipo=TipoCuenta.BANCO, moneda=cxc.moneda,
        ).first()
        if not cuenta_destino:
            raise ValueError('Elegí una cuenta bancaria propia válida para el cheque histórico.')

    fecha_emision_raw = datos.get('fecha_emision')
    if not fecha_emision_raw:
        raise ValueError('Indicá la fecha de emisión del cheque histórico.')
    try:
        fecha_emision = date.fromisoformat(str(fecha_emision_raw))
    except ValueError:
        raise ValueError('Fecha de emisión del cheque histórico inválida.')
    # cuota.fecha_vencimiento es el vencimiento TEÓRICO del plan (en modo
    # fijas puede no coincidir con la fecha real en que se cobró) —
    # fecha_confirmacion sí es la fecha real de cobro que se cargó, ya
    # seteada por _aplicar_pago_historico antes de llamar acá.
    fecha_cobro = cuota.fecha_confirmacion.date()

    origen_desc = cxc.pago_venta.venta.numero if cxc.pago_venta_id else f'Cuenta por cobrar #{cxc.pk}'
    numero_factura = cxc.numero_comprobante or origen_desc

    Cheque.objects.create(
        tipo=TipoCheque.A_COBRAR,
        numero_cheque=str(datos.get('numero_cheque', '') or '').strip(),
        numero_factura=numero_factura,
        monto=cuota.monto, moneda=cxc.moneda,
        fecha_emision=fecha_emision, fecha_cobro=fecha_cobro,
        cuenta_destino=cuenta_destino,
        banco=str(datos.get('banco', '') or '').strip(),
        emisor=str(datos.get('emisor', '') or '').strip(),
        receptor=str(datos.get('receptor', '') or '').strip(),
        notas=f'Cuota histórica {cuota.numero} de {origen_desc}',
        estado=EstadoCheque.CONFIRMADO,
        es_historico=True,
        fecha_confirmacion=cuota.fecha_confirmacion,
        confirmado_por=usuario,
        cuota_cobro=cuota,
        creado_por=usuario,
    )


# ── Helpers de chequera / fondeo — usados desde caja.views_cheques
# (alta manual de un cheque) y desde compras.models (cheque cargado
# como medio de pago en el checkout de una compra). Viven acá, no en
# views_cheques.py, justamente para poder reusarse desde otra app sin
# que compras tenga que importar código de la capa de vistas de caja. ──

def cuenta_chequera_valida(cuenta_pk, moneda=None):
    """La 'chequera' de un cheque A_PAGAR: cuenta bancaria propia (no
    efectivo, no tarjeta de crédito). `moneda=None` no filtra por moneda
    (caso Compras: se elige la cuenta primero y su moneda define la del
    cheque, al revés que en el alta manual desde Cheques)."""
    if not cuenta_pk:
        return None
    qs = CuentaCaja.objects.filter(
        pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True, es_credito=False,
        tipo=TipoCuenta.BANCO,
    )
    if moneda is not None:
        qs = qs.filter(moneda=moneda)
    return qs.first()


def cuenta_caja_valida(cuenta_pk, moneda):
    if not cuenta_pk:
        return None
    return CuentaCaja.objects.filter(
        pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True, es_credito=False, moneda=moneda,
    ).first()


def validar_cuenta_financiadora(cuenta_financiadora_pk, cuenta_chequera, moneda, monto):
    """
    Fondeo opcional al emitir un cheque A_PAGAR: antes de crear el cheque,
    valida la cuenta desde la que se va a transferir `monto` hacia la
    chequera, para que el egreso del cheque (recién al confirmarlo) salga
    de un banco que realmente tiene la plata — en vez de "aparecer" en
    la chequera sin ningún movimiento que lo respalde.
    Devuelve (cuenta, None) o (None, error).
    """
    financiadora = cuenta_caja_valida(cuenta_financiadora_pk, moneda)
    if not financiadora:
        return None, 'Elegí una cuenta financiadora válida.'
    if financiadora.pk == cuenta_chequera.pk:
        return None, 'La cuenta financiadora no puede ser la misma chequera.'
    if financiadora.saldo < monto:
        return None, (
            f'Saldo insuficiente en {financiadora.nombre}: '
            f'disponible {financiadora.saldo}, se necesitan {monto}.'
        )
    return financiadora, None


def fondear_chequera(financiadora, cuenta_chequera, monto, fecha, cheque, usuario):
    """Ejecuta la transferencia de fondeo ya validada por validar_cuenta_financiadora().
    Usa el mismo criterio que la pantalla de Transacciones: DEPOSITO si la
    financiadora es Efectivo, TRANSFERENCIA si es otro banco."""
    tipo_transaccion = (
        TipoTransaccion.DEPOSITO if financiadora.nombre == CUENTA_EFECTIVO_DEFAULT_NOMBRE
        else TipoTransaccion.TRANSFERENCIA
    )
    transaccion = TransaccionCaja.objects.create(
        tipo=tipo_transaccion,
        cuenta_origen=financiadora,
        cuenta_destino=cuenta_chequera,
        monto_origen=monto,
        monto_destino=monto,
        fecha=fecha,
        descripcion=f'Fondeo cheque {cheque.numero_cheque or "s/n"}',
        creado_por=usuario,
    )
    transaccion.ejecutar()
    return transaccion


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
    TRANSFERENCIA = 'transferencia', 'Transferencia entre cuentas'
    COMPRA_DIVISA = 'compra_divisa', 'Compra de divisa'
    VENTA_DIVISA  = 'venta_divisa',  'Venta de divisa'


class TransaccionCaja(models.Model):
    """
    Registra un movimiento entre dos cuentas de la caja grande.

    Tipos soportados:
    - DEPOSITO:      Efectivo → Banco (misma moneda)
    - EXTRACCION:    Banco → Efectivo (misma moneda)
    - TRANSFERENCIA: Banco → Banco (misma moneda, ninguno de los dos
                     lados es Efectivo — para eso ya están depósito
                     y extracción).
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