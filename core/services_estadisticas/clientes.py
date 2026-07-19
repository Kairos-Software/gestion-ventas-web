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
    hoy = timezone.now().date()
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
#  DISTRIBUCIÓN POR NIVEL DE RIESGO Y ESTADO
#  (tiempo real — foto de la base de clientes hoy, no del período)
# ══════════════════════════════════════════════════════════════════

def distribucion_riesgo():
    labels = dict(Cliente.NIVEL_RIESGO_CHOICES)
    return [
        {'nivel': f['nivel_riesgo'], 'label': labels.get(f['nivel_riesgo'], f['nivel_riesgo']), 'cantidad': f['cantidad']}
        for f in Cliente.objects.values('nivel_riesgo').annotate(cantidad=Count('id')).order_by('-cantidad')
    ]


def distribucion_estado():
    labels = dict(Cliente.ESTADO_CHOICES)
    return [
        {'estado': f['estado'], 'label': labels.get(f['estado'], f['estado']), 'cantidad': f['cantidad']}
        for f in Cliente.objects.values('estado').annotate(cantidad=Count('id')).order_by('-cantidad')
    ]
