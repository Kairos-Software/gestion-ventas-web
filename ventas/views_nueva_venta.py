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
from core.models import Cliente, DatosEmpresa, ConfiguracionArca
from compras.models import LoteCompra
from .models import (
    Venta, ItemVenta, EstadoVenta, MedioPago, TipoResolucionLote,
    EtiquetaBalanza, EstadoEtiquetaBalanza,
)
from core.permisos import chequear_permiso
from core.services_arca import facturacion
from core.services_arca.tipos import CondicionIvaReceptor
from core.services_arca.wsaa import ArcaError

# Subconjunto de CondicionIvaReceptor.LABELS para el selector de "facturar a
# nombre de un cliente" — las 4 que realmente aparecen en el día a día.
CONDICIONES_IVA_RECEPTOR_COMUNES = [
    (CondicionIvaReceptor.CONSUMIDOR_FINAL, 'Consumidor Final'),
    (CondicionIvaReceptor.RESPONSABLE_INSCRIPTO, 'Responsable Inscripto'),
    (CondicionIvaReceptor.MONOTRIBUTO, 'Monotributo'),
    (CondicionIvaReceptor.EXENTO, 'Exento'),
]
from caja.models import TurnoCaja, CuentaCaja, TipoCaja


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

        # ── Precarga desde un borrador existente ("Editar carrito") ──
        ctx['venta_editar_pk'] = None
        ctx['items_iniciales']  = []

        editar_pk = self.request.GET.get('editar', '').strip()
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
            qs = qs.filter(nombre__icontains=q) | qs.filter(razon_social__icontains=q)
        data = [
            {
                'pk':     c.pk,
                'nombre': c.nombre or c.razon_social or str(c),
                'codigo': c.codigo or '',
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
            fecha      = body.get('fecha') or timezone.now().date().isoformat(),
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
                suma_ars = Decimal('0')
                for p in pagos_raw:
                    medio_p = p.get('medio', '').strip()
                    if medio_p not in valores_validos:
                        return JsonResponse({'error': f'Medio de pago inválido en pagos: {medio_p}'}, status=400)
                    try:
                        monto_p = Decimal(str(p.get('monto', 0)))
                    except Exception:
                        return JsonResponse({'error': 'Monto de pago inválido.'}, status=400)
                    if monto_p <= 0:
                        continue

                    cotizacion_p = None
                    monto_ars = monto_p
                    if medio_p != MedioPago.EFECTIVO:
                        cuenta = CuentaCaja.objects.filter(pk=p.get('cuenta_pk'), caja=TipoCaja.GRANDE, activa=True).first()
                        if cuenta and cuenta.moneda != 'ARS':
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
                        'cuenta_pk': p.get('cuenta_pk'),
                        'cotizacion': cotizacion_p,
                    })

                if not pagos_normalizados:
                    return JsonResponse({'error': 'Agregá al menos un medio de pago con monto.'}, status=400)

                # El total recién se recalcula en confirmar(); usamos el total actual del borrador
                total_actual = venta.calcular_total() or venta.total
                venta.refresh_from_db(fields=['total'])
                diferencia = abs(suma_ars - venta.total)
                if diferencia > Decimal('0.01'):
                    return JsonResponse({
                        'error': f'La suma de los pagos (${suma_ars}) no coincide con el total (${venta.total}).'
                    }, status=400)

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
            cliente = None
            cliente_pk = body.get('cliente_pk')
            if cliente_pk:
                cliente = Cliente.objects.filter(pk=cliente_pk).first()
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

        cliente = None
        cliente_pk = body.get('cliente_pk')
        if cliente_pk:
            cliente = Cliente.objects.filter(pk=cliente_pk).first()

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

        venta.delete()
        return JsonResponse({'ok': True})


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

class DetalleVentaView(LoginRequiredMixin, View):
    template_name = 'ventas/detalle_venta.html'

    def get(self, request, pk):
        if not chequear_permiso(request.user, 'crear_ventas'):
            from django.shortcuts import redirect
            return redirect('core:dashboard')

        venta = get_object_or_404(
            Venta.objects.prefetch_related(
                'items__producto', 'items__cliente', 'items__combinacion',
                'documentos', 'pagos__cuenta',
            ),
            pk=pk
        )

        from caja.models import asegurar_cuentas_efectivo
        asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE)

        moneda_venta = venta.items.values_list('moneda', flat=True).first() or 'ARS'
        cuentas = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False)
            .order_by('orden', 'nombre')
        )
        cuentas_json = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda}
            for c in cuentas
        ])

        # Si todos los ítems de la venta comparten el mismo cliente, se lo
        # ofrece como destinatario directo de la factura (sin tener que
        # buscarlo de nuevo) — si hay más de uno o ninguno, sólo queda la
        # opción de facturar a Consumidor Final.
        clientes_venta = {item.cliente_id for item in venta.items.all() if item.cliente_id}
        cliente_unico = None
        if len(clientes_venta) == 1:
            cliente_unico = Cliente.objects.filter(pk=clientes_venta.pop()).first()

        from django.urls import reverse
        return _render(request, self.template_name, {
            'venta':      venta,
            'items':      venta.items.select_related('producto', 'cliente', 'combinacion').all(),
            'documentos': venta.documentos.all(),
            'pagos':      venta.pagos.all(),
            'es_borrador': venta.estado == EstadoVenta.BORRADOR,
            'medios_pago': MedioPago.choices,
            'datos_empresa': DatosEmpresa.get_solo(),
            'configuracion_arca': ConfiguracionArca.get_solo(),
            'comprobante_arca': getattr(venta, 'comprobante_arca', None),
            'cliente_unico_venta': cliente_unico,
            'condiciones_iva_receptor': CONDICIONES_IVA_RECEPTOR_COMUNES,
            'venta_moneda': moneda_venta,
            'cuentas_json': cuentas_json,
            'url_confirmar':         reverse('ventas:confirmar_venta'),
            'url_eliminar_borrador': reverse('ventas:eliminar_borrador'),
            'url_nueva_venta':       reverse('ventas:nueva_venta'),
            'url_historial':         reverse('ventas:historial_ventas'),
            'url_doc_subir':         reverse('ventas:documento_subir'),
            'url_doc_eliminar':      reverse('ventas:documento_eliminar'),
            'url_facturar':          reverse('ventas:venta_facturar', args=[venta.pk]),
        })