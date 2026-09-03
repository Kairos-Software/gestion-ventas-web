"""
Congela la ganancia bruta (margen + redondeos + recargos) en el
snapshot `totales_cierre` de cada turno YA cerrado.

Antes de este cambio, TurnoCaja.ganancia_turno era otra cosa
(≈recaudación). Ahora es el margen real y, para los turnos cerrados
que no tienen el valor congelado, la property lo recalcula en vivo en
cada visita al Historial — 3 queries por turno. Este backfill lo deja
guardado una sola vez: el Historial vuelve a ser O(1) y el número
queda fijo en el tiempo (igual que el resto del snapshot de cierre).

Idempotente: salta los turnos que ya tienen la clave.
"""

from decimal import Decimal

from django.db import migrations
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from django.utils import timezone


def backfill(apps, schema_editor):
    TurnoCaja = apps.get_model('caja', 'TurnoCaja')
    Venta = apps.get_model('ventas', 'Venta')
    ItemVenta = apps.get_model('ventas', 'ItemVenta')
    ConsumoLoteVenta = apps.get_model('ventas', 'ConsumoLoteVenta')
    PagoVenta = apps.get_model('ventas', 'PagoVenta')

    money = DecimalField(max_digits=14, decimal_places=2)

    for t in TurnoCaja.objects.filter(estado='cerrado').iterator():
        if not t.totales_cierre or t.totales_cierre.get('ganancia_bruta_turno') is not None:
            continue

        fin = t.fecha_cierre or timezone.now()
        ventas = Venta.objects.filter(
            estado='confirmada',
            fecha_alta__gte=t.fecha_apertura,
            fecha_alta__lte=fin,
        )
        ingresos = (
            ItemVenta.objects.filter(venta__in=ventas)
            .annotate(_s=ExpressionWrapper(
                F('cantidad') * F('precio_unitario') * (1 - F('descuento_pct') / 100),
                output_field=money))
            .aggregate(x=Sum('_s'))['x'] or Decimal('0')
        )
        costo = (
            ConsumoLoteVenta.objects.filter(item_venta__venta__in=ventas)
            .annotate(_c=ExpressionWrapper(
                F('cantidad') * F('costo_unitario_snapshot'), output_field=money))
            .aggregate(x=Sum('_c'))['x'] or Decimal('0')
        )
        ex = PagoVenta.objects.filter(venta__in=ventas).aggregate(
            r=Sum('recargo_monto'), d=Sum('redondeo_monto'))
        extra = (ex['r'] or Decimal('0')) + (ex['d'] or Decimal('0'))

        t.totales_cierre['ganancia_bruta_turno'] = str(ingresos - costo + extra)
        t.save(update_fields=['totales_cierre'])


def limpiar(apps, schema_editor):
    TurnoCaja = apps.get_model('caja', 'TurnoCaja')
    for t in TurnoCaja.objects.filter(estado='cerrado').iterator():
        if t.totales_cierre and 'ganancia_bruta_turno' in t.totales_cierre:
            t.totales_cierre.pop('ganancia_bruta_turno')
            t.save(update_fields=['totales_cierre'])


class Migration(migrations.Migration):

    dependencies = [
        ('caja', '0038_backfill_conceptos_gasto'),
        ('ventas', '0026_pagoventa_redondeo_monto'),
    ]

    operations = [
        migrations.RunPython(backfill, limpiar),
    ]
