from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from caja.models import CuotaDeuda, EstadoCuota, EstadoDeuda, Cheque, EstadoCheque, TipoCheque
from core.services_estadisticas.productos import perdidas_vencimiento, sin_movimiento


def _fmt(valor):
    return f'{valor:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.')


# ══════════════════════════════════════════════════════════════════
#  PRODUCTOS POR VENCER  (recomendación: liquidar/ofertar)
# ══════════════════════════════════════════════════════════════════

def productos_por_vencer(dias_aviso, hoy=None):
    """
    Reusa perdidas_vencimiento() (ya calcula lotes_por_vencer con la
    misma ventana que usa la pantalla de Estadísticas) y le da el
    formato que necesita el mail de alerta.
    """
    datos = perdidas_vencimiento(dias_alerta=dias_aviso)
    hoy = hoy or timezone.now().date()

    lotes = []
    for lote in datos['lotes_por_vencer']:
        dias_restantes = (lote.fecha_vencimiento - hoy).days
        lotes.append({
            'codigo': lote.codigo,
            'producto_nombre': lote.producto.nombre if lote.producto else '(producto eliminado)',
            'dias_restantes': dias_restantes,
            'valor_fmt': _fmt(lote.valor_en_riesgo or Decimal('0')),
            'referencia': lote.codigo,
        })
    lotes.sort(key=lambda f: f['dias_restantes'])

    return {
        'lotes': lotes,
        'total_valor_riesgo': _fmt(datos['total_en_riesgo']),
        'dias_aviso': dias_aviso,
    }


# ══════════════════════════════════════════════════════════════════
#  DEUDAS PRÓXIMAS A VENCER  (cuotas propias: crédito/préstamo)
# ══════════════════════════════════════════════════════════════════

def deudas_por_vencer(dias_aviso, hoy=None):
    hoy = hoy or timezone.now().date()
    limite = hoy + timedelta(days=dias_aviso)

    qs = (
        CuotaDeuda.objects
        .filter(
            estado=EstadoCuota.PENDIENTE, deuda__estado=EstadoDeuda.ACTIVA,
            fecha_vencimiento__lte=limite,
        )
        .select_related('deuda')
        .order_by('fecha_vencimiento')
    )

    cuotas = []
    total = Decimal('0')
    for cuota in qs:
        dias_restantes = (cuota.fecha_vencimiento - hoy).days
        total += cuota.monto
        cuotas.append({
            'descripcion': cuota.deuda.descripcion or cuota.deuda.get_tipo_display(),
            'numero': cuota.numero,
            'total_cuotas': cuota.deuda.cantidad_cuotas,
            'dias_restantes': dias_restantes,
            'monto_fmt': _fmt(cuota.monto),
            'referencia': cuota.pk,
        })

    return {
        'cuotas': cuotas,
        'total_adeudado': _fmt(total),
        'dias_aviso': dias_aviso,
    }


# ══════════════════════════════════════════════════════════════════
#  DEUDAS RECIÉN PAGADAS
# ══════════════════════════════════════════════════════════════════

def deudas_pagadas_recientemente(dentro_de_dias, hoy=None):
    """Cuotas confirmadas (pagadas) en los últimos `dentro_de_dias` días."""
    ahora = timezone.now()
    limite = ahora - timedelta(days=dentro_de_dias)

    qs = (
        CuotaDeuda.objects
        .filter(estado=EstadoCuota.CONFIRMADA, fecha_confirmacion__gte=limite)
        .select_related('deuda')
        .order_by('-fecha_confirmacion')
    )

    cuotas = []
    total = Decimal('0')
    for cuota in qs:
        total += cuota.monto
        cuotas.append({
            'descripcion': cuota.deuda.descripcion or cuota.deuda.get_tipo_display(),
            'numero': cuota.numero,
            'total_cuotas': cuota.deuda.cantidad_cuotas,
            'fecha_confirmacion': cuota.fecha_confirmacion.strftime('%d/%m/%Y'),
            'monto_fmt': _fmt(cuota.monto),
            'referencia': cuota.pk,
        })

    return {
        'cuotas': cuotas,
        'total_pagado': _fmt(total),
    }


# ══════════════════════════════════════════════════════════════════
#  STOCK ESTANCADO  (recomendación: liquidar/combo/bajar precio)
# ══════════════════════════════════════════════════════════════════

def stock_estancado(dias, top=30):
    productos = sin_movimiento(dias=dias, top=top)

    filas = []
    total_valor = Decimal('0')
    for p in productos:
        total_valor += p['valor']
        filas.append({
            'nombre': p['nombre'],
            'codigo': p['codigo'],
            'stock_actual': p['stock_actual'],
            'valor_fmt': _fmt(p['valor']),
            'referencia': p['id'],
        })

    return {
        'productos': filas,
        'total_valor': _fmt(total_valor),
        'dias': dias,
    }


# ══════════════════════════════════════════════════════════════════
#  CHEQUES PRÓXIMOS A VENCER  (a cobrar y a pagar)
# ══════════════════════════════════════════════════════════════════

def cheques_por_vencer(dias_aviso, hoy=None):
    hoy = hoy or timezone.now().date()
    limite = hoy + timedelta(days=dias_aviso)

    qs = (
        Cheque.objects
        .filter(estado=EstadoCheque.PENDIENTE, fecha_cobro__lte=limite)
        .order_by('fecha_cobro')
    )

    cheques = []
    neto = Decimal('0')
    for cheque in qs:
        dias_restantes = (cheque.fecha_cobro - hoy).days
        es_a_cobrar = cheque.tipo == TipoCheque.A_COBRAR
        neto += cheque.monto if es_a_cobrar else -cheque.monto
        cheques.append({
            'numero': cheque.numero_cheque or f'#{cheque.pk}',
            'es_a_cobrar': es_a_cobrar,
            'dias_restantes': dias_restantes,
            'monto_fmt': _fmt(cheque.monto),
            'referencia': cheque.pk,
        })

    return {
        'cheques': cheques,
        'neto': _fmt(neto),
        'dias_aviso': dias_aviso,
    }
