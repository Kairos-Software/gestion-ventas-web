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

    activa  = models.BooleanField(default=True)
    notas   = models.CharField(max_length=300, blank=True)
    orden   = models.PositiveSmallIntegerField(default=0)

    fecha_alta         = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Cuenta de caja'
        verbose_name_plural = 'Cuentas de caja'
        ordering            = ['caja', 'orden', 'nombre']
        unique_together     = [('nombre', 'caja')]

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
    Sincroniza el MovimientoCaja asociado a una Venta con su estado actual.

    - BORRADOR: no genera movimiento (no es plata real todavía).
    - CONFIRMADA: ingreso por venta.total, en la cuenta efectivo default
      según la moneda predominante de sus ítems (ARS por defecto).
    - ANULADA: no debe quedar movimiento (la venta no se concretó).

    IMPORTANTE: este movimiento se registra en CAJA DIARIA, NUNCA en
    caja grande. El dinero de una venta recién "existe" para la caja
    grande cuando el turno se cierra y TurnoCaja.cerrar() transfiere lo
    correspondiente (ver ese método). Si esto generara caja=GRANDE acá,
    se duplicaría con la transferencia del cierre de turno.

    Se llama desde Venta.confirmar(), Venta.anular() [si existiera] y
    Venta.editar_completa() (que internamente re-confirma).
    """
    _borrar_movimiento_origen('ventas', OrigenMovimiento.VENTA, venta.pk)

    # Import local para evitar dependencia circular a nivel de módulo
    from ventas.models import EstadoVenta

    if venta.estado != EstadoVenta.CONFIRMADA:
        return None

    moneda = venta.items.values_list('moneda', flat=True).first() or Moneda.ARS
    cuenta   = _cuenta_default(moneda=moneda, caja=TipoCaja.DIARIA)
    concepto = _concepto_default(CONCEPTO_VENTA_NOMBRE, TipoMovimientoCaja.INGRESO)

    return MovimientoCaja.objects.create(
        caja        = TipoCaja.DIARIA,
        cuenta      = cuenta,
        concepto    = concepto,
        tipo        = TipoMovimientoCaja.INGRESO,
        monto       = venta.total,
        moneda      = moneda,
        fecha       = venta.fecha,
        descripcion = f'Venta {venta.numero}',
        referencia  = venta.numero,
        origen      = OrigenMovimiento.VENTA,
        origen_app  = 'ventas',
        origen_id   = venta.pk,
        creado_por  = venta.confirmado_por,
    )


@transaction.atomic
def sincronizar_movimiento_compra(compra):
    """
    Sincroniza el MovimientoCaja asociado a una Compra con su estado actual.

    - BORRADOR: no genera movimiento.
    - CONFIRMADA: egreso por compra.total.
    - ANULADA: no debe quedar movimiento (se revirtió, no hubo gasto neto).

    Se llama desde Compra.confirmar(), Compra.anular(), Compra.reactivar()
    y Compra.editar_completa().
    """
    _borrar_movimiento_origen('compras', OrigenMovimiento.COMPRA, compra.pk)

    from compras.models import EstadoCompra

    if compra.estado != EstadoCompra.CONFIRMADA:
        return None

    moneda = compra.items.values_list('moneda', flat=True).first() or Moneda.ARS
    cuenta   = _cuenta_default(moneda=moneda, caja=TipoCaja.GRANDE)
    concepto = _concepto_default(CONCEPTO_COMPRA_NOMBRE, TipoMovimientoCaja.EGRESO)

    return MovimientoCaja.objects.create(
        caja        = TipoCaja.GRANDE,
        cuenta      = cuenta,
        concepto    = concepto,
        tipo        = TipoMovimientoCaja.EGRESO,
        monto       = compra.total,
        moneda      = moneda,
        fecha       = compra.fecha,
        descripcion = f'Compra {compra.numero}',
        referencia  = compra.numero,
        origen      = OrigenMovimiento.COMPRA,
        origen_app  = 'compras',
        origen_id   = compra.pk,
        creado_por  = compra.creado_por,
    )


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
        from django.db import transaction

        cajas = _normalizar_cajas(cajas)
        monto_inicial_total = sum(Decimal(str(c['monto'])) for c in cajas)

        with transaction.atomic():
            # Verificar que no haya un turno abierto
            if cls.turno_actual():
                raise ValueError('Ya existe un turno abierto')
            
            # Crear el turno
            turno = cls(
                numero=cls.obtener_siguiente_numero(),
                monto_inicial_efectivo=monto_inicial_total,
                estado=EstadoTurno.ABIERTO,
                abierto_por=usuario,
            )
            turno.save()

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
    
    def calcular_totales_por_medio_pago(self):
        """
        Calcula los totales de ventas agrupados por medio de pago
        para este turno.
        
        Usa PagoVenta para soportar pagos divididos (ej: mitad efectivo, mitad transferencia).
        """
        from ventas.models import Venta, MedioPago, PagoVenta
        
        ventas_en_turno = Venta.objects.filter(
            estado='confirmada',
            fecha_alta__gte=self.fecha_apertura,
            fecha_alta__lte=self.fecha_cierre if self.fecha_cierre else timezone.now()
        )
        
        # Obtener todos los pagos de las ventas en este turno
        pagos_en_turno = PagoVenta.objects.filter(
            venta__in=ventas_en_turno
        )
        
        totales = {}
        for medio, label in MedioPago.choices:
            totales[medio] = pagos_en_turno.filter(medio=medio).aggregate(
                total=Sum('monto')
            )['total'] or 0
        
        return totales
    
    def cerrar(self, cajas, usuario, notas=''):
        """
        Cierra el turno. Es el ÚNICO momento en que el dinero de un
        turno "aparece" en caja grande — ninguna venta individual
        impacta ahí antes de esto (ver sincronizar_movimiento_venta).

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
           se transfieren a caja grande por el monto que el sistema
           registró (no requieren conteo físico).
        """
        from django.db import transaction

        cajas = _normalizar_cajas(cajas)
        monto_final_efectivo = sum(Decimal(str(c['monto'])) for c in cajas)

        with transaction.atomic():
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

            # ── 2. Resto de medios de pago: van por lo que el sistema
            #      registró (no hay conteo físico posible para esto) ──
            from ventas.models import MedioPago
            labels_medio = dict(MedioPago.choices)

            for medio, monto in totales.items():
                if medio == 'efectivo' or not monto or monto <= 0:
                    continue
                medio_label = labels_medio.get(medio, medio.capitalize())
                cuenta_medio = _cuenta_grande_para_medio_pago(medio, medio_label, moneda=Moneda.ARS)
                concepto_medio = _concepto_default(f'Cierre de turno - {medio_label}', TipoMovimientoCaja.INGRESO)

                MovimientoCaja.objects.create(
                    caja=TipoCaja.GRANDE,
                    cuenta=cuenta_medio,
                    concepto=concepto_medio,
                    tipo=TipoMovimientoCaja.INGRESO,
                    monto=monto,
                    moneda=Moneda.ARS,
                    fecha=fecha_cierre,
                    descripcion=f'Cierre turno #{self.numero} — {medio_label}',
                    referencia=f'Turno #{self.numero}',
                    origen=OrigenMovimiento.AJUSTE,
                    origen_app='caja',
                    origen_id=self.pk,
                    creado_por=usuario,
                )


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
    Registro de gastos operativos (alquiler, mecánico, luz, etc.).
    
    Cada gasto genera automáticamente un MovimientoCaja en la caja grande
    como egreso manual. Al editar/eliminar el gasto, se sincroniza el
    movimiento de caja correspondiente.
    """
    
    fecha = models.DateField(help_text='Fecha del gasto')
    hora = models.TimeField(help_text='Hora del gasto (automática)')
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=5, choices=Moneda.choices, default=Moneda.ARS)
    descripcion = models.CharField(max_length=300, help_text='Descripción del gasto (ej: alquiler, mecánico, luz)')
    
    # ── Auditoría ────────────────────────────────────────────────
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='gastos_creados',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Gasto'
        verbose_name_plural = 'Gastos'
        ordering = ['-fecha', '-hora']
    
    def __str__(self):
        return f'{self.descripcion} - {self.monto} {self.moneda} ({self.fecha})'
    
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
    Sincroniza el MovimientoCaja asociado a un Gasto.
    
    - Si el gasto existe: crea/actualiza el movimiento de caja como egreso
    - Si el gasto se elimina: borra el movimiento de caja asociado
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
    cuenta = _cuenta_default(moneda=moneda, caja=TipoCaja.GRANDE)
    concepto = _concepto_default('Gasto', TipoMovimientoCaja.EGRESO)
    
    if movimiento:
        # Actualizar movimiento existente
        movimiento.cuenta = cuenta
        movimiento.concepto = concepto
        movimiento.tipo = TipoMovimientoCaja.EGRESO
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
            tipo = TipoMovimientoCaja.EGRESO,
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