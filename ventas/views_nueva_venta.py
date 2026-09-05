import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from productos.models import (
    Producto, CombinacionVariante, ListaDescuento, cantidad_valida_para_unidad,
    ofertas_vigentes_hoy,
)
from core.models import Cliente, DatosEmpresa, ConfiguracionArca, permite_venta_sin_stock
from compras.models import LoteCompra
from .models import (
    Venta, ItemVenta, EstadoVenta, MedioPago, TipoResolucionLote,
    EtiquetaBalanza, EstadoEtiquetaBalanza, descartar_borradores_vencidos,
    TipoComprobante,
)
from core.permisos import chequear_permiso
from core.services_arca import facturacion
from core.services_arca.wsaa import ArcaError
from caja.models import (
    TurnoCaja, CuentaCaja, TipoCaja, TipoCuenta, CuentaPredeterminadaMedio,
)


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Nueva Venta
# ══════════════════════════════════════════════════════════════════

class NuevaVentaView(LoginRequiredMixin, TemplateView):
    """
    Solo carga de productos al carrito. No se elige fecha ni medio
    de pago acá — eso se hace en el detalle/borrador, al que se
    llega con "Continuar al detalle".

    Si se accede con ?editar=<pk>, precarga los ítems de ese borrador
    existente (viene del botón "Editar carrito" en detalle_venta).
    """
    template_name = 'ventas/nueva_venta.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'crear_ventas'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_crear'] = True

        editar_pk = self.request.GET.get('editar', '').strip()
        descartar_borradores_vencidos(excluir_pk=editar_pk or None)

        ctx['listas_descuento'] = [
            {'nombre': l.nombre, 'porcentaje': str(l.porcentaje)}
            for l in ListaDescuento.objects.filter(activa=True).order_by('orden', 'nombre')
        ]

        # Ofertas vigentes HOY (fecha + día de semana): se manda el alcance
        # (pks de productos/categorías) para que el frontend decida, por
        # cada línea del carrito, si la oferta aplica — sin ir y volver
        # al servidor por cada producto agregado.
        ctx['ofertas_vigentes'] = [
            {
                'nombre':         o.nombre,
                'tipo':           o.tipo,
                'porcentaje':     str(o.porcentaje) if o.porcentaje is not None else '',
                'cantidad_lleva': o.cantidad_lleva,
                'cantidad_paga':  o.cantidad_paga,
                'monto_minimo':   str(o.monto_minimo) if o.monto_minimo is not None else '',
                'base_calculo':   o.base_calculo,
                'aplicacion':     o.aplicacion,
                'productos':      list(o.productos.values_list('pk', flat=True)),
                'categorias':     list(o.categorias.values_list('pk', flat=True)),
            }
            for o in ofertas_vigentes_hoy()
        ]

        # Verificar si hay turno abierto
        turno_actual = TurnoCaja.turno_actual()
        if not turno_actual:
            ctx['sin_turno'] = True

        # ¿Se puede vender sin stock? (Configuración → Ventas). El JS lo
        # usa para pedir confirmación antes de confirmar una venta que
        # dejaría stock negativo — ver detalle_venta.js.
        ctx['permitir_venta_sin_stock'] = permite_venta_sin_stock()

        # ── Precarga desde un borrador existente ("Editar carrito") ──
        ctx['venta_editar_pk'] = None
        ctx['items_iniciales']  = []

        if editar_pk:
            venta = (
                Venta.objects
                .filter(pk=editar_pk, estado=EstadoVenta.BORRADOR)
                .prefetch_related('items__producto', 'items__combinacion', 'items__cliente', 'items__lote_escaneado')
                .first()
            )
            if venta:
                ctx['venta_editar_pk'] = venta.pk
                # Solo importa si era una oferta MANUAL elegida a mano — si
                # era automática, se vuelve a resolver sola al recargar el
                # carrito (ver ofertaGlobalManualElegida en nueva_venta.js).
                ctx['venta_editar_oferta_global_nombre'] = venta.oferta_global_nombre
                items_iniciales = []
                for item in venta.items.all():
                    nombre = item.nombre_producto_display
                    if item.combinacion_descripcion:
                        nombre = f'{nombre} — {item.combinacion_descripcion}'
                    etiqueta = EtiquetaBalanza.objects.filter(item_venta=item).first()
                    items_iniciales.append({
                        'producto_pk':    item.producto_id,
                        'categoria_id':   item.producto.categoria_id if item.producto_id else None,
                        'combinacion_pk': item.combinacion_id,
                        'nombre':         nombre,
                        'codigo':         item.producto_codigo,
                        'tipo_escaneo':   item.tipo_escaneo,
                        'lote_pk':        item.lote_escaneado_id,
                        'lote_codigo':    item.lote_escaneado.codigo if item.lote_escaneado_id else '',
                        'etiqueta_balanza_pk':     etiqueta.pk if etiqueta else None,
                        'etiqueta_balanza_codigo': etiqueta.codigo if etiqueta else '',
                        'cliente_pk':     item.cliente_id,
                        'cliente_nombre': item.nombre_cliente_display if item.cliente_id else '',
                        'cantidad':       str(item.cantidad),
                        'precio':         str(item.precio_unitario),
                        'moneda':         item.moneda,
                        'descuento':      str(item.descuento_pct),
                        'lista_descuento_nombre': item.lista_descuento_nombre,
                        'oferta_aplicada_nombre': item.oferta_aplicada_nombre,
                        'condicion':      item.condicion_pago,
                        'referencia':     item.referencia,
                    })
                ctx['items_iniciales'] = items_iniciales

        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar productos
# ══════════════════════════════════════════════════════════════════

class BuscarProductoAjax(LoginRequiredMixin, View):
    """
    Cada resultado trae 'tipo_resultado':
      'simple'                  → producto sin variantes.
      'variante'                → una variante puntual identificada
                                   (por búsqueda de texto o por código
                                   de barras propio de esa variante).
      'producto_con_variantes'  → se identificó el producto (por texto
                                   o por un código de barras a nivel
                                   producto, compartido por sus
                                   variantes) pero no una variante
                                   puntual. Trae 'combinaciones' con
                                   todas las variantes activas para que
                                   el frontend arme el panel de colores
                                   y el usuario reparta la cantidad.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        base_qs = (
            Producto.objects
            .select_related('categoria', 'tipo')
            .prefetch_related('combinaciones')
            .filter(estado='activo')
        )

        q = request.GET.get('q', '').strip()

        if not q:
            resultados = []
            for p in base_qs.order_by('nombre')[:30]:
                resultados.extend(self._filas_texto(p))
            return JsonResponse({'results': resultados[:30]})

        # ── 1) Coincidencia EXACTA de código de barras / SKU de una VARIANTE puntual ──
        combinacion_exacta = (
            CombinacionVariante.objects
            .select_related('producto', 'producto__categoria', 'producto__tipo')
            .filter(activo=True, producto__estado='activo')
            .filter(Q(codigo_barras__iexact=q) | Q(sku_variante__iexact=q))
            .exclude(codigo_barras='')
            .first()
        )
        if combinacion_exacta:
            return JsonResponse({
                'results': [self._fila_variante(
                    combinacion_exacta.producto, combinacion_exacta, match_exacto=True
                )]
            })

        # ── 2) Coincidencia EXACTA de código de barras / SKU a nivel PRODUCTO ──
        #     Aplica tanto a productos simples como a productos con
        #     variantes cuyo código de barras es el mismo para todas
        #     (caso típico: se imprime un solo código para el producto
        #     y las variantes se distinguen por talle/color en el local).
        producto_exacto = (
            base_qs.filter(Q(codigo_barras__iexact=q) | Q(sku__iexact=q))
            .exclude(codigo_barras='')
            .first()
        )
        if producto_exacto:
            return JsonResponse({'results': [self._fila_producto_exacto(producto_exacto)]})

        # ── 3) Búsqueda parcial por texto — variantes separadas ──
        productos_match = base_qs.filter(
            Q(nombre__icontains=q) | Q(codigo__icontains=q) |
            Q(codigo_barras__icontains=q) | Q(sku__icontains=q)
        ).distinct().order_by('nombre')

        combinaciones_match = (
            CombinacionVariante.objects
            .select_related('producto', 'producto__categoria', 'producto__tipo')
            .filter(activo=True, producto__estado='activo')
            .filter(Q(codigo_barras__icontains=q) | Q(sku_variante__icontains=q))
            .order_by('producto__nombre')
        )

        resultados = []
        vistos = set()

        for p in productos_match:
            for fila in self._filas_texto(p):
                clave = (fila['pk'], fila.get('combinacion_pk'))
                if clave not in vistos:
                    vistos.add(clave)
                    resultados.append(fila)

        for c in combinaciones_match:
            fila = self._fila_variante(c.producto, c)
            clave = (fila['pk'], fila['combinacion_pk'])
            if clave not in vistos:
                vistos.add(clave)
                resultados.append(fila)

        return JsonResponse({'results': resultados[:30]})

    # ── Helpers de serialización ────────────────────────────────────
    def _filas_texto(self, p):
        """Para listado general / búsqueda por texto: cada variante activa, fila separada."""
        if p.gestiona_variantes:
            return [
                self._fila_variante(p, c)
                for c in p.combinaciones.filter(activo=True).order_by('pk')
            ]
        return [self._fila_simple(p)]

    def _base(self, p):
        return {
            'pk':                  p.pk,
            'codigo':              p.codigo,
            'unidad_medida':       p.get_unidad_medida_display(),
            'categoria_id':        p.categoria_id,
            'categoria':           p.categoria.nombre if p.categoria else '',
            'tipo':                p.tipo.nombre if p.tipo else '',
            'marca':               p.marca,
            'modelo':              p.modelo,
            'gestiona_variantes':  p.gestiona_variantes,
            'gestiona_stock':      p.gestiona_stock,
            'es_paquete':          p.es_paquete,
            'precio_venta':        float(p.precio_venta) if p.precio_venta is not None else None,
            'moneda':              'ARS',
            # Origen del stock: por defecto, se resuelve el lote más
            # viejo con stock (FIFO) recién al confirmar (ver
            # BuscarLoteVentaAjax para el caso de escanear un código
            # de lote puntual).
            'tipo_escaneo':        TipoResolucionLote.NORMAL,
            'lote_pk':             None,
        }

    def _fila_simple(self, p, match_exacto=False):
        fila = self._base(p)
        stock = p.stock_disponible_paquete if p.es_paquete else p.stock_actual
        fila.update({
            'tipo_resultado': 'simple',
            'combinacion_pk': None,
            'nombre':         p.nombre,
            'variante_desc':  '',
            'stock_actual':   float(stock),
            'match_exacto':   match_exacto,
        })
        return fila

    def _fila_variante(self, p, c, match_exacto=False):
        fila = self._base(p)
        fila.update({
            'tipo_resultado': 'variante',
            'combinacion_pk': c.pk,
            'nombre':         f'{p.nombre} — {c.descripcion_legible()}',
            'variante_desc':  c.descripcion_legible(),
            'stock_actual':   float(c.stock_actual),
            'match_exacto':   match_exacto,
        })
        return fila

    def _fila_producto_exacto(self, p):
        """Match exacto de código a nivel producto. Si maneja variantes,
        no sabemos cuál se vendió: se devuelve el producto con todas sus
        variantes activas para que el frontend abra el panel de colores."""
        if not p.gestiona_variantes:
            return self._fila_simple(p, match_exacto=True)

        fila = self._base(p)
        fila.update({
            'tipo_resultado': 'producto_con_variantes',
            'combinacion_pk': None,
            'nombre':         p.nombre,
            'variante_desc':  '',
            'stock_actual':   float(p.stock_actual),
            'match_exacto':   True,
            'combinaciones': [
                {
                    'combinacion_pk': c.pk,
                    'nombre':         c.descripcion_legible(),
                    'stock_actual':   float(c.stock_actual),
                }
                for c in p.combinaciones.filter(activo=True).order_by('pk')
            ],
        })
        return fila


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar lote por código puntual (LT-AAAA-XXXXX)
#
#  El frontend detecta si lo escaneado tiene forma de código de lote
#  (el que genera/muestra el módulo de inventario) y llama acá en vez
#  de a BuscarProductoAjax. El ítem que se arme con este resultado
#  queda con tipo_escaneo=lote_especifico y el lote ya fijado: al
#  confirmar la venta, el stock sale específicamente de ESE lote (con
#  su costo, fecha de compra y vencimiento), no del más reciente.
# ══════════════════════════════════════════════════════════════════

class BuscarLoteVentaAjax(LoginRequiredMixin, View):
    """GET ?codigo=LT-2025-00001"""

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        codigo = request.GET.get('codigo', '').strip()
        if not codigo:
            return JsonResponse({'error': 'Falta el código de lote.'}, status=400)

        lote = (
            LoteCompra.objects
            .select_related('producto', 'producto__categoria', 'producto__tipo', 'combinacion')
            .filter(codigo__iexact=codigo)
            .first()
        )
        if not lote:
            return JsonResponse({'error': f'No se encontró ningún lote con el código "{codigo}".'}, status=404)
        if not lote.activo:
            return JsonResponse({'error': f'El lote {lote.codigo} está anulado y no se puede usar.'}, status=400)
        if lote.cantidad_actual <= 0:
            return JsonResponse({'error': f'El lote {lote.codigo} no tiene stock disponible.'}, status=400)
        if lote.producto is None:
            return JsonResponse({'error': f'El producto del lote {lote.codigo} ya no existe.'}, status=400)

        p = lote.producto
        c = lote.combinacion

        return JsonResponse({'results': [{
            'pk':                       p.pk,
            'codigo':                   p.codigo,
            'categoria_id':             p.categoria_id,
            'nombre':                   f'{p.nombre} — {c.descripcion_legible()}' if c else p.nombre,
            'tipo_resultado':           'variante' if c else 'simple',
            'combinacion_pk':           c.pk if c else None,
            'variante_desc':            c.descripcion_legible() if c else '',
            'gestiona_variantes':       p.gestiona_variantes,
            'gestiona_stock':           p.gestiona_stock,
            'stock_actual':             float(c.stock_actual if c else p.stock_actual),
            'precio_venta':             float(p.precio_venta) if p.precio_venta is not None else None,
            'moneda':                   'ARS',
            'tipo_escaneo':             TipoResolucionLote.LOTE_ESPECIFICO,
            'lote_pk':                  lote.pk,
            'lote_codigo':              lote.codigo,
            'lote_cantidad_disponible': lote.cantidad_actual,
            'lote_costo_unitario':      str(lote.costo_unitario),
            'lote_fecha_vencimiento':   lote.fecha_vencimiento.isoformat() if lote.fecha_vencimiento else None,
            'lote_fecha_compra':        lote.fecha_compra.isoformat(),
            'match_exacto':             True,
        }]})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar clientes
# ══════════════════════════════════════════════════════════════════

class BuscarClienteAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q  = request.GET.get('q', '').strip()
        qs = Cliente.objects.filter(estado='activo').order_by('nombre')
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) | Q(apellido__icontains=q) |
                Q(dni__icontains=q) | Q(cuil__icontains=q) |
                Q(razon_social__icontains=q) | Q(nombre_comercial__icontains=q) |
                Q(cuit__icontains=q)
            )
        data = [
            {
                'pk':     c.pk,
                'nombre': c.get_nombre_display(),
                'codigo': c.codigo or '',
                'doc':    c.dni or c.cuit or c.cuil or '',
                # Scoring de riesgo de pago — el frontend lo usa para
                # avisar/bloquear cuotas y cheque (ver detalle_venta.js).
                'scoring':        c.scoring,
                'scoring_banda':  c.scoring_banda,
                'scoring_banda_label': c.scoring_banda_label,
                'scoring_sin_historial': c.scoring_sin_historial,
                'scoring_alerta': c.scoring_alerta,
            }
            for c in qs[:20]
        ]
        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Guardar Borrador
# ══════════════════════════════════════════════════════════════════

class GuardarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "items": [ { producto_pk, cliente_pk, combinacion_pk, cantidad,
                     precio_unitario, moneda, descuento_pct,
                     condicion_pago, referencia } ]
    }
    Crea la venta en estado BORRADOR con fecha de hoy y medio de
    pago por defecto (efectivo) — ambos se terminan de definir en
    el detalle/borrador antes de confirmar.
    Respuesta: { ok, pk, numero }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        
        # Verificar si hay turno abierto
        if not TurnoCaja.turno_actual():
            return JsonResponse({'error': 'No hay un turno de caja abierto. Abrí un turno antes de vender.'}, status=400)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        items_raw = body.get('items', [])
        if not items_raw:
            return JsonResponse({'error': 'El carrito está vacío.'}, status=400)

        venta = Venta(
            fecha      = body.get('fecha') or timezone.localtime().date().isoformat(),
            notas      = body.get('notas', ''),
            medio_pago = MedioPago.EFECTIVO,
            estado     = EstadoVenta.BORRADOR,
            creado_por = request.user,
        )
        venta.save()

        errores = []
        for idx, raw in enumerate(items_raw, start=1):
            producto_pk = raw.get('producto_pk')
            if not producto_pk:
                errores.append(f'Ítem {idx}: falta producto.')
                continue

            try:
                producto = Producto.objects.get(pk=producto_pk)
            except Producto.DoesNotExist:
                errores.append(f'Ítem {idx}: producto no encontrado.')
                continue

            try:
                cantidad        = Decimal(str(raw.get('cantidad', 0)))
                precio_unitario = Decimal(str(raw.get('precio_unitario', 0)))
                descuento_pct   = Decimal(str(raw.get('descuento_pct', 0)))
            except Exception:
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            # ── Etiqueta de balanza: cantidad y precio ya vienen fijados
            #    en la etiqueta (se pesó una sola vez) — se ignora lo que
            #    mande el cliente para esos dos campos y se usa siempre
            #    el valor real guardado en la etiqueta, por las dudas.
            etiqueta_balanza = None
            etiqueta_pk = raw.get('etiqueta_balanza_pk')
            if etiqueta_pk:
                etiqueta_balanza = EtiquetaBalanza.objects.filter(pk=etiqueta_pk).first()
                if not etiqueta_balanza:
                    errores.append(f'Ítem {idx}: la etiqueta de balanza ya no existe.')
                    continue
                if etiqueta_balanza.estado != EstadoEtiquetaBalanza.DISPONIBLE:
                    errores.append(
                        f'Ítem {idx}: la etiqueta {etiqueta_balanza.codigo} ya no está disponible '
                        f'({etiqueta_balanza.get_estado_display()}).'
                    )
                    continue
                if etiqueta_balanza.producto_id != producto.pk:
                    errores.append(f'Ítem {idx}: la etiqueta no corresponde a este producto.')
                    continue
                cantidad        = etiqueta_balanza.cantidad
                precio_unitario = etiqueta_balanza.precio_unitario

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if not cantidad_valida_para_unidad(producto.unidad_medida, cantidad):
                errores.append(
                    f'Ítem {idx}: "{producto.nombre}" se vende por {producto.get_unidad_medida_display()} '
                    f'— la cantidad tiene que ser un número entero.'
                )
                continue
            if precio_unitario < 0:
                errores.append(f'Ítem {idx}: el precio no puede ser negativo.')
                continue

            cliente    = None
            cliente_pk = raw.get('cliente_pk')
            if cliente_pk:
                cliente = Cliente.objects.filter(pk=cliente_pk).first()

            combinacion    = None
            combinacion_pk = raw.get('combinacion_pk')
            if combinacion_pk:
                combinacion = CombinacionVariante.objects.filter(pk=combinacion_pk, producto=producto).first()
                if not combinacion:
                    errores.append(f'Ítem {idx}: la combinación no pertenece a este producto.')
                    continue

            # ── Origen del stock: normal (se resuelve al confirmar) o
            #    lote específico (ya viene fijado desde el escaneo) ──
            tipo_escaneo   = raw.get('tipo_escaneo', TipoResolucionLote.NORMAL)
            lote_escaneado = None
            if tipo_escaneo == TipoResolucionLote.LOTE_ESPECIFICO:
                lote_pk = raw.get('lote_pk')
                if not lote_pk:
                    errores.append(f'Ítem {idx}: falta el lote escaneado.')
                    continue
                lote_escaneado = LoteCompra.objects.filter(pk=lote_pk).first()
                if not lote_escaneado:
                    errores.append(f'Ítem {idx}: el lote escaneado ya no existe.')
                    continue

            item = ItemVenta.objects.create(
                venta           = venta,
                producto        = producto,
                cliente         = cliente,
                combinacion     = combinacion,
                tipo_escaneo    = tipo_escaneo,
                lote_escaneado  = lote_escaneado,
                cantidad        = cantidad,
                precio_unitario = precio_unitario,
                moneda          = raw.get('moneda', 'ARS'),
                descuento_pct   = descuento_pct,
                lista_descuento_nombre = raw.get('lista_descuento_nombre', ''),
                oferta_aplicada_nombre = raw.get('oferta_aplicada_nombre', ''),
                condicion_pago  = raw.get('condicion_pago', 'contado'),
                referencia      = raw.get('referencia', ''),
                notas           = raw.get('notas', ''),
            )
            if etiqueta_balanza:
                etiqueta_balanza.item_venta = item
                etiqueta_balanza.save(update_fields=['item_venta'])

        if errores:
            venta.delete()
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # Descuento global (oferta por monto mínimo de compra) — se
        # calcula en el carrito sobre el total de todos los ítems, no
        # por línea (ver Oferta tipo=umbral en productos/models.py).
        try:
            descuento_global_pct = Decimal(str(body.get('descuento_global_pct', 0) or 0))
        except Exception:
            descuento_global_pct = Decimal('0')
        venta.aplicar_descuento_global(
            descuento_global_pct, body.get('oferta_global_nombre', ''),
        )

        return JsonResponse({'ok': True, 'pk': venta.pk, 'numero': venta.numero})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Actualizar Borrador  (usado cuando se edita el carrito de
#  un borrador existente desde Nueva Venta con ?editar=<pk> — mismo
#  patrón que compras.views.ActualizarBorradorAjax)
# ══════════════════════════════════════════════════════════════════

class ActualizarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "venta_pk": 42,
        "fecha":    "2025-01-15",
        "notas":    "...",
        "items":    [ ... mismo formato que GuardarBorradorAjax ... ],
        "descuento_global_pct": 10, "oferta_global_nombre": "..."
    }

    Reemplaza TODOS los ítems del borrador por los que llegan en el body,
    en el mismo lugar (mismo pk/número) — a diferencia de GuardarBorradorAjax,
    que siempre crea una venta nueva. El borrador sigue en BORRADOR, no
    toca stock ni caja todavía (eso recién pasa al confirmar).

    Respuesta: { ok: true, pk, numero }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta_pk = body.get('venta_pk')
        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)

        venta = get_object_or_404(Venta, pk=venta_pk)

        if venta.estado != EstadoVenta.BORRADOR:
            return JsonResponse(
                {'error': f'La venta ya está en estado "{venta.get_estado_display()}". Solo se pueden editar borradores desde acá.'},
                status=400
            )

        items_raw = body.get('items', [])
        if not items_raw:
            return JsonResponse({'error': 'El carrito no puede quedar vacío.'}, status=400)

        errores = []
        items_para_crear = []

        for idx, raw in enumerate(items_raw, start=1):
            producto_pk = raw.get('producto_pk')
            if not producto_pk:
                errores.append(f'Ítem {idx}: falta producto.')
                continue

            try:
                producto = Producto.objects.get(pk=producto_pk)
            except Producto.DoesNotExist:
                errores.append(f'Ítem {idx}: producto no encontrado.')
                continue

            try:
                cantidad        = Decimal(str(raw.get('cantidad', 0)))
                precio_unitario = Decimal(str(raw.get('precio_unitario', 0)))
                descuento_pct   = Decimal(str(raw.get('descuento_pct', 0)))
            except Exception:
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            # Mismo criterio que GuardarBorradorAjax: la etiqueta de
            # balanza manda su propia cantidad/precio reales.
            etiqueta_balanza = None
            etiqueta_pk = raw.get('etiqueta_balanza_pk')
            if etiqueta_pk:
                etiqueta_balanza = EtiquetaBalanza.objects.filter(pk=etiqueta_pk).first()
                if not etiqueta_balanza:
                    errores.append(f'Ítem {idx}: la etiqueta de balanza ya no existe.')
                    continue
                if etiqueta_balanza.estado != EstadoEtiquetaBalanza.DISPONIBLE:
                    errores.append(
                        f'Ítem {idx}: la etiqueta {etiqueta_balanza.codigo} ya no está disponible '
                        f'({etiqueta_balanza.get_estado_display()}).'
                    )
                    continue
                if etiqueta_balanza.producto_id != producto.pk:
                    errores.append(f'Ítem {idx}: la etiqueta no corresponde a este producto.')
                    continue
                cantidad        = etiqueta_balanza.cantidad
                precio_unitario = etiqueta_balanza.precio_unitario

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if not cantidad_valida_para_unidad(producto.unidad_medida, cantidad):
                errores.append(
                    f'Ítem {idx}: "{producto.nombre}" se vende por {producto.get_unidad_medida_display()} '
                    f'— la cantidad tiene que ser un número entero.'
                )
                continue
            if precio_unitario < 0:
                errores.append(f'Ítem {idx}: el precio no puede ser negativo.')
                continue

            cliente    = None
            cliente_pk = raw.get('cliente_pk')
            if cliente_pk:
                cliente = Cliente.objects.filter(pk=cliente_pk).first()

            combinacion    = None
            combinacion_pk = raw.get('combinacion_pk')
            if combinacion_pk:
                combinacion = CombinacionVariante.objects.filter(pk=combinacion_pk, producto=producto).first()
                if not combinacion:
                    errores.append(f'Ítem {idx}: la combinación no pertenece a este producto.')
                    continue

            tipo_escaneo   = raw.get('tipo_escaneo', TipoResolucionLote.NORMAL)
            lote_escaneado = None
            if tipo_escaneo == TipoResolucionLote.LOTE_ESPECIFICO:
                lote_pk = raw.get('lote_pk')
                if not lote_pk:
                    errores.append(f'Ítem {idx}: falta el lote escaneado.')
                    continue
                lote_escaneado = LoteCompra.objects.filter(pk=lote_pk).first()
                if not lote_escaneado:
                    errores.append(f'Ítem {idx}: el lote escaneado ya no existe.')
                    continue

            items_para_crear.append(dict(
                producto=producto, cliente=cliente, combinacion=combinacion,
                tipo_escaneo=tipo_escaneo, lote_escaneado=lote_escaneado,
                cantidad=cantidad, precio_unitario=precio_unitario,
                moneda=raw.get('moneda', 'ARS'), descuento_pct=descuento_pct,
                lista_descuento_nombre=raw.get('lista_descuento_nombre', ''),
                oferta_aplicada_nombre=raw.get('oferta_aplicada_nombre', ''),
                condicion_pago=raw.get('condicion_pago', 'contado'),
                referencia=raw.get('referencia', ''), notas=raw.get('notas', ''),
                etiqueta_balanza=etiqueta_balanza,
            ))

        if errores:
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # — Recién acá se toca la base: reemplazo total de ítems —
        venta.items.all().delete()
        for datos in items_para_crear:
            etiqueta_balanza = datos.pop('etiqueta_balanza')
            item = ItemVenta.objects.create(venta=venta, **datos)
            if etiqueta_balanza:
                etiqueta_balanza.item_venta = item
                etiqueta_balanza.save(update_fields=['item_venta'])

        venta.fecha = body.get('fecha') or venta.fecha
        venta.notas = body.get('notas', venta.notas)
        venta.save(update_fields=['fecha', 'notas'])

        try:
            descuento_global_pct = Decimal(str(body.get('descuento_global_pct', 0) or 0))
        except Exception:
            descuento_global_pct = Decimal('0')
        venta.aplicar_descuento_global(
            descuento_global_pct, body.get('oferta_global_nombre', ''),
        )
        venta.refresh_from_db(fields=['total'])

        # `total` lo usa el panel flotante de cobro para re-conciliar los
        # pagos ya cargados cuando el carrito cambia con el panel abierto
        # (ver panel_cobro.js / detalleVentaSetTotal).
        return JsonResponse({
            'ok': True, 'pk': venta.pk, 'numero': venta.numero,
            'total': str(venta.total),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Confirmar Venta
# ══════════════════════════════════════════════════════════════════

class ConfirmarVentaAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "venta_pk":   5,
        "fecha":      "2025-01-15",
        "notas":      "...",
        "medio_pago": "efectivo",          // medio principal (el primero de "pagos")
        "pagos": [                          // opcional — pago dividido
            {"medio": "efectivo",      "monto": 3000},
            {"medio": "transferencia", "monto": 999.97}
        ]
    }

    Si se manda "pagos", la suma de montos debe igualar el total de
    la venta (con tolerancia de 1 centavo). Si no se manda "pagos",
    se asume pago completo con "medio_pago" (compatibilidad hacia atrás).

    Confirma el borrador: resta stock, guarda confirmado_por,
    medio_pago principal y las líneas de PagoVenta.

    Si "facturar" viene en true, después de confirmar (fuera de la
    transacción de arriba — un CAE no se puede deshacer, así que el pedido a
    ARCA nunca puede quedar adentro de un bloque atómico que podría hacer
    rollback) se intenta pedir el CAE. Si ARCA falla, la venta queda
    confirmada igual: se informa el error en "factura_error" y se puede
    reintentar después desde VentaFacturarAjax.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta_pk   = body.get('venta_pk')
        fecha      = body.get('fecha', '').strip()
        medio_pago = body.get('medio_pago', '').strip()
        pagos_raw  = body.get('pagos')
        cliente_pk = body.get('cliente_pk') if 'cliente_pk' in body else False

        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)
        if not fecha:
            return JsonResponse({'error': 'La fecha es requerida.'}, status=400)
        if not medio_pago:
            return JsonResponse({'error': 'El medio de pago es requerido.'}, status=400)

        valores_validos = [v for v, _ in MedioPago.choices]
        if medio_pago not in valores_validos:
            return JsonResponse({'error': f'Medio de pago inválido: {medio_pago}'}, status=400)

        # select_for_update(): bloquea esta venta hasta que termine la
        # transacción. Si llega un segundo clic/request para el mismo
        # venta_pk mientras el primero todavía está confirmando, se
        # queda esperando acá y cuando lo destraba ya la va a encontrar
        # en estado CONFIRMADA (no BORRADOR) — evita descontar stock
        # y generar pagos/movimientos de caja duplicados.
        #
        # OJO: este "with" es a propósito más chico que todo el método —
        # termina (commit) antes de intentar facturar en ARCA más abajo. Un
        # CAE no se puede deshacer, así que ese pedido nunca puede quedar
        # adentro de una transacción que todavía podría hacer rollback.
        with transaction.atomic():
            venta = get_object_or_404(Venta.objects.select_for_update(), pk=venta_pk)

            if venta.estado != EstadoVenta.BORRADOR:
                return JsonResponse(
                    {'error': f'La venta ya está en estado "{venta.get_estado_display()}".'},
                    status=400
                )

            # ── Validar pagos divididos, si se mandaron ──
            # La venta siempre está en pesos: si una línea se cobra en una
            # cuenta que no es en pesos (ej: transferencia en USD), se
            # convierte con la cotización que mandó el cajero para poder
            # validar que la suma cubre venta.total. El efectivo físico
            # siempre es en pesos (ver PagoVenta).
            pagos_normalizados = None
            if pagos_raw:
                pagos_normalizados = []
                suma_ars = Decimal('0')          # solo la porción que cubre venta.total
                for p in pagos_raw:
                    medio_p = p.get('medio', '').strip()
                    if medio_p not in valores_validos:
                        return JsonResponse({'error': f'Medio de pago inválido en pagos: {medio_p}'}, status=400)
                    try:
                        monto_p = Decimal(str(p.get('monto', 0)))
                    except Exception:
                        return JsonResponse({'error': 'Monto de pago inválido.'}, status=400)

                    # Redondeo a favor: lo que el cliente pagó por encima del
                    # precio de los productos. Viene EXPLÍCITO desde el panel
                    # (control "+ Redondeo a favor") en su propia línea con
                    # monto 0 — no se infiere. Siempre en pesos.
                    try:
                        redondeo_p = Decimal(str(p.get('redondeo', 0) or 0))
                    except Exception:
                        return JsonResponse({'error': 'Monto de redondeo inválido.'}, status=400)
                    if redondeo_p < 0:
                        return JsonResponse({'error': 'El redondeo a favor no puede ser negativo.'}, status=400)

                    # Se descarta la línea solo si no aporta nada (ni a la
                    # venta ni como redondeo).
                    if monto_p <= 0 and redondeo_p <= 0:
                        continue

                    cotizacion_p = None
                    monto_ars = monto_p
                    if medio_p != MedioPago.EFECTIVO:
                        cuenta = CuentaCaja.objects.filter(pk=p.get('cuenta_pk'), caja=TipoCaja.GRANDE, activa=True).first()
                        if cuenta and cuenta.moneda != 'ARS':
                            if redondeo_p > 0:
                                return JsonResponse({
                                    'error': 'El redondeo a favor solo se puede registrar en pesos.'
                                }, status=400)
                            try:
                                cotizacion_p = Decimal(str(p.get('cotizacion', 0)))
                            except Exception:
                                cotizacion_p = None
                            if not cotizacion_p or cotizacion_p <= 0:
                                return JsonResponse({
                                    'error': f'Ingresá la cotización usada para el pago en {cuenta.get_moneda_display()}.'
                                }, status=400)
                            monto_ars = (monto_p * cotizacion_p).quantize(Decimal('0.01'))

                    suma_ars += monto_ars
                    pagos_normalizados.append({
                        'medio': medio_p,
                        'monto': monto_p,
                        # Excedente explícito de esta línea (en pesos). Venta.confirmar
                        # lo guarda en PagoVenta.redondeo_monto y lo fuerza a 0 para
                        # cuotas/cheque.
                        'redondeo': redondeo_p,
                        'cuenta_pk': p.get('cuenta_pk'),
                        'cotizacion': cotizacion_p,
                        # Solo se usan si medio_p == 'cuotas' (ver Venta.confirmar) —
                        # se pasan tal cual, la validación real vive ahí.
                        'modo_cuotas': p.get('modo_cuotas'),
                        'cuotas': p.get('cuotas'),
                        'interes_pct': p.get('interes_pct'),
                        'fecha_inicio_cobro': p.get('fecha_inicio_cobro'),
                        # N° de pagaré firmado por esta deuda puntual (opcional) —
                        # ver CuentaPorCobrar.numero_pagare.
                        'numero_pagare': p.get('numero_pagare'),
                        # Solo se usa si medio_p == 'cheque' — lista de cheques
                        # cargados en el modal, se valida y crea en Venta.confirmar().
                        'cheques': p.get('cheques'),
                        # Recargo por medio de pago (débito/crédito/QR/transferencia) —
                        # se pasa tal cual, `monto_p`/`suma_ars` de arriba NO lo incluyen
                        # (siguen siendo la porción que cubre venta.total); el recargo se
                        # calcula y snapshotea aparte en Venta.confirmar().
                        'recargo_pct': p.get('recargo_pct'),
                        'cantidad_pagos': p.get('cantidad_pagos'),
                        'nombre_plan': p.get('nombre_plan'),
                        # Con qué tarjeta/billetera pagó el cliente (define
                        # el recargo) — dato aparte de 'cuenta_pk' (a cuál
                        # de MIS cuentas entra la plata). Ver Venta.confirmar.
                        'tarjeta_pk': p.get('tarjeta_pk'),
                    })

                if not pagos_normalizados:
                    return JsonResponse({'error': 'Agregá al menos un medio de pago con monto.'}, status=400)

                # El total recién se recalcula en confirmar(); usamos el total actual del borrador
                venta.calcular_total()
                venta.refresh_from_db(fields=['total'])

                # La porción que cubre la venta tiene que dar EXACTO
                # venta.total. Cobrar de MENOS: bloqueado (un cero de menos
                # sin mirar es grave). Cobrar de MÁS: no se tipea un importe
                # mayor acá — se carga con el control "+ Redondeo a favor".
                if suma_ars < venta.total - Decimal('0.01'):
                    falta = (venta.total - suma_ars).quantize(Decimal('0.01'))
                    return JsonResponse({
                        'error': f'Los pagos cubren ${suma_ars} y el total es ${venta.total} — falta cubrir ${falta}.'
                    }, status=400)
                if suma_ars > venta.total + Decimal('0.01'):
                    sobra = (suma_ars - venta.total).quantize(Decimal('0.01'))
                    return JsonResponse({
                        'error': (
                            f'Los pagos superan el total en ${sobra}. Si el cliente pagó de más '
                            f'para redondear, cargá ese excedente como "redondeo a favor".'
                        )
                    }, status=400)

            # El cliente se puede corregir/cargar acá también (no solo desde
            # el carrito) — se aplica a TODOS los ítems, que es de donde sale
            # `Venta.cliente_unico` (ver esa property). `cliente_pk=False`
            # (sentinel, no viene la clave) significa "no tocar"; `None` o ''
            # significa "vaciar" (queda Consumidor Final).
            if cliente_pk is not False:
                cliente = Cliente.objects.filter(pk=cliente_pk).first() if cliente_pk else None
                # cliente_nombre es un snapshot (ver ItemVenta.save()) que
                # normalmente se completa solo al guardar un ítem nuevo —
                # como acá se pisa con un `.update()` masivo (no pasa por
                # save()), hay que resolverlo a mano para que no quede
                # desincronizado del cliente real recién asignado.
                venta.items.update(
                    cliente=cliente,
                    cliente_nombre=cliente.get_nombre_display() if cliente else '',
                )

            try:
                venta.editar_cabecera(fecha=fecha, notas=body.get('notas', ''))
            except Exception as e:
                import traceback
                return JsonResponse({'error': f'editar_cabecera: {e}', 'detalle': traceback.format_exc()}, status=400)

            try:
                avisos = venta.confirmar(confirmado_por=request.user, medio_pago=medio_pago, pagos=pagos_normalizados)
            except Exception as e:
                import traceback
                return JsonResponse({'error': f'confirmar: {e}', 'detalle': traceback.format_exc()}, status=400)

        # ── Facturación electrónica (opcional) ──
        # Fuera del "with" de arriba a propósito: la venta ya está
        # confirmada y comprometida pase lo que pase acá abajo.
        factura_error = None
        comprobante = None
        if body.get('facturar'):
            # El cliente a facturar es el cliente único de la venta (ya
            # elegido una sola vez en el carrito) — no se vuelve a pedir
            # acá. cliente_pk sigue soportado por si algún caller externo
            # lo manda explícito, pero el frontend ya no lo hace.
            cliente_pk = body.get('cliente_pk')
            if cliente_pk:
                cliente = Cliente.objects.filter(pk=cliente_pk).first()
            else:
                cliente = venta.cliente_unico
            try:
                comprobante = facturacion.facturar_venta(
                    venta,
                    cliente=cliente,
                    condicion_iva_receptor_id=body.get('condicion_iva_receptor_id'),
                )
            except ArcaError as exc:
                factura_error = str(exc)

        respuesta = {
            'ok':     True,
            'pk':     venta.pk,
            'numero': venta.numero,
            'total':  str(venta.total),
            'avisos': avisos or [],
        }
        if comprobante:
            respuesta['cae'] = comprobante.cae
            respuesta['numero_comprobante'] = comprobante.numero
        if factura_error:
            respuesta['factura_error'] = factura_error
        return JsonResponse(respuesta)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Facturar (reintento manual, para ventas ya confirmadas
#  que no tienen comprobante ARCA — por ejemplo porque falló al
#  confirmar)
# ══════════════════════════════════════════════════════════════════

class VentaFacturarAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        venta = get_object_or_404(Venta, pk=pk)
        if venta.estado != EstadoVenta.CONFIRMADA:
            return JsonResponse({'error': 'Solo se puede facturar una venta confirmada.'}, status=400)

        try:
            body = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            body = {}

        # Sin cliente_pk explícito en el body (el caso común: el botón
        # "Facturar ahora" manda body vacío) se usa el cliente único de
        # la venta — antes acá quedaba en None y el reintento terminaba
        # facturando siempre a Consumidor Final aunque la venta tuviera
        # un cliente real con su condición de IVA cargada.
        cliente_pk = body.get('cliente_pk')
        if cliente_pk:
            cliente = Cliente.objects.filter(pk=cliente_pk).first()
        else:
            cliente = venta.cliente_unico

        try:
            comprobante = facturacion.facturar_venta(
                venta,
                cliente=cliente,
                condicion_iva_receptor_id=body.get('condicion_iva_receptor_id'),
            )
        except ArcaError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

        return JsonResponse({
            'ok': True,
            'cae': comprobante.cae,
            'numero_comprobante': comprobante.numero,
            'cae_vencimiento': comprobante.cae_vencimiento.isoformat(),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar Borrador
# ══════════════════════════════════════════════════════════════════

class EliminarBorradorAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        venta_pk = body.get('venta_pk')
        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)

        venta = get_object_or_404(Venta, pk=venta_pk)

        if venta.estado != EstadoVenta.BORRADOR:
            return JsonResponse(
                {'error': 'Solo se pueden eliminar borradores desde este endpoint.'},
                status=400
            )

        # Si era una venta real reactivada para editar, descartar_edicion()
        # la revierte a ANULADA en vez de borrarla — ver su docstring.
        borrado = venta.descartar_edicion()
        return JsonResponse({'ok': True, 'borrado': borrado})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Documentos de venta
# ══════════════════════════════════════════════════════════════════

import os
from .models import VentaDocumento
from django.shortcuts import render as _render


class VentaDocumentoSubirAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        venta_pk = request.POST.get('venta_pk')
        if not venta_pk:
            return JsonResponse({'error': 'venta_pk requerido.'}, status=400)

        archivo = request.FILES.get('archivo')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

        if archivo.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 10 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf'}:
            return JsonResponse(
                {'error': 'Tipo no permitido. Usá JPG, PNG, WEBP, GIF o PDF.'},
                status=400
            )

        venta = get_object_or_404(Venta, pk=venta_pk)

        doc = VentaDocumento(
            venta       = venta,
            archivo     = archivo,
            tipo        = request.POST.get('tipo', 'otro'),
            descripcion = request.POST.get('descripcion', ''),
            subido_por  = request.user,
        )
        doc.save()

        return JsonResponse({
            'ok': True,
            'documento': {
                'pk':          doc.pk,
                'nombre':      doc.nombre_archivo,
                'url':         doc.archivo.url,
                'tipo':        doc.tipo,
                'tipo_label':  doc.get_tipo_display(),
                'descripcion': doc.descripcion,
                'es_imagen':   doc.es_imagen,
                'es_pdf':      doc.es_pdf,
                'subido_el':   doc.subido_el.strftime('%d/%m/%Y %H:%M'),
            },
        })


class VentaDocumentoEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        doc = get_object_or_404(VentaDocumento, pk=pk)

        if doc.archivo and os.path.isfile(doc.archivo.path):
            os.remove(doc.archivo.path)

        doc.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  VISTA — Detalle de venta
# ══════════════════════════════════════════════════════════════════

def _venta_detalle_qs():
    return Venta.objects.prefetch_related(
        'items__producto', 'items__cliente', 'items__combinacion',
        'documentos', 'pagos__cuenta', 'pagos__tarjeta',
    )


def construir_contexto_detalle(request, venta):
    """
    Contexto completo del detalle de venta. Lo comparten:
      - DetalleVentaView          → página completa (permalink del Historial)
      - CobroFragmentoAjax        → fragmento HTML para el panel flotante de
                                 cobro que vive sobre /ventas/nueva/
    """
    from caja.models import asegurar_cuentas_efectivo
    asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE)

    moneda_venta = venta.items.values_list('moneda', flat=True).first() or 'ARS'
    # Efectivo se excluye acá: el pago en efectivo resuelve su cuenta solo
    # (ver PagoVenta), nunca se elige a mano — no tiene sentido ofrecerlo
    # como destino de un cobro con tarjeta/QR/transferencia.
    cuentas = (
        CuentaCaja.objects
        .filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False)
        .exclude(tipo=TipoCuenta.EFECTIVO)
        .order_by('orden', 'nombre')
    )
    cuentas_json = json.dumps([
        {
            'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'titular': c.titular,
            # Qué medios acepta ESTA CUENTA REAL (a dónde entra la
            # plata) — ver caja.models.CuentaCaja.acepta_*. No confundir
            # con TarjetaPago.acepta_* de más abajo (con qué le pagó el
            # cliente): son dos ejes independientes, ver
            # ventas.models.TarjetaPago.__doc__.
            'acepta_debito': c.acepta_debito,
            'acepta_credito': c.acepta_credito,
            'acepta_qr': c.acepta_qr,
            'acepta_transferencia': c.acepta_transferencia,
        }
        for c in cuentas
    ])

    # Tarjetas/billeteras del CLIENTE (Visa, Mercado Pago, Personal
    # Pay...) — definen el recargo, independiente de a cuál `cuenta`
    # real entra la plata (ver ventas.models.TarjetaPago.__doc__).
    from .models import RecargoMedioPago, TarjetaPago
    tarjetas = TarjetaPago.objects.filter(activa=True).order_by('orden', 'nombre')
    tarjetas_json = json.dumps([
        {
            'pk': t.pk, 'nombre': t.nombre,
            'acepta_debito': t.acepta_debito,
            'acepta_credito': t.acepta_credito,
            'acepta_qr': t.acepta_qr,
            'acepta_transferencia': t.acepta_transferencia,
        }
        for t in tarjetas
    ])

    # Recargos configurados (ver ventas.models.RecargoMedioPago) para las
    # tarjetas elegibles de esta venta — el JS arma los selectores de
    # plan/recargo por línea de pago a partir de esta lista plana.
    recargos_json = json.dumps([
        {
            'tarjeta_pk': r.tarjeta_id,
            'medio': r.medio,
            'cantidad_pagos': r.cantidad_pagos,
            'nombre_plan': r.nombre_plan,
            'etiqueta_plan': r.etiqueta_plan,
            'recargo_pct': str(r.recargo_pct),
        }
        for r in RecargoMedioPago.objects.filter(tarjeta__in=tarjetas, activo=True)
    ])

    # El cliente a facturar es el mismo cliente único de la venta (ya
    # resuelto una sola vez desde el carrito, ver Venta.cliente_unico) —
    # no se vuelve a preguntar acá. Si la empresa ya tiene ARCA
    # habilitado, se previsualiza qué tipo de comprobante saldría con
    # los datos actuales (sin llamar a ARCA), para mostrarlo antes de
    # que el vendedor confirme.
    cliente_unico = venta.cliente_unico
    config_arca = ConfiguracionArca.get_solo()
    tipo_previsto = None
    if config_arca.habilitado and config_arca.tiene_certificado():
        tipo_previsto = facturacion.tipo_comprobante_previsto(cliente_unico)

    pagos_lista = list(venta.pagos.all())
    total_recargo = sum((p.recargo_monto for p in pagos_lista), Decimal('0'))
    # Redondeo a favor: lo que el/los cliente/s pagaron por encima del
    # precio de los productos. A ARCA/factura le llega venta.total; nunca
    # aparece en el ticket.
    total_redondeo = sum((p.redondeo_monto for p in pagos_lista), Decimal('0'))

    # — Devoluciones (solo tiene sentido sobre una venta ya confirmada) —
    # cuentas_reembolso_json es igual a cuentas_json pero SIN excluir
    # Efectivo: ese exclude de arriba es específico del cobro con
    # tarjeta/QR/transferencia, un reembolso sí puede salir de efectivo.
    items_lista = list(venta.items.select_related('producto', 'cliente', 'combinacion').all())
    devoluciones = list(
        venta.devoluciones.select_related('cuenta').prefetch_related('items').order_by('-fecha_alta')
    ) if venta.estado == EstadoVenta.CONFIRMADA else []

    # cantidad_devuelta/disponible_devolucion se setean SIEMPRE (no
    # solo si está confirmada) para que items-devolucion-data en el
    # template pueda leerlos sin condicionales — en un borrador
    # nunca hubo devoluciones, así que disponible = cantidad.
    cantidad_devuelta_por_item = {}
    for dev in devoluciones:
        for dev_item in dev.items.all():
            if dev_item.item_venta_id:
                cantidad_devuelta_por_item[dev_item.item_venta_id] = (
                    cantidad_devuelta_por_item.get(dev_item.item_venta_id, Decimal('0')) + dev_item.cantidad
                )
    for item in items_lista:
        item.cantidad_devuelta = cantidad_devuelta_por_item.get(item.pk, Decimal('0'))
        item.disponible_devolucion = item.cantidad - item.cantidad_devuelta

    cuentas_reembolso_json = '[]'
    if venta.estado == EstadoVenta.CONFIRMADA:
        cuentas_reembolso = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False)
            .order_by('orden', 'nombre')
        )
        cuentas_reembolso_json = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'tipo': c.tipo, 'titular': c.titular}
            for c in cuentas_reembolso
        ])

    from django.urls import reverse
    return {
        'venta':      venta,
        'items':      items_lista,
        'documentos': venta.documentos.all(),
        'devoluciones': devoluciones,
        'cuentas_reembolso_json': cuentas_reembolso_json,
        'puede_registrar_devoluciones': chequear_permiso(request.user, 'registrar_devoluciones'),
        'pagos':      pagos_lista,
        'total_recargo': total_recargo,
        'total_redondeo': total_redondeo,
        'total_a_cobrar': venta.total + total_recargo + total_redondeo,
        'es_borrador': venta.estado == EstadoVenta.BORRADOR,
        'medios_pago': MedioPago.choices,
        'datos_empresa': DatosEmpresa.get_solo(),
        'configuracion_arca': config_arca,
        'comprobante_arca': getattr(venta, 'comprobante_arca', None),
        'cliente_unico_venta': cliente_unico,
        'tipo_comprobante_previsto_display': (
            TipoComprobante(tipo_previsto).label if tipo_previsto else None
        ),
        'venta_moneda': moneda_venta,
        'cuentas_json': cuentas_json,
        # Cuenta sugerida por defecto para cada medio de pago (débito/
        # crédito/QR/transferencia) — ver caja.models.CuentaPredeterminadaMedio
        # y detalle_venta.js _aplicarMedioALinea. Solo preselecciona; el
        # vendedor cambia la cuenta a mano si hace falta.
        'cuentas_predeterminadas_json': json.dumps(CuentaPredeterminadaMedio.como_dict()),
        # Cuenta principal del negocio — fallback del panel de cobro
        # cuando un medio no tiene su CuentaPredeterminadaMedio propia,
        # y default del <select> de reembolso de devoluciones.
        'cuenta_principal_pk': CuentaCaja.principal_pk(),
        'tarjetas_json': tarjetas_json,
        'recargos_json': recargos_json,
        'url_confirmar':         reverse('ventas:confirmar_venta'),
        'url_eliminar_borrador': reverse('ventas:eliminar_borrador'),
        'url_nueva_venta':       reverse('ventas:nueva_venta'),
        'url_historial':         reverse('ventas:historial_ventas'),
        'url_doc_subir':         reverse('ventas:documento_subir'),
        'url_doc_eliminar':      reverse('ventas:documento_eliminar'),
        'url_facturar':          reverse('ventas:venta_facturar', args=[venta.pk]),
        'url_buscar_cliente':    reverse('ventas:buscar_cliente'),
        'url_registrar_devolucion': reverse('ventas:registrar_devolucion'),
        'url_cobro_fragmento': reverse('ventas:cobro_fragmento', args=[0]).replace('/0/', '/'),
    }


class DetalleVentaView(LoginRequiredMixin, View):
    """Página completa del detalle de venta — permalink del Historial y
    fallback para abrir un borrador por URL directa. El flujo normal de
    cobro de un borrador vive en el panel flotante de Nueva Venta (ver
    CobroFragmentoAjax)."""
    template_name = 'ventas/detalle_venta.html'

    def get(self, request, pk):
        if not chequear_permiso(request.user, 'crear_ventas'):
            from django.shortcuts import redirect
            return redirect('core:dashboard')

        venta = get_object_or_404(_venta_detalle_qs(), pk=pk)
        return _render(request, self.template_name,
                       construir_contexto_detalle(request, venta))


class CobroFragmentoAjax(LoginRequiredMixin, View):
    """
    GET ?pk → { ok, html, estado, numero, total }

    `html` es el panel de cobro (borrador o confirmada) + sus modales +
    los <script> de datos (VDT_CONFIG / TICKET_DATA / data blocks). Lo
    inyecta panel_cobro.js en el panel flotante sobre /ventas/nueva/ y
    re-ejecuta sus <script> (innerHTML no los corre solo).
    """

    def get(self, request, pk):
        if not chequear_permiso(request.user, 'crear_ventas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        from django.template.loader import render_to_string

        venta = get_object_or_404(_venta_detalle_qs(), pk=pk)
        ctx   = construir_contexto_detalle(request, venta)

        panel = ('ventas/_panel_cobro_confirmada.html'
                 if venta.estado == EstadoVenta.CONFIRMADA
                 else 'ventas/_panel_cobro_borrador.html')

        html = (
            render_to_string(panel, ctx, request)
            + render_to_string('ventas/_detalle_venta_modales.html', ctx, request)
            + render_to_string('ventas/_detalle_venta_datos.html', ctx, request)
        )
        resp = JsonResponse({
            'ok':     True,
            'html':   html,
            'estado': venta.estado,
            'numero': venta.numero,
            'total':  str(venta.total),
        })
        # El fragmento refleja el estado vivo del borrador — nunca cachearlo.
        resp['Cache-Control'] = 'no-store'
        return resp