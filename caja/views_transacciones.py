# ══════════════════════════════════════════════════════════════════
#  views_transacciones.py
#  AJAX views para el módulo de Transacciones de Caja Grande.
#
#  Estrategia de cuentas:
#  En vez de requerir que el usuario administre CuentaCaja
#  individualmente, el formulario expone contenedores fijos
#  (Efectivo ARS, Banco ARS, Efectivo USD, etc.) y el backend
#  resuelve la CuentaCaja correspondiente con get_or_create.
#  Esto evita la necesidad de un CRUD de cuentas por ahora.
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
    TipoCuenta,
)
from productos.models import Moneda


# ──────────────────────────────────────────────────────────────────
#  Contenedores disponibles (fijos, sin gestión manual)
# ──────────────────────────────────────────────────────────────────

# Cada contenedor tiene una clave única que el frontend envía,
# y se mapea a (tipo_cuenta, moneda, nombre_legible).
# Mapa de contenedores: clave → (tipo_cuenta, moneda, nombre_en_db, label_frontend)
#
# CRÍTICO: nombre_en_db para 'efectivo_*' debe ser exactamente 'Efectivo' —
# el mismo valor de CUENTA_EFECTIVO_DEFAULT_NOMBRE en models.py — para que
# las transacciones y los movimientos de ventas/compras/turnos compartan
# la misma CuentaCaja y aparezcan en el mismo balance.
# Los bancos usan 'Banco' como nombre base; no tienen default en models.py
# así que cualquier nombre consistente sirve.

CONTENEDORES = {
    'efectivo_ars': (TipoCuenta.EFECTIVO, Moneda.ARS, 'Efectivo', 'Efectivo ARS'),
    'banco_ars':    (TipoCuenta.BANCO,    Moneda.ARS, 'Banco',    'Banco ARS'),
    'efectivo_usd': (TipoCuenta.EFECTIVO, Moneda.USD, 'Efectivo', 'Efectivo USD'),
    'banco_usd':    (TipoCuenta.BANCO,    Moneda.USD, 'Banco',    'Banco USD'),
    'efectivo_eur': (TipoCuenta.EFECTIVO, Moneda.EUR, 'Efectivo', 'Efectivo EUR'),
    'banco_eur':    (TipoCuenta.BANCO,    Moneda.EUR, 'Banco',    'Banco EUR'),
}

# Monedas de cada contenedor (para validaciones rápidas)
_MONEDA_DE = {k: v[1] for k, v in CONTENEDORES.items()}


def _resolver_cuenta(clave: str) -> CuentaCaja:
    """
    Dado un contenedor (ej: 'efectivo_ars'), devuelve la CuentaCaja
    correspondiente, creándola si no existe todavía.

    Busca por (nombre_en_db, moneda, caja) para coincidir con la cuenta
    que ya crea _cuenta_default() en models.py al registrar ventas y turnos.
    """
    tipo, moneda, nombre_db, _ = CONTENEDORES[clave]
    cuenta, _ = CuentaCaja.objects.get_or_create(
        nombre=nombre_db,
        caja=TipoCaja.GRANDE,
        moneda=moneda,
        defaults={
            'tipo':   tipo,
            'activa': True,
            'orden':  list(CONTENEDORES.keys()).index(clave),
        },
    )
    return cuenta


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
        # Pasamos los contenedores al template para que el JS los use
        ctx['contenedores'] = [
            {'clave': k, 'label': v[3], 'moneda': v[1]}
            for k, v in CONTENEDORES.items()
        ]
        return ctx


# ──────────────────────────────────────────────────────────────────
#  Calcular preview (sin guardar)
# ──────────────────────────────────────────────────────────────────

class CalcularTransaccionAjax(LoginRequiredMixin, View):
    """
    POST /caja/transacciones/calcular/
    {
        "tipo":           "compra_divisa",
        "contenedor_origen":  "efectivo_ars",
        "contenedor_destino": "efectivo_usd",
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
        "contenedor_origen":   "efectivo_ars",
        "contenedor_destino":  "efectivo_usd",
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

        # ── Contenedores ──────────────────────────────────────────
        clave_origen  = data.get('contenedor_origen', '')
        clave_destino = data.get('contenedor_destino', '')

        if clave_origen not in CONTENEDORES:
            return _json_error('Contenedor origen inválido.')
        if clave_destino not in CONTENEDORES:
            return _json_error('Contenedor destino inválido.')
        if clave_origen == clave_destino:
            return _json_error('El origen y el destino no pueden ser el mismo.')

        # Validar monedas según tipo
        moneda_origen  = _MONEDA_DE[clave_origen]
        moneda_destino = _MONEDA_DE[clave_destino]

        if tipo in (TipoTransaccion.DEPOSITO, TipoTransaccion.EXTRACCION):
            if moneda_origen != moneda_destino:
                return _json_error(
                    f'Para {TipoTransaccion(tipo).label} el origen y destino '
                    f'deben ser de la misma moneda.'
                )

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

        # ── Resolver cuentas (get_or_create) ──────────────────────
        cuenta_origen  = _resolver_cuenta(clave_origen)
        cuenta_destino = _resolver_cuenta(clave_destino)

        # NOTA: La validación de saldo está deshabilitada intencionalmente.
        # Las cuentas de CuentaCaja (caja grande) todavía no están sincronizadas
        # automáticamente con los movimientos de caja diaria (ventas/compras),
        # por lo que el saldo calculado no refleja la realidad.
        # Se habilitará cuando exista esa sincronización.

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