"""
caja/views_cuenta_corriente.py

Pantalla "Cuenta corriente" — vista por cliente del saldo consolidado y
cobro con imputación FIFO. Solo tiene sentido con
core.models.usa_cuenta_corriente() en True; si está en False, la vista
redirige a "Cuentas por cobrar" (el modo individual de siempre).
"""

import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from core.models import Cliente, usa_cuenta_corriente
from core.permisos import chequear_permiso

from . import services_cuenta_corriente as svc
from .models import (
    CuentaCaja, TipoCaja, CuentaPorCobrar, CobroCuentaCorriente,
    EstadoDeuda, EstadoCuota, ModoCuotas,
    registrar_cobro_cuenta_corriente,
)

PERMISO_VER      = 'ver_cuentas_cobrar'
PERMISO_COBRAR   = 'confirmar_cuotas_cobro'
PERMISO_ANULAR   = 'eliminar_cuentas_cobrar'
PERMISO_EDITAR   = 'editar_cuentas_cobrar'


def _cuentas_cobro_json():
    cuentas = CuentaCaja.objects.filter(
        caja=TipoCaja.GRANDE, activa=True, es_credito=False,
    ).order_by('orden', 'nombre')
    return [
        {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'tipo': c.tipo,
         'titular': c.titular, 'preferida': c.preferida}
        for c in cuentas
    ]


# ══════════════════════════════════════════════════════════════════
#  PÁGINA
# ══════════════════════════════════════════════════════════════════

class CuentaCorrienteView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/cuenta_corriente.html'

    def dispatch(self, request, *args, **kwargs):
        # Si la instalación no está en modo cuenta corriente, esta
        # pantalla no aplica — mandamos a la de siempre.
        if request.user.is_authenticated and not usa_cuenta_corriente():
            return redirect('caja:cuentas_cobrar')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_ver'] = True
        ctx['puede_cobrar'] = chequear_permiso(self.request.user, PERMISO_COBRAR)
        ctx['puede_anular'] = chequear_permiso(self.request.user, PERMISO_ANULAR)
        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)
        ctx['puede_crear_deuda'] = chequear_permiso(self.request.user, 'crear_cuentas_cobrar')
        ctx['today'] = timezone.localtime().date().isoformat()
        ctx['cuentas_json'] = json.dumps(_cuentas_cobro_json())

        ctx['urls'] = json.dumps({
            'listar':          reverse('caja:cc_listar'),
            'detalleCliente':  reverse('caja:cc_detalle_cliente', args=[0]),
            'cobrar':          reverse('caja:cc_cobrar', args=[0]),
            'anularCobro':     reverse('caja:cc_anular_cobro', args=[0]),
            'convertirLibre':  reverse('caja:cc_convertir_libre', args=[0]),
            'cuentasCobrar':   reverse('caja:cuentas_cobrar'),
            'clientePerfilBase': reverse('core:estadisticas_cliente_perfil', args=[0])[:-2],
        })
        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — listado de clientes con saldo
# ══════════════════════════════════════════════════════════════════

class CuentaCorrienteListarAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        q = request.GET.get('q', '').strip()
        filas = svc.clientes_con_saldo(q)
        total = sum(Decimal(f['saldo_total']) for f in filas) if filas else Decimal('0')
        return JsonResponse({
            'results': filas,
            'saldo_total': str(total),
            'clientes_con_deuda': len(filas),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — detalle de un cliente
# ══════════════════════════════════════════════════════════════════

class CuentaCorrienteDetalleClienteAjax(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        cliente = get_object_or_404(Cliente, pk=pk)
        return JsonResponse({'resumen': svc.resumen_cliente(cliente)})


# ══════════════════════════════════════════════════════════════════
#  AJAX — registrar un cobro (cascada FIFO)
# ══════════════════════════════════════════════════════════════════

class CuentaCorrienteCobrarAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_COBRAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cliente = get_object_or_404(Cliente, pk=pk)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        try:
            monto = Decimal(str(data.get('monto')))
        except (InvalidOperation, TypeError, ValueError):
            return JsonResponse({'error': 'Monto inválido.'}, status=400)

        cuenta_pk = data.get('cuenta_pk')
        if not cuenta_pk:
            return JsonResponse({'error': 'Elegí una cuenta para el cobro.'}, status=400)

        fecha = None
        if data.get('fecha'):
            try:
                fecha = date.fromisoformat(str(data.get('fecha')))
            except ValueError:
                return JsonResponse({'error': 'Fecha inválida.'}, status=400)

        numero_comprobante = str(data.get('numero_comprobante', '') or '').strip()[:100]
        notas = str(data.get('notas', '') or '').strip()[:300]

        try:
            cobro = registrar_cobro_cuenta_corriente(
                cliente=cliente, monto=monto, cuenta_pk=cuenta_pk, usuario=request.user,
                fecha=fecha, numero_comprobante=numero_comprobante, notas=notas,
            )
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

        return JsonResponse({
            'success': True,
            'cobro_pk': cobro.pk,
            'resumen': svc.resumen_cliente(cliente),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — anular un cobro
# ══════════════════════════════════════════════════════════════════

class CuentaCorrienteAnularCobroAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_ANULAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cobro = get_object_or_404(CobroCuentaCorriente, pk=pk)
        try:
            cobro.anular(usuario=request.user)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

        return JsonResponse({
            'success': True,
            'resumen': svc.resumen_cliente(cobro.cliente),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — convertir una deuda de cuotas fijas a saldo libre
# ══════════════════════════════════════════════════════════════════

class CuentaCorrienteConvertirLibreAjax(LoginRequiredMixin, View):
    """
    Pasa una CuentaPorCobrar de modo_cuotas=FIJAS a LIBRE: descarta las
    cuotas PENDIENTE pre-generadas (no movieron plata), conserva las
    CONFIRMADA, y el saldo pasa a calcularse como total − cobrado. Sirve
    para que la cascada FIFO pueda imputar fracciones a esa deuda.
    """
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)
        if not usa_cuenta_corriente():
            return JsonResponse({'error': 'El modo cuenta corriente no está activado.'}, status=400)

        cxc = get_object_or_404(CuentaPorCobrar, pk=pk)

        if cxc.modo_cuotas == ModoCuotas.LIBRE:
            return JsonResponse({'error': 'Esta deuda ya es de saldo libre.'}, status=400)
        if cxc.estado != EstadoDeuda.ACTIVA:
            return JsonResponse({'error': 'La deuda no está activa.'}, status=400)

        from django.db import transaction
        from .models import Cheque, EstadoCheque
        if Cheque.objects.filter(
            cuota_cobro__cuenta_por_cobrar=cxc,
            estado__in=(EstadoCheque.PENDIENTE, EstadoCheque.CONFIRMADO),
        ).exists():
            return JsonResponse(
                {'error': 'Esta deuda tiene un cheque en trámite en alguna cuota — resolvelo primero.'},
                status=400,
            )

        with transaction.atomic():
            # El monto objetivo (capital + interés) se conserva vía la
            # property monto_total de LIBRE, que usa monto_original y
            # porcentaje_interes — no hace falta tocarlos.
            cxc.cuotas.filter(estado=EstadoCuota.PENDIENTE).delete()
            cxc.modo_cuotas = ModoCuotas.LIBRE
            cxc.cantidad_cuotas = None
            cxc.save(update_fields=['modo_cuotas', 'cantidad_cuotas'])

        return JsonResponse({'success': True})
