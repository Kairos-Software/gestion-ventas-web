# ══════════════════════════════════════════════════════════════════
#  views_transacciones.py
#  AJAX views para el módulo de Transacciones de Caja Grande.
#
#  El usuario elige directamente las CuentaCaja reales (origen y
#  destino) que ya carga desde Configuración — no hay contenedores
#  fijos ni get_or_create automático acá. Se excluyen las cuentas de
#  crédito: una transacción mueve plata real entre cuentas, y una
#  tarjeta de crédito no tiene "saldo disponible" para mover.
# ══════════════════════════════════════════════════════════════════

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.views import View
from django.views.generic import TemplateView

from .models import (
    CuentaCaja,
    TransaccionCaja,
    TipoTransaccion,
    TipoCaja,
    CUENTA_EFECTIVO_DEFAULT_NOMBRE,
    asegurar_cuentas_efectivo,
)


def _cuentas_disponibles():
    """Cuentas de caja grande utilizables en una transacción (sin crédito)."""
    asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE)
    return (
        CuentaCaja.objects
        .filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False)
        .order_by('orden', 'nombre')
    )


def _resolver_cuenta(pk):
    """Devuelve la CuentaCaja si es válida para transacciones, o None."""
    if not pk:
        return None
    return _cuentas_disponibles().filter(pk=pk).first()


# ──────────────────────────────────────────────────────────────────
#  Helpers internos
# ──────────────────────────────────────────────────────────────────

def _parse_decimal(value, field_name):
    try:
        d = Decimal(str(value).replace(',', '.'))
        if d < 0:
            return None, f'{field_name} no puede ser negativo.'
        return d, None
    except (InvalidOperation, TypeError, ValueError):
        return None, f'{field_name} tiene un valor inválido.'


def _json_error(msg, status=400):
    return JsonResponse({'ok': False, 'error': msg}, status=status)


def _json_ok(data=None):
    payload = {'ok': True}
    if data:
        payload.update(data)
    return JsonResponse(payload)


def _serializar_transaccion(t):
    return {
        'id':                t.pk,
        'tipo':              t.tipo,
        'tipo_label':        t.get_tipo_display(),
        'cuenta_origen':     str(t.cuenta_origen),
        'cuenta_destino':    str(t.cuenta_destino),
        'monto_origen':      str(t.monto_origen),
        'monto_destino':     str(t.monto_destino),
        'tipo_cambio':       str(t.tipo_cambio)  if t.tipo_cambio  else None,
        'costo_extra':       str(t.costo_extra)  if t.costo_extra  else None,
        'descripcion_costo': t.descripcion_costo,
        'fecha':             t.fecha.strftime('%Y-%m-%d'),
        'descripcion':       t.descripcion,
        'creado_por':        t.creado_por.get_full_name() or t.creado_por.username if t.creado_por else '—',
        'fecha_alta':        t.fecha_alta.strftime('%d/%m/%Y %H:%M'),
    }


# ──────────────────────────────────────────────────────────────────
#  Página principal
# ──────────────────────────────────────────────────────────────────

class TransaccionesPageView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/transacciones.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuentas_json'] = json.dumps([
            {
                'pk': c.pk,
                'nombre': c.nombre,
                'moneda': c.moneda,
                'es_efectivo': c.nombre == CUENTA_EFECTIVO_DEFAULT_NOMBRE,
                'saldo': str(c.saldo),
            }
            for c in _cuentas_disponibles()
        ])
        return ctx


# ──────────────────────────────────────────────────────────────────
#  Calcular preview (sin guardar)
# ──────────────────────────────────────────────────────────────────

class CalcularTransaccionAjax(LoginRequiredMixin, View):
    """
    POST /caja/transacciones/calcular/
    {
        "tipo":           "compra_divisa",
        "monto_origen":   15000,
        "tipo_cambio":    1200,
        "costo_extra":    450
    }
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _json_error('Body JSON inválido.')

        tipo = data.get('tipo', '')
        if tipo not in TipoTransaccion.values:
            return _json_error('Tipo de transacción inválido.')

        monto_origen, err = _parse_decimal(data.get('monto_origen', 0), 'Monto origen')
        if err:
            return _json_error(err)

        costo_extra = Decimal('0')
        if data.get('costo_extra'):
            costo_extra, err = _parse_decimal(data['costo_extra'], 'Costo extra')
            if err:
                return _json_error(err)

        tipo_cambio   = None
        monto_destino = monto_origen

        if tipo in (TipoTransaccion.COMPRA_DIVISA, TipoTransaccion.VENTA_DIVISA):
            if not data.get('tipo_cambio'):
                return _json_error('El tipo de cambio es requerido.')
            tipo_cambio, err = _parse_decimal(data['tipo_cambio'], 'Tipo de cambio')
            if err:
                return _json_error(err)
            if tipo_cambio == 0:
                return _json_error('El tipo de cambio no puede ser 0.')
            monto_destino = (monto_origen / tipo_cambio).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        return _json_ok({
            'monto_destino':  str(monto_destino),
            'total_egresado': str(monto_origen + costo_extra),
            'tipo_cambio':    str(tipo_cambio) if tipo_cambio else None,
        })


# ──────────────────────────────────────────────────────────────────
#  Crear transacción
# ──────────────────────────────────────────────────────────────────

class CrearTransaccionAjax(LoginRequiredMixin, View):
    """
    POST /caja/transacciones/crear/
    {
        "tipo":                "compra_divisa",
        "cuenta_origen_pk":    3,
        "cuenta_destino_pk":   7,
        "monto_origen":        15000,
        "tipo_cambio":         1200,
        "costo_extra":         450,
        "descripcion_costo":   "Impuesto PAIS 30%",
        "fecha":               "2026-07-01",
        "descripcion":         "Compra de dólares"
    }
    """

    @transaction.atomic
    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _json_error('Body JSON inválido.')

        # ── Tipo ──────────────────────────────────────────────────
        tipo = data.get('tipo', '')
        if tipo not in TipoTransaccion.values:
            return _json_error('Tipo de transacción inválido.')

        # ── Cuentas ───────────────────────────────────────────────
        cuenta_origen = _resolver_cuenta(data.get('cuenta_origen_pk'))
        cuenta_destino = _resolver_cuenta(data.get('cuenta_destino_pk'))

        if not cuenta_origen:
            return _json_error('Elegí una cuenta de origen válida.')
        if not cuenta_destino:
            return _json_error('Elegí una cuenta de destino válida.')
        if cuenta_origen.pk == cuenta_destino.pk:
            return _json_error('El origen y el destino no pueden ser la misma cuenta.')

        moneda_origen  = cuenta_origen.moneda
        moneda_destino = cuenta_destino.moneda

        if tipo in (TipoTransaccion.DEPOSITO, TipoTransaccion.EXTRACCION):
            if moneda_origen != moneda_destino:
                return _json_error(
                    f'Para {TipoTransaccion(tipo).label} el origen y destino '
                    f'deben ser de la misma moneda.'
                )

        if tipo == TipoTransaccion.DEPOSITO:
            if cuenta_origen.nombre != CUENTA_EFECTIVO_DEFAULT_NOMBRE:
                return _json_error('Un depósito sale de la cuenta Efectivo.')
            if cuenta_destino.nombre == CUENTA_EFECTIVO_DEFAULT_NOMBRE:
                return _json_error('El destino de un depósito no puede ser Efectivo.')

        if tipo == TipoTransaccion.EXTRACCION:
            if cuenta_origen.nombre == CUENTA_EFECTIVO_DEFAULT_NOMBRE:
                return _json_error('El origen de una extracción no puede ser Efectivo.')
            if cuenta_destino.nombre != CUENTA_EFECTIVO_DEFAULT_NOMBRE:
                return _json_error('Una extracción entra a la cuenta Efectivo.')

        if tipo in (TipoTransaccion.COMPRA_DIVISA, TipoTransaccion.VENTA_DIVISA):
            if moneda_origen == moneda_destino:
                return _json_error(
                    'Para operaciones con divisas, origen y destino deben '
                    'tener monedas distintas.'
                )

        # ── Montos ────────────────────────────────────────────────
        monto_origen, err = _parse_decimal(data.get('monto_origen', 0), 'Monto origen')
        if err:
            return _json_error(err)
        if monto_origen <= 0:
            return _json_error('El monto debe ser mayor a 0.')

        tipo_cambio   = None
        costo_extra   = None
        monto_destino = monto_origen

        if tipo in (TipoTransaccion.COMPRA_DIVISA, TipoTransaccion.VENTA_DIVISA):
            tipo_cambio, err = _parse_decimal(data.get('tipo_cambio', 0), 'Tipo de cambio')
            if err:
                return _json_error(err)
            if tipo_cambio <= 0:
                return _json_error('El tipo de cambio debe ser mayor a 0.')
            monto_destino = (monto_origen / tipo_cambio).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        if data.get('costo_extra'):
            costo_extra, err = _parse_decimal(data['costo_extra'], 'Costo extra')
            if err:
                return _json_error(err)
            if costo_extra == 0:
                costo_extra = None

        # ── Fecha ─────────────────────────────────────────────────
        fecha_str = data.get('fecha', '')
        if not fecha_str:
            return _json_error('La fecha es requerida.')
        try:
            from datetime import date
            fecha = date.fromisoformat(fecha_str)
        except ValueError:
            return _json_error('Fecha inválida. Usar formato YYYY-MM-DD.')

        # ── Saldo suficiente ──────────────────────────────────────
        # Chequeo justo antes de crear, para achicar la ventana de
        # concurrencia (dos transacciones cargándose casi al mismo
        # tiempo podrían igual dejar el saldo en negativo, pero no
        # hay uso concurrente real en este sistema).
        total_a_debitar = monto_origen + (costo_extra or Decimal('0'))
        if cuenta_origen.saldo < total_a_debitar:
            return _json_error(
                f'Saldo insuficiente en {cuenta_origen.nombre}: '
                f'disponible {cuenta_origen.saldo}, se necesitan {total_a_debitar}.'
            )

        # ── Crear ─────────────────────────────────────────────────
        transaccion = TransaccionCaja.objects.create(
            tipo              = tipo,
            cuenta_origen     = cuenta_origen,
            cuenta_destino    = cuenta_destino,
            monto_origen      = monto_origen,
            monto_destino     = monto_destino,
            tipo_cambio       = tipo_cambio,
            costo_extra       = costo_extra,
            descripcion_costo = data.get('descripcion_costo', '').strip(),
            fecha             = fecha,
            descripcion       = data.get('descripcion', '').strip(),
            creado_por        = request.user,
        )
        transaccion.ejecutar()

        return _json_ok({
            'transaccion': _serializar_transaccion(transaccion),
            'mensaje':     f'{transaccion.get_tipo_display()} registrada correctamente.',
        })


# ──────────────────────────────────────────────────────────────────
#  Listar transacciones
# ──────────────────────────────────────────────────────────────────

class ListarTransaccionesAjax(LoginRequiredMixin, View):
    """
    GET /caja/transacciones/listar/
    Parámetros opcionales: tipo, desde, hasta, page, page_size
    """

    def get(self, request):
        qs = (
            TransaccionCaja.objects
            .select_related('cuenta_origen', 'cuenta_destino', 'creado_por')
            .filter(cuenta_origen__caja=TipoCaja.GRANDE)
            .order_by('-fecha', '-fecha_alta')
        )

        tipo = request.GET.get('tipo')
        if tipo and tipo in TipoTransaccion.values:
            qs = qs.filter(tipo=tipo)

        desde = request.GET.get('desde')
        hasta = request.GET.get('hasta')
        try:
            from datetime import date
            if desde:
                qs = qs.filter(fecha__gte=date.fromisoformat(desde))
            if hasta:
                qs = qs.filter(fecha__lte=date.fromisoformat(hasta))
        except ValueError:
            pass

        try:
            page      = max(1, int(request.GET.get('page', 1)))
            page_size = min(100, max(1, int(request.GET.get('page_size', 20))))
        except (ValueError, TypeError):
            page, page_size = 1, 20

        total  = qs.count()
        offset = (page - 1) * page_size
        items  = list(qs[offset: offset + page_size])

        return _json_ok({
            'transacciones': [_serializar_transaccion(t) for t in items],
            'total':         total,
            'page':          page,
            'page_size':     page_size,
            'paginas':       -(-total // page_size),
        })


# ──────────────────────────────────────────────────────────────────
#  Detalle
# ──────────────────────────────────────────────────────────────────

class DetalleTransaccionAjax(LoginRequiredMixin, View):
    def get(self, request, pk):
        try:
            t = TransaccionCaja.objects.select_related(
                'cuenta_origen', 'cuenta_destino', 'creado_por'
            ).get(pk=pk)
        except TransaccionCaja.DoesNotExist:
            return _json_error('Transacción no encontrada.', status=404)
        return _json_ok({'transaccion': _serializar_transaccion(t)})


# ──────────────────────────────────────────────────────────────────
#  Anular
# ──────────────────────────────────────────────────────────────────

class AnularTransaccionAjax(LoginRequiredMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        if not (request.user.is_staff or request.user.is_superuser):
            return _json_error('No tenés permisos para anular transacciones.', status=403)
        try:
            t = TransaccionCaja.objects.get(pk=pk)
        except TransaccionCaja.DoesNotExist:
            return _json_error('Transacción no encontrada.', status=404)

        tipo_label = t.get_tipo_display()
        t.revertir()
        return _json_ok({'mensaje': f'{tipo_label} anulada y movimientos revertidos.'})
