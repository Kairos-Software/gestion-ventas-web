"""
core/scoring.py

Motor de scoring de clientes. Un número de 0 a 1000 que mide el RIESGO
DE PAGO de un cliente: qué tan probable es que cumpla si le vendés en
cuotas o le aceptás un cheque.

Cómo funciona
─────────────
Arranca en 1000 (cliente nuevo = se le cree). Baja con atrasos, mora y
cheques rechazados; sube pagando a término. Se recalcula ENTERO cada
vez (no acumula "deltas") mirando todo el historial reciente del
cliente — así el número siempre es explicable ("bajó porque tiene una
cuota vencida hace 40 días") y se recupera solo cuando el cliente se
pone al día o las penas viejas se caen de la ventana.

Qué NO mide
───────────
El VALOR del cliente (cuánto compra, cuánta ganancia deja). Eso ya está
en core.services_estadisticas (perfil_valor / mejores_clientes). Acá
solo importa si PAGA. Un cliente que compra mucho pero paga tarde tiene
mal score igual.

Links a los datos
─────────────────
- Ventas: ItemVenta.cliente (cliente único por venta, ya garantizado).
- Cuotas / cuentas por cobrar: CuentaPorCobrar.cliente (FK directo).
- Cheques de cliente (A_COBRAR): vía la cuota que saldan
  (cuota_cobro__cuenta_por_cobrar__cliente) o vía la venta que los
  originó (pago_venta__venta con ítems de ese cliente).
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone


# ══════════════════════════════════════════════════════════════════
#  PESOS Y UMBRALES — todo lo tuneable vive acá.
#  (Si más adelante se quiere que cada negocio los ajuste sin deploy,
#   estos valores pasan a un singleton ConfiguracionScoring — ver plan.)
# ══════════════════════════════════════════════════════════════════

PUNTAJE_INICIAL = 1000
PUNTAJE_MIN     = 0
PUNTAJE_MAX     = 1000

# Solo se mira el historial de los últimos 2 años — las penas viejas
# se caen solas (un cliente que zafó hace 3 años y viene pagando bien
# no queda clavado para siempre).
VENTANA_DIAS = 730

# — Penalización por CUOTA PAGADA TARDE, según días de atraso —
#   (umbral_dias_hasta, puntos). Se toma el primer tramo que aplica.
ATRASO_PAGADO = [
    (7,          -5),
    (30,        -15),
    (60,        -35),
    (10 ** 9,   -60),
]

# — Penalización por CUOTA VENCIDA SIN PAGAR (mora activa HOY), según
#   hace cuántos días venció. Es lo más pesado y escala con el tiempo,
#   por eso hace falta el recálculo nocturno. —
MORA_ACTIVA = [
    (15,        -20),
    (30,        -50),
    (60,       -100),
    (90,       -180),
    (10 ** 9,  -300),
]

# — Cheque del cliente rechazado (rebotado) —
CHEQUE_RECHAZADO       = -250   # dentro de la ventana
CHEQUE_RECHAZADO_VIEJO = -120   # más viejo que la ventana (nunca se borra del todo)

# — Uso del crédito: si lo que debe supera este % de todo lo que se le
#   fió alguna vez, está "al límite". —
CREDITO_LIMITE_PCT      = Decimal("80")
CREDITO_LIMITE_PENALIZA = -40

# — Tope de puntaje según la mora más vieja sin pagar HOY. No importa
#   cuánto historial limpio haya: si debés una cuota vencida hace 2
#   meses, no podés estar mejor que "Riesgo". El puntaje real puede
#   quedar aún más abajo (las penas de arriba escalan) — esto es el
#   techo. (umbral_dias_hasta, tope). —
TOPE_POR_MORA = [
    (30,        699),   # mora reciente → como mucho "Regular" (aviso blando)
    (59,        499),   # 1-2 meses → "Riesgo" (aviso fuerte)
    (89,        399),   # 2-3 meses → "Riesgo" hondo
    (10 ** 9,   299),   # 90+ días → "Crítico" (el sistema desaconseja/oculta cuotas)
]

# — Bonos (para reconstruir el 1000) —
CUOTA_A_TERMINO      = 8      # por cada cuota pagada en fecha
CUOTA_A_TERMINO_TOPE = 240    # tope del bono acumulado por puntualidad

BONUS_VIEJO_LIMPIO       = 40   # ≥ ANTIGUEDAD_MESES y ≥ VENTAS_MIN ventas, sin mora activa
ANTIGUEDAD_MESES_BONUS   = 12
VENTAS_MIN_BONUS         = 10

BONUS_SANO_VIGENTE   = 20      # sin deuda activa + compró hace poco
DIAS_COMPRA_RECIENTE = 60

# — Bandas (umbral_desde, nombre, nivel_riesgo). Ordenadas de mayor a
#   menor; se toma la primera cuyo umbral el score alcanza. —
BANDAS = [
    (850, "excelente", "bajo"),
    (700, "bueno",     "bajo"),
    (500, "regular",   "medio"),
    (300, "riesgo",    "alto"),
    (0,   "critico",   "alto"),
]

BANDA_LABEL = {
    "excelente": "Excelente",
    "bueno":     "Bueno",
    "regular":   "Regular",
    "riesgo":    "Riesgo",
    "critico":   "Crítico",
    "sin_historial": "Sin historial",
}


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def _ars(monto):
    """'$ 9.000' — formato de miles argentino, sin decimales."""
    return "$ " + f"{monto:,.0f}".replace(",", ".")


def _tramo(tabla, valor):
    """Devuelve los puntos del primer tramo (umbral_hasta, puntos) que
    cubre `valor`."""
    for umbral, puntos in tabla:
        if valor <= umbral:
            return puntos
    return tabla[-1][1]


def banda_de_score(score):
    """(nombre, nivel_riesgo) para un score dado."""
    for umbral, nombre, riesgo in BANDAS:
        if score >= umbral:
            return nombre, riesgo
    return "critico", "alto"


def _cheques_de_cliente(cliente):
    """Todos los cheques A_COBRAR atribuibles a este cliente: los que
    saldan una de sus cuotas y los que fueron medio de pago de una venta
    suya."""
    from ventas.models import ItemVenta
    from caja.models import Cheque, TipoCheque

    ventas_ids = (
        ItemVenta.objects.filter(cliente=cliente)
        .values_list("venta_id", flat=True)
    )
    return (
        Cheque.objects
        .filter(tipo=TipoCheque.A_COBRAR)
        .filter(
            Q(cuota_cobro__cuenta_por_cobrar__cliente=cliente)
            | Q(pago_venta__venta_id__in=list(ventas_ids))
        )
        .distinct()
    )


# ══════════════════════════════════════════════════════════════════
#  CÁLCULO
# ══════════════════════════════════════════════════════════════════

def calcular_scoring(cliente):
    """
    Recalcula el scoring del cliente desde cero.

    Devuelve un dict:
        {
          'score':          int  (0-1000, ya clampeado),
          'score_bruto':    int  (antes de clampear — puede ser > 1000 o < 0),
          'banda':          str  ('excelente'|'bueno'|'regular'|'riesgo'|'critico'),
          'nivel_riesgo':   str  ('bajo'|'medio'|'alto'),
          'sin_historial':  bool,
          'desglose': [ {'concepto': str, 'detalle': str, 'puntos': int}, ... ],
        }

    El desglose SIEMPRE arranca con la fila "Base" (1000) y suma/resta
    desde ahí, así la suma de `puntos` da `score_bruto`.
    """
    from ventas.models import ItemVenta, EstadoVenta
    from caja.models import (
        CuentaPorCobrar, CuotaCobro, EstadoCuota, EstadoDeuda, EstadoCheque,
    )

    hoy    = timezone.localtime().date()
    limite = hoy - timedelta(days=VENTANA_DIAS)

    desglose = [{"concepto": "Base", "detalle": "Puntaje inicial", "puntos": PUNTAJE_INICIAL}]
    puntos   = PUNTAJE_INICIAL

    # ── ¿Tiene algún historial de crédito? ──
    tiene_cxc     = CuentaPorCobrar.objects.filter(cliente=cliente).exists()
    cheques_qs    = _cheques_de_cliente(cliente)
    tiene_cheques = cheques_qs.exists()

    if not tiene_cxc and not tiene_cheques:
        return {
            "score": PUNTAJE_INICIAL,
            "score_bruto": PUNTAJE_INICIAL,
            "banda": "excelente",
            "nivel_riesgo": "bajo",
            "sin_historial": True,
            "desglose": [
                {"concepto": "Sin historial de crédito",
                 "detalle": "El cliente nunca compró en cuotas ni pagó con cheque",
                 "puntos": 0},
            ],
        }

    # ── 1) Cuotas pagadas: a término (+) y con atraso (−) ──
    #    es_historica=True = cuota "ya cobrada antes del sistema", sin
    #    fecha de pago real comparable — no cuenta para puntualidad.
    confirmadas = (
        CuotaCobro.objects
        .filter(cuenta_por_cobrar__cliente=cliente,
                estado=EstadoCuota.CONFIRMADA, es_historica=False)
        .exclude(fecha_confirmacion__isnull=True)
        .only("fecha_confirmacion", "fecha_vencimiento")
    )
    n_termino = 0
    atrasos_dias = []
    penal_atraso = 0
    for c in confirmadas:
        pagada = c.fecha_confirmacion.date()
        if pagada < limite:
            continue  # fuera de ventana
        dias = (pagada - c.fecha_vencimiento).days
        if dias <= 0:
            n_termino += 1
        else:
            atrasos_dias.append(dias)
            penal_atraso += _tramo(ATRASO_PAGADO, dias)

    if n_termino:
        bono = min(CUOTA_A_TERMINO * n_termino, CUOTA_A_TERMINO_TOPE)
        puntos += bono
        desglose.append({
            "concepto": "Cuotas pagadas a término",
            "detalle": f"{n_termino} cuota{'s' if n_termino != 1 else ''}",
            "puntos": bono,
        })
    if atrasos_dias:
        prom = round(sum(atrasos_dias) / len(atrasos_dias))
        puntos += penal_atraso
        desglose.append({
            "concepto": "Cuotas pagadas con atraso",
            "detalle": f"{len(atrasos_dias)} cuota{'s' if len(atrasos_dias) != 1 else ''} "
                       f"(promedio {prom} día{'s' if prom != 1 else ''} tarde)",
            "puntos": penal_atraso,
        })

    # ── 2) Mora activa: cuotas vencidas HOY sin pagar ──
    mora = list(
        CuotaCobro.objects
        .filter(cuenta_por_cobrar__cliente=cliente,
                cuenta_por_cobrar__estado=EstadoDeuda.ACTIVA,
                estado=EstadoCuota.PENDIENTE,
                fecha_vencimiento__lt=hoy)
        .only("fecha_vencimiento", "monto")
    )
    hay_mora = bool(mora)
    peor_dias_mora = 0
    if mora:
        penal_mora = 0
        monto_mora = Decimal("0")
        for c in mora:
            d = (hoy - c.fecha_vencimiento).days
            peor_dias_mora = max(peor_dias_mora, d)
            monto_mora += c.monto or Decimal("0")
            penal_mora += _tramo(MORA_ACTIVA, d)
        puntos += penal_mora
        desglose.append({
            "concepto": "Cuotas vencidas sin pagar",
            "detalle": f"{len(mora)} cuota{'s' if len(mora) != 1 else ''} en mora "
                       f"({_ars(monto_mora)}, la más vieja hace {peor_dias_mora} días)",
            "puntos": penal_mora,
        })

    # ── 3) Cheques rechazados ──
    rechazados = cheques_qs.filter(estado=EstadoCheque.RECHAZADO).only("fecha_cobro")
    n_rech = n_rech_viejo = 0
    penal_cheque = 0
    for ch in rechazados:
        if ch.fecha_cobro and ch.fecha_cobro < limite:
            n_rech_viejo += 1
            penal_cheque += CHEQUE_RECHAZADO_VIEJO
        else:
            n_rech += 1
            penal_cheque += CHEQUE_RECHAZADO
    if penal_cheque:
        total_rech = n_rech + n_rech_viejo
        detalle = f"{total_rech} cheque{'s' if total_rech != 1 else ''} rebotado{'s' if total_rech != 1 else ''}"
        if n_rech_viejo and not n_rech:
            detalle += " (hace más de 2 años)"
        puntos += penal_cheque
        desglose.append({
            "concepto": "Cheques rechazados",
            "detalle": detalle,
            "puntos": penal_cheque,
        })

    # ── 4) Uso del crédito ──
    cuentas_activas = list(
        CuentaPorCobrar.objects.filter(cliente=cliente, estado=EstadoDeuda.ACTIVA)
    )
    otorgado = sum((c.monto_total for c in cuentas_activas), Decimal("0"))
    saldo    = sum((c.saldo_pendiente for c in cuentas_activas), Decimal("0"))
    if otorgado > 0 and saldo / otorgado * 100 >= CREDITO_LIMITE_PCT:
        puntos += CREDITO_LIMITE_PENALIZA
        desglose.append({
            "concepto": "Crédito al límite",
            "detalle": f"Debe {_ars(saldo)} de {_ars(otorgado)} otorgados "
                       f"({round(saldo / otorgado * 100)}%)",
            "puntos": CREDITO_LIMITE_PENALIZA,
        })

    # ── 5) Bono: cliente viejo y limpio ──
    items_cli = ItemVenta.objects.filter(
        cliente=cliente, venta__estado=EstadoVenta.CONFIRMADA
    )
    n_ventas = items_cli.values("venta_id").distinct().count()
    primera  = items_cli.order_by("venta__fecha").values_list("venta__fecha", flat=True).first()
    ultima   = items_cli.order_by("-venta__fecha").values_list("venta__fecha", flat=True).first()
    antiguo  = bool(primera and (hoy - primera).days >= ANTIGUEDAD_MESES_BONUS * 30)

    if antiguo and n_ventas >= VENTAS_MIN_BONUS and not hay_mora:
        puntos += BONUS_VIEJO_LIMPIO
        desglose.append({
            "concepto": "Cliente antiguo y cumplidor",
            "detalle": f"{n_ventas} compras, cliente hace más de {ANTIGUEDAD_MESES_BONUS} meses, sin mora",
            "puntos": BONUS_VIEJO_LIMPIO,
        })

    # ── 6) Bono: sin deuda activa y comprando hace poco ──
    sin_deuda   = not cuentas_activas and not hay_mora
    compro_hace = (hoy - ultima).days if ultima else None
    if sin_deuda and compro_hace is not None and compro_hace <= DIAS_COMPRA_RECIENTE:
        puntos += BONUS_SANO_VIGENTE
        desglose.append({
            "concepto": "Al día y activo",
            "detalle": f"Sin deudas abiertas, compró hace {compro_hace} días",
            "puntos": BONUS_SANO_VIGENTE,
        })

    score_bruto = puntos

    # ── Tope por mora activa ──
    #  El techo depende de la cuota vencida más vieja: cuanto más atrás
    #  quedó sin pagar, más abajo el máximo posible. (Las penas de mora
    #  de arriba ya pueden dejar el puntaje aún más abajo — esto solo
    #  pone el techo.)
    if hay_mora:
        tope = _tramo(TOPE_POR_MORA, peor_dias_mora)
        if puntos > tope:
            ajuste = tope - puntos
            puntos += ajuste
            desglose.append({
                "concepto": "Tope por mora activa",
                "detalle": f"Con una cuota vencida hace {peor_dias_mora} días, "
                           f"el puntaje no puede superar {tope}",
                "puntos": ajuste,
            })

    score = max(PUNTAJE_MIN, min(PUNTAJE_MAX, puntos))
    if score != puntos:
        desglose.append({
            "concepto": "Ajuste de rango",
            "detalle": f"El total ({puntos}) se lleva al rango 0–1000",
            "puntos": score - puntos,
        })

    banda, nivel_riesgo = banda_de_score(score)
    return {
        "score": score,
        "score_bruto": score_bruto,
        "banda": banda,
        "nivel_riesgo": nivel_riesgo,
        "sin_historial": False,
        "desglose": desglose,
    }
