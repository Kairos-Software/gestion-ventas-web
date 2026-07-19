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
    CuotaDeuda, EstadoCuota, EstadoDeuda,
    Cheque, TipoCheque, EstadoCheque,
    TurnoCaja, EstadoTurno,
)


# ══════════════════════════════════════════════════════════════════
#  GASTOS POR CATEGORÍA
#  (agrupa por descripción; si más adelante Gasto tiene un campo
#  categoria propio, cambiar el agrupamiento acá por ese campo)
# ══════════════════════════════════════════════════════════════════

def gastos_por_categoria(desde, hasta, top=8):
    return list(
        Gasto.objects.filter(fecha__range=(desde, hasta))
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

    # — Deudas propias pendientes (cuotas de crédito/préstamos activos) —
    deudas = (
        CuotaDeuda.objects
        .filter(estado=EstadoCuota.PENDIENTE, deuda__estado=EstadoDeuda.ACTIVA)
        .values('deuda__moneda')
        .annotate(total=Sum('monto'))
    )
    deudas_pendientes = _por_moneda([
        {'moneda': f['deuda__moneda'], 'total': f['total']} for f in deudas
    ])

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

    return {
        'saldo_cuentas': saldo_cuentas,
        'deudas_pendientes': deudas_pendientes,
        'cheques_a_cobrar': cheques_a_cobrar,
        'cheques_a_pagar': cheques_a_pagar,
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
