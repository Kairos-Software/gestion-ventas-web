"""
compras/views_factura_inicial.py
────────────────────────────────────────────────────────────────────
Herramienta "Factura inicial".

Es el carrito de Compras normal (mismos datos: proveedor, ítems con
costo/descuento/lista/vencimiento, tipo de comprobante, alícuota de IVA,
medios de pago con pago dividido y cuotas/cheque) pero:

  ✓ con el diseño de la columna de cobro de Ventas (panel anclado a la
    derecha, botonera de medios de pago, total prominente),
  ✓ mueve stock + crea lotes (Compra real, confirmada con pagos=None),
  ✓ se guarda con numeración propia FIN-00001 y su historial aparte,
  ✓ genera un PDF de comprobante. En el PDF:
        • el EMISOR es el PROVEEDOR (sale de su ficha — no se carga a mano),
        • el CLIENTE / RECEPTOR es MI EMPRESA (sale de DatosEmpresa).
    El payload se guarda en `Compra.factura_inicial_datos` para reimprimir.

  ✗ La forma de pago es SOLO informativa: NO crea PagoCompra, NI Deuda,
    NI Cheque, NI MovimientoCaja.
  ✗ No aparece en Compras → Historial ni en Estadísticas.
"""

import json
from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from productos.models import (
    Producto, CombinacionVariante, Proveedor, ListaDescuento,
    AlicuotaIVA, TipoProveedor, cantidad_valida_para_unidad,
)
from core.models import DatosEmpresa
from core.permisos import chequear_permiso

from .models import (
    Compra, ItemCompra, EstadoCompra, TipoDocumentoCompra, MedioPagoCompra,
)
from .views import BuscarProductoAjax

PERMISO = 'usar_factura_inicial'

# ── Tipo de comprobante que "emitió" el proveedor ──────────────────
# Es lo mismo que se elige en un carrito de Compras normal, pero con la
# letra explícita (una factura de compra la tiene). `iva`:
#   'discriminado' → Factura A / Comprobante: neto + IVA + total aparte
#   'incluido'     → Factura B / C: solo total, IVA contenido
#   'sin'          → Remito: sin IVA
TIPOS_COMPROBANTE = {
    'factura_a':   {'label': 'Factura A',            'titulo': 'Factura',              'letra': 'A', 'iva': 'discriminado'},
    'factura_b':   {'label': 'Factura B',            'titulo': 'Factura',              'letra': 'B', 'iva': 'incluido'},
    'factura_c':   {'label': 'Factura C',            'titulo': 'Factura',              'letra': 'C', 'iva': 'incluido'},
    'remito':      {'label': 'Remito',               'titulo': 'Remito',               'letra': 'R', 'iva': 'sin'},
    'comprobante': {'label': 'Comprobante de compra', 'titulo': 'Comprobante de compra', 'letra': 'X', 'iva': 'discriminado'},
}
TIPO_COMPROBANTE_DEFECTO = 'factura_a'

# Medios de pago que se pueden anotar. SOLO informativo.
MEDIOS_PAGO_INFO = {
    'efectivo':      'Efectivo',
    'transferencia': 'Transferencia',
    'debito':        'Débito',
    'qr':            'QR',
    'credito':       'Tarjeta de crédito',
    'cheque':        'Cheque',
}


def _d(v, defecto='0'):
    try:
        return Decimal(str(v if v not in (None, '') else defecto))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(defecto)


def _q(v):
    return _d(v).quantize(Decimal('0.01'))


def _fmt_dec(d):
    """Decimal → string en punto fijo, sin notación científica ('1E+1')
    ni ceros de más. 10.00 → '10', 10.50 → '10.5'."""
    d = (d or Decimal('0'))
    s = f'{d.normalize():f}'
    return s if s not in ('-0', '0E-1') else '0'


def _fmt_fecha(iso):
    try:
        y, m, d = str(iso).split('-')
        return f'{int(d):02d}/{int(m):02d}/{y}'
    except (ValueError, AttributeError):
        return str(iso or '')


def _info_comprobante(tipo_key):
    return TIPOS_COMPROBANTE.get(tipo_key, TIPOS_COMPROBANTE[TIPO_COMPROBANTE_DEFECTO])


def _compra_fields_comprobante(tipo_key, alic_str, iva_incluido):
    """Traduce el tipo de comprobante de la herramienta a los campos que
    entiende `Compra` (para que Compra.total / neto / monto_iva calculen
    bien). Un Remito no discrimina IVA; una Factura A/Comprobante sí, y
    ahí respeta el check "los costos ya incluyen IVA"; una Factura B/C
    siempre lleva el IVA contenido en el total."""
    modo = _info_comprobante(tipo_key)['iva']
    if modo == 'sin':
        return dict(tipo_documento=TipoDocumentoCompra.REMITO,
                    alicuota_iva='', iva_incluido=True)
    if modo == 'incluido':
        return dict(tipo_documento=TipoDocumentoCompra.FACTURA,
                    alicuota_iva=alic_str, iva_incluido=True)
    return dict(
        tipo_documento=TipoDocumentoCompra.FACTURA,
        alicuota_iva=alic_str,
        iva_incluido=bool(iva_incluido),
    )


def _emisor_desde_proveedor(prov):
    """Encabezado del comprobante = EMISOR = el PROVEEDOR. Sale tal cual
    de su ficha; nunca se tipea a mano. Si la compra no tiene un único
    proveedor, queda genérico."""
    if prov is None:
        return {'razon_social': 'Proveedor inicial', 'cuit': '', 'domicilio': '',
                'telefono': '', 'email': '', 'condicion_iva': ''}
    return {
        'razon_social': prov.nombre,
        'cuit': prov.cuit,
        'domicilio': prov.direccion_completa,
        'telefono': prov.telefono,
        'email': prov.email,
        # Proveedor no guarda condición de IVA — se infiere del tipo.
        'condicion_iva': ('Monotributista' if prov.tipo == TipoProveedor.MONOTRIBUTISTA
                          else 'Responsable Inscripto'),
    }


def _receptor_empresa():
    """CLIENTE / RECEPTOR del comprobante = MI EMPRESA. Sale de
    DatosEmpresa (Configuración → Empresa). En esta compra yo soy el
    cliente: por eso mis datos van acá y no como emisor."""
    emp = DatosEmpresa.get_solo()
    return {
        'razon_social': emp.razon_social or emp.nombre_comercial or 'Mi empresa',
        'cuit': emp.cuit,
        'domicilio': emp.domicilio,
        'condicion_iva': emp.get_condicion_iva_display() if emp.condicion_iva else '',
    }


def _normalizar_pago(pago_raw):
    """
    Forma de pago para el PDF. SOLO informativa: cada línea es texto que
    se imprime. Para tarjeta/cheque se admiten datos de cuotas/banco.
    """
    pago_raw = pago_raw or {}
    lineas = []
    for l in (pago_raw.get('lineas') or []):
        medio = l.get('medio', 'efectivo')
        if medio not in MEDIOS_PAGO_INFO:
            medio = 'efectivo'
        try:
            monto = _q(l.get('monto')) if l.get('monto') not in (None, '') else None
        except Exception:
            monto = None

        # Detalle: se arma con lo que corresponda al medio.
        partes = []
        cuotas = l.get('cuotas')
        try:
            cuotas = int(cuotas) if cuotas not in (None, '') else None
        except (ValueError, TypeError):
            cuotas = None
        if medio in ('credito', 'cheque') and cuotas and cuotas > 1:
            partes.append(f'{cuotas} cuotas')
        interes = l.get('interes_pct')
        try:
            interes = Decimal(str(interes)) if interes not in (None, '') else None
        except Exception:
            interes = None
        if medio == 'credito' and interes and interes > 0:
            partes.append(f'interés {_fmt_dec(interes)}%')
        if medio == 'cheque':
            if l.get('banco'):
                partes.append(str(l['banco']).strip())
            if l.get('numero_cheque'):
                partes.append(f"cheque N° {str(l['numero_cheque']).strip()}")
            if l.get('fecha'):
                partes.append(_fmt_fecha(l['fecha']))
        libre = (l.get('detalle') or '').strip()
        if libre:
            partes.append(libre)
        detalle = ' · '.join(partes)

        if not (monto or detalle):
            continue
        lineas.append({
            'medio': medio,
            'medio_label': MEDIOS_PAGO_INFO.get(medio, 'Otro'),
            'monto': str(monto) if monto is not None else '',
            'detalle': detalle,
        })
    return {
        'condicion': (pago_raw.get('condicion') or '').strip(),
        'lineas': lineas,
    }


# ══════════════════════════════════════════════════════════════════
#  VISTAS
# ══════════════════════════════════════════════════════════════════

class FacturaInicialView(LoginRequiredMixin, TemplateView):
    template_name = 'compras/factura_inicial.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if not chequear_permiso(self.request.user, PERMISO):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_usar'] = True
        ctx['today'] = timezone.localtime().date().isoformat()
        ctx['listas_descuento'] = [
            {'nombre': l.nombre, 'porcentaje': str(l.porcentaje)}
            for l in ListaDescuento.objects.filter(activa=True).order_by('orden', 'nombre')
        ]
        ctx['alicuotas_iva'] = [{'valor': v, 'label': lbl} for v, lbl in AlicuotaIVA.choices]
        ctx['tipos_comprobante'] = [
            {'valor': k, 'label': v['label'], 'modo_iva': v['iva']}
            for k, v in TIPOS_COMPROBANTE.items()
        ]
        ctx['medios_pago'] = [{'valor': k, 'label': v} for k, v in MEDIOS_PAGO_INFO.items()]
        return ctx


class FacturaInicialHistorialView(LoginRequiredMixin, TemplateView):
    template_name = 'compras/factura_inicial_historial.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sin_permiso'] = not chequear_permiso(self.request.user, PERMISO)
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — búsquedas
# ══════════════════════════════════════════════════════════════════

class FacturaInicialBuscarProductoAjax(BuscarProductoAjax):
    permiso_requerido = PERMISO


class FacturaInicialBuscarProveedorAjax(LoginRequiredMixin, View):
    """GET ?q= → proveedores activos (para el selector del panel).
    Los datos completos del comprobante se leen server-side al armar
    el PDF, directo de la ficha — acá alcanza con pk/nombre/cuit."""

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        q = (request.GET.get('q') or '').strip()
        qs = Proveedor.objects.filter(activo=True).order_by('nombre')
        if q:
            qs = qs.filter(nombre__icontains=q)
        data = [
            {'pk': p.pk, 'nombre': p.nombre, 'cuit': p.cuit,
             'condicion_pago': p.get_condicion_pago_display()}
            for p in qs[:20]
        ]
        return JsonResponse({'results': data})


# ══════════════════════════════════════════════════════════════════
#  Armado del payload del PDF
# ══════════════════════════════════════════════════════════════════

def _payload_desde_compra(compra, doc):
    """dict que consume facturaInicialHtmlA4(...)."""
    tipo_key = doc.get('tipo_comprobante') or TIPO_COMPROBANTE_DEFECTO
    info = _info_comprobante(tipo_key)
    modo_iva = info['iva']
    alic = compra.alicuota_iva or '0'
    discrimina_iva = modo_iva == 'discriminado' and alic not in ('', '0')

    items_out, subtotal_bruto, descuento_monto = [], Decimal('0'), Decimal('0')
    for item in compra.items.select_related('producto', 'combinacion').all():
        base = item.cantidad * item.costo_unitario
        subtotal_bruto += base
        descuento_monto += base * (item.descuento_pct or Decimal('0')) / Decimal('100')
        detalle = (item.producto.nombre if item.producto
                   else (item.producto_nombre or '(producto eliminado)'))
        if item.nombre_combinacion_display:
            detalle = f'{detalle} — {item.nombre_combinacion_display}'
        items_out.append({
            'codigo': item.producto_codigo or (item.producto.codigo if item.producto else ''),
            'detalle': detalle,
            'cantidad': f'{item.cantidad.normalize():f}',
            'unidad': item.producto.get_unidad_medida_display() if item.producto else '',
            'precio_unitario': str(_q(item.costo_unitario)),
            'descuento_pct': (_fmt_dec(item.descuento_pct)
                              if item.descuento_pct else ''),
            'subtotal': str(_q(item.subtotal)),
            'referencia': item.referencia or '',
        })

    total = compra.total
    neto = compra.neto
    iva = compra.monto_iva
    if neto is None:
        neto, iva = total, Decimal('0')

    # Proveedor único de la compra (mismo criterio que Compra en el detalle)
    prov = None
    prov_ids = {i.proveedor_id for i in compra.items.all() if i.proveedor_id}
    if len(prov_ids) == 1:
        prov = compra.items.exclude(proveedor__isnull=True).first().proveedor

    return {
        'ok': True,
        'pk': compra.pk,
        'numero_interno': compra.numero,
        'comprobante': {
            'titulo': info['titulo'],
            'letra': info['letra'],
            'tipo': tipo_key,
            'numero': compra.numero_comprobante or '',
            'fecha': _fmt_fecha(compra.fecha.isoformat()),
            'discrimina_iva': discrimina_iva,
            'alicuota_pct': alic,
            'modo_iva': modo_iva,
        },
        'emisor': _emisor_desde_proveedor(prov),
        'receptor': _receptor_empresa(),
        'items': items_out,
        'totales': {
            'subtotal': str(_q(subtotal_bruto)),
            'descuento': str(_q(descuento_monto)),
            'neto': str(_q(neto)),
            'iva': str(_q(iva)),
            'total': str(_q(total)),
        },
        'pago': _normalizar_pago(doc.get('pago')),
        'observaciones': compra.notas or '',
        'incluir_leyenda': bool(doc.get('incluir_leyenda', True)),
    }


# ══════════════════════════════════════════════════════════════════
#  AJAX — crear (Compra real, sin caja)
# ══════════════════════════════════════════════════════════════════

class FacturaInicialCrearAjax(LoginRequiredMixin, View):

    @transaction.atomic
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        items_raw = body.get('items') or []
        doc = body.get('documento') or {}
        if not items_raw:
            return JsonResponse({'error': 'El comprobante no tiene ningún ítem.'}, status=400)

        tipo_key = doc.get('tipo_comprobante', TIPO_COMPROBANTE_DEFECTO)
        if tipo_key not in TIPOS_COMPROBANTE:
            return JsonResponse({'error': f'Tipo de comprobante inválido: {tipo_key}'}, status=400)
        modo_iva = _info_comprobante(tipo_key)['iva']

        alic_validas = {v for v, _ in AlicuotaIVA.choices}
        alic_str = str(doc.get('alicuota_iva', '21'))
        if modo_iva != 'sin' and alic_str not in alic_validas:
            return JsonResponse({'error': f'Alícuota de IVA inválida: {alic_str}'}, status=400)

        iva_incluido = bool(doc.get('iva_incluido', True))
        campos_comp = _compra_fields_comprobante(tipo_key, alic_str, iva_incluido)

        fecha_raw = (doc.get('fecha') or '').strip() or timezone.localtime().date().isoformat()
        try:
            fecha = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Fecha inválida.'}, status=400)

        proveedor = None
        if doc.get('proveedor_pk'):
            proveedor = Proveedor.objects.filter(pk=doc['proveedor_pk']).first()

        items_ok, errores = [], []
        for idx, raw in enumerate(items_raw, start=1):
            producto = Producto.objects.filter(pk=raw.get('producto_pk')).first()
            if not producto:
                errores.append(f'Ítem {idx}: producto no encontrado.')
                continue
            cantidad = _d(raw.get('cantidad'))
            costo = _d(raw.get('costo_unitario'))
            desc = _d(raw.get('descuento_pct'))
            if cantidad <= 0:
                errores.append(f'Ítem {idx}: la cantidad debe ser mayor a 0.')
                continue
            if not cantidad_valida_para_unidad(producto.unidad_medida, cantidad):
                errores.append(
                    f'Ítem {idx}: "{producto.nombre}" se cuenta por '
                    f'{producto.get_unidad_medida_display()} — la cantidad tiene que ser entera.')
                continue
            if costo < 0:
                errores.append(f'Ítem {idx}: el costo no puede ser negativo.')
                continue
            if desc < 0 or desc > 100:
                errores.append(f'Ítem {idx}: el descuento tiene que estar entre 0 y 100.')
                continue

            combinacion = None
            if producto.gestiona_variantes and raw.get('combinacion_pk'):
                combinacion = CombinacionVariante.objects.filter(
                    pk=raw['combinacion_pk'], producto=producto).first()
                if combinacion is None:
                    errores.append(f'Ítem {idx}: la combinación no existe o no pertenece al producto.')
                    continue

            fecha_venc = None
            fv = raw.get('fecha_vencimiento')
            if fv:
                try:
                    fecha_venc = datetime.strptime(fv, '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    fecha_venc = None
            if producto.es_perecedero and not fecha_venc:
                errores.append(f'Ítem {idx}: "{producto.nombre}" es perecedero — falta la fecha de vencimiento.')
                continue

            items_ok.append(dict(
                producto=producto, combinacion=combinacion, cantidad=cantidad,
                costo_unitario=costo, descuento_pct=desc,
                lista_descuento_nombre=(raw.get('lista_descuento_nombre') or ''),
                referencia=(raw.get('referencia') or '').strip(),
                fecha_vencimiento=fecha_venc,
            ))

        if errores:
            return JsonResponse({'error': ' | '.join(errores)}, status=400)

        # medio_pago (informativo, para el historial): el primero anotado
        pago_lineas = (doc.get('pago') or {}).get('lineas') or []
        medio_pago = ''
        for l in pago_lineas:
            if l.get('medio') in MedioPagoCompra.values:
                medio_pago = l['medio']
                break

        compra = Compra(
            fecha=fecha,
            estado=EstadoCompra.BORRADOR,
            es_carga_inicial=True,
            medio_pago=medio_pago,
            numero_comprobante=(doc.get('numero_comprobante') or '').strip(),
            notas=(doc.get('observaciones') or '').strip(),
            creado_por=request.user,
            **campos_comp,
        )
        compra.save()

        for d in items_ok:
            ItemCompra.objects.create(
                compra=compra, producto=d['producto'], proveedor=proveedor,
                combinacion=d['combinacion'], cantidad=d['cantidad'],
                costo_unitario=d['costo_unitario'], moneda='ARS',
                descuento_pct=d['descuento_pct'],
                lista_descuento_nombre=d['lista_descuento_nombre'],
                condicion_pago='contado', referencia=d['referencia'],
                fecha_vencimiento=d['fecha_vencimiento'],
            )

        # Confirmar SIN pago: stock + lotes + costo/precio; cero caja.
        try:
            compra.confirmar(medio_pago=medio_pago, pagos=None)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        payload = _payload_desde_compra(compra, doc)
        compra.factura_inicial_datos = payload
        compra.save(update_fields=['factura_inicial_datos'])
        return JsonResponse(payload)


# ══════════════════════════════════════════════════════════════════
#  AJAX — historial de la herramienta
# ══════════════════════════════════════════════════════════════════

class FacturaInicialListarAjax(LoginRequiredMixin, View):
    PAGE_SIZE = 20

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = (Compra.objects
              .filter(es_carga_inicial=True,
                      estado__in=[EstadoCompra.CONFIRMADA, EstadoCompra.ANULADA])
              .prefetch_related('items__producto', 'items__proveedor')
              .order_by('-fecha', '-fecha_alta'))

        q = (request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(numero__icontains=q) | Q(numero_comprobante__icontains=q)
                           | Q(notas__icontains=q))

        try:
            page = max(1, int(request.GET.get('page', 1)))
        except ValueError:
            page = 1

        total = qs.count()
        off = (page - 1) * self.PAGE_SIZE
        filas = []
        for c in qs[off:off + self.PAGE_SIZE]:
            prov_ids = {i.proveedor_id for i in c.items.all() if i.proveedor_id}
            prov_nombre = ''
            if len(prov_ids) == 1:
                p = c.items.exclude(proveedor__isnull=True).first()
                prov_nombre = p.proveedor.nombre if p and p.proveedor else ''

            datos = c.factura_inicial_datos or {}
            comp_info = datos.get('comprobante') or {}
            titulo = comp_info.get('titulo') or c.get_tipo_documento_display()
            letra = comp_info.get('letra') or ''
            comp = f'{titulo} {letra}'.strip() if letra not in ('', 'R', 'X') else titulo
            num_comp = comp_info.get('numero') or c.numero_comprobante
            if num_comp:
                comp = f'{comp} · {num_comp}'

            filas.append({
                'pk': c.pk,
                'numero': c.numero,
                'fecha': c.fecha.strftime('%d/%m/%Y'),
                'estado': c.estado,
                'estado_label': c.get_estado_display(),
                'comprobante': comp,
                'proveedor': prov_nombre,
                'items': c.items.count(),
                'total': str(c.total),
            })

        return JsonResponse({
            'rows': filas, 'page': page, 'total': total,
            'has_more': off + self.PAGE_SIZE < total,
        })


class FacturaInicialReimprimirAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        compra = get_object_or_404(Compra, pk=request.GET.get('pk'), es_carga_inicial=True)
        datos = compra.factura_inicial_datos
        if not datos:
            return JsonResponse({'error': 'Esta factura inicial no tiene datos de PDF guardados.'}, status=404)
        datos = dict(datos)
        datos['ok'] = True
        return JsonResponse(datos)


class FacturaInicialAnularAjax(LoginRequiredMixin, View):
    @transaction.atomic
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        try:
            pk = json.loads(request.body).get('pk')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)
        compra = get_object_or_404(Compra.objects.select_for_update(),
                                   pk=pk, es_carga_inicial=True)
        try:
            compra.anular()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        return JsonResponse({'ok': True, 'estado': compra.estado,
                             'estado_label': compra.get_estado_display()})


class FacturaInicialEliminarAjax(LoginRequiredMixin, View):
    @transaction.atomic
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        try:
            pk = json.loads(request.body).get('pk')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)
        compra = get_object_or_404(Compra.objects.select_for_update(),
                                   pk=pk, es_carga_inicial=True)
        try:
            compra.delete()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        return JsonResponse({'ok': True})
