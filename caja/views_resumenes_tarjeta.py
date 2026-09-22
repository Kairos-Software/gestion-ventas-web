import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.permisos import chequear_permiso

from .models import (
    CuentaCaja, TipoCaja, ResumenTarjeta, EstadoResumenTarjeta, EstadoCuota,
)

PERMISO_VER       = 'ver_deudas'
PERMISO_EDITAR    = 'editar_deudas'
PERMISO_CONFIRMAR = 'confirmar_cuotas_deuda'

MESES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]


def _serializar_cuota_resumen(c):
    deuda = c.deuda
    return {
        'pk': c.pk,
        'numero': c.numero,
        'monto': str(c.monto),
        'fecha_vencimiento': c.fecha_vencimiento.isoformat(),
        'estado': c.estado,
        'deuda_pk': deuda.pk,
        'deuda_descripcion': deuda.descripcion or (deuda.pago_compra.compra.numero if deuda.pago_compra_id else f'Deuda #{deuda.pk}'),
        'compra_numero': deuda.pago_compra.compra.numero if deuda.pago_compra_id else '',
        'cantidad_cuotas': deuda.cantidad_cuotas,
        # Para que "Compras incluidas" también sirva de historial de
        # pago — no solo "Pagada", sino cuándo y con qué cuenta.
        'fecha_confirmacion': timezone.localtime(c.fecha_confirmacion).isoformat() if c.fecha_confirmacion else '',
        'cuenta_pago_nombre': c.cuenta_pago.nombre if c.cuenta_pago_id else '',
        'es_historica': c.es_historica,
    }


def _serializar_resumen(r, con_detalle=False):
    data = {
        'pk': r.pk,
        'cuenta_tarjeta_pk': r.cuenta_tarjeta_id,
        'cuenta_tarjeta_nombre': r.cuenta_tarjeta.nombre,
        'anio': r.anio,
        'mes': r.mes,
        'periodo_label': f'{MESES[r.mes - 1]} {r.anio}',
        'fecha_cierre': r.fecha_cierre.isoformat() if r.fecha_cierre else None,
        'fecha_vencimiento': r.fecha_vencimiento.isoformat() if r.fecha_vencimiento else None,
        'moneda': r.cuenta_tarjeta.moneda,
        'monto_cuotas': str(r.monto_cuotas),
        'monto_ajuste': str(r.monto_ajuste),
        'descripcion_ajuste': r.descripcion_ajuste,
        'ajuste_pagado': r.ajuste_pagado,
        'fecha_pago_ajuste': timezone.localtime(r.fecha_pago_ajuste).isoformat() if r.fecha_pago_ajuste else '',
        'cuenta_pago_ajuste_nombre': r.cuenta_pago_ajuste.nombre if r.cuenta_pago_ajuste_id else '',
        'monto_total': str(r.monto_total),
        'saldo_pendiente': str(r.saldo_pendiente),
        'estado': r.estado,
        'estado_display': EstadoResumenTarjeta(r.estado).label,
    }
    if con_detalle:
        cuotas = list(r.cuotas)
        data['cuotas'] = [_serializar_cuota_resumen(c) for c in cuotas]
        data['cantidad_cuotas'] = len(cuotas)
    return data


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Resúmenes de tarjeta (pantalla propia)
#
#  Antes vivía embebida como una grilla sin límite dentro de Deudas —
#  con muchos meses/tarjetas se llenaba de tarjetas y tapaba el
#  historial de deudas. Ahora Deudas solo muestra un resumen
#  compacto (el más próximo por tarjeta, ver resumenes_tarjeta_widget.js)
#  con un link para acá, donde sí se ve todo con filtros.
# ══════════════════════════════════════════════════════════════════

class ResumenesTarjetaView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/resumenes_tarjeta.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)
        ctx['puede_confirmar'] = chequear_permiso(self.request.user, PERMISO_CONFIRMAR)

        ctx['tarjetas'] = CuentaCaja.objects.filter(
            caja=TipoCaja.GRANDE, es_credito=True, activa=True,
        ).order_by('orden', 'nombre')

        cuentas = CuentaCaja.objects.filter(caja=TipoCaja.GRANDE, activa=True).order_by('orden', 'nombre')
        ctx['cuentas_json'] = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'es_credito': c.es_credito,
             'tipo': c.tipo, 'titular': c.titular, 'preferida': c.preferida}
            for c in cuentas
        ])

        from django.urls import reverse
        ctx['url_deudas'] = reverse('caja:deudas')
        ctx['url_listar'] = reverse('caja:listar_resumenes_tarjeta')
        ctx['url_detalle'] = reverse('caja:detalle_resumen_tarjeta', args=[0])
        ctx['url_editar_ajuste'] = reverse('caja:editar_ajuste_resumen_tarjeta', args=[0])
        ctx['url_pagar'] = reverse('caja:pagar_resumen_tarjeta', args=[0])
        ctx['url_deshacer_pago'] = reverse('caja:deshacer_pago_resumen_tarjeta', args=[0])

        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listar resúmenes (todas las tarjetas, o una puntual)
# ══════════════════════════════════════════════════════════════════

class ListarResumenesTarjetaAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        tarjetas = CuentaCaja.objects.filter(caja=TipoCaja.GRANDE, es_credito=True, activa=True)
        tarjeta_pk = request.GET.get('cuenta_tarjeta_pk', '').strip()
        if tarjeta_pk:
            tarjetas = tarjetas.filter(pk=tarjeta_pk)

        resumenes = []
        for tarjeta in tarjetas.order_by('orden', 'nombre'):
            resumenes.extend(ResumenTarjeta.listar_para_tarjeta(tarjeta))

        estado_filtro = request.GET.get('estado', '').strip()
        if estado_filtro in EstadoResumenTarjeta.values:
            resumenes = [r for r in resumenes if r.estado == estado_filtro]

        # Pendientes/parciales primero (por vencimiento, más próximo
        # primero), pagados al final (más reciente primero).
        pendientes = sorted(
            (r for r in resumenes if r.estado != EstadoResumenTarjeta.PAGADO),
            key=lambda r: (r.anio, r.mes),
        )
        pagados = sorted(
            (r for r in resumenes if r.estado == EstadoResumenTarjeta.PAGADO),
            key=lambda r: (r.anio, r.mes), reverse=True,
        )

        return JsonResponse({'results': [_serializar_resumen(r) for r in pendientes + pagados]})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Detalle (resumen + cuotas que lo componen)
# ══════════════════════════════════════════════════════════════════

class DetalleResumenTarjetaAjax(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        resumen = get_object_or_404(ResumenTarjeta.objects.select_related('cuenta_tarjeta'), pk=pk)
        return JsonResponse({'resumen': _serializar_resumen(resumen, con_detalle=True)})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Cargar/editar el cargo propio del resumen (interés, IVA, etc.)
# ══════════════════════════════════════════════════════════════════

class EditarAjusteResumenAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        resumen = get_object_or_404(ResumenTarjeta.objects.select_related('cuenta_tarjeta'), pk=pk)

        try:
            data = json.loads(request.body)
            monto_raw = data.get('monto_ajuste')
            try:
                monto_ajuste = Decimal(str(monto_raw)) if monto_raw not in (None, '') else Decimal('0')
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({'error': 'Monto inválido.'}, status=400)

            resumen.editar_ajuste(
                monto_ajuste=monto_ajuste,
                descripcion_ajuste=str(data.get('descripcion_ajuste', '') or '').strip()[:200],
            )
            return JsonResponse({'success': True, 'resumen': _serializar_resumen(resumen, con_detalle=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Pagar el resumen completo (todas sus cuotas + el ajuste)
# ══════════════════════════════════════════════════════════════════

class PagarResumenTarjetaAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        resumen = get_object_or_404(ResumenTarjeta.objects.select_related('cuenta_tarjeta'), pk=pk)

        try:
            data = json.loads(request.body)
            cuenta_pk = data.get('cuenta_pk')
            if not cuenta_pk:
                return JsonResponse({'error': 'Elegí la cuenta con la que se paga el resumen.'}, status=400)

            # Se toman ANTES de pagar: son las que este pago va a confirmar
            # ahora — si se leyeran después, incluirían también cuotas ya
            # confirmadas en un pago parcial previo y les reenviaría el
            # mail de "deuda pagada" de nuevo.
            cuotas_a_confirmar_pks = list(
                resumen.cuotas.filter(estado=EstadoCuota.PENDIENTE).values_list('pk', flat=True)
            )

            resumen.pagar(cuenta_pk=cuenta_pk, usuario=request.user)

            from .models import CuotaDeuda
            from asistencia.services.eventos import notificar_deuda_pagada, enviar_en_background
            for cuota in CuotaDeuda.objects.filter(pk__in=cuotas_a_confirmar_pks):
                enviar_en_background(notificar_deuda_pagada, cuota)

            resumen.refresh_from_db()
            return JsonResponse({'success': True, 'resumen': _serializar_resumen(resumen, con_detalle=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Deshacer el pago del resumen (reversa de "pagar")
# ══════════════════════════════════════════════════════════════════

class DeshacerPagoResumenAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        resumen = get_object_or_404(ResumenTarjeta.objects.select_related('cuenta_tarjeta'), pk=pk)

        try:
            resumen.revertir_pago(usuario=request.user)
            resumen.refresh_from_db()
            return JsonResponse({'success': True, 'resumen': _serializar_resumen(resumen, con_detalle=True)})
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
