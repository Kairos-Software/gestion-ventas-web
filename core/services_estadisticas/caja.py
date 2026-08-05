"""
core/services_estadisticas/caja.py

Situación financiera (tiempo real), gastos por categoría e historial
de arqueos de caja diaria.
"""

from decimal import Decimal

from django.db.models import Q, Sum

from productos.models import Moneda
from caja.models import (
    Gasto, MovimientoCaja, TipoCaja, TipoMovimientoCaja,
    Deuda, CuotaDeuda, EstadoCuota, EstadoDeuda, ModoCuotas,
    CuentaPorCobrar, CuotaCobro,
    Cheque, TipoCheque, EstadoCheque,
    TurnoCaja, EstadoTurno,
)


# ══════════════════════════════════════════════════════════════════
#  GASTOS POR CATEGORÍA
#  (agrupa por descripción; si más adelante Gasto tiene un campo
#  categoria propio, cambiar el agrupamiento acá por ese campo)
# ══════════════════════════════════════════════════════════════════

def gastos_por_categoria(desde, hasta, top=8):
    # Gasto también registra ingresos manuales (tipo=INGRESO) — acá
    # solo interesan los egresos, si no un ingreso manual se mostraría
    # mezclado en este ranking como si fuera un gasto más.
    return list(
        Gasto.objects.filter(
            fecha__range=(desde, hasta), tipo=TipoMovimientoCaja.EGRESO,
        )
        .values('descripcion')
        .annotate(total=Sum('monto'))
        .order_by('-total')[:top]
    )


# ══════════════════════════════════════════════════════════════════
#  SITUACIÓN FINANCIERA ACTUAL
#  (estado en tiempo real — no depende del filtro de fecha del
#  dashboard. Responde "¿cuánta plata tengo, cuánto debo, cuánto me
#  deben?" de un vistazo.)
# ══════════════════════════════════════════════════════════════════

def _por_moneda(lista, campo_total='total'):
    """Filtra a solo las monedas con movimiento y les agrega el label."""
    labels = dict(Moneda.choices)
    return [
        {'moneda': f['moneda'], 'label': labels.get(f['moneda'], f['moneda']),
         'total': f[campo_total] or Decimal('0')}
        for f in lista if f[campo_total]
    ]


def _saldo_libres_por_moneda(qs):
    """
    modo_cuotas=libre no pregenera cuotas/abonos futuros (ver
    CuentaPorCobrar/Deuda.registrar_abono) — no hay filas "pendiente"
    para sumar con una query, el saldo es la property saldo_pendiente
    de cada cuenta. Devuelve {moneda: total}.
    """
    totales = {}
    for obj in qs:
        saldo = obj.saldo_pendiente
        if saldo > 0:
            totales[obj.moneda] = totales.get(obj.moneda, Decimal('0')) + saldo
    return totales


def situacion_financiera():
    # — Plata disponible: cuentas reales (no tarjetas) de caja grande —
    saldos = (
        MovimientoCaja.objects
        .filter(caja=TipoCaja.GRANDE, cuenta__activa=True, cuenta__es_credito=False)
        .values('moneda')
        .annotate(
            ingresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.INGRESO)),
            egresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.EGRESO)),
        )
    )
    saldo_cuentas = _por_moneda([
        {'moneda': f['moneda'], 'total': (f['ingresos'] or Decimal('0')) - (f['egresos'] or Decimal('0'))}
        for f in saldos
    ])

    # — Deudas propias pendientes (créditos/préstamos activos): cuotas
    # fijas (CuotaDeuda) + saldo de cuentas en cuotas libres —
    totales_deuda = {
        f['deuda__moneda']: f['total'] or Decimal('0')
        for f in (
            CuotaDeuda.objects
            .filter(estado=EstadoCuota.PENDIENTE, deuda__estado=EstadoDeuda.ACTIVA)
            .values('deuda__moneda').annotate(total=Sum('monto'))
        )
    }
    for moneda, total in _saldo_libres_por_moneda(
        Deuda.objects.filter(estado=EstadoDeuda.ACTIVA, modo_cuotas=ModoCuotas.LIBRE)
    ).items():
        totales_deuda[moneda] = totales_deuda.get(moneda, Decimal('0')) + total
    deudas_pendientes = _por_moneda([{'moneda': m, 'total': t} for m, t in totales_deuda.items()])

    # — Cuentas por cobrar pendientes (ventas en cuotas — lo que te
    # deben LOS CLIENTES, contracara de "deudas_pendientes" de arriba,
    # que es lo que VOS debés): cuotas fijas + saldo de cuentas libres —
    totales_cxc = {
        f['cuenta_por_cobrar__moneda']: f['total'] or Decimal('0')
        for f in (
            CuotaCobro.objects
            .filter(estado=EstadoCuota.PENDIENTE, cuenta_por_cobrar__estado=EstadoDeuda.ACTIVA)
            .values('cuenta_por_cobrar__moneda').annotate(total=Sum('monto'))
        )
    }
    for moneda, total in _saldo_libres_por_moneda(
        CuentaPorCobrar.objects.filter(estado=EstadoDeuda.ACTIVA, modo_cuotas=ModoCuotas.LIBRE)
    ).items():
        totales_cxc[moneda] = totales_cxc.get(moneda, Decimal('0')) + total
    cxc_pendientes = _por_moneda([{'moneda': m, 'total': t} for m, t in totales_cxc.items()])

    # — Cheques pendientes: a cobrar (a favor) vs a pagar (en contra) —
    cheques = (
        Cheque.objects
        .filter(estado=EstadoCheque.PENDIENTE)
        .values('tipo', 'moneda')
        .annotate(total=Sum('monto'))
    )
    cheques_a_cobrar = _por_moneda([
        {'moneda': f['moneda'], 'total': f['total']}
        for f in cheques if f['tipo'] == TipoCheque.A_COBRAR
    ])
    cheques_a_pagar = _por_moneda([
        {'moneda': f['moneda'], 'total': f['total']}
        for f in cheques if f['tipo'] == TipoCheque.A_PAGAR
    ])

    # — Posición neta proyectada: "si cobrara todo lo que me deben y
    # pagara todo lo que debo, ¿cuánto me queda?" — arrancando de la
    # plata disponible hoy, suma lo que entra (CxC + cheques a cobrar) y
    # resta lo que sale (deudas + cheques a pagar). Se arma por moneda —
    # nunca se mezclan ARS/USD/EUR en un solo número.
    def _monto(lista, moneda):
        return next((f['total'] for f in lista if f['moneda'] == moneda), Decimal('0'))

    monedas = sorted({
        f['moneda']
        for lista in (saldo_cuentas, deudas_pendientes, cxc_pendientes, cheques_a_cobrar, cheques_a_pagar)
        for f in lista
    })
    labels = dict(Moneda.choices)
    posicion_neta = [
        {
            'moneda': moneda,
            'label': labels.get(moneda, moneda),
            'total': (
                _monto(saldo_cuentas, moneda) + _monto(cxc_pendientes, moneda) + _monto(cheques_a_cobrar, moneda)
                - _monto(deudas_pendientes, moneda) - _monto(cheques_a_pagar, moneda)
            ),
        }
        for moneda in monedas
    ]

    # Mismos números que arriba, pero reagrupados por moneda en vez de
    # por categoría — para armar en el template un renglón "+/−/=" por
    # moneda (el detalle de arriba sirve para el reporte periódico por
    # mail, que ya consume saldo_cuentas/deudas_pendientes sueltos).
    por_moneda = [
        {
            'moneda': moneda,
            'label': labels.get(moneda, moneda),
            'saldo': _monto(saldo_cuentas, moneda),
            'cxc': _monto(cxc_pendientes, moneda),
            'cheques_cobrar': _monto(cheques_a_cobrar, moneda),
            'deudas': _monto(deudas_pendientes, moneda),
            'cheques_pagar': _monto(cheques_a_pagar, moneda),
            'neto': next(p['total'] for p in posicion_neta if p['moneda'] == moneda),
        }
        for moneda in monedas
    ]

    return {
        'saldo_cuentas': saldo_cuentas,
        'deudas_pendientes': deudas_pendientes,
        'cxc_pendientes': cxc_pendientes,
        'cheques_a_cobrar': cheques_a_cobrar,
        'cheques_a_pagar': cheques_a_pagar,
        'posicion_neta': posicion_neta,
        'por_moneda': por_moneda,
    }


# ══════════════════════════════════════════════════════════════════
#  HISTORIAL DE ARQUEOS DE CAJA DIARIA
#  diferencia_efectivo > 0 = sobró plata al cerrar; < 0 = faltó.
#  Sirve para detectar turnos/cajeros con descuadres frecuentes.
# ══════════════════════════════════════════════════════════════════

def historial_arqueos(desde, hasta):
    turnos = (
        TurnoCaja.objects
        .filter(estado=EstadoTurno.CERRADO, fecha_cierre__date__range=(desde, hasta))
        .select_related('cerrado_por')
        .order_by('fecha_cierre')
    )

    detalle = []
    total_sobrante = Decimal('0')
    total_faltante = Decimal('0')
    cantidad_con_diferencia = 0

    for turno in turnos:
        diferencia = turno.diferencia_efectivo or Decimal('0')
        if diferencia > 0:
            total_sobrante += diferencia
        elif diferencia < 0:
            total_faltante += diferencia
        if abs(diferencia) >= Decimal('0.01'):
            cantidad_con_diferencia += 1

        detalle.append({
            'numero': turno.numero,
            'fecha_cierre': turno.fecha_cierre,
            'diferencia_efectivo': diferencia,
            'cerrado_por': turno.cerrado_por.get_full_name() if turno.cerrado_por else None,
        })

    return {
        'detalle': detalle,
        'cantidad_turnos': len(detalle),
        'cantidad_con_diferencia': cantidad_con_diferencia,
        'total_sobrante': round(total_sobrante, 2),
        'total_faltante': round(total_faltante, 2),
    }
