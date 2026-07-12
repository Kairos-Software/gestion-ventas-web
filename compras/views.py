import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from django.db.models import Q

from productos.models import Producto, Proveedor, CombinacionVariante, ListaDescuento
from .models import Compra, ItemCompra, EstadoCompra, MedioPagoCompra
from core.permisos import chequear_permiso
from caja.models import CuentaCaja, TipoCaja


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Nueva Compra
# ══════════════════════════════════════════════════════════════════

class NuevaCompraView(LoginRequiredMixin, TemplateView):
    """
    Renderiza el formulario / carrito para crear una nueva compra.

    Si se accede con ?editar=<pk>, precarga el carrito con los ítems
    de ese borrador existente (en vez de arrancar vacío). Al guardar,
    el JS actualiza ese mismo borrador en vez de crear uno nuevo.
    """
    template_name = 'compras/nueva_compra.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, 'crear_compras'):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_crear'] = True
        ctx['today'] = timezone.now().date().isoformat()

        ctx['listas_descuento'] = [
            {'nombre': l.nombre, 'porcentaje': str(l.porcentaje)}
            for l in ListaDescuento.objects.filter(activa=True).order_by('orden', 'nombre')
        ]

        ctx['editing_pk'] = None
        ctx['items_json'] = []

        editar_pk = self.request.GET.get('editar', '').strip()
        if editar_pk:
            compra = Compra.objects.filter(pk=editar_pk, estado=EstadoCompra.BORRADOR).first()
            if compra:
                ctx['editing_pk'] = compra.pk
                items_bootstrap = []
                for item in compra.items.select_related('producto', 'proveedor', 'combinacion').all():
                    items_bootstrap.append({
                        'producto_pk':      item.producto_id,
                        'combinacion_pk':   item.combinacion_id or None,
                        'nombre':           (f'{item.nombre_producto_display} — {item.nombre_combinacion_display}'
                                             if item.nombre_combinacion_display else item.nombre_producto_display),
                        'producto_nombre':  item.nombre_producto_display,
                        'variante_desc':    item.nombre_combinacion_display or '',
                        'codigo':           item.producto_codigo or (item.producto.codigo if item.producto else ''),
                        'proveedor_pk':     item.proveedor_id or '',
                        'proveedor':        item.nombre_proveedor_display,
                        'cantidad':         str(item.cantidad),
                        'costo':            str(item.costo_unitario),
                        'moneda':           item.moneda,
                        'descuento':        str(item.descuento_pct),
                        'lista_descuento_nombre': item.lista_descuento_nombre,
                        'condicion':        item.condicion_pago,
                        'referencia':       item.referencia,
                        'fecha_vencimiento': item.fecha_vencimiento.strftime('%Y-%m-%d') if item.fecha_vencimiento else '',
                        'es_perecedero':    bool(item.producto.es_perecedero) if item.producto else bool(item.fecha_vencimiento),
                    })
                ctx['items_json'] = items_bootstrap
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar productos (para el buscador del carrito)
# ══════════════════════════════════════════════════════════════════

class BuscarProductoAjax(LoginRequiredMixin, View):
    """
    GET ?q=texto → lista de RESULTADOS ya resueltos a nivel de unidad
    agregable (producto simple, o producto+variante puntual).

    Cada fila del resultado representa exactamente lo que se va a agregar
    al carrito con un solo clic — nunca un "producto con combinaciones
    adentro" que obligue a distribuir manualmente.

    Reglas:
      1) Si `q` matchea EXACTO el código de barras (o SKU) de una variante,
         o el código de barras de un producto sin variantes, se devuelve
         un único resultado marcado `match_exacto: true`. Este es el caso
         de un escaneo — el frontend lo agrega directo sin mostrar dropdown.
      2) Si no hay match exacto, se hace búsqueda parcial por texto:
         - Si el texto matchea el producto (nombre/código/código de barras
           global), se listan TODAS sus variantes activas como filas
           independientes (o una fila única si no tiene variantes).
         - Si el texto matchea el código de barras / SKU de una variante
           puntual, se agrega esa fila igual.
    """

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        base_qs = (
            Producto.objects
            .select_related('categoria', 'tipo', 'proveedor')
            .prefetch_related('combinaciones')
            .filter(estado='activo')
        )

        # ── Modo ?pk= : producto específico con todas sus variantes.
        #    Usado por el editor del historial para enriquecer swatches
        #    al abrir el panel de edición de una compra anulada. ──
        pk_param = request.GET.get('pk', '').strip()
        if pk_param:
            try:
                p = base_qs.get(pk=pk_param)
            except Producto.DoesNotExist:
                return JsonResponse({'results': []})
            return JsonResponse({'results': self._filas_producto(p)})

        q = request.GET.get('q', '').strip()

        if not q:
            resultados = []
            for p in base_qs.order_by('nombre')[:30]:
                resultados.extend(self._filas_producto(p))
            return JsonResponse({'results': resultados[:30]})

        # ── 1) Coincidencia EXACTA de código de barras / SKU (escaneo) ──
        combinacion_exacta = (
            CombinacionVariante.objects
            .select_related('producto', 'producto__categoria',
                             'producto__tipo', 'producto__proveedor')
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

        producto_exacto = (
            base_qs.filter(codigo_barras__iexact=q, gestiona_variantes=False)
            .exclude(codigo_barras='')
            .first()
        )
        if producto_exacto:
            return JsonResponse({'results': [self._fila_simple(producto_exacto, match_exacto=True)]})

        # ── 2) Búsqueda parcial por texto ──
        productos_match = base_qs.filter(
            Q(nombre__icontains=q) | Q(codigo__icontains=q) | Q(codigo_barras__icontains=q)
        ).distinct().order_by('nombre')

        combinaciones_match = (
            CombinacionVariante.objects
            .select_related('producto', 'producto__categoria',
                             'producto__tipo', 'producto__proveedor')
            .filter(activo=True, producto__estado='activo')
            .filter(Q(codigo_barras__icontains=q) | Q(sku_variante__icontains=q))
            .order_by('producto__nombre')
        )

        resultados = []
        vistos = set()  # (producto_pk, combinacion_pk|None)

        for p in productos_match:
            for fila in self._filas_producto(p):
                clave = (fila['producto_pk'], fila['combinacion_pk'])
                if clave not in vistos:
                    vistos.add(clave)
                    resultados.append(fila)

        for c in combinaciones_match:
            fila = self._fila_variante(c.producto, c)
            clave = (fila['producto_pk'], fila['combinacion_pk'])
            if clave not in vistos:
                vistos.add(clave)
                resultados.append(fila)

        return JsonResponse({'results': resultados[:30]})

    # ── Helpers de serialización ────────────────────────────────────
    def _filas_producto(self, p):
        """Filas 'agregables' de un producto: una por variante activa,
        o una única fila si el producto no gestiona variantes."""
        if p.gestiona_variantes:
            return [
                self._fila_variante(p, c)
                for c in p.combinaciones.filter(activo=True).order_by('pk')
            ]
        return [self._fila_simple(p)]

    def _base_producto(self, p):
        return {
            'producto_pk':        p.pk,
            'producto_nombre':    p.nombre,
            'codigo':             p.codigo,
            'unidad_medida':      p.get_unidad_medida_display(),
            'stock_minimo':       float(p.stock_minimo),
            'categoria':          p.categoria.nombre if p.categoria else '',
            'tipo':               p.tipo.nombre if p.tipo else '',
            'marca':              p.marca,
            'modelo':             p.modelo,
            'proveedor_pk':       p.proveedor_id or '',
            'proveedor':          p.proveedor.nombre if p.proveedor else '',
            'es_perecedero':      p.es_perecedero,
            'gestiona_variantes': p.gestiona_variantes,
        }

    def _fila_simple(self, p, match_exacto=False):
        fila = self._base_producto(p)
        fila.update({
            'combinacion_pk': None,
            'nombre':         p.nombre,
            'variante_desc':  '',
            'codigo_barras':  p.codigo_barras,
            'stock_actual':   float(p.stock_actual),
            'match_exacto':   match_exacto,
        })
        return fila

    def _fila_variante(self, p, c, match_exacto=False):
        fila = self._base_producto(p)
        fila.update({
            'combinacion_pk': c.pk,
            'nombre':         f'{p.nombre} — {c.descripcion_legible()}',
            'variante_desc':  c.descripcion_legible(),
            'codigo_barras':  c.codigo_barras,
            'sku_variante':   c.sku_variante,
            'stock_actual':   float(c.stock_actual),
            'match_exacto':   match_exacto,
        })
        return fila


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar proveedores (para el select de cada ítem)
# ══════════════════════════════════════════════════════════════════

class BuscarProveedorAjax(LoginRequiredMixin, View):
    """GET ?q=texto → lista de proveedores activos."""

    def get(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q  = request.GET.get('q', '').strip()
        qs = Proveedor.objects.filter(activo=True).order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q)
        data = [
            {
                'pk':     p.pk,
                'nombre': p.nombre,
                'cuit':   p.cuit,
                'ciudad': p.ciudad,
            }
            for p in qs[:20]
        ]
        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Guardar Borrador
#  Nuevo endpoint: crea la Compra en BORRADOR con sus ítems.
#  No toca stock. Devuelve el pk para redirigir al detalle.
# ══════════════════════════════════════════════════════════════════

class GuardarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "fecha": "2025-01-15",       // opcional, usa hoy si falta
        "notas": "...",
        "items": [
            {
                "producto_pk":       1,
                "proveedor_pk":      2,        // opcional
                "combinacion_pk":    5,        // solo si tiene variantes
                "cantidad":          "10.000",
                "costo_unitario":    "150.00",
                "moneda":            "ARS",
                "descuento_pct":     "0",
                "condicion_pago":    "contado",
                "referencia":        "FA-0001"
            },
            ...
        ]
    }

    Respuesta: { ok: true, pk: <compra_pk>, numero: "CMP-00001" }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        items_raw = body.get('items', [])
        if not items_raw:
            return JsonResponse({'error': 'El carrito está vacío.'}, status=400)

        # Usar hoy si no se provee fecha (se puede editar en el detalle)
        fecha = body.get('fecha') or timezone.now().date().isoformat()

        # — Crear cabecera en BORRADOR —
        compra = Compra(
            fecha      = fecha,
            notas      = body.get('notas', ''),
            estado     = EstadoCompra.BORRADOR,
            creado_por = request.user,
        )
        compra.save()

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
                cantidad       = Decimal(str(raw.get('cantidad', 0)))
                costo_unitario = Decimal(str(raw.get('costo_unitario', 0)))
                descuento_pct  = Decimal(str(raw.get('descuento_pct', 0)))
            except Exception:
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if costo_unitario < 0:
                errores.append(f'Ítem {idx}: el costo no puede ser negativo.')
                continue

            # — Proveedor (opcional) —
            proveedor = None
            proveedor_pk = raw.get('proveedor_pk')
            if proveedor_pk:
                proveedor = Proveedor.objects.filter(pk=proveedor_pk).first()

            # — Combinación (solo si el producto gestiona variantes) —
            combinacion = None
            combinacion_pk = raw.get('combinacion_pk')
            if producto.gestiona_variantes and combinacion_pk:
                combinacion = CombinacionVariante.objects.filter(
                    pk=combinacion_pk, producto=producto, activo=True
                ).first()
                if combinacion is None:
                    errores.append(
                        f'Ítem {idx}: la combinación indicada no existe o no pertenece al producto.'
                    )
                    continue

            # — Fecha de vencimiento (opcional, requerida para perecederos) —
            fecha_vencimiento = None
            fv_raw = raw.get('fecha_vencimiento')
            if fv_raw:
                try:
                    from datetime import datetime
                    fecha_vencimiento = datetime.strptime(fv_raw, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass  # Si el formato es inválido, se deja como None

            ItemCompra.objects.create(
                compra         = compra,
                producto       = producto,
                proveedor      = proveedor,
                combinacion    = combinacion,
                cantidad       = cantidad,
                costo_unitario = costo_unitario,
                moneda         = raw.get('moneda', 'ARS'),
                descuento_pct  = descuento_pct,
                lista_descuento_nombre = raw.get('lista_descuento_nombre', ''),
                condicion_pago = raw.get('condicion_pago', 'contado'),
                referencia     = raw.get('referencia', ''),
                notas          = raw.get('notas', ''),
                fecha_vencimiento = fecha_vencimiento,
            )

        if errores:
            compra.delete()
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # Calcular total sin confirmar (para mostrarlo en el detalle)
        compra.total = sum(item.subtotal for item in compra.items.all())
        compra.save(update_fields=['total'])

        return JsonResponse({
            'ok':     True,
            'pk':     compra.pk,
            'numero': compra.numero,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Actualizar Borrador  (usado cuando se edita el carrito de
#  un borrador existente desde Nueva Compra con ?editar=<pk>)
# ══════════════════════════════════════════════════════════════════

class ActualizarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "compra_pk": 42,
        "fecha":     "2025-01-15",
        "notas":     "...",
        "items":     [ ... mismo formato que GuardarBorradorAjax ... ]
    }

    Reemplaza TODOS los ítems del borrador por los que llegan en el body.
    El borrador sigue en BORRADOR — no toca stock ni crea lotes todavía.

    Respuesta: { ok: true, pk, numero, total }
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra_pk = body.get('compra_pk')
        if not compra_pk:
            return JsonResponse({'error': 'compra_pk requerido.'}, status=400)

        compra = get_object_or_404(Compra, pk=compra_pk)

        if compra.estado != EstadoCompra.BORRADOR:
            return JsonResponse(
                {'error': f'La compra ya está en estado "{compra.get_estado_display()}". Solo se pueden editar borradores desde acá.'},
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
                cantidad       = Decimal(str(raw.get('cantidad', 0)))
                costo_unitario = Decimal(str(raw.get('costo_unitario', 0)))
                descuento_pct  = Decimal(str(raw.get('descuento_pct', 0)))
            except Exception:
                errores.append(f'Ítem {idx}: valores numéricos inválidos.')
                continue

            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if costo_unitario < 0:
                errores.append(f'Ítem {idx}: el costo no puede ser negativo.')
                continue

            proveedor = None
            proveedor_pk = raw.get('proveedor_pk')
            if proveedor_pk:
                proveedor = Proveedor.objects.filter(pk=proveedor_pk).first()

            combinacion = None
            combinacion_pk = raw.get('combinacion_pk')
            if producto.gestiona_variantes and combinacion_pk:
                combinacion = CombinacionVariante.objects.filter(
                    pk=combinacion_pk, producto=producto, activo=True
                ).first()
                if combinacion is None:
                    errores.append(
                        f'Ítem {idx}: la combinación indicada no existe o no pertenece al producto.'
                    )
                    continue

            fecha_vencimiento = None
            fv_raw = raw.get('fecha_vencimiento')
            if fv_raw:
                try:
                    from datetime import datetime
                    fecha_vencimiento = datetime.strptime(fv_raw, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass

            items_para_crear.append(dict(
                producto=producto, proveedor=proveedor, combinacion=combinacion,
                cantidad=cantidad, costo_unitario=costo_unitario,
                moneda=raw.get('moneda', 'ARS'), descuento_pct=descuento_pct,
                lista_descuento_nombre=raw.get('lista_descuento_nombre', ''),
                condicion_pago=raw.get('condicion_pago', 'contado'),
                referencia=raw.get('referencia', ''), notas=raw.get('notas', ''),
                fecha_vencimiento=fecha_vencimiento,
            ))

        if errores:
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # — Recién acá se toca la base: reemplazo total de ítems —
        compra.items.all().delete()
        for datos in items_para_crear:
            ItemCompra.objects.create(compra=compra, **datos)

        compra.fecha = body.get('fecha') or compra.fecha
        compra.notas = body.get('notas', compra.notas)
        compra.total = sum(item.subtotal for item in compra.items.all())
        compra.save(update_fields=['fecha', 'notas', 'total'])

        return JsonResponse({
            'ok':     True,
            'pk':     compra.pk,
            'numero': compra.numero,
            'total':  str(compra.total),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Confirmar Compra  (desde el detalle del borrador)
#  Recibe { compra_pk, fecha, notas }, actualiza cabecera y confirma.
# ══════════════════════════════════════════════════════════════════

class ConfirmarCompraAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "compra_pk":  42,
        "fecha":      "2025-01-15",
        "notas":      "...",
        "medio_pago": "efectivo",          // medio principal (el primero de "pagos")
        "pagos": [                          // pago dividido (o único)
            {"medio": "efectivo",      "monto": 3000, "cuenta_pk": 1},
            {"medio": "transferencia", "monto": 999.97, "cuenta_pk": 5}
        ]
    }

    1. Carga el borrador existente.
    2. Actualiza fecha y notas con editar_cabecera().
    3. Valida que la suma de "pagos" cubra el total.
    4. Llama a compra.confirmar(medio_pago, pagos) → suma stock,
       calcula total, resuelve las cuentas de pago, pasa a CONFIRMADA.
    5. Devuelve { ok, pk, numero, total }.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra_pk  = body.get('compra_pk')
        fecha      = body.get('fecha', '').strip()
        pagos_raw  = body.get('pagos')

        if not compra_pk:
            return JsonResponse({'error': 'compra_pk requerido.'}, status=400)
        if not fecha:
            return JsonResponse({'error': 'La fecha es requerida.'}, status=400)

        compra = get_object_or_404(Compra, pk=compra_pk)

        if compra.estado != EstadoCompra.BORRADOR:
            return JsonResponse(
                {'error': f'La compra ya está en estado "{compra.get_estado_display()}". Solo se pueden confirmar borradores.'},
                status=400
            )

        valores_validos = MedioPagoCompra.values

        # ── Validar pagos ──
        if not pagos_raw:
            return JsonResponse({'error': 'Agregá al menos un medio de pago con monto.'}, status=400)

        pagos_normalizados = []
        suma = Decimal('0')
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
            suma += monto_p
            linea = {
                'medio': medio_p,
                'monto': monto_p,
                'cuenta_pk': p.get('cuenta_pk'),
            }
            if medio_p == MedioPagoCompra.CREDITO:
                linea['cuotas'] = p.get('cuotas')
                linea['interes_pct'] = p.get('interes_pct')
                linea['fecha_inicio_debito'] = p.get('fecha_inicio_debito')
            pagos_normalizados.append(linea)

        if not pagos_normalizados:
            return JsonResponse({'error': 'Agregá al menos un medio de pago con monto.'}, status=400)

        medio_pago = pagos_normalizados[0]['medio']

        # Actualizar cabecera antes de confirmar
        try:
            compra.editar_cabecera(fecha=fecha, notas=body.get('notas', ''))
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        # El total recién se recalcula en confirmar(); usamos el total actual del borrador
        compra.calcular_total()
        diferencia = abs(suma - compra.total)
        if diferencia > Decimal('0.01'):
            return JsonResponse({
                'error': f'La suma de los pagos (${suma}) no coincide con el total (${compra.total}).'
            }, status=400)

        # Confirmar: suma stock + calcula total + resuelve pagos + pasa a CONFIRMADA
        try:
            compra.confirmar(medio_pago=medio_pago, pagos=pagos_normalizados)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({
            'ok':     True,
            'pk':     compra.pk,
            'numero': compra.numero,
            'total':  str(compra.total),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar Borrador  (botón "Volver" desde el detalle)
#  Solo elimina si está en BORRADOR — no toca stock.
# ══════════════════════════════════════════════════════════════════

class EliminarBorradorAjax(LoginRequiredMixin, View):
    """
    POST JSON { "compra_pk": 42 }

    Elimina un borrador sin pasar por el flujo de anulación
    (el stock nunca fue modificado, así que basta con borrar).
    Solo opera sobre compras en estado BORRADOR.
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        compra_pk = body.get('compra_pk')
        if not compra_pk:
            return JsonResponse({'error': 'compra_pk requerido.'}, status=400)

        compra = get_object_or_404(Compra, pk=compra_pk)

        if compra.estado != EstadoCompra.BORRADOR:
            return JsonResponse(
                {'error': 'Solo se pueden eliminar borradores desde este endpoint.'},
                status=400
            )

        compra.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Documentos de compra
# ══════════════════════════════════════════════════════════════════

import os
from .models import CompraDocumento
from django.shortcuts import render as _render


class CompraDocumentoSubirAjax(LoginRequiredMixin, View):
    """
    POST multipart → sube un documento a una compra existente.
    Funciona tanto para borradores como para compras confirmadas.
    Campos: compra_pk, archivo, tipo (opcional), descripcion (opcional)
    """

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        compra_pk = request.POST.get('compra_pk')
        if not compra_pk:
            return JsonResponse({'error': 'compra_pk requerido.'}, status=400)

        archivo = request.FILES.get('archivo')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

        if archivo.size > 10 * 1024 * 1024:
            return JsonResponse({'error': 'El archivo supera el límite de 10 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        PERMITIDOS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf'}
        if ext not in PERMITIDOS:
            return JsonResponse(
                {'error': 'Tipo de archivo no permitido. Usá JPG, PNG, WEBP, GIF o PDF.'},
                status=400
            )

        compra = get_object_or_404(Compra, pk=compra_pk)

        doc = CompraDocumento(
            compra      = compra,
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


class CompraDocumentoEliminarAjax(LoginRequiredMixin, View):
    """POST JSON { pk } → elimina el documento y el archivo del disco."""

    def post(self, request):
        if not chequear_permiso(request.user, 'crear_compras'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        doc = get_object_or_404(CompraDocumento, pk=pk)

        if doc.archivo and os.path.isfile(doc.archivo.path):
            os.remove(doc.archivo.path)

        doc.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  VISTA — Detalle de compra
#  Sirve tanto para BORRADOR (con botón Confirmar) como para
#  CONFIRMADA/ANULADA (solo lectura + documentos).
# ══════════════════════════════════════════════════════════════════

class DetalleCompraView(LoginRequiredMixin, View):
    """
    GET /compras/detalle/<pk>/

    Contexto extra respecto a la versión anterior:
      - es_borrador: bool → el template muestra el formulario de confirmación
      - url_confirmar, url_eliminar_borrador, url_nueva_compra: para el JS
    """
    template_name = 'compras/detalle_compra.html'

    def get(self, request, pk):
        if not chequear_permiso(request.user, 'crear_compras'):
            from django.shortcuts import redirect
            return redirect('core:dashboard')

        compra = get_object_or_404(
            Compra.objects.prefetch_related(
                'items__producto',
                'items__proveedor',
                'items__combinacion',
                'documentos',
                'pagos__cuenta',
            ),
            pk=pk
        )

        from caja.models import asegurar_cuentas_efectivo
        asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE)

        moneda_compra = compra.items.values_list('moneda', flat=True).first() or 'ARS'
        cuentas = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False)
            .order_by('orden', 'nombre')
        )
        cuentas_json = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda}
            for c in cuentas
        ])

        tarjetas = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True, es_credito=True)
            .order_by('orden', 'nombre')
        )
        tarjetas_json = json.dumps([
            {'pk': t.pk, 'nombre': t.nombre, 'moneda': t.moneda, 'terminada_en': t.terminada_en}
            for t in tarjetas
        ])

        from django.urls import reverse
        return _render(request, self.template_name, {
            'compra':     compra,
            'items':      compra.items.select_related('producto', 'proveedor', 'combinacion').all(),
            'documentos': compra.documentos.all(),
            'pagos':      compra.pagos.all(),
            # — Flags para el template —
            'es_borrador': compra.estado == EstadoCompra.BORRADOR,
            'compra_moneda': moneda_compra,
            'cuentas_json': cuentas_json,
            'tarjetas_json': tarjetas_json,
            # — URLs para el JS del template —
            'url_confirmar':        reverse('compras:confirmar_compra'),
            'url_eliminar_borrador': reverse('compras:eliminar_borrador'),
            'url_nueva_compra':     reverse('compras:nueva_compra'),
            'url_editar_carrito':   f"{reverse('compras:nueva_compra')}?editar={compra.pk}",
            'url_historial':        reverse('compras:historial_compras'),
            'url_doc_subir':        reverse('compras:documento_subir'),
            'url_doc_eliminar':     reverse('compras:documento_eliminar'),
        })