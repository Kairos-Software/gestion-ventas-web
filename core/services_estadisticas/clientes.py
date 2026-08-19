"""
core/services_estadisticas/clientes.py

Estadísticas del CRM (core.models.Cliente): mejores clientes, nuevos
vs. recurrentes, clientes inactivos y distribución por riesgo/estado.
El link a ventas es `ItemVenta.cliente` — el cliente vive a nivel de
ítem, no de cabecera de Venta (una venta puede tener ítems de
distintos clientes), así que todo se agrupa desde ItemVenta.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Max, Sum
from django.utils import timezone

from core.models import Cliente
from ventas.models import ItemVenta, EstadoVenta
from caja.models import CuentaPorCobrar, CuotaCobro, EstadoCuota, EstadoDeuda, ModoCuotas

from .ventas import SUBTOTAL_EXPR


def _items_confirmados_con_cliente(desde, hasta):
    return (
        ItemVenta.objects
        .filter(venta__estado=EstadoVenta.CONFIRMADA, venta__fecha__range=(desde, hasta))
        .exclude(cliente__isnull=True)
        .annotate(subtotal_calc=SUBTOTAL_EXPR)
    )


# ══════════════════════════════════════════════════════════════════
#  MEJORES CLIENTES DEL PERÍODO
# ══════════════════════════════════════════════════════════════════

def mejores_clientes(desde, hasta, top=10):
    items = _items_confirmados_con_cliente(desde, hasta)

    ranking = (
        items.values('cliente__id', 'cliente_nombre')
        .annotate(
            total_comprado=Sum('subtotal_calc'),
            cant_ventas=Count('venta', distinct=True),
        )
        .order_by('-total_comprado')[:top]
    )
    return [
        {
            'id': fila['cliente__id'],
            'nombre': fila['cliente_nombre'],
            'total_comprado': fila['total_comprado'] or Decimal('0'),
            'cant_ventas': fila['cant_ventas'],
        }
        for fila in ranking
    ]


# ══════════════════════════════════════════════════════════════════
#  NUEVOS VS. RECURRENTES EN EL PERÍODO
# ══════════════════════════════════════════════════════════════════

def nuevos_vs_recurrentes(desde, hasta):
    """
    - nuevos: clientes dados de alta dentro del período (fecha_alta).
    - compradores: clientes distintos con al menos una venta
      confirmada en el período.
    - recurrentes: de esos compradores, los que volvieron más de una
      vez (más de una Venta distinta con ítems de ese cliente).
    """
    nuevos = Cliente.objects.filter(fecha_alta__date__range=(desde, hasta)).count()

    items = _items_confirmados_con_cliente(desde, hasta)
    compradores = (
        items.values('cliente__id')
        .annotate(cant_ventas=Count('venta', distinct=True))
    )
    cantidad_compradores = compradores.count()
    recurrentes = sum(1 for c in compradores if c['cant_ventas'] > 1)

    return {
        'nuevos': nuevos,
        'compradores': cantidad_compradores,
        'recurrentes': recurrentes,
        'de_una_sola_vez': cantidad_compradores - recurrentes,
    }


# ══════════════════════════════════════════════════════════════════
#  CLIENTES INACTIVOS (tiempo real — no depende del filtro de fecha)
# ══════════════════════════════════════════════════════════════════

def clientes_inactivos(dias_sin_comprar=60, top=20):
    """
    Clientes con estado='activo' que no tienen ninguna venta
    confirmada en los últimos `dias_sin_comprar` días (o que nunca
    compraron desde que están cargados).
    """
    hoy = timezone.localtime().date()
    limite = hoy - timedelta(days=dias_sin_comprar)

    ultima_compra_por_cliente = {
        fila['cliente__id']: fila['ultima']
        for fila in (
            ItemVenta.objects
            .filter(venta__estado=EstadoVenta.CONFIRMADA)
            .exclude(cliente__isnull=True)
            .values('cliente__id')
            .annotate(ultima=Max('venta__fecha'))
        )
    }

    inactivos = []
    for cliente in Cliente.objects.filter(estado='activo').order_by('nombre', 'razon_social')[:200]:
        ultima = ultima_compra_por_cliente.get(cliente.id)
        if ultima is None or ultima < limite:
            inactivos.append({
                'id': cliente.id,
                'nombre': cliente.nombre or cliente.razon_social or str(cliente),
                'codigo': cliente.codigo,
                'ultima_compra': ultima,
            })
            if len(inactivos) >= top:
                break

    return inactivos


# ══════════════════════════════════════════════════════════════════
#  DISTRIBUCIÓN POR TIPO Y ESTADO
#  (tiempo real — foto de la base de clientes hoy, no del período)
# ══════════════════════════════════════════════════════════════════

def distribucion_tipo():
    """
    Persona física vs. empresa — a diferencia de nivel_riesgo (campo
    manual que nadie calcula), tipo es obligatorio y siempre está
    cargado, así que esta distribución sí refleja algo real de la
    cartera.
    """
    labels = dict(Cliente.TIPO_CHOICES)
    return [
        {'tipo': f['tipo'], 'label': labels.get(f['tipo'], f['tipo']), 'cantidad': f['cantidad']}
        for f in Cliente.objects.values('tipo').annotate(cantidad=Count('id')).order_by('-cantidad')
    ]


def distribucion_estado():
    labels = dict(Cliente.ESTADO_CHOICES)
    return [
        {'estado': f['estado'], 'label': labels.get(f['estado'], f['estado']), 'cantidad': f['cantidad']}
        for f in Cliente.objects.values('estado').annotate(cantidad=Count('id')).order_by('-cantidad')
    ]


# ══════════════════════════════════════════════════════════════════
#  CUENTAS POR COBRAR (ventas en cuotas — financiación propia del
#  comercio, ver ventas.models.MedioPago.CUOTAS). Tiempo real, salvo
#  "cobrado_periodo" que sí respeta el filtro de fecha. No confundir
#  con Deuda/CuotaDeuda (caja/models.py): eso es lo que VOS le debés
#  a un proveedor o préstamo; esto es lo que te deben LOS CLIENTES.
# ══════════════════════════════════════════════════════════════════

def cuentas_por_cobrar(desde, hasta, dias_proximo_vencimiento=15, top=10):
    """
    IMPORTANTE — modo_cuotas=libre no genera CuotaCobro por adelantado
    (ver CuentaPorCobrar.registrar_abono): no hay "cuotas pendientes"
    pregeneradas, solo un saldo abierto sin fecha de vencimiento propia.
    Si solo se suman CuotaCobro con estado=pendiente, toda la deuda de
    cuentas libres queda afuera de "pendiente de cobro" y del ranking de
    deudores — hay que sumar el saldo_pendiente de esas cuentas aparte.
    Por no tener fecha de vencimiento, tampoco entran en "vencido" ni
    "vence en N días" (no hay contra qué fecha comparar).
    """
    hoy = timezone.localtime().date()

    cuotas_pendientes = CuotaCobro.objects.filter(
        estado=EstadoCuota.PENDIENTE, cuenta_por_cobrar__estado=EstadoDeuda.ACTIVA,
    )
    total_fijas = cuotas_pendientes.aggregate(total=Sum('monto'))['total'] or Decimal('0')
    cantidad_fijas = cuotas_pendientes.count()

    vencidas = cuotas_pendientes.filter(fecha_vencimiento__lt=hoy)
    total_vencido = vencidas.aggregate(total=Sum('monto'))['total'] or Decimal('0')
    cantidad_vencidas = vencidas.count()

    proximas = cuotas_pendientes.filter(
        fecha_vencimiento__gte=hoy,
        fecha_vencimiento__lte=hoy + timedelta(days=dias_proximo_vencimiento),
    )
    total_proximo = proximas.aggregate(total=Sum('monto'))['total'] or Decimal('0')
    cantidad_proximas = proximas.count()

    cuentas_libres = CuentaPorCobrar.objects.filter(
        estado=EstadoDeuda.ACTIVA, modo_cuotas=ModoCuotas.LIBRE,
    )
    libres_con_saldo = [(c, c.saldo_pendiente) for c in cuentas_libres]
    libres_con_saldo = [(c, s) for c, s in libres_con_saldo if s > 0]
    total_libres = sum((s for _, s in libres_con_saldo), Decimal('0'))
    cantidad_libres = len(libres_con_saldo)

    total_pendiente = total_fijas + total_libres
    cantidad_pendiente = cantidad_fijas + cantidad_libres

    cobrado_periodo = CuotaCobro.objects.filter(
        estado=EstadoCuota.CONFIRMADA, fecha_confirmacion__date__range=(desde, hasta),
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0')

    deuda_por_cliente = {}
    for f in (
        cuotas_pendientes.values('cuenta_por_cobrar__cliente__id')
        .annotate(total=Sum('monto'), cantidad=Count('id'))
    ):
        acumulado = deuda_por_cliente.setdefault(
            f['cuenta_por_cobrar__cliente__id'], {'total': Decimal('0'), 'cantidad': 0})
        acumulado['total'] += f['total'] or Decimal('0')
        acumulado['cantidad'] += f['cantidad']
    for cxc, saldo in libres_con_saldo:
        acumulado = deuda_por_cliente.setdefault(
            cxc.cliente_id, {'total': Decimal('0'), 'cantidad': 0})
        acumulado['total'] += saldo
        acumulado['cantidad'] += 1

    top_clientes = sorted(
        deuda_por_cliente.items(), key=lambda kv: kv[1]['total'], reverse=True)[:top]
    clientes_dict = {
        c.id: c for c in Cliente.objects.filter(id__in=[cid for cid, _ in top_clientes])
    }
    ranking_deudores = [
        {
            'id': cid,
            'nombre': (
                clientes_dict[cid].get_nombre_display()
                if cid in clientes_dict else '(cliente eliminado)'
            ),
            'total': datos['total'],
            'cantidad_cuotas': datos['cantidad'],
        }
        for cid, datos in top_clientes
    ]

    return {
        'total_pendiente': total_pendiente,
        'cantidad_pendiente': cantidad_pendiente,
        'total_vencido': total_vencido,
        'cantidad_vencidas': cantidad_vencidas,
        'total_proximo': total_proximo,
        'cantidad_proximas': cantidad_proximas,
        'cobrado_periodo': cobrado_periodo,
        'ranking_deudores': ranking_deudores,
    }
