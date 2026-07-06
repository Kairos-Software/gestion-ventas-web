import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Q, Count, F, Value, Case, When

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import (
    CuentaCaja, ConceptoMovimiento, MovimientoCaja,
    TipoCaja, TipoCuenta, TipoMovimientoCaja, OrigenMovimiento,
)


PERMISO_VER    = 'ver_caja'
PERMISO_CARGAR = 'cargar_movimientos_caja'


# ══════════════════════════════════════════════════════════════════
#  PÁGINA PRINCIPAL — Caja grande
# ══════════════════════════════════════════════════════════════════

class CajaGrandeView(LoginRequiredMixin, TemplateView):
    """
    Pantalla principal de la caja grande: balance general por cuenta/
    moneda + listado filtrable de movimientos (cargado vía AJAX).
    """
    template_name = 'caja/caja_grande.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_ver']    = True
        ctx['puede_cargar'] = chequear_permiso(self.request.user, PERMISO_CARGAR)

        ctx['cuentas'] = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True)
            .order_by('orden', 'nombre')
        )
        ctx['conceptos'] = (
            ConceptoMovimiento.objects
            .filter(activo=True)
            .order_by('orden', 'nombre')
        )
        ctx['monedas']        = Moneda.choices
        ctx['tipos_cuenta']   = TipoCuenta.choices
        ctx['tipos_movimiento'] = TipoMovimientoCaja.choices
        ctx['today']          = timezone.now().date().isoformat()

        from django.urls import reverse
        ctx['url_balance'] = reverse('caja:balance_grande')

        return ctx


# ══════════════════════════════════════════════════════════════════
#  HELPER — aplica filtros comunes a un queryset de MovimientoCaja
# ══════════════════════════════════════════════════════════════════

def _aplicar_filtros(qs, params):
    """
    Filtros soportados (todos opcionales, vía querystring):
      - desde, hasta        : rango de fecha (YYYY-MM-DD)
      - cuenta              : pk de CuentaCaja
      - concepto             : pk de ConceptoMovimiento
      - tipo                : 'ingreso' | 'egreso'
      - moneda               : 'ARS' | 'USD' | 'EUR'
      - origen                : 'venta' | 'compra' | 'manual' | 'ajuste'
      - q                    : texto libre (descripción / referencia)
      - monto_min, monto_max : rango de monto
    """
    desde = params.get('desde', '').strip()
    hasta = params.get('hasta', '').strip()
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)

    cuenta_pk = params.get('cuenta', '').strip()
    if cuenta_pk:
        qs = qs.filter(cuenta_id=cuenta_pk)

    concepto_pk = params.get('concepto', '').strip()
    if concepto_pk:
        qs = qs.filter(concepto_id=concepto_pk)

    tipo = params.get('tipo', '').strip()
    if tipo in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
        qs = qs.filter(tipo=tipo)

    moneda = params.get('moneda', '').strip()
    if moneda:
        qs = qs.filter(moneda=moneda)

    origen = params.get('origen', '').strip()
    valores_origen = [v for v, _ in OrigenMovimiento.choices]
    if origen in valores_origen:
        qs = qs.filter(origen=origen)

    q = params.get('q', '').strip()
    if q:
        qs = qs.filter(Q(descripcion__icontains=q) | Q(referencia__icontains=q))

    monto_min = params.get('monto_min', '').strip()
    if monto_min:
        try:
            qs = qs.filter(monto__gte=Decimal(monto_min))
        except InvalidOperation:
            pass

    monto_max = params.get('monto_max', '').strip()
    if monto_max:
        try:
            qs = qs.filter(monto__lte=Decimal(monto_max))
        except InvalidOperation:
            pass

    return qs


# ══════════════════════════════════════════════════════════════════
#  AJAX — Balance (resumen por cuenta/moneda, respetando filtros)
# ══════════════════════════════════════════════════════════════════

class BalanceGrandeAjax(LoginRequiredMixin, View):
    """
    Devuelve:
      - balance_por_moneda: saldo TOTAL (histórico) por moneda, calculado
        exclusivamente desde MovimientoCaja(caja=GRANDE). Una venta solo
        aparece acá una vez que su turno se cerró (ver TurnoCaja.cerrar).
      - metricas_por_moneda: métricas detalladas por moneda (recaudado,
        gastos, etc.), respetando los filtros de _aplicar_filtros().
    """

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        # ── Calcular balance ÚNICAMENTE desde MovimientoCaja(caja=GRANDE) ──
        #
        # IMPORTANTE: antes esta vista sumaba Venta.total/Compra.total
        # directamente, además de los movimientos "extra". Para ventas
        # eso era un bug: contaba la plata de una venta como si ya
        # estuviera en caja grande apenas se confirmaba, aunque el
        # turno todavía estuviera abierto y esa plata siguiera "en el
        # cajón". Ahora una venta NUNCA genera un movimiento en caja
        # grande directamente — el único momento en que esa plata entra
        # a caja grande es cuando TurnoCaja.cerrar() la transfiere
        # (queda registrada con origen=AJUSTE). Por eso alcanza con
        # sumar MovimientoCaja: ya incluye ventas liquidadas (vía
        # cierre de turno), compras (origen=COMPRA), gastos y cargas
        # manuales (origen=MANUAL), transacciones internas
        # (origen=TRANSACCION) y ajustes de turno (origen=AJUSTE).
        #
        # NOTA (fase 2 pendiente): las compras todavía generan su
        # movimiento apenas se confirman, sin pasar por ningún "cierre"
        # — eso es intencional por ahora (compras no tienen turno), y
        # queda incluido acá sin tratamiento especial.

        balance_por_moneda = {}
        metricas_por_moneda = {}

        for moneda, _label in Moneda.choices:
            qs_moneda = MovimientoCaja.objects.filter(
                caja=TipoCaja.GRANDE,
                moneda=moneda,
            )

            agregados_totales = qs_moneda.aggregate(
                ingresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.INGRESO)),
                egresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.EGRESO)),
            )
            total_ingresos = agregados_totales['ingresos'] or 0
            total_egresos  = agregados_totales['egresos']  or 0
            saldo = total_ingresos - total_egresos

            # Desglose informativo por origen (ventas liquidadas, compras,
            # manuales/gastos, transacciones internas, ajustes de turno)
            ventas_liquidadas = qs_moneda.filter(
                origen=OrigenMovimiento.AJUSTE, tipo=TipoMovimientoCaja.INGRESO,
            ).aggregate(total=Sum('monto'))['total'] or 0

            egresos_compras = qs_moneda.filter(
                origen=OrigenMovimiento.COMPRA,
            ).aggregate(total=Sum('monto'))['total'] or 0
            
            balance_por_moneda[moneda] = {
                'saldo': str(saldo),
                'ingresos': str(total_ingresos),
                'egresos': str(total_egresos),
                'ventas': str(ventas_liquidadas),
                'compras': str(egresos_compras),
                # Desglose por cuenta (Efectivo, Transferencia, Débito, etc.)
                # dentro de esta moneda. Usa CuentaCaja.saldo, que ya suma
                # ingresos - egresos de esa cuenta puntual.
                'cuentas': [
                    {
                        'nombre': cuenta.nombre,
                        'tipo': cuenta.tipo,
                        'saldo': str(cuenta.saldo),
                    }
                    for cuenta in CuentaCaja.objects.filter(
                        caja=TipoCaja.GRANDE, moneda=moneda, activa=True,
                    ).order_by('orden', 'nombre')
                ],
            }

            # Métricas detalladas (con filtros de fecha/cuenta/concepto/etc
            # aplicados), todo derivado del mismo queryset de MovimientoCaja.
            qs_filtrado = _aplicar_filtros(qs_moneda, request.GET)

            agregados_filtrados = qs_filtrado.aggregate(
                ingresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.INGRESO)),
                egresos=Sum('monto', filter=Q(tipo=TipoMovimientoCaja.EGRESO)),
                total_movimientos=Count('pk'),
            )
            ingresos_filtrados  = agregados_filtrados['ingresos'] or 0
            egresos_filtrados   = agregados_filtrados['egresos']  or 0
            total_movimientos   = agregados_filtrados['total_movimientos'] or 0

            # Ventas liquidadas y compras dentro del mismo filtro, para
            # desglosar el origen del recaudado/gastos (informativo).
            ventas_filtradas = qs_filtrado.filter(
                origen=OrigenMovimiento.AJUSTE, tipo=TipoMovimientoCaja.INGRESO,
            ).aggregate(total=Sum('monto'))['total'] or 0
            compras_filtradas = qs_filtrado.filter(
                origen=OrigenMovimiento.COMPRA,
            ).aggregate(total=Sum('monto'))['total'] or 0

            if ingresos_filtrados or egresos_filtrados:
                metricas_por_moneda[moneda] = {
                    'recaudado': str(ingresos_filtrados),
                    'gastos': str(egresos_filtrados),
                    'neto': str(ingresos_filtrados - egresos_filtrados),
                    'total_movimientos': total_movimientos,
                    'ventas': str(ventas_filtradas),
                    'compras': str(compras_filtradas),
                }

        return JsonResponse({
            'balance_por_moneda': balance_por_moneda,
            'metricas_por_moneda': metricas_por_moneda,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear movimiento manual
# ══════════════════════════════════════════════════════════════════

class CrearMovimientoGrandeAjax(LoginRequiredMixin, View):
    """
    POST JSON:
    {
        "fecha": "2026-06-20",
        "cuenta_pk": 1,
        "concepto_pk": 3,
        "tipo": "ingreso" | "egreso",
        "monto": "15000.00",
        "descripcion": "...",
        "referencia": "..."
    }
    Solo permite cargar movimientos MANUALES — los automáticos
    (venta/compra) se generan exclusivamente desde sus propios modelos.
    """

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CARGAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        cuenta_pk   = body.get('cuenta_pk')
        concepto_pk = body.get('concepto_pk')
        tipo        = body.get('tipo', '').strip()
        fecha       = body.get('fecha') or timezone.now().date().isoformat()

        if not cuenta_pk:
            return JsonResponse({'error': 'cuenta_pk requerido.'}, status=400)
        if not concepto_pk:
            return JsonResponse({'error': 'concepto_pk requerido.'}, status=400)
        if tipo not in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
            return JsonResponse({'error': 'tipo debe ser "ingreso" o "egreso".'}, status=400)

        try:
            monto = Decimal(str(body.get('monto', 0)))
        except InvalidOperation:
            return JsonResponse({'error': 'Monto inválido.'}, status=400)
        if monto <= 0:
            return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)

        cuenta = get_object_or_404(CuentaCaja, pk=cuenta_pk, caja=TipoCaja.GRANDE)
        concepto = get_object_or_404(ConceptoMovimiento, pk=concepto_pk)

        movimiento = MovimientoCaja.objects.create(
            caja        = TipoCaja.GRANDE,
            cuenta      = cuenta,
            concepto    = concepto,
            tipo        = tipo,
            monto       = monto,
            moneda      = cuenta.moneda,
            fecha       = fecha,
            descripcion = body.get('descripcion', ''),
            referencia  = body.get('referencia', ''),
            origen      = OrigenMovimiento.MANUAL,
            creado_por  = request.user,
        )

        return JsonResponse({'ok': True, 'pk': movimiento.pk})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Editar movimiento manual
# ══════════════════════════════════════════════════════════════════

class EditarMovimientoGrandeAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CARGAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        movimiento = get_object_or_404(MovimientoCaja, pk=pk, caja=TipoCaja.GRANDE)

        if not movimiento.es_editable:
            return JsonResponse(
                {'error': 'Este movimiento fue generado automáticamente y no se puede editar directamente. Editá la venta/compra de origen.'},
                status=400,
            )

        cuenta_pk   = body.get('cuenta_pk')
        concepto_pk = body.get('concepto_pk')
        tipo        = body.get('tipo', '').strip()
        fecha       = body.get('fecha')

        if cuenta_pk:
            movimiento.cuenta = get_object_or_404(CuentaCaja, pk=cuenta_pk, caja=TipoCaja.GRANDE)
            movimiento.moneda = movimiento.cuenta.moneda
        if concepto_pk:
            movimiento.concepto = get_object_or_404(ConceptoMovimiento, pk=concepto_pk)
        if tipo in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
            movimiento.tipo = tipo
        if fecha:
            movimiento.fecha = fecha

        if 'monto' in body:
            try:
                monto = Decimal(str(body.get('monto', 0)))
            except InvalidOperation:
                return JsonResponse({'error': 'Monto inválido.'}, status=400)
            if monto <= 0:
                return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)
            movimiento.monto = monto

        movimiento.descripcion = body.get('descripcion', movimiento.descripcion)
        movimiento.referencia  = body.get('referencia', movimiento.referencia)

        movimiento.save()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar movimiento manual
# ══════════════════════════════════════════════════════════════════

class EliminarMovimientoGrandeAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CARGAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        movimiento = get_object_or_404(MovimientoCaja, pk=pk, caja=TipoCaja.GRANDE)

        if not movimiento.es_editable:
            return JsonResponse(
                {'error': 'Este movimiento fue generado automáticamente y no se puede eliminar directamente. Anulá la venta/compra de origen.'},
                status=400,
            )

        movimiento.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear cuenta de caja (grande)
# ══════════════════════════════════════════════════════════════════

class CrearCuentaGrandeAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CARGAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre = body.get('nombre', '').strip()
        moneda = body.get('moneda', '').strip()
        tipo   = body.get('tipo', TipoCuenta.EFECTIVO).strip()

        if not nombre:
            return JsonResponse({'error': 'El nombre es requerido.'}, status=400)
        valores_moneda = [v for v, _ in Moneda.choices]
        if moneda not in valores_moneda:
            return JsonResponse({'error': 'Moneda inválida.'}, status=400)
        valores_tipo = [v for v, _ in TipoCuenta.choices]
        if tipo not in valores_tipo:
            return JsonResponse({'error': 'Tipo de cuenta inválido.'}, status=400)

        if CuentaCaja.objects.filter(nombre=nombre, caja=TipoCaja.GRANDE).exists():
            return JsonResponse({'error': 'Ya existe una cuenta con ese nombre en la caja grande.'}, status=400)

        cuenta = CuentaCaja.objects.create(
            nombre=nombre, moneda=moneda, tipo=tipo, caja=TipoCaja.GRANDE,
            notas=body.get('notas', ''),
        )
        return JsonResponse({'ok': True, 'pk': cuenta.pk, 'nombre': cuenta.nombre})


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