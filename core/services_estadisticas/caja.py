"""
core/services_estadisticas/caja.py

Situación financiera (tiempo real), gastos por categoría e historial
de arqueos de caja diaria.
"""

from decimal import Decimal

from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncMonth

from productos.models import Moneda
from caja.models import (
    Gasto, MovimientoCaja, TipoCaja, TipoMovimientoCaja,
    Deuda, CuotaDeuda, EstadoCuota, EstadoDeuda, ModoCuotas,
    CuentaPorCobrar, CuotaCobro,
    Cheque, TipoCheque, EstadoCheque,
    ResumenTarjeta, InstanciaProgramada, EstadoInstanciaProgramada,
    TurnoCaja, EstadoTurno,
)


# ══════════════════════════════════════════════════════════════════
#  INGRESOS Y EGRESOS MANUALES POR CONCEPTO
#
#  Agrupa los Gasto (ingresos y egresos manuales) por su `concepto`
#  del catálogo (ver caja.ConceptoGasto). Los que no tienen concepto
#  cargado caen en "Sin concepto". Cada moneda se muestra por separado.
# ══════════════════════════════════════════════════════════════════

def _rankear(bucket):
    """dict{nombre: fila} → lista ordenada por total desc, con % del total."""
    lista = sorted(bucket.values(), key=lambda x: x['total'], reverse=True)
    total = sum((x['total'] for x in lista), Decimal('0'))
    for x in lista:
        x['pct'] = round(x['total'] / total * 100, 1) if total else Decimal('0')
    return lista, total


def movimientos_por_concepto(desde, hasta):
    filas = (
        Gasto.objects
        .filter(fecha__range=(desde, hasta))
        .values('concepto__nombre', 'tipo', 'moneda')
        .annotate(total=Sum('monto'), cantidad=Count('id'))
    )

    por_moneda = {}
    for f in filas:
        nombre = f['concepto__nombre'] or 'Sin concepto'
        grupo = por_moneda.setdefault(f['moneda'], {'egresos': {}, 'ingresos': {}})
        destino = grupo['egresos'] if f['tipo'] == TipoMovimientoCaja.EGRESO else grupo['ingresos']
        fila = destino.setdefault(
            nombre, {'concepto': nombre, 'total': Decimal('0'), 'cantidad': 0})
        fila['total'] += f['total'] or Decimal('0')
        fila['cantidad'] += f['cantidad']

    labels = dict(Moneda.choices)
    resultado = []
    for moneda, grupo in sorted(por_moneda.items()):
        egr_lista, egr_total = _rankear(grupo['egresos'])
        ing_lista, ing_total = _rankear(grupo['ingresos'])
        resultado.append({
            'moneda': moneda, 'label': labels.get(moneda, moneda),
            'egresos': egr_lista, 'total_egresos': egr_total,
            'ingresos': ing_lista, 'total_ingresos': ing_total,
        })
    return {'por_moneda': resultado}


def _mes_anterior(fecha):
    """Primer día del mes anterior a `fecha` (que ya debe ser un día 1)."""
    if fecha.month == 1:
        return fecha.replace(year=fecha.year - 1, month=12)
    return fecha.replace(month=fecha.month - 1)


def serie_mensual_conceptos(hoy, meses=6, tipo=TipoMovimientoCaja.EGRESO, top=5):
    """Para el gráfico "cuánto gasto por mes en cada rubro": los `top`
    conceptos con más movimiento en la ventana, mes a mes, y el resto
    junto en "Otros". Siempre devuelve `meses` casilleros (con $0 los
    vacíos, e incluyendo el mes en curso) para que las barras se vean
    parejas."""
    primer_mes = hoy.replace(day=1)
    for _ in range(meses - 1):
        primer_mes = _mes_anterior(primer_mes)

    filas = (
        Gasto.objects
        .filter(tipo=tipo, fecha__range=(primer_mes, hoy))
        .annotate(mes=TruncMonth('fecha'))
        .values('mes', 'concepto__nombre', 'moneda')
        .annotate(total=Sum('monto'))
    )

    por_moneda = {}
    for f in filas:
        nombre = f['concepto__nombre'] or 'Sin concepto'
        t = f['total'] or Decimal('0')
        grupo = por_moneda.setdefault(f['moneda'], {'conceptos': {}, 'meses': {}})
        grupo['conceptos'][nombre] = grupo['conceptos'].get(nombre, Decimal('0')) + t
        clave = (f['mes'], nombre)
        grupo['meses'][clave] = grupo['meses'].get(clave, Decimal('0')) + t

    meses_cal = []
    cursor = primer_mes
    for _ in range(meses):
        meses_cal.append(cursor)
        cursor = (cursor.replace(year=cursor.year + 1, month=1)
                  if cursor.month == 12 else cursor.replace(month=cursor.month + 1))

    labels = dict(Moneda.choices)
    resultado = []
    for moneda, grupo in sorted(por_moneda.items()):
        conceptos = grupo['conceptos']
        por_mes_concepto = grupo['meses']
        top_nombres = [n for n, _ in sorted(conceptos.items(), key=lambda x: x[1], reverse=True)[:top]]
        series = [
            {'concepto': nombre,
             'valores': [por_mes_concepto.get((m, nombre), Decimal('0')) for m in meses_cal],
             'total': conceptos[nombre]}
            for nombre in top_nombres
        ]
        otros = set(conceptos) - set(top_nombres)
        if otros:
            series.append({
                'concepto': 'Otros',
                'valores': [sum((por_mes_concepto.get((m, n), Decimal('0')) for n in otros), Decimal('0')) for m in meses_cal],
                'total': sum((conceptos[n] for n in otros), Decimal('0')),
            })
        resultado.append({'moneda': moneda, 'label': labels.get(moneda, moneda), 'series': series})

    return {'meses': meses_cal, 'por_moneda': resultado}


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
        .filter(
            Q(tipo=TipoCheque.A_COBRAR, cuota_cobro__isnull=True) |
            Q(tipo=TipoCheque.A_PAGAR, cuota_deuda__isnull=True)
        )
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
#  OBLIGACIONES DEL PERÍODO — "a pagar" vs "pagado", CON fecha
#
#  A diferencia de situacion_financiera() (una foto de HOY, sin
#  importar cuándo vence cada cosa), esto mira el rango de fechas
#  filtrado: qué vence en ese rango (independiente de si ya se pagó) y
#  qué se pagó de verdad en ese rango (independiente de cuándo vencía).
#  Sirve para poner al lado de "Total vendido" del mismo período.
# ══════════════════════════════════════════════════════════════════

def _sumar_moneda(dic, moneda, monto):
    if monto:
        dic[moneda] = dic.get(moneda, Decimal('0')) + monto


def _deudas_resumenes_cheques(desde, hasta):
    """
    Cuotas de Deuda (fijas/variable) + cargo propio de Resumen de tarjeta +
    cheques A_PAGAR sueltos — todo lo que representa una deuda/tarjeta/
    cheque propio, con fecha real de vencimiento o de pago dentro de
    [desde, hasta]. A PROPÓSITO no incluye Gasto (ni Movimientos
    programados) — eso se cuenta aparte como "Total gastado", para no
    duplicarlo en dos categorías distintas del mismo resumen.

      - Cuotas de Deuda pendientes de una deuda activa, fijas/variable
        (préstamos, tarjetas de crédito, deudas de cheque con cronograma
        fijo). El saldo de deudas modo LIBRE queda afuera: no tiene una
        fecha de vencimiento mensual real (es "pagá cuando puedas") — ya
        se refleja completo, sin fecha, en situacion_financiera().
      - El cargo propio de cada Resumen de tarjeta (interés/IVA/seguro),
        con su fecha de vencimiento real (según día de cierre/vencimiento
        configurado en la tarjeta — es una property, no un campo, así que
        se filtra en Python sobre el universo chico de resúmenes).
      - Cheques A_PAGAR sueltos (no nacidos de ninguna Deuda/Compra/Venta
        — esos ya están contados arriba vía su cuota) con fecha de cobro/
        confirmación en el rango.

    Devuelve (a_pagar, pagado), cada uno {moneda: Decimal}.
    """
    a_pagar = {}
    pagado = {}

    for f in (CuotaDeuda.objects
              .filter(estado=EstadoCuota.PENDIENTE, deuda__estado=EstadoDeuda.ACTIVA,
                      deuda__modo_cuotas__in=(ModoCuotas.FIJAS, ModoCuotas.VARIABLE),
                      fecha_vencimiento__range=(desde, hasta))
              .values('deuda__moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(a_pagar, f['deuda__moneda'], f['total'])

    for f in (CuotaDeuda.objects
              .filter(estado=EstadoCuota.CONFIRMADA, es_historica=False,
                      fecha_confirmacion__date__range=(desde, hasta))
              .values('deuda__moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(pagado, f['deuda__moneda'], f['total'])

    for r in ResumenTarjeta.objects.exclude(monto_ajuste=0).select_related('cuenta_tarjeta'):
        venc = r.fecha_vencimiento
        if not venc:
            continue
        if not r.ajuste_pagado and desde <= venc <= hasta:
            _sumar_moneda(a_pagar, r.cuenta_tarjeta.moneda, r.monto_ajuste)
        elif r.ajuste_pagado and r.fecha_pago_ajuste and desde <= r.fecha_pago_ajuste.date() <= hasta:
            _sumar_moneda(pagado, r.cuenta_tarjeta.moneda, r.monto_ajuste)

    cheques_sueltos = Cheque.objects.filter(
        tipo=TipoCheque.A_PAGAR, cuota_deuda__isnull=True,
        pago_compra__isnull=True, pago_venta__isnull=True,
    )
    for f in (cheques_sueltos.filter(estado=EstadoCheque.PENDIENTE, fecha_cobro__range=(desde, hasta))
              .values('moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(a_pagar, f['moneda'], f['total'])
    for f in (cheques_sueltos.filter(estado=EstadoCheque.CONFIRMADO, fecha_confirmacion__date__range=(desde, hasta))
              .values('moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(pagado, f['moneda'], f['total'])

    return a_pagar, pagado


def deudas_y_tarjetas_pagadas_blend(desde, hasta):
    """
    Igual que `_deudas_resumenes_cheques` (lado "pagado"), pero sumado en
    un solo número sin distinguir moneda — mismo criterio que ventas/
    compras/gastos en el resto de Estadísticas (la enorme mayoría es ARS).
    Para el waterfall simple de "Cuánto te queda realmente" del Resumen.
    """
    _, pagado = _deudas_resumenes_cheques(desde, hasta)
    return sum(pagado.values(), Decimal('0'))


def _cxc_cobros(desde, hasta):
    """
    Espejo de `_deudas_resumenes_cheques`, del lado de lo que te deben a
    VOS (Cuentas por cobrar — clientes que compraron a cuenta corriente).
    Solo cuotas de CxC modo FIJAS (libre no tiene vencimiento mensual
    real, mismo criterio que Deuda — ver situacion_financiera). Devuelve
    (a_cobrar, cobrado), cada uno {moneda: Decimal}.
    """
    a_cobrar = {}
    cobrado = {}

    for f in (CuotaCobro.objects
              .filter(estado=EstadoCuota.PENDIENTE, cuenta_por_cobrar__estado=EstadoDeuda.ACTIVA,
                      cuenta_por_cobrar__modo_cuotas=ModoCuotas.FIJAS,
                      fecha_vencimiento__range=(desde, hasta))
              .values('cuenta_por_cobrar__moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(a_cobrar, f['cuenta_por_cobrar__moneda'], f['total'])

    for f in (CuotaCobro.objects
              .filter(estado=EstadoCuota.CONFIRMADA, es_historica=False,
                      fecha_confirmacion__date__range=(desde, hasta))
              .values('cuenta_por_cobrar__moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(cobrado, f['cuenta_por_cobrar__moneda'], f['total'])

    return a_cobrar, cobrado


def cxc_cobrado_blend(desde, hasta):
    """Igual que `deudas_y_tarjetas_pagadas_blend`, pero del lado de lo
    que te cobraron a vos (CxC) — para sumarlo como entrada de caja real
    en el waterfall de "Cuánto te queda realmente"."""
    _, cobrado = _cxc_cobros(desde, hasta)
    return sum(cobrado.values(), Decimal('0'))


def cobros_del_periodo(desde, hasta):
    """
    Espejo de `obligaciones_del_periodo`, del lado de lo que te deben:
    cuotas de CxC que vencen en el rango ('a cobrar') contra las que se
    cobraron de verdad con fecha dentro del rango ('cobrado'). Para la
    tarjeta "Cobros del período" de Caja y Finanzas.
    """
    a_cobrar, cobrado = _cxc_cobros(desde, hasta)
    labels = dict(Moneda.choices)
    monedas = sorted(set(a_cobrar) | set(cobrado))
    return {
        'por_moneda': [
            {
                'moneda': m, 'label': labels.get(m, m),
                'a_cobrar': a_cobrar.get(m, Decimal('0')),
                'cobrado': cobrado.get(m, Decimal('0')),
            }
            for m in monedas
        ],
    }


def obligaciones_del_periodo(desde, hasta):
    """
    'A pagar' (vence en [desde, hasta], esté o no ya pagado):
      - Todo lo de `_deudas_resumenes_cheques` (deudas/tarjetas/cheques).
      - Instancias de Movimientos programados (egresos) pendientes.

    'Pagado' (se pagó de verdad, con fecha dentro de [desde, hasta]):
      - Todo lo de `_deudas_resumenes_cheques`.
      - Gastos (egresos) del rango — cubre tanto los de un solo pago como
        los que salieron de confirmar una instancia programada (ambos
        terminan siendo un Gasto, ver InstanciaProgramada.confirmar()).

    A diferencia de `deudas_y_tarjetas_pagadas_blend`, este SÍ mezcla
    Gastos adentro — pensado para la tarjeta "Compromisos de pago" de
    Caja y Finanzas (un pantallazo completo de todo lo que hay que pagar/
    ya se pagó), no para el waterfall de Resumen (que muestra "Total
    gastado" aparte y necesita evitar que se cuente dos veces).

    Devuelve por moneda: [{moneda, label, a_pagar, pagado}, ...].
    """
    a_pagar, pagado = _deudas_resumenes_cheques(desde, hasta)

    # — Movimientos programados (egresos) pendientes —
    for f in (InstanciaProgramada.objects
              .filter(estado=EstadoInstanciaProgramada.PENDIENTE, programado__tipo=TipoMovimientoCaja.EGRESO,
                      fecha_vencimiento__range=(desde, hasta))
              .values('programado__moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(a_pagar, f['programado__moneda'], f['total'])

    # — Gastos ya ejecutados (un solo pago o programado ya confirmado) —
    for f in (Gasto.objects
              .filter(tipo=TipoMovimientoCaja.EGRESO, fecha__range=(desde, hasta))
              .values('moneda').annotate(total=Sum('monto'))):
        _sumar_moneda(pagado, f['moneda'], f['total'])

    labels = dict(Moneda.choices)
    monedas = sorted(set(a_pagar) | set(pagado))
    return {
        'por_moneda': [
            {
                'moneda': m, 'label': labels.get(m, m),
                'a_pagar': a_pagar.get(m, Decimal('0')),
                'pagado': pagado.get(m, Decimal('0')),
            }
            for m in monedas
        ],
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
