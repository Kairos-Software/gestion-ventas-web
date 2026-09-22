"""
core/services_estadisticas/cliente_perfil.py

Ficha individual de un cliente: ventas y margen bruto estimado en ARS,
otras ventas por moneda, y qué tan cumplidor es pagando sus cuotas. A diferencia
del resto de services_estadisticas/*, estas funciones no reciben
desde/hasta — es un perfil de todo el historial del cliente, no una
foto de un período.
"""

from decimal import Decimal

from django.db.models import Count, Max, Sum
from django.utils import timezone

from caja.models import CuentaPorCobrar, CuotaCobro, EstadoCuota, EstadoDeuda
from caja.views_cuentas_cobrar import _serializar_cxc
from productos.models import Moneda
from ventas.models import ItemVenta, Venta, EstadoVenta

from .ventas import SUBTOTAL_EXPR, _costo_de_items


# ══════════════════════════════════════════════════════════════════
#  VALOR DEL CLIENTE — margen bruto estimado solo en ARS
# ══════════════════════════════════════════════════════════════════

def perfil_valor(cliente):
    todos_los_items = (
        ItemVenta.objects
        .filter(cliente=cliente, venta__estado=EstadoVenta.CONFIRMADA)
        .annotate(subtotal_calc=SUBTOTAL_EXPR)
    )
    items = todos_los_items.filter(moneda=Moneda.ARS)

    ingresos = items.aggregate(total=Sum('subtotal_calc'))['total'] or Decimal('0')
    costo = _costo_de_items(items)
    ganancia = ingresos - costo

    cant_ventas = items.values('venta').distinct().count()
    ultima_compra = todos_los_items.aggregate(ultima=Max('venta__fecha'))['ultima']
    ticket_promedio = round(ingresos / cant_ventas, 2) if cant_ventas else Decimal('0')
    margen_pct = round(ganancia / ingresos * 100, 1) if ingresos else Decimal('0')
    ventas_otras_monedas = [
        {
            'moneda': fila['moneda'],
            'ingresos': fila['ingresos'] or Decimal('0'),
            'cant_ventas': fila['cant_ventas'],
        }
        for fila in (
            todos_los_items.exclude(moneda=Moneda.ARS)
            .values('moneda')
            .annotate(ingresos=Sum('subtotal_calc'), cant_ventas=Count('venta', distinct=True))
        )
    ]

    return {
        'ingresos': ingresos,
        'costo': costo,
        'ganancia': ganancia,
        'margen_pct': margen_pct,
        'cant_ventas': cant_ventas,
        'ticket_promedio': ticket_promedio,
        'ultima_compra': ultima_compra,
        'ventas_otras_monedas': ventas_otras_monedas,
    }


# ══════════════════════════════════════════════════════════════════
#  COMPORTAMIENTO DE PAGO — puntualidad y uso del crédito otorgado
# ══════════════════════════════════════════════════════════════════

def comportamiento_pago(cliente):
    hoy = timezone.localtime().date()

    # es_historica=True: cuota cargada como "ya cobrada antes del
    # sistema" (carga inicial) — no tiene una fecha de pago real
    # comparable contra el vencimiento, así que no cuenta para
    # puntualidad.
    confirmadas = list(
        CuotaCobro.objects
        .filter(cuenta_por_cobrar__cliente=cliente, estado=EstadoCuota.CONFIRMADA, es_historica=False)
        .exclude(fecha_confirmacion__isnull=True)
    )
    a_termino = [c for c in confirmadas if timezone.localtime(c.fecha_confirmacion).date() <= c.fecha_vencimiento]
    con_atraso = [c for c in confirmadas if timezone.localtime(c.fecha_confirmacion).date() > c.fecha_vencimiento]
    evaluadas = len(a_termino) + len(con_atraso)

    pct_a_termino = round(len(a_termino) / evaluadas * 100, 1) if evaluadas else None
    atraso_promedio_dias = (
        round(sum((timezone.localtime(c.fecha_confirmacion).date() - c.fecha_vencimiento).days for c in con_atraso) / len(con_atraso), 1)
        if con_atraso else 0
    )

    mora = CuotaCobro.objects.filter(
        cuenta_por_cobrar__cliente=cliente,
        cuenta_por_cobrar__estado=EstadoDeuda.ACTIVA,
        estado=EstadoCuota.PENDIENTE, fecha_vencimiento__lt=hoy,
    )
    mora_por_moneda = {
        fila['cuenta_por_cobrar__moneda']: {
            'total': fila['total'] or Decimal('0'),
            'cantidad': fila['cantidad'],
        }
        for fila in (
            mora.values('cuenta_por_cobrar__moneda')
            .annotate(total=Sum('monto'), cantidad=Count('id'))
        )
    }

    cuentas_activas = list(CuentaPorCobrar.objects.filter(cliente=cliente, estado=EstadoDeuda.ACTIVA))
    saldo_por_moneda = {}
    total_por_moneda = {}
    cantidad_cuentas_ars = 0
    for cuenta in cuentas_activas:
        saldo = cuenta.saldo_pendiente
        saldo_por_moneda[cuenta.moneda] = saldo_por_moneda.get(cuenta.moneda, Decimal('0')) + saldo
        total_por_moneda[cuenta.moneda] = total_por_moneda.get(cuenta.moneda, Decimal('0')) + cuenta.monto_total
        if cuenta.moneda == Moneda.ARS and saldo > 0:
            cantidad_cuentas_ars += 1
    monto_total_otorgado = total_por_moneda.get(Moneda.ARS, Decimal('0'))
    saldo_actual = saldo_por_moneda.get(Moneda.ARS, Decimal('0'))
    uso_credito_pct = round(saldo_actual / monto_total_otorgado * 100, 1) if monto_total_otorgado else None
    mora_pesos = mora_por_moneda.get(Moneda.ARS, {'total': Decimal('0'), 'cantidad': 0})
    otras_monedas = [
        {
            'moneda': moneda,
            'saldo_actual': saldo_por_moneda.get(moneda, Decimal('0')),
            'mora_total': mora_por_moneda.get(moneda, {}).get('total', Decimal('0')),
            'mora_cantidad': mora_por_moneda.get(moneda, {}).get('cantidad', 0),
        }
        for moneda in (Moneda.USD, Moneda.EUR)
        if moneda in saldo_por_moneda or moneda in mora_por_moneda
    ]

    return {
        'pct_a_termino': pct_a_termino,
        'cantidad_evaluadas': evaluadas,
        'cantidad_a_termino': len(a_termino),
        'cantidad_con_atraso': len(con_atraso),
        'atraso_promedio_dias': atraso_promedio_dias,
        'mora_total': mora_pesos['total'],
        'mora_cantidad': mora_pesos['cantidad'],
        'saldo_actual': saldo_actual,
        'cantidad_cuentas_ars': cantidad_cuentas_ars,
        'otras_monedas': otras_monedas,
        'monto_total_otorgado': monto_total_otorgado,
        'uso_credito_pct': uso_credito_pct,
    }


# ══════════════════════════════════════════════════════════════════
#  DEUDA CONSOLIDADA — todas las CuentaPorCobrar activas con saldo
# ══════════════════════════════════════════════════════════════════

def deudas_activas(cliente):
    cuentas = (
        CuentaPorCobrar.objects
        .filter(cliente=cliente, estado=EstadoDeuda.ACTIVA)
        .select_related('pago_venta__venta')
        .prefetch_related('cuotas__cheques', 'documentos')
    )
    resultado = []
    for c in cuentas:
        if c.saldo_pendiente <= 0:
            continue
        data = _serializar_cxc(c, con_cuotas=True)
        # Título para mostrar: descripción propia si la tiene, si no "Venta
        # X" (evita repetir el número de venta dos veces cuando
        # numero_comprobante ya se autocompletó con el mismo valor).
        data['titulo'] = (
            c.descripcion
            or (f'Venta {data["venta_numero"]}' if data['venta_numero'] else '')
            or c.numero_comprobante
            or f'Cuenta #{c.pk}'
        )
        resultado.append(data)
    return resultado


# ══════════════════════════════════════════════════════════════════
#  HISTORIAL — cada venta y cada pago de cuota, ordenado por fecha
# ══════════════════════════════════════════════════════════════════

def historial_cliente(cliente):
    """
    Línea de tiempo con saldo corrido por moneda: no se suman pesos,
    dólares y euros como si fueran un mismo importe. Cada evento suma
    o resta en la moneda de su cuenta, en orden cronológico.
    """
    eventos = []

    montos_por_venta = {}
    for fila in (
        ItemVenta.objects.filter(cliente=cliente, venta__estado=EstadoVenta.CONFIRMADA)
        .annotate(subtotal_calc=SUBTOTAL_EXPR)
        .values('venta_id', 'moneda')
        .annotate(monto_cliente=Sum('subtotal_calc'))
    ):
        montos_por_venta.setdefault(fila['venta_id'], []).append({
            'moneda': fila['moneda'],
            'monto': fila['monto_cliente'] or Decimal('0'),
        })
    ventas = (
        Venta.objects.filter(pk__in=montos_por_venta)
        .prefetch_related('pagos__cuenta_por_cobrar')
    )
    for venta in ventas:
        pago_cxc = next((p for p in venta.pagos.all() if getattr(p, 'cuenta_por_cobrar', None)), None)
        cxc = pago_cxc.cuenta_por_cobrar if pago_cxc else None
        if cxc and (cxc.cliente_id != cliente.id or cxc.estado == EstadoDeuda.ANULADA):
            cxc = None  # venta con ítems mezclados de varios clientes, o cuenta anulada — no es deuda vigente
        for parte in montos_por_venta[venta.pk]:
            eventos.append({
                'fecha': venta.fecha,
                'descripcion': f'Venta {venta.numero}',
                'medio_pago': venta.get_medio_pago_display(),
                'moneda': parte['moneda'],
                # Una venta puede mezclar clientes y monedas: mostrar
                # solamente el importe de este cliente en esta moneda.
                'monto': parte['monto'],
                # La cuenta por cobrar puede incluir interés; lo que
                # pasa a deber no siempre coincide con la venta.
                'delta': cxc.monto_total if cxc and cxc.moneda == parte['moneda'] else Decimal('0'),
            })
        if cxc and all(parte['moneda'] != cxc.moneda for parte in montos_por_venta[venta.pk]):
            eventos.append({
                'fecha': venta.fecha,
                'descripcion': f'Saldo a cobrar de venta {venta.numero}',
                'medio_pago': '',
                'moneda': cxc.moneda,
                'monto': cxc.monto_total,
                'delta': cxc.monto_total,
            })

    # Deudas cargadas a mano (sin venta asociada, ej. "carga inicial" de
    # saldos previos al sistema) — no hay una fila de "venta" que las
    # origine, así que su alta es su propio evento: sube el saldo total
    # del cliente en ese momento igual que si fuera una venta en cuotas.
    cuentas_sin_venta = (
        CuentaPorCobrar.objects
        .filter(cliente=cliente, pago_venta__isnull=True, estado=EstadoDeuda.ACTIVA)
        .prefetch_related('cuotas')
    )
    for cxc in cuentas_sin_venta:
        # fecha_inicio es el vencimiento de la 1ª cuota (fecha de plan),
        # no cuándo arrancó la deuda — para que el saldo corrido cierre
        # bien, esta fila tiene que quedar ANTES que cualquier pago propio
        # ya registrado, así que se toma la fecha más vieja entre todas
        # las relacionadas a la cuenta.
        fechas = [cxc.fecha_inicio]
        for cuota in cxc.cuotas.all():
            fechas.append(cuota.fecha_vencimiento)
            if cuota.fecha_confirmacion:
                fechas.append(timezone.localtime(cuota.fecha_confirmacion).date())
        eventos.append({
            'fecha': min(fechas),
            'descripcion': f'Deuda cargada: {cxc.descripcion or cxc.numero_comprobante or f"#{cxc.pk}"}',
            'medio_pago': '',
            'moneda': cxc.moneda,
            'monto': cxc.monto_total,
            'delta': cxc.monto_total,
        })

    cuotas = (
        CuotaCobro.objects
        .filter(cuenta_por_cobrar__cliente=cliente, estado=EstadoCuota.CONFIRMADA)
        .select_related('cuenta_por_cobrar')
    )
    # Las cuotas/abonos que generó un cobro por cuenta corriente (cascada
    # FIFO) se muestran como UN solo evento por recibo — "pagó $X", no una
    # línea por cada deuda que tocó. El resto, una línea por cuota.
    cobros_cc = {}   # (cobro_id, moneda) -> {fecha, monto, moneda}
    for cuota in cuotas:
        cxc = cuota.cuenta_por_cobrar
        fecha = timezone.localtime(cuota.fecha_confirmacion).date() if cuota.fecha_confirmacion else cuota.fecha_vencimiento
        if cuota.cobro_cuenta_corriente_id:
            acc = cobros_cc.setdefault(
                (cuota.cobro_cuenta_corriente_id, cxc.moneda),
                {'fecha': fecha, 'monto': Decimal('0'), 'moneda': cxc.moneda},
            )
            acc['monto'] += cuota.monto
            acc['fecha'] = min(acc['fecha'], fecha)
            continue
        referencia = cxc.descripcion or cxc.numero_comprobante or f'deuda #{cxc.pk}'
        numero_cuota = f'{cuota.numero}/{cxc.cantidad_cuotas}' if cxc.cantidad_cuotas else str(cuota.numero)
        eventos.append({
            'fecha': fecha,
            'descripcion': f'Pago cuota {numero_cuota} — {referencia}',
            'medio_pago': '',
            'moneda': cxc.moneda,
            'monto': cuota.monto,
            'delta': -cuota.monto,
        })
    for acc in cobros_cc.values():
        eventos.append({
            'fecha': acc['fecha'],
            'descripcion': 'Cobro de cuenta corriente',
            'medio_pago': '',
            'moneda': acc['moneda'],
            'monto': acc['monto'],
            'delta': -acc['monto'],
        })

    eventos.sort(key=lambda e: e['fecha'])

    saldos_por_moneda = {}
    filas = []
    for e in eventos:
        moneda = e['moneda']
        saldos_por_moneda[moneda] = saldos_por_moneda.get(moneda, Decimal('0')) + e['delta']
        filas.append({
            'fecha': e['fecha'],
            'descripcion': e['descripcion'],
            'medio_pago': e['medio_pago'],
            'moneda': moneda,
            'monto': str(e['monto']),
            'saldo': str(saldos_por_moneda[moneda]),
        })
    return filas


# ══════════════════════════════════════════════════════════════════
#  HISTORIAL DE SCORING — línea de tiempo del riesgo de pago
# ══════════════════════════════════════════════════════════════════

def historial_scoring(cliente):
    """
    Puntos guardados en HistorialScoring (uno por fecha en que el
    puntaje efectivo cambió — ver Cliente.recalcular_scoring()), más un
    punto final con el valor VIGENTE ahora mismo si todavía no coincide
    con el último guardado, para que el gráfico siempre termine en el
    número real de hoy aunque recién no se haya disparado ningún
    recálculo.

    Un cliente sin historial de crédito (nunca compró en cuotas ni pagó
    con cheque — mismo `sin_historial` que calcular_scoring()) devuelve
    lista vacía en vez de un punto trivial "1000, hoy": todavía no hay
    nada que graficar.
    """
    from core.scoring import BANDA_LABEL

    puntos = list(
        cliente.historial_scoring
        .order_by('fecha')
        .values('fecha', 'score', 'banda', 'desglose', 'es_backfill')
    )

    if not puntos and cliente.scoring_sin_historial:
        return []

    if not puntos or puntos[-1]['score'] != cliente.scoring:
        puntos.append({
            'fecha': timezone.localtime().date(),
            'score': cliente.scoring,
            'banda': cliente.scoring_banda,
            'desglose': cliente.scoring_desglose or [],
            'es_backfill': False,
            # Vigente AHORA MISMO pero todavía no se guardó como punto real
            # (nadie disparó un recálculo hoy) — el frontend lo aclara para
            # no hacer parecer que fue "registrado" ese día como los demás.
            'es_actual': True,
        })

    for p in puntos:
        p['banda_label'] = BANDA_LABEL.get(p['banda'], p['banda'])
        p.setdefault('es_actual', False)

    return puntos
