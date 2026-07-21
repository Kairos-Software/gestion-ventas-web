import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.urls import reverse
from django.db.models import Sum, Q

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import (
    CuentaCaja, ConceptoMovimiento, MovimientoCaja,
    TipoCaja, TipoMovimientoCaja,
    _cuenta_default,
)


PERMISO_VER    = 'ver_caja'
PERMISO_CARGAR = 'cargar_movimientos_caja'

# Cuántos movimientos recientes mostrar en el balance (ver
# BalanceGrandeAjax) — a propósito chico, es un vistazo rápido de
# "qué pasó últimamente", no un historial completo.
CANTIDAD_ULTIMOS_MOVIMIENTOS = 6


# ══════════════════════════════════════════════════════════════════
#  PÁGINA PRINCIPAL — Caja grande
# ══════════════════════════════════════════════════════════════════

class CajaGrandeView(LoginRequiredMixin, TemplateView):
    """
    Pantalla principal de la caja grande: balance por moneda, desglose
    por cuenta y últimos movimientos — todo se carga vía AJAX
    (BalanceGrandeAjax), acá solo se resuelve el permiso.
    """
    template_name = 'caja/caja_grande.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['url_balance'] = reverse('caja:balance_grande')
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Balance (resumen por cuenta/moneda)
# ══════════════════════════════════════════════════════════════════

class BalanceGrandeAjax(LoginRequiredMixin, View):
    """
    Devuelve balance_por_moneda: saldo TOTAL (histórico) por moneda, el
    desglose por cuenta (Efectivo, Transferencia, Débito, etc.) y los
    últimos movimientos — todo calculado exclusivamente desde
    MovimientoCaja(caja=GRANDE). Solo el estado ACTUAL de las cuentas
    — los reportes históricos (recaudado, gastos, ventas vs. compras,
    evolución en el tiempo) viven en Estadísticas, no acá.
    """

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        balance_por_moneda = {}

        for moneda, _label in Moneda.choices:
            # El efectivo siempre existe, en las tres monedas, aunque
            # todavía no tenga movimientos — se auto-provisiona acá
            # (get_or_create) para que la card nunca falte.
            _cuenta_default(moneda=moneda, caja=TipoCaja.GRANDE)

            agregados_totales = MovimientoCaja.objects.filter(
                caja=TipoCaja.GRANDE,
                moneda=moneda,
                cuenta__es_credito=False,
            ).aggregate(
                ingresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.INGRESO)),
                egresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.EGRESO)),
            )
            saldo = (agregados_totales['ingresos'] or 0) - (agregados_totales['egresos'] or 0)

            ultimos = (
                MovimientoCaja.objects
                .filter(caja=TipoCaja.GRANDE, moneda=moneda)
                .select_related('cuenta', 'concepto')
                .order_by('-fecha', '-pk')[:CANTIDAD_ULTIMOS_MOVIMIENTOS]
            )

            balance_por_moneda[moneda] = {
                'saldo': str(saldo),
                # Desglose por cuenta (Efectivo, Transferencia, Débito, etc.)
                # dentro de esta moneda. Usa CuentaCaja.saldo, que ya suma
                # ingresos - egresos de esa cuenta puntual.
                'cuentas': [
                    {
                        'nombre': cuenta.nombre,
                        'tipo': cuenta.tipo,
                        'es_credito': cuenta.es_credito,
                        'titular': cuenta.titular,
                        'terminada_en': cuenta.terminada_en,
                        'saldo': str(cuenta.saldo),
                    }
                    for cuenta in CuentaCaja.objects.filter(
                        caja=TipoCaja.GRANDE, moneda=moneda, activa=True,
                    ).order_by('orden', 'nombre')
                ],
                # Vistazo rápido de actividad reciente — no reemplaza a
                # Estadísticas, es solo "qué pasó últimamente" en esta
                # moneda (venta, compra, gasto, transacción, etc).
                'ultimos_movimientos': [
                    {
                        'fecha': m.fecha.isoformat(),
                        'origen': m.origen,
                        'tipo': m.tipo,
                        'monto': str(m.monto),
                        'cuenta_nombre': m.cuenta.nombre,
                        'titulo': m.concepto.nombre if m.concepto else m.get_origen_display(),
                        'detalle': m.descripcion or m.referencia or m.get_origen_display(),
                    }
                    for m in ultimos
                ],
            }

        return JsonResponse({'balance_por_moneda': balance_por_moneda})


# ══════════════════════════════════════════════════════════════════
#  Nota: la creación/edición de cuentas de caja grande (tarjetas,
#  billeteras, bancos) se gestiona desde Configuración (app core,
#  ver core/views_cuentas.py). La carga manual de movimientos se hace
#  desde Finanzas > Ingresos y egresos (ver caja/views_gastos.py) —
#  Caja Grande solo lee.
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear concepto de movimiento (compartido entre cajas)
# ══════════════════════════════════════════════════════════════════

class CrearConceptoAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CARGAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre       = body.get('nombre', '').strip()
        tipo_default = body.get('tipo_default', TipoMovimientoCaja.EGRESO).strip()

        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido.'}, status=400)
        if tipo_default not in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
            return JsonResponse({'error': 'tipo_default inválido.'}, status=400)

        if ConceptoMovimiento.objects.filter(nombre=nombre).exists():
            return JsonResponse({'error': 'Ya existe un concepto con ese nombre.'}, status=400)

        concepto = ConceptoMovimiento.objects.create(
            nombre=nombre, tipo_default=tipo_default,
            descripcion=body.get('descripcion', ''),
        )
        return JsonResponse({'ok': True, 'pk': concepto.pk, 'nombre': concepto.nombre})
