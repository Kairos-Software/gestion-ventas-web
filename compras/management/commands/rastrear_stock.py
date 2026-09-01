"""
Rastrea de dónde salió el stock de un producto.

    python manage.py rastrear_stock "coca cola 2.25"
    python manage.py rastrear_stock PRD-00123
    python manage.py rastrear_stock "arroz" --todos      # lista coincidencias

El sistema NO tiene un único "libro de stock": cada entrada por Compra o
Factura inicial deja un LoteCompra; los ajustes a mano, mermas y
fraccionamientos dejan un MovimientoStock. Este comando junta las dos
cosas para un producto y muestra, lote por lote, qué compra / factura
inicial / ajuste lo generó, con cantidad, fecha y usuario.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q, Sum

from productos.models import Producto, MovimientoStock
from compras.models import LoteCompra, ItemCompra, Fraccionamiento


def _dec(v):
    try:
        return f'{Decimal(v):,.3f}'.rstrip('0').rstrip('.')
    except Exception:
        return str(v)


class Command(BaseCommand):
    help = 'Muestra el origen del stock de un producto (lotes de compra/factura inicial + ajustes manuales).'

    def add_arguments(self, parser):
        parser.add_argument('busqueda', help='Codigo, SKU o parte del nombre del producto.')
        parser.add_argument('--todos', action='store_true',
                            help='Si hay varias coincidencias, procesarlas todas en vez de cortar.')

    def handle(self, *args, **opts):
        # La consola de Windows (cp1252) no encodea algunos caracteres que
        # pueden venir en datos del usuario (motivos, nombres). Que no
        # explote: reemplaza lo que no entre en vez de crashear.
        try:
            self.stdout._out.reconfigure(errors='replace')
        except Exception:
            pass
        w = self.stdout.write
        q = opts['busqueda'].strip()

        qs = Producto.objects.filter(
            Q(codigo__icontains=q) | Q(nombre__icontains=q) | Q(sku__icontains=q)
        ).order_by('nombre')

        n = qs.count()
        if n == 0:
            raise CommandError(f'Ningun producto coincide con "{q}".')
        if n > 1 and not opts['todos']:
            w(f'{n} productos coinciden con "{q}" (usa --todos para ver todos):')
            for p in qs[:60]:
                w(f'   [{p.codigo}]  {p.nombre}   (stock {_dec(p.stock_actual)})')
            return

        for p in qs:
            self._rastrear(p)

    # ------------------------------------------------------------------
    def _rastrear(self, p):
        w = self.stdout.write
        SEP = '=' * 78
        w('')
        w(SEP)
        w(f'PRODUCTO   [{p.codigo}]  {p.nombre}')
        w(f'  stock actual ......... {_dec(p.stock_actual)}')
        w(f'  gestiona variantes .. {p.gestiona_variantes}')
        w(f'  costo de referencia . {p.costo}')
        w(SEP)

        # 1) LOTES -----------------------------------------------------
        w('')
        w('1) LOTES  (cada entrada de stock por compra / factura inicial / ajuste)')
        w('')
        lotes = (LoteCompra.objects
                 .filter(producto=p)
                 .select_related('item_compra', 'item_compra__compra',
                                 'item_compra__compra__creado_por', 'combinacion')
                 .order_by('fecha_compra', 'id'))
        if not lotes:
            w('   (sin lotes)')
        frac_por_lote = {
            f.lote_destino_id: f
            for f in Fraccionamiento.objects.filter(lote_destino__producto=p)
            if f.lote_destino_id
        }
        tot_activos = Decimal('0')
        for lote in lotes:
            it = lote.item_compra
            if it and it.compra_id:
                c = it.compra
                clase = ('FACTURA INICIAL' if getattr(c, 'es_carga_inicial', False)
                         else 'COMPRA')
                quien = getattr(c.creado_por, 'username', None) or '-'
                origen = (f'{clase} {c.numero}  estado={c.estado}  '
                          f'fecha={c.fecha}  cargo={quien}')
                if getattr(it, 'cantidad', None) is not None:
                    origen += f'  (la linea de compra decia {_dec(it.cantidad)})'
            elif it:
                origen = 'item de compra sin cabecera (?)'
            elif lote.id in frac_por_lote:
                f = frac_por_lote[lote.id]
                quien = getattr(f.creado_por, 'username', None) or '-'
                origen = (f'FRACCIONAMIENTO  fecha={f.fecha}  cargo={quien}  '
                          f'(desde "{f.producto_origen_nombre_snapshot}")')
            else:
                origen = 'AJUSTE MANUAL DE STOCK  (no paso por compras)'
            estado = 'activo ' if lote.activo else 'ANULADO'
            var = (f'  [{lote.combinacion.descripcion_legible()}]'
                   if lote.combinacion else '')
            w(f'   lote {lote.codigo or "(s/cod)":15}  {estado}  '
              f'inicial={_dec(lote.cantidad_inicial):>12}  '
              f'actual={_dec(lote.cantidad_actual):>12}  '
              f'costo=${lote.costo_unitario}{var}')
            w(f'        -> {origen}')
            if lote.activo:
                tot_activos += lote.cantidad_inicial
        w('')
        w(f'   Suma de cantidad_inicial de los lotes ACTIVOS = {_dec(tot_activos)}')

        # 2) MOVIMIENTOS DE STOCK ------------------------------------
        w('')
        w('2) MOVIMIENTOS DE STOCK  (ajustes a mano, mermas, fraccionamiento)')
        w('')
        movs = (MovimientoStock.objects.filter(producto=p)
                .select_related('usuario').order_by('fecha'))
        if not movs:
            w('   (ninguno: nadie lo toco a mano, no hubo merma ni fraccionamiento)')
        for m in movs:
            signo = '+' if m.es_entrada else '-'
            quien = getattr(m.usuario, 'username', None) or '-'
            w(f'   {m.fecha:%d/%m/%Y %H:%M}  {m.get_tipo_display():24}  '
              f'{signo}{_dec(m.cantidad):>10}   {_dec(m.stock_anterior)} -> {_dec(m.stock_posterior)}   '
              f'por {quien}')
            if m.motivo or m.referencia:
                w(f'        motivo="{m.motivo}"  ref="{m.referencia}"')

        # 3) LINEAS DE COMPRA (todas, aunque el lote se haya borrado) --
        w('')
        w('3) LINEAS DE COMPRA / FACTURA INICIAL con este producto (todas, todo estado)')
        w('')
        items = (ItemCompra.objects.filter(producto=p)
                 .select_related('compra').order_by('compra__fecha', 'id'))
        if not items:
            w('   (ninguna)')
        for it in items:
            c = it.compra
            clase = 'FACT.INICIAL' if getattr(c, 'es_carga_inicial', False) else 'COMPRA'
            w(f'   {clase:12}  {c.numero:14}  estado={c.estado:11}  fecha={c.fecha}  '
              f'cantidad={_dec(it.cantidad)}  costo=${it.costo_unitario}')

        # 4) salidas por venta (contexto) ---------------------------
        vendido = (p.items_venta.aggregate(s=Sum('cantidad'))['s']
                   if hasattr(p, 'items_venta') else None)
        w('')
        w(f'4) Vendido historico (todas las ventas): {_dec(vendido) if vendido else 0}')

        # 5) CONCILIACION -----------------------------------------------
        stock_lotes = (LoteCompra.objects
                       .filter(producto=p, activo=True)
                       .aggregate(s=Sum('cantidad_actual'))['s'] or Decimal('0'))
        w('')
        w(SEP)
        w(f'CONCILIACION   stock_actual del producto ... {_dec(p.stock_actual)}')
        w(f'               suma de lotes activos ....... {_dec(stock_lotes)}')
        dif = (p.stock_actual or Decimal('0')) - stock_lotes
        if abs(dif) < Decimal('0.001'):
            w('               -> COINCIDE. Todo el stock viene de lotes rastreables arriba.')
        else:
            w(f'               -> NO COINCIDE (diferencia {_dec(dif)}).')
            w('               Hay stock que NO salio de ninguna compra, factura inicial,')
            w('               ajuste ni fraccionamiento: se cargo directo en stock_actual')
            w('               (importacion de datos inicial, Django admin, o edicion en la')
            w('               base). No hay registro de quien ni cuando.')
        w(SEP)
        w('Si el numero raro aparece como lote de una FACTURA INICIAL, abri esa')
        w('factura en su historial y corregi/anula esa carga.')
        w('')
