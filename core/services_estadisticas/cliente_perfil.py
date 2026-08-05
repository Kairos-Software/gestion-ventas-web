"""
core/services_estadisticas/cliente_perfil.py

Ficha individual de un cliente: cuánto vale (ganancia real, no solo
facturación) y qué tan cumplidor es pagando sus cuotas. A diferencia
del resto de services_estadisticas/*, estas funciones no reciben
desde/hasta — es un perfil de todo el historial del cliente, no una
foto de un período.
"""

from decimal import Decimal

from django.db.models import Max, Sum
from django.utils import timezone

from caja.models import CuentaPorCobrar, CuotaCobro, EstadoCuota, EstadoDeuda
from caja.views_cuentas_cobrar import _serializar_cxc
from ventas.models import ItemVenta, Venta, EstadoVenta

from .ventas import SUBTOTAL_EXPR, _costo_de_items


# ══════════════════════════════════════════════════════════════════
#  VALOR DEL CLIENTE — ganancia real, no solo facturación
# ══════════════════════════════════════════════════════════════════

def perfil_valor(cliente):
    items = (
        ItemVenta.objects
        .filter(cliente=cliente, venta__estado=EstadoVenta.CONFIRMADA)
        .annotate(subtotal_calc=SUBTOTAL_EXPR)
    )

    ingresos = items.aggregate(total=Sum('subtotal_calc'))['total'] or Decimal('0')
    costo = _costo_de_items(items)
    ganancia = ingresos - costo

    cant_ventas = items.values('venta').distinct().count()
    ultima_compra = items.aggregate(ultima=Max('venta__fecha'))['ultima']
    ticket_promedio = round(ingresos / cant_ventas, 2) if cant_ventas else Decimal('0')
    margen_pct = round(ganancia / ingresos * 100, 1) if ingresos else Decimal('0')

    return {
        'ingresos': ingresos,
        'costo': costo,
        'ganancia': ganancia,
        'margen_pct': margen_pct,
        'cant_ventas': cant_ventas,
        'ticket_promedio': ticket_promedio,
        'ultima_compra': ultima_compra,
    }


# ══════════════════════════════════════════════════════════════════
#  COMPORTAMIENTO DE PAGO — puntualidad y uso del crédito otorgado
# ══════════════════════════════════════════════════════════════════

def comportamiento_pago(cliente):
    hoy = timezone.now().date()

    # es_historica=True: cuota cargada como "ya cobrada antes del
    # sistema" (carga inicial) — no tiene una fecha de pago real
    # comparable contra el vencimiento, así que no cuenta para
    # puntualidad.
    confirmadas = list(
        CuotaCobro.objects
        .filter(cuenta_por_cobrar__cliente=cliente, estado=EstadoCuota.CONFIRMADA, es_historica=False)
        .exclude(fecha_confirmacion__isnull=True)
    )
    a_termino = [c for c in confirmadas if c.fecha_confirmacion.date() <= c.fecha_vencimiento]
    con_atraso = [c for c in confirmadas if c.fecha_confirmacion.date() > c.fecha_vencimiento]
    evaluadas = len(a_termino) + len(con_atraso)

    pct_a_termino = round(len(a_termino) / evaluadas * 100, 1) if evaluadas else None
    atraso_promedio_dias = (
        round(sum((c.fecha_confirmacion.date() - c.fecha_vencimiento).days for c in con_atraso) / len(con_atraso), 1)
        if con_atraso else 0
    )

    mora = CuotaCobro.objects.filter(
        cuenta_por_cobrar__cliente=cliente, estado=EstadoCuota.PENDIENTE, fecha_vencimiento__lt=hoy,
    )
    mora_total = mora.aggregate(total=Sum('monto'))['total'] or Decimal('0')
    mora_cantidad = mora.count()

    cuentas_activas = list(CuentaPorCobrar.objects.filter(cliente=cliente, estado=EstadoDeuda.ACTIVA))
    monto_total_otorgado = sum((c.monto_total for c in cuentas_activas), Decimal('0'))
    saldo_actual = sum((c.saldo_pendiente for c in cuentas_activas), Decimal('0'))
    uso_credito_pct = round(saldo_actual / monto_total_otorgado * 100, 1) if monto_total_otorgado else None

    return {
        'pct_a_termino': pct_a_termino,
        'cantidad_evaluadas': evaluadas,
        'cantidad_a_termino': len(a_termino),
        'cantidad_con_atraso': len(con_atraso),
        'atraso_promedio_dias': atraso_promedio_dias,
        'mora_total': mora_total,
        'mora_cantidad': mora_cantidad,
        'saldo_actual': saldo_actual,
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
    Línea de tiempo con SALDO CORRIDO real: no es el saldo de una cuenta
    por cobrar puntual, es lo que el cliente debe en total sumando todas
    sus deudas, punto por punto en el tiempo. Cada evento suma o resta
    contra ese acumulador, en orden cronológico ascendente (para que la
    cuenta "iba debiendo esto, pagó, quedó esto, sacó otra deuda, ahora
    debe esto otro" se pueda seguir leyendo de arriba hacia abajo).
    """
    eventos = []

    ventas_ids = (
        ItemVenta.objects.filter(cliente=cliente, venta__estado=EstadoVenta.CONFIRMADA)
        .values_list('venta_id', flat=True).distinct()
    )
    ventas = (
        Venta.objects.filter(pk__in=ventas_ids)
        .prefetch_related('pagos__cuenta_por_cobrar')
    )
    for venta in ventas:
        pago_cxc = next((p for p in venta.pagos.all() if getattr(p, 'cuenta_por_cobrar', None)), None)
        cxc = pago_cxc.cuenta_por_cobrar if pago_cxc else None
        if cxc and (cxc.cliente_id != cliente.id or cxc.estado == EstadoDeuda.ANULADA):
            cxc = None  # venta con ítems mezclados de varios clientes, o cuenta anulada — no es deuda vigente
        eventos.append({
            'fecha': venta.fecha,
            'descripcion': f'Venta {venta.numero}',
            'medio_pago': venta.get_medio_pago_display(),
            'monto': venta.total,
            # Si la venta generó una cuenta por cobrar, lo que pasa a deber
            # es el monto TOTAL de esa cuenta (con interés si tiene) — no
            # necesariamente el total de la venta. Si se pagó de contado,
            # no generó deuda nueva.
            'delta': cxc.monto_total if cxc else Decimal('0'),
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
                fechas.append(cuota.fecha_confirmacion.date())
        eventos.append({
            'fecha': min(fechas),
            'descripcion': f'Deuda cargada: {cxc.descripcion or cxc.numero_comprobante or f"#{cxc.pk}"}',
            'medio_pago': '',
            'monto': cxc.monto_total,
            'delta': cxc.monto_total,
        })

    cuotas = (
        CuotaCobro.objects
        .filter(cuenta_por_cobrar__cliente=cliente, estado=EstadoCuota.CONFIRMADA)
        .select_related('cuenta_por_cobrar')
    )
    for cuota in cuotas:
        cxc = cuota.cuenta_por_cobrar
        referencia = cxc.descripcion or cxc.numero_comprobante or f'deuda #{cxc.pk}'
        numero_cuota = f'{cuota.numero}/{cxc.cantidad_cuotas}' if cxc.cantidad_cuotas else str(cuota.numero)
        fecha = cuota.fecha_confirmacion.date() if cuota.fecha_confirmacion else cuota.fecha_vencimiento
        eventos.append({
            'fecha': fecha,
            'descripcion': f'Pago cuota {numero_cuota} — {referencia}',
            'medio_pago': '',
            'monto': cuota.monto,
            'delta': -cuota.monto,
        })

    eventos.sort(key=lambda e: e['fecha'])

    saldo = Decimal('0')
    filas = []
    for e in eventos:
        saldo += e['delta']
        filas.append({
            'fecha': e['fecha'].isoformat(),
            'descripcion': e['descripcion'],
            'medio_pago': e['medio_pago'],
            'monto': str(e['monto']),
            'saldo': str(saldo),
        })
    return filas
