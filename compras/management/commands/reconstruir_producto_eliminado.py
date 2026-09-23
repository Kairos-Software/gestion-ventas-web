"""
python manage.py reconstruir_producto_eliminado [busqueda]

Solo lectura. Un Producto eliminado se borra de verdad — no hay papelera
(ver Producto.delete(), productos/models.py) — pero sus LoteCompra
sobreviven (producto=SET_NULL) con `cantidad_actual` intacto EXACTAMENTE
como quedó al momento del borrado: Producto.delete() solo los desactiva
(activo=False), nunca toca esa cantidad. Cruzando eso con el snapshot de
texto que cada lote conserva vía su ItemCompra de origen
(producto_nombre/producto_codigo, que tampoco se borran) se puede
reconstruir, para cada producto eliminado: qué era, cuánto stock exacto
le quedaba al momento de eliminarse, cuánto valía a costo, y de qué
compra (o factura inicial) salió cada lote.

Lo que esto NO reconstruye: el historial de MovimientoStock (ajustes
manuales de stock, ventas puntuales) — Producto.delete() lo borra en
bloque sin dejar ningún snapshot, así que no hay forma de ver el detalle
de cómo se movió el stock antes de llegar a ese número final. El número
final en sí (cantidad_actual del lote) es exacto, no una aproximación.

Sin argumento: lista TODOS los productos eliminados con lotes huérfanos
detectables. Con texto: filtra por código o nombre (snapshot).
"""
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from compras.models import LoteCompra


class Command(BaseCommand):
    help = (
        'Reconstruye (solo lectura) el stock que tenían productos ya eliminados, '
        'a partir de sus lotes de compra huérfanos.'
    )

    def add_arguments(self, parser):
        parser.add_argument('busqueda', nargs='?', type=str, default=None)

    def handle(self, *args, **options):
        lotes = (
            LoteCompra.objects
            .filter(producto__isnull=True)
            .select_related('item_compra__compra')
            .order_by('fecha_compra')
        )

        busqueda = options.get('busqueda')
        if busqueda:
            lotes = lotes.filter(
                Q(item_compra__producto_codigo__icontains=busqueda)
                | Q(item_compra__producto_nombre__icontains=busqueda)
            )

        grupos = defaultdict(list)
        sin_snapshot = []
        for lote in lotes:
            if lote.item_compra_id and lote.item_compra.producto_codigo:
                grupos[lote.item_compra.producto_codigo].append(lote)
            else:
                sin_snapshot.append(lote)

        if not grupos and not sin_snapshot:
            self.stdout.write(self.style.SUCCESS(
                'No se encontraron lotes huérfanos (de productos eliminados) que coincidan.'
            ))
            return

        for codigo in sorted(grupos):
            lotes_grupo = grupos[codigo]
            nombre = lotes_grupo[0].item_compra.producto_nombre or '(sin nombre registrado)'

            activos_al_borrar = [l for l in lotes_grupo if not l.activo]
            anomalos = [l for l in lotes_grupo if l.activo]

            stock_total = sum((l.cantidad_actual for l in activos_al_borrar), Decimal('0'))
            valor_total = sum(
                (l.cantidad_actual * l.costo_unitario for l in activos_al_borrar), Decimal('0'),
            )

            self.stdout.write(self.style.WARNING(f'\n[{codigo}] {nombre}'))
            self.stdout.write(
                f'  Stock que tenía al momento de eliminarse: {stock_total} unidad(es) '
                f'— valor a costo: ${valor_total:.2f}'
            )
            for lote in sorted(lotes_grupo, key=lambda l: l.fecha_compra):
                if lote.item_compra_id and lote.item_compra.compra_id:
                    origen = f'compra {lote.item_compra.compra.numero}'
                else:
                    origen = 'ajuste manual (sin compra de origen)'
                self.stdout.write(
                    f'    - {lote.codigo}: {lote.cantidad_actual}/{lote.cantidad_inicial} u. '
                    f'a ${lote.costo_unitario}/u ({lote.fecha_compra}, {origen})'
                )
            if anomalos:
                self.stdout.write(self.style.ERROR(
                    f'  ! {len(anomalos)} lote(s) de este producto siguen "activo=True" pese a no '
                    f'tener producto — no debería pasar (ver migración compras/0021), revisar a mano.'
                ))

        if sin_snapshot:
            self.stdout.write(self.style.ERROR(
                f'\n{len(sin_snapshot)} lote(s) huérfano(s) sin snapshot de producto asociado '
                f'(vinieron de un ajuste manual, no de una compra) — no se puede identificar a qué '
                f'producto pertenecían:'
            ))
            for lote in sin_snapshot:
                self.stdout.write(f'  - {lote.codigo}: {lote.cantidad_actual} u., {lote.fecha_compra}')
