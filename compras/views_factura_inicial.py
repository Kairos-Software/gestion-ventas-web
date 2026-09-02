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
    _costo_para_lote,
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


def _tipo_key_de_compra(compra):
    """Clave de TIPOS_COMPROBANTE guardada al crear/editar la factura
    inicial (en factura_inicial_datos). Fallback razonable si falta."""
    datos = compra.factura_inicial_datos or {}
    tipo = (datos.get('comprobante') or {}).get('tipo')
    if tipo in TIPOS_COMPROBANTE:
        return tipo
    # Sin dato guardado: reconstruir lo mejor posible desde los campos.
    if compra.tipo_documento == TipoDocumentoCompra.REMITO:
        return 'remito'
    if compra.alicuota_iva and not compra.iva_incluido:
        return 'factura_a'
    return TIPO_COMPROBANTE_DEFECTO


def _comprobante_label(compra):
    """"Factura A · 0001-00012345" para las filas del historial."""
    datos = compra.factura_inicial_datos or {}
    comp_info = datos.get('comprobante') or {}
    titulo = comp_info.get('titulo') or compra.get_tipo_documento_display()
    letra = comp_info.get('letra') or ''
    txt = f'{titulo} {letra}'.strip() if letra not in ('', 'R', 'X') else titulo
    num = comp_info.get('numero') or compra.numero_comprobante
    return f'{txt} · {num}' if num else txt


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
        if not ctx['sin_permiso']:
            # Para el modal "Editar datos" de una factura ya confirmada.
            ctx['tipos_comprobante'] = [
                {'valor': k, 'label': v['label'], 'modo_iva': v['iva']}
                for k, v in TIPOS_COMPROBANTE.items()
            ]
            ctx['alicuotas_iva'] = [
                {'valor': v, 'label': lbl} for v, lbl in AlicuotaIVA.choices
            ]
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

        # Filtro por PRODUCTO: solo las facturas iniciales que lo contienen.
        prod_q = (request.GET.get('producto') or '').strip()
        if prod_q:
            qs = qs.filter(
                Q(items__producto__nombre__icontains=prod_q)
                | Q(items__producto__codigo__icontains=prod_q)
                | Q(items__producto_nombre__icontains=prod_q)
                | Q(items__producto_codigo__icontains=prod_q)
            ).distinct()

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
            prov_pk = ''
            if len(prov_ids) == 1:
                p = c.items.exclude(proveedor__isnull=True).first()
                if p and p.proveedor:
                    prov_nombre = p.proveedor.nombre
                    prov_pk = p.proveedor_id

            # Si se filtró por producto, adjuntar las líneas que matchean
            # para mostrarlas directo en la fila (con su cantidad).
            items_match = []
            if prod_q:
                pql = prod_q.lower()
                for it in c.items.all():
                    nom = (it.producto.nombre if it.producto
                           else it.producto_nombre) or ''
                    cod = (it.producto.codigo if it.producto
                           else it.producto_codigo) or ''
                    if pql in nom.lower() or pql in cod.lower():
                        items_match.append({
                            'item_pk': it.pk,
                            'producto': it.nombre_producto_display,
                            'codigo': cod,
                            'variante': it.nombre_combinacion_display,
                            'cantidad': _fmt_dec(it.cantidad),
                            'costo': str(_q(it.costo_unitario)),
                        })

            filas.append({
                'pk': c.pk,
                'numero': c.numero,
                'fecha': c.fecha.strftime('%d/%m/%Y'),
                'estado': c.estado,
                'estado_label': c.get_estado_display(),
                'comprobante': _comprobante_label(c),
                'proveedor': prov_nombre,
                'items': c.items.count(),
                'total': str(c.total),
                'items_match': items_match,
                # Valores para pre-cargar el modal "Editar datos".
                'cabecera': {
                    'fecha': c.fecha.isoformat(),
                    'proveedor_pk': str(prov_pk or ''),
                    'proveedor_nombre': prov_nombre,
                    'tipo_comprobante': _tipo_key_de_compra(c),
                    'numero_comprobante': c.numero_comprobante or '',
                    'alicuota_iva': c.alicuota_iva or '21',
                    'iva_incluido': bool(c.iva_incluido),
                    'observaciones': c.notas or '',
                },
            })

        return JsonResponse({
            'rows': filas, 'page': page, 'total': total,
            'has_more': off + self.PAGE_SIZE < total,
            'filtro_producto': prod_q,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — ver / corregir los ítems de una factura inicial
# ══════════════════════════════════════════════════════════════════

def _serializar_item_fi(it, compra):
    """Una línea de la factura inicial para el detalle desplegable."""
    lote = it.lotes.filter(activo=True).first()
    consumido = Decimal('0')
    if lote is not None:
        consumido = lote.cantidad_inicial - lote.cantidad_actual
    prod = it.producto
    return {
        'item_pk': it.pk,
        'producto': it.nombre_producto_display,
        'codigo': it.producto_codigo or (prod.codigo if prod else ''),
        'variante': it.nombre_combinacion_display,
        'unidad': prod.get_unidad_medida_display() if prod else '',
        'entero': bool(prod and not cantidad_valida_para_unidad(
            prod.unidad_medida, Decimal('0.5'))),
        'cantidad': _fmt_dec(it.cantidad),
        'costo': str(_q(it.costo_unitario)),
        'subtotal': str(it.subtotal),
        'consumido': _fmt_dec(consumido) if consumido > 0 else '',
        'editable': (compra.estado == EstadoCompra.CONFIRMADA
                     and it.producto_id is not None),
    }


class FacturaInicialItemsAjax(LoginRequiredMixin, View):
    """GET ?pk= → los ítems de una factura inicial (para el desplegable)."""

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        compra = get_object_or_404(
            Compra.objects.prefetch_related('items__producto', 'items__combinacion',
                                            'items__lotes'),
            pk=request.GET.get('pk'), es_carga_inicial=True)
        items = [_serializar_item_fi(it, compra)
                 for it in compra.items.all().order_by('id')]
        return JsonResponse({
            'ok': True,
            'estado': compra.estado,
            'total': str(compra.total),
            'items': items,
        })


class FacturaInicialCorregirItemAjax(LoginRequiredMixin, View):
    """
    POST {item_pk, cantidad, costo}

    Corrige UNA línea de una factura inicial CONFIRMADA sin anular todo
    el comprobante:
      - ajusta ItemCompra.cantidad / costo_unitario
      - ajusta el LoteCompra de esa carga (cantidad + costo), respetando
        lo que ya se haya consumido/vendido de ese lote
      - ajusta el stock del producto vía MovimientoStock (queda auditado:
        quién, cuándo, "Corrección FIN-xxxx: 9000 -> 90")
      - recalcula el total de la factura y el costo/precio del producto
      - regenera el PDF (factura_inicial_datos)
    """

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        try:
            with transaction.atomic():
                item = (ItemCompra.objects
                        .select_related('compra', 'producto', 'combinacion')
                        .filter(pk=body.get('item_pk'),
                                compra__es_carga_inicial=True)
                        .first())
                if item is None:
                    raise ValueError('No se encontró la línea.')
                # El lock va sobre la Compra (serializa correcciones
                # concurrentes de la misma factura); no sobre el ítem, que
                # con select_related de FKs nulables rompe el FOR UPDATE.
                compra = Compra.objects.select_for_update().get(pk=item.compra_id)
                if compra.estado != EstadoCompra.CONFIRMADA:
                    raise ValueError('Solo se corrigen facturas iniciales '
                                     'confirmadas.')
                producto = item.producto
                if producto is None:
                    raise ValueError('El producto de esta línea fue eliminado.')

                nueva_cant = _d(body.get('cantidad'))
                nuevo_costo = _d(body.get('costo'))
                if nueva_cant <= 0:
                    raise ValueError('La cantidad debe ser mayor a 0. Usá '
                                     '"Quitar" para eliminar la línea.')
                if not cantidad_valida_para_unidad(producto.unidad_medida,
                                                   nueva_cant):
                    raise ValueError(
                        f'"{producto.nombre}" se cuenta por '
                        f'{producto.get_unidad_medida_display()} — la cantidad '
                        f'tiene que ser entera.')
                if nuevo_costo < 0:
                    raise ValueError('El costo no puede ser negativo.')

                vieja_cant = item.cantidad
                delta = nueva_cant - vieja_cant

                lotes = list(item.lotes.filter(activo=True))
                if len(lotes) > 1:
                    raise ValueError('Esta línea tiene más de un lote — '
                                     'corregila desde Inventario.')
                consumido = Decimal('0')
                if lotes:
                    consumido = lotes[0].cantidad_inicial - lotes[0].cantidad_actual
                    if nueva_cant < consumido:
                        raise ValueError(
                            f'De esta carga ya se usaron/vendieron '
                            f'{_fmt_dec(consumido)} unidades — no la podés dejar '
                            f'en menos de eso.')

                # Guarda a nivel stock (mensaje claro antes de MovimientoStock)
                if delta < 0 and not producto.permite_stock_negativo:
                    ref = (item.combinacion.stock_actual if item.combinacion_id
                           else producto.stock_actual)
                    if ref + delta < 0:
                        raise ValueError(
                            f'El stock actual es {_fmt_dec(ref)} — no podés bajar '
                            f'esta carga en más de eso (ya se movió el resto).')

                # ── aplicar ──
                item.cantidad = nueva_cant
                item.costo_unitario = _q(nuevo_costo)
                item.save(update_fields=['cantidad', 'costo_unitario'])

                if lotes:
                    lote = lotes[0]
                    lote.cantidad_inicial = nueva_cant
                    lote.cantidad_actual = nueva_cant - consumido
                    lote.costo_unitario = _costo_para_lote(item)
                    lote.save(update_fields=['cantidad_inicial',
                                             'cantidad_actual', 'costo_unitario'])

                if producto.gestiona_stock and delta != 0:
                    from productos.models import MovimientoStock, TipoMovimiento
                    entrada = delta > 0
                    mov = MovimientoStock(
                        producto=producto,
                        tipo=(TipoMovimiento.AJUSTE_POS if entrada
                              else TipoMovimiento.AJUSTE_NEG),
                        cantidad=abs(delta),
                        motivo=(f'Corrección {compra.numero}: '
                                f'{_fmt_dec(vieja_cant)} -> {_fmt_dec(nueva_cant)}'),
                        referencia=compra.numero,
                        usuario=request.user,
                    )
                    mov.save()  # ajusta producto.stock_actual + guarda
                    if item.combinacion_id:
                        comb = CombinacionVariante.objects.select_for_update().get(
                            pk=item.combinacion_id)
                        comb.stock_actual = comb.stock_actual + delta
                        comb.save(update_fields=['stock_actual'])
                        producto.sincronizar_stock_desde_combinaciones()

                compra.calcular_total()
                producto.actualizar_costo_y_precio()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        # Regenerar el payload del PDF con los datos ya corregidos.
        compra.refresh_from_db()
        datos = compra.factura_inicial_datos or {}
        doc = {
            'tipo_comprobante': ((datos.get('comprobante') or {}).get('tipo')
                                 or TIPO_COMPROBANTE_DEFECTO),
            'incluir_leyenda': datos.get('incluir_leyenda', True),
        }
        payload = _payload_desde_compra(compra, doc)
        if datos.get('pago'):
            payload['pago'] = datos['pago']  # ya normalizado, dejarlo tal cual
        compra.factura_inicial_datos = payload
        compra.save(update_fields=['factura_inicial_datos'])

        producto.refresh_from_db()
        item.refresh_from_db()
        return JsonResponse({
            'ok': True,
            'total': str(compra.total),
            'stock_actual': str(producto.stock_actual),
            'item': _serializar_item_fi(item, compra),
        })


class FacturaInicialQuitarItemAjax(LoginRequiredMixin, View):
    """
    POST {item_pk} — saca una línea entera de una factura inicial
    CONFIRMADA (producto cargado por error). Revierte su stock (con
    MovimientoStock de auditoría), borra su lote y el ítem, y recalcula.
    No se puede si de esa carga ya se consumió/vendió algo, ni si es la
    única línea (para eso está Anular / Eliminar la factura entera).
    """

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        try:
            with transaction.atomic():
                item = (ItemCompra.objects
                        .select_related('compra', 'producto', 'combinacion')
                        .filter(pk=body.get('item_pk'),
                                compra__es_carga_inicial=True)
                        .first())
                if item is None:
                    raise ValueError('No se encontró la línea.')
                # El lock va sobre la Compra (serializa correcciones
                # concurrentes de la misma factura); no sobre el ítem, que
                # con select_related de FKs nulables rompe el FOR UPDATE.
                compra = Compra.objects.select_for_update().get(pk=item.compra_id)
                if compra.estado != EstadoCompra.CONFIRMADA:
                    raise ValueError('Solo se corrigen facturas iniciales '
                                     'confirmadas.')
                if compra.items.count() <= 1:
                    raise ValueError('Es la única línea — usá "Anular" o '
                                     '"Eliminar" la factura entera.')

                producto = item.producto
                cant = item.cantidad
                for lote in item.lotes.filter(activo=True):
                    if lote.cantidad_actual < lote.cantidad_inicial:
                        raise ValueError('De esta carga ya se usó/vendió parte '
                                         '— no se puede quitar la línea.')

                if producto is not None and producto.gestiona_stock and cant > 0:
                    if not producto.permite_stock_negativo:
                        ref = (item.combinacion.stock_actual
                               if item.combinacion_id else producto.stock_actual)
                        if ref - cant < 0:
                            raise ValueError(
                                f'El stock actual es {_fmt_dec(ref)} — no alcanza '
                                f'para revertir esta carga.')
                    from productos.models import MovimientoStock, TipoMovimiento
                    mov = MovimientoStock(
                        producto=producto,
                        tipo=TipoMovimiento.AJUSTE_NEG,
                        cantidad=cant,
                        motivo=f'Quitado de {compra.numero} (cargado por error)',
                        referencia=compra.numero,
                        usuario=request.user,
                    )
                    mov.save()
                    if item.combinacion_id:
                        comb = CombinacionVariante.objects.select_for_update().get(
                            pk=item.combinacion_id)
                        comb.stock_actual = comb.stock_actual - cant
                        comb.save(update_fields=['stock_actual'])
                        producto.sincronizar_stock_desde_combinaciones()

                item.delete()  # borra el/los LoteCompra en cascada
                compra.calcular_total()
                if producto is not None:
                    producto.actualizar_costo_y_precio()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        compra.refresh_from_db()
        datos = compra.factura_inicial_datos or {}
        doc = {
            'tipo_comprobante': ((datos.get('comprobante') or {}).get('tipo')
                                 or TIPO_COMPROBANTE_DEFECTO),
            'incluir_leyenda': datos.get('incluir_leyenda', True),
        }
        payload = _payload_desde_compra(compra, doc)
        if datos.get('pago'):
            payload['pago'] = datos['pago']
        compra.factura_inicial_datos = payload
        compra.save(update_fields=['factura_inicial_datos'])

        return JsonResponse({'ok': True, 'total': str(compra.total),
                             'items': compra.items.count()})


class FacturaInicialEditarCabeceraAjax(LoginRequiredMixin, View):
    """
    POST {pk, fecha, proveedor_pk, tipo_comprobante, numero_comprobante,
          alicuota_iva, iva_incluido, observaciones}

    Corrige los DATOS de una factura inicial CONFIRMADA (se cargó mal el
    proveedor, la fecha, el tipo de comprobante...) sin anular ni tocar
    cantidades de stock. Cuida los efectos colaterales:

      - `fecha` se propaga a `LoteCompra.fecha_compra` de cada lote de la
        carga → cambia la fecha que se ve en Inventario y el orden de
        salida (FIFO) para ventas FUTURAS. Lo ya vendido no se toca
        (queda congelado en ConsumoLoteVenta).
      - `proveedor` se aplica a todos los ItemCompra (uno por factura) y
        a su snapshot de nombre.
      - cambiar tipo de comprobante / alícuota / "IVA incluido" cambia
        cómo se deriva el costo del lote (ver _costo_para_lote): se
        recalcula `LoteCompra.costo_unitario` y el costo/precio del
        producto. Los márgenes de ventas ya hechas no cambian.
      - se recalcula el total y se regenera el PDF (factura_inicial_datos).
    """

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        tipo_key = body.get('tipo_comprobante', TIPO_COMPROBANTE_DEFECTO)
        if tipo_key not in TIPOS_COMPROBANTE:
            return JsonResponse({'error': f'Tipo de comprobante inválido: {tipo_key}'}, status=400)
        modo_iva = _info_comprobante(tipo_key)['iva']

        alic_validas = {v for v, _ in AlicuotaIVA.choices}
        alic_str = str(body.get('alicuota_iva', '21'))
        if modo_iva != 'sin' and alic_str not in alic_validas:
            return JsonResponse({'error': f'Alícuota de IVA inválida: {alic_str}'}, status=400)

        fecha_raw = (body.get('fecha') or '').strip()
        try:
            fecha = datetime.strptime(fecha_raw, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Fecha inválida.'}, status=400)
        if fecha > timezone.localtime().date():
            return JsonResponse({'error': 'La fecha no puede ser futura.'}, status=400)

        proveedor = None
        if body.get('proveedor_pk'):
            proveedor = Proveedor.objects.filter(pk=body['proveedor_pk']).first()
            if proveedor is None:
                return JsonResponse({'error': 'El proveedor elegido ya no existe.'}, status=400)

        iva_incluido = bool(body.get('iva_incluido', True))
        campos_comp = _compra_fields_comprobante(tipo_key, alic_str, iva_incluido)

        try:
            with transaction.atomic():
                compra = get_object_or_404(
                    Compra.objects.select_for_update(),
                    pk=body.get('pk'), es_carga_inicial=True)
                if compra.estado != EstadoCompra.CONFIRMADA:
                    raise ValueError('Solo se pueden editar facturas iniciales confirmadas.')

                compra.fecha = fecha
                compra.numero_comprobante = (body.get('numero_comprobante') or '').strip()
                compra.notas = (body.get('observaciones') or '').strip()
                compra.tipo_documento = campos_comp['tipo_documento']
                compra.alicuota_iva = campos_comp['alicuota_iva']
                compra.iva_incluido = campos_comp['iva_incluido']
                compra.save(update_fields=['fecha', 'numero_comprobante', 'notas',
                                           'tipo_documento', 'alicuota_iva', 'iva_incluido'])

                productos_afectados = {}
                for item in compra.items.select_related('producto').all():
                    item.compra = compra  # que _costo_para_lote vea los campos nuevos
                    item.proveedor = proveedor
                    item.proveedor_nombre = proveedor.nombre if proveedor else ''
                    item.save(update_fields=['proveedor', 'proveedor_nombre'])
                    if item.producto_id:
                        productos_afectados[item.producto_id] = item.producto
                    for lote in item.lotes.filter(activo=True):
                        lote.fecha_compra = fecha
                        lote.costo_unitario = _costo_para_lote(item)
                        lote.save(update_fields=['fecha_compra', 'costo_unitario'])

                compra.calcular_total()
                for prod in productos_afectados.values():
                    prod.actualizar_costo_y_precio()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        compra.refresh_from_db()
        datos = compra.factura_inicial_datos or {}
        doc = {'tipo_comprobante': tipo_key,
               'incluir_leyenda': datos.get('incluir_leyenda', True)}
        payload = _payload_desde_compra(compra, doc)
        if datos.get('pago'):
            payload['pago'] = datos['pago']
        compra.factura_inicial_datos = payload
        compra.save(update_fields=['factura_inicial_datos'])

        return JsonResponse({
            'ok': True,
            'fecha': compra.fecha.strftime('%d/%m/%Y'),
            'comprobante': _comprobante_label(compra),
            'proveedor': proveedor.nombre if proveedor else '',
            'total': str(compra.total),
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
