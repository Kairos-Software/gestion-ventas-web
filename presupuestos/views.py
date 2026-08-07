import json
from decimal import Decimal

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Q

from productos.models import Producto, CombinacionVariante, ListaDescuento
from core.models import Cliente, DatosEmpresa
from core.permisos import chequear_permiso
from .models import Presupuesto, crear_presupuesto, actualizar_presupuesto

PERMISO_VER      = 'ver_presupuestos'
PERMISO_CREAR    = 'crear_presupuestos'
PERMISO_ELIMINAR = 'eliminar_presupuestos'


def _datos_impresion(request, presupuesto):
    """Payload para presupuesto_a4.js — igual shape que window.TICKET_DATA
    de Ventas, pero simplificado (sin ARCA/pagos). Se usa tanto al
    guardar (respuesta de Crear/ActualizarPresupuestoAjax, para
    imprimir en el mismo movimiento) como al reimprimir uno viejo
    desde el historial (PresupuestoDatosAjax)."""
    emp = DatosEmpresa.get_solo()
    return {
        'ok': True,
        'pk': presupuesto.pk,
        'numero': presupuesto.numero,
        'empresa': {
            'nombre': emp.nombre_comercial,
            'razon_social': emp.razon_social,
            'domicilio': emp.domicilio,
            'telefono': emp.telefono,
            'email': emp.email,
            'logo_url': f'{request.scheme}://{request.get_host()}{emp.logo.url}' if emp.logo else '',
        },
        'presupuesto': {
            'numero': presupuesto.numero,
            'fecha': presupuesto.fecha.strftime('%d/%m/%Y'),
            'notas': presupuesto.notas,
            'total': str(presupuesto.total),
        },
        'cliente_nombre': presupuesto.cliente_nombre,
        'items': [
            {
                'nombre': item.nombre_producto_display + (f' — {item.combinacion_descripcion}' if item.combinacion_descripcion else ''),
                'cantidad': f'{item.cantidad:.3f}'.rstrip('0').rstrip('.'),
                'precio_unitario': str(item.precio_unitario),
                'descuento_pct': str(item.descuento_pct),
                'subtotal': str(item.subtotal),
            }
            for item in presupuesto.items.all()
        ],
    }


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Nuevo Presupuesto (también sirve de editor:
#  ?editar=<pk> precarga el carrito con los ítems de un presupuesto
#  ya guardado, mismo patrón que ?editar=<pk> en Nueva Venta)
# ══════════════════════════════════════════════════════════════════

class NuevoPresupuestoView(LoginRequiredMixin, TemplateView):
    template_name = 'presupuestos/nuevo_presupuesto.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, PERMISO_CREAR):
            ctx['sin_permiso'] = True
            return ctx

        ctx['listas_descuento'] = [
            {'nombre': l.nombre, 'porcentaje': str(l.porcentaje)}
            for l in ListaDescuento.objects.filter(activa=True).order_by('orden', 'nombre')
        ]

        ctx['presupuesto_editar_pk'] = None
        ctx['items_iniciales'] = []
        ctx['cliente_editar_pk'] = None
        ctx['cliente_editar_nombre'] = ''

        editar_pk = self.request.GET.get('editar', '').strip()
        if editar_pk:
            presupuesto = (
                Presupuesto.objects
                .filter(pk=editar_pk)
                .prefetch_related('items__producto', 'items__combinacion')
                .first()
            )
            if presupuesto:
                ctx['presupuesto_editar_pk'] = presupuesto.pk
                ctx['cliente_editar_pk'] = presupuesto.cliente_id
                ctx['cliente_editar_nombre'] = presupuesto.cliente_nombre
                ctx['items_iniciales'] = [
                    {
                        'producto_pk':    item.producto_id,
                        'combinacion_pk': item.combinacion_id,
                        'nombre':         item.nombre_producto_display + (f' — {item.combinacion_descripcion}' if item.combinacion_descripcion else ''),
                        'codigo':         item.producto.codigo if item.producto_id else '',
                        'stock_actual':   float(item.stock_al_emitir) if item.stock_al_emitir is not None else 0,
                        'cantidad':       str(item.cantidad),
                        'precio':         str(item.precio_unitario),
                        'descuento':      str(item.descuento_pct),
                        'lista_descuento_nombre': item.lista_descuento_nombre,
                    }
                    for item in presupuesto.items.all()
                ]
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar productos / clientes
#  (copias de ventas.views_nueva_venta, con el permiso de este módulo
#  en vez de 'crear_ventas' — ver Plan, sección Vistas, para el porqué
#  de duplicar en vez de compartir estas dos)
# ══════════════════════════════════════════════════════════════════

class BuscarProductoAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
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

        producto_exacto = (
            base_qs.filter(Q(codigo_barras__iexact=q) | Q(sku__iexact=q))
            .exclude(codigo_barras='')
            .first()
        )
        if producto_exacto:
            return JsonResponse({'results': [self._fila_producto_exacto(producto_exacto)]})

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

    def _filas_texto(self, p):
        if p.gestiona_variantes:
            return [
                self._fila_variante(p, c)
                for c in p.combinaciones.filter(activo=True).order_by('pk')
            ]
        return [self._fila_simple(p)]

    def _base(self, p):
        return {
            'pk':                 p.pk,
            'codigo':             p.codigo,
            'unidad_medida':      p.get_unidad_medida_display(),
            'categoria_id':       p.categoria_id,
            'categoria':          p.categoria.nombre if p.categoria else '',
            'tipo':               p.tipo.nombre if p.tipo else '',
            'marca':              p.marca,
            'modelo':             p.modelo,
            'gestiona_variantes': p.gestiona_variantes,
            'es_paquete':         p.es_paquete,
            'precio_venta':       float(p.precio_venta) if p.precio_venta is not None else None,
            'moneda':             'ARS',
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


class BuscarClienteAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
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
            }
            for c in qs[:20]
        ]
        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear / Actualizar presupuesto
#  (mismo par que GuardarBorradorAjax/ActualizarBorradorAjax en ventas)
# ══════════════════════════════════════════════════════════════════

def _parsear_items(items_raw):
    """Devuelve (items_data, error) — error es un string listo para
    devolver en un 400, o None si todo resolvió bien."""
    items_data = []
    for idx, raw in enumerate(items_raw, start=1):
        producto_pk = raw.get('producto_pk')
        producto = Producto.objects.filter(pk=producto_pk).first() if producto_pk else None
        if not producto:
            return None, f'Ítem {idx}: producto no encontrado.'

        combinacion = None
        combinacion_pk = raw.get('combinacion_pk')
        if combinacion_pk:
            combinacion = CombinacionVariante.objects.filter(pk=combinacion_pk, producto=producto).first()
            if not combinacion:
                return None, f'Ítem {idx}: la combinación no pertenece a este producto.'

        try:
            cantidad        = Decimal(str(raw.get('cantidad', 0)))
            precio_unitario = Decimal(str(raw.get('precio_unitario', 0)))
            descuento_pct   = Decimal(str(raw.get('descuento_pct', 0) or 0))
            stock_al_emitir = raw.get('stock_al_emitir')
            stock_al_emitir = Decimal(str(stock_al_emitir)) if stock_al_emitir is not None else None
        except Exception:
            return None, f'Ítem {idx}: valores numéricos inválidos.'

        items_data.append({
            'producto': producto,
            'combinacion': combinacion,
            'cantidad': cantidad,
            'precio_unitario': precio_unitario,
            'descuento_pct': descuento_pct,
            'lista_descuento_nombre': raw.get('lista_descuento_nombre', ''),
            'stock_al_emitir': stock_al_emitir,
        })
    return items_data, None


class CrearPresupuestoAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "cliente_pk": 12|null, "cliente_nombre": "...", "notas": "...",
        "items": [ { producto_pk, combinacion_pk, cantidad, precio_unitario,
                     descuento_pct, lista_descuento_nombre, stock_al_emitir } ]
    }
    Respuesta: datos completos para imprimir de una (ver _datos_impresion) —
    así "Guardar" en el carrito guarda Y abre la impresión en el mismo
    movimiento, sin una segunda vuelta al servidor.
    """

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        items_raw = body.get('items', [])
        if not items_raw:
            return JsonResponse({'error': 'El presupuesto no tiene ítems.'}, status=400)

        cliente = None
        cliente_pk = body.get('cliente_pk')
        if cliente_pk:
            cliente = Cliente.objects.filter(pk=cliente_pk).first()

        items_data, error = _parsear_items(items_raw)
        if error:
            return JsonResponse({'error': error}, status=400)

        try:
            presupuesto = crear_presupuesto(
                fecha=timezone.now().date(),
                items_data=items_data,
                cliente=cliente,
                cliente_nombre=body.get('cliente_nombre', '') or (cliente.get_nombre_display() if cliente else ''),
                notas=body.get('notas', ''),
                usuario=request.user,
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse(_datos_impresion(request, presupuesto))


class ActualizarPresupuestoAjax(LoginRequiredMixin, View):
    """POST JSON igual a CrearPresupuestoAjax + "presupuesto_pk". Reemplaza
    los ítems de un presupuesto ya guardado (no cambia su número ni su
    fecha de emisión original). Misma respuesta que Crear: lista para
    imprimir en el mismo movimiento."""

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        presupuesto = get_object_or_404(Presupuesto, pk=body.get('presupuesto_pk'))

        items_raw = body.get('items', [])
        if not items_raw:
            return JsonResponse({'error': 'El presupuesto no tiene ítems.'}, status=400)

        cliente = None
        cliente_pk = body.get('cliente_pk')
        if cliente_pk:
            cliente = Cliente.objects.filter(pk=cliente_pk).first()

        items_data, error = _parsear_items(items_raw)
        if error:
            return JsonResponse({'error': error}, status=400)

        try:
            presupuesto = actualizar_presupuesto(
                presupuesto,
                items_data=items_data,
                cliente=cliente,
                cliente_nombre=body.get('cliente_nombre', '') or (cliente.get_nombre_display() if cliente else ''),
                notas=body.get('notas'),
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse(_datos_impresion(request, presupuesto))


class PresupuestoDatosAjax(LoginRequiredMixin, View):
    """GET ?pk=<pk> — mismos datos que Crear/ActualizarPresupuestoAjax
    devuelven al guardar, para el botón "Imprimir" de una fila del
    historial (reimprimir uno viejo sin pasar por el carrito)."""

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        presupuesto = get_object_or_404(
            Presupuesto.objects.prefetch_related('items'), pk=request.GET.get('pk')
        )
        return JsonResponse(_datos_impresion(request, presupuesto))


class EliminarPresupuestoAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        presupuesto_pk = request.POST.get('presupuesto_pk')
        presupuesto = get_object_or_404(Presupuesto, pk=presupuesto_pk)
        presupuesto.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  Historial — único lugar donde se ve/edita/elimina/reimprime un
#  presupuesto ya guardado (no hay página de detalle aparte)
# ══════════════════════════════════════════════════════════════════

class HistorialPresupuestosView(LoginRequiredMixin, TemplateView):
    template_name = 'presupuestos/historial_presupuestos.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx
        ctx['puede_editar']   = chequear_permiso(self.request.user, PERMISO_CREAR)
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, PERMISO_ELIMINAR)
        return ctx


class ListarPresupuestosAjax(LoginRequiredMixin, View):
    PAGE_SIZE = 20

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = (
            Presupuesto.objects
            .select_related('cliente', 'creado_por')
            .prefetch_related('items')
            .order_by('-fecha_alta')
        )

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(numero__icontains=q) | Q(cliente_nombre__icontains=q))

        fecha_desde = request.GET.get('fecha_desde', '').strip()
        if fecha_desde:
            qs = qs.filter(fecha__gte=fecha_desde)
        fecha_hasta = request.GET.get('fecha_hasta', '').strip()
        if fecha_hasta:
            qs = qs.filter(fecha__lte=fecha_hasta)

        try:
            page = max(1, int(request.GET.get('page', 1)))
        except ValueError:
            page = 1

        total  = qs.count()
        offset = (page - 1) * self.PAGE_SIZE

        data = [
            {
                'pk':          p.pk,
                'numero':      p.numero,
                'fecha':       p.fecha.strftime('%d/%m/%Y'),
                'cliente':     p.cliente_nombre or (p.cliente.get_nombre_display() if p.cliente_id else ''),
                'total':       str(p.total),
                'cantidad_items': p.items.count(),
                'creado_por':  p.creado_por.get_full_name() or p.creado_por.username if p.creado_por_id else '',
            }
            for p in qs[offset:offset + self.PAGE_SIZE]
        ]

        return JsonResponse({
            'results':   data,
            'total':     total,
            'page':      page,
            'page_size': self.PAGE_SIZE,
            'has_next':  (offset + self.PAGE_SIZE) < total,
            'has_prev':  page > 1,
        })
