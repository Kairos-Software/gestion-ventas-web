# ══════════════════════════════════════════════════════════════════
#  views_transacciones.py
#  AJAX views para el módulo de Transacciones de Caja Grande.
# ══════════════════════════════════════════════════════════════════

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

from .models import (
    CuentaCaja,
    TransaccionCaja,
    TipoTransaccion,
    TipoCaja,
)


# ──────────────────────────────────────────────────────────────────
#  Helpers internos
# ──────────────────────────────────────────────────────────────────

def _parse_decimal(value, field_name):
    """
    Convierte un valor a Decimal.
    Retorna (decimal, None) si OK, o (None, mensaje_error) si falla.
    """
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
    """Serializa una TransaccionCaja para devolver al frontend."""
    return {
        'id':                  t.pk,
        'tipo':                t.tipo,
        'tipo_label':          t.get_tipo_display(),
        'cuenta_origen_id':    t.cuenta_origen_id,
        'cuenta_origen':       str(t.cuenta_origen),
        'cuenta_destino_id':   t.cuenta_destino_id,
        'cuenta_destino':      str(t.cuenta_destino),
        'monto_origen':        str(t.monto_origen),
        'monto_destino':       str(t.monto_destino),
        'tipo_cambio':         str(t.tipo_cambio) if t.tipo_cambio else None,
        'costo_extra':         str(t.costo_extra) if t.costo_extra else None,
        'descripcion_costo':   t.descripcion_costo,
        'fecha':               t.fecha.strftime('%Y-%m-%d'),
        'descripcion':         t.descripcion,
        'creado_por':          t.creado_por.get_full_name() if t.creado_por else '—',
        'fecha_alta':          t.fecha_alta.strftime('%d/%m/%Y %H:%M'),
    }


# ──────────────────────────────────────────────────────────────────
#  Cuentas disponibles (para popular selects en el frontend)
# ──────────────────────────────────────────────────────────────────

class CuentasDisponiblesAjax(LoginRequiredMixin, View):
    """
    GET /caja/transacciones/cuentas/
    Devuelve todas las cuentas activas de caja grande.
    El frontend las usa para popular los selects de origen y destino.
    """

    def get(self, request):
        cuentas = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True)
            .order_by('orden', 'nombre')
            .values('id', 'nombre', 'tipo', 'moneda')
        )
        return _json_ok({'cuentas': list(cuentas)})


# ──────────────────────────────────────────────────────────────────
#  Calcular preview (sin guardar)
# ──────────────────────────────────────────────────────────────────

class CalcularTransaccionAjax(LoginRequiredMixin, View):
    """
    POST /caja/transacciones/calcular/
    Recibe los parámetros del formulario y devuelve el monto_destino
    calculado, el total egresado (monto_origen + costo_extra) y un
    resumen textual. No guarda nada.

    Body JSON:
    {
        "tipo":           "compra_divisa",
        "monto_origen":   15000,
        "tipo_cambio":    1200,       ← solo para compra/venta divisa
        "costo_extra":    450         ← opcional
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

        # Calcular monto destino
        if tipo in (TipoTransaccion.COMPRA_DIVISA, TipoTransaccion.VENTA_DIVISA):
            tipo_cambio_raw = data.get('tipo_cambio')
            if not tipo_cambio_raw:
                return _json_error('El tipo de cambio es requerido para operaciones con divisas.')
            tipo_cambio, err = _parse_decimal(tipo_cambio_raw, 'Tipo de cambio')
            if err:
                return _json_error(err)
            if tipo_cambio == 0:
                return _json_error('El tipo de cambio no puede ser 0.')
            monto_destino = (monto_origen / tipo_cambio).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        else:
            # Depósito / Extracción: mismo monto, misma moneda
            tipo_cambio   = None
            monto_destino = monto_origen

        total_egresado = monto_origen + costo_extra

        return _json_ok({
            'monto_destino':  str(monto_destino),
            'total_egresado': str(total_egresado),
            'tipo_cambio':    str(tipo_cambio) if tipo_cambio else None,
        })


# ──────────────────────────────────────────────────────────────────
#  Crear transacción
# ──────────────────────────────────────────────────────────────────

class CrearTransaccionAjax(LoginRequiredMixin, View):
    """
    POST /caja/transacciones/crear/

    Body JSON:
    {
        "tipo":               "compra_divisa",
        "cuenta_origen_id":   1,
        "cuenta_destino_id":  3,
        "monto_origen":       15000,
        "tipo_cambio":        1200,        ← obligatorio para compra/venta divisa
        "costo_extra":        450,         ← opcional
        "descripcion_costo":  "Impuesto PAIS 30%",
        "fecha":              "2026-06-23",
        "descripcion":        "Compra de USD en Banco Nación"
    }
    """

    @transaction.atomic
    def post(self, request):
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _json_error('Body JSON inválido.')

        # ── Validar tipo ──────────────────────────────────────────
        tipo = data.get('tipo', '')
        if tipo not in TipoTransaccion.values:
            return _json_error('Tipo de transacción inválido.')

        # ── Validar cuentas ───────────────────────────────────────
        try:
            cuenta_origen  = CuentaCaja.objects.get(pk=data.get('cuenta_origen_id'),  caja=TipoCaja.GRANDE, activa=True)
            cuenta_destino = CuentaCaja.objects.get(pk=data.get('cuenta_destino_id'), caja=TipoCaja.GRANDE, activa=True)
        except CuentaCaja.DoesNotExist:
            return _json_error('Una o ambas cuentas no existen o no están activas.')

        if cuenta_origen.pk == cuenta_destino.pk:
            return _json_error('La cuenta origen y destino no pueden ser la misma.')

        # ── Validar monedas según tipo ────────────────────────────
        if tipo in (TipoTransaccion.DEPOSITO, TipoTransaccion.EXTRACCION):
            if cuenta_origen.moneda != cuenta_destino.moneda:
                return _json_error(
                    f'Para {TipoTransaccion(tipo).label}, origen y destino deben tener la misma moneda.'
                )

        if tipo in (TipoTransaccion.COMPRA_DIVISA, TipoTransaccion.VENTA_DIVISA):
            if cuenta_origen.moneda == cuenta_destino.moneda:
                return _json_error(
                    'Para operaciones con divisas, origen y destino deben tener monedas distintas.'
                )

        # ── Validar montos ────────────────────────────────────────
        monto_origen, err = _parse_decimal(data.get('monto_origen', 0), 'Monto origen')
        if err:
            return _json_error(err)
        if monto_origen <= 0:
            return _json_error('El monto origen debe ser mayor a 0.')

        # Tipo de cambio y monto destino
        tipo_cambio   = None
        costo_extra   = None
        monto_destino = monto_origen  # default depósito/extracción

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
                costo_extra = None  # ignorar si envían 0

        # ── Validar fecha ─────────────────────────────────────────
        fecha_str = data.get('fecha', '')
        if not fecha_str:
            return _json_error('La fecha es requerida.')
        try:
            from datetime import date
            fecha = date.fromisoformat(fecha_str)
        except ValueError:
            return _json_error('Fecha inválida. Usar formato YYYY-MM-DD.')

        # ── Validar saldo suficiente en cuenta origen ─────────────
        saldo_origen = cuenta_origen.saldo
        total_a_debitar = monto_origen + (costo_extra or Decimal('0'))
        if saldo_origen < total_a_debitar:
            return _json_error(
                f'Saldo insuficiente en "{cuenta_origen.nombre}". '
                f'Disponible: {saldo_origen} {cuenta_origen.moneda}, '
                f'requerido: {total_a_debitar} {cuenta_origen.moneda}.'
            )

        # ── Crear la transacción ──────────────────────────────────
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

        # Ejecutar: crea los MovimientoCaja y los linkea
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
    Parámetros opcionales:
      - tipo:   filtrar por TipoTransaccion
      - cuenta: filtrar por cuenta (origen o destino)
      - desde / hasta: filtrar por fecha (YYYY-MM-DD)
      - page / page_size: paginación simple
    """

    def get(self, request):
        qs = (
            TransaccionCaja.objects
            .select_related('cuenta_origen', 'cuenta_destino', 'creado_por')
            .filter(cuenta_origen__caja=TipoCaja.GRANDE)
            .order_by('-fecha', '-fecha_alta')
        )

        # Filtros
        tipo = request.GET.get('tipo')
        if tipo and tipo in TipoTransaccion.values:
            qs = qs.filter(tipo=tipo)

        cuenta_id = request.GET.get('cuenta')
        if cuenta_id:
            qs = qs.filter(
                cuenta_origen_id=cuenta_id
            ) | qs.filter(cuenta_destino_id=cuenta_id)

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

        # Paginación simple
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
            'paginas':       -(-total // page_size),  # ceil sin math
        })


# ──────────────────────────────────────────────────────────────────
#  Detalle de una transacción
# ──────────────────────────────────────────────────────────────────

class DetalleTransaccionAjax(LoginRequiredMixin, View):
    """
    GET /caja/transacciones/<pk>/
    """

    def get(self, request, pk):
        try:
            t = TransaccionCaja.objects.select_related(
                'cuenta_origen', 'cuenta_destino', 'creado_por'
            ).get(pk=pk)
        except TransaccionCaja.DoesNotExist:
            return _json_error('Transacción no encontrada.', status=404)

        return _json_ok({'transaccion': _serializar_transaccion(t)})


# ──────────────────────────────────────────────────────────────────
#  Anular (revertir) una transacción
# ──────────────────────────────────────────────────────────────────

class AnularTransaccionAjax(LoginRequiredMixin, View):
    """
    POST /caja/transacciones/<pk>/anular/
    Revierte todos los movimientos de caja generados por la transacción
    y la elimina. Solo permitido a superusuarios o staff.
    """

    @transaction.atomic
    def post(self, request, pk):
        if not (request.user.is_staff or request.user.is_superuser):
            return _json_error('No tenés permisos para anular transacciones.', status=403)

        try:
            t = TransaccionCaja.objects.select_related(
                'cuenta_origen', 'cuenta_destino'
            ).get(pk=pk)
        except TransaccionCaja.DoesNotExist:
            return _json_error('Transacción no encontrada.', status=404)

        tipo_label = t.get_tipo_display()
        t.revertir()

        return _json_ok({'mensaje': f'{tipo_label} anulada y movimientos revertidos.'})


class TransaccionesPageView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/transacciones.html'