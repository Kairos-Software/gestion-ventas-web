import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Q

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import CuentaPorCobrar, CuotaCobro, CuentaCaja, TipoCaja, EstadoDeuda


PERMISO_VER       = 'ver_cuentas_cobrar'
PERMISO_EDITAR    = 'editar_cuentas_cobrar'
PERMISO_ELIMINAR  = 'eliminar_cuentas_cobrar'
PERMISO_CONFIRMAR = 'confirmar_cuotas_cobro'


def _serializar_cuota(c):
    return {
        'pk': c.pk,
        'numero': c.numero,
        'monto': str(c.monto),
        'fecha_vencimiento': c.fecha_vencimiento.isoformat(),
        'estado': c.estado,
        'habilitada': c.habilitada,
        'cuenta_cobro_pk': c.cuenta_cobro_id,
        'cuenta_cobro_nombre': c.cuenta_cobro.nombre if c.cuenta_cobro_id else '',
        'fecha_confirmacion': c.fecha_confirmacion.isoformat() if c.fecha_confirmacion else '',
        'confirmado_por': str(c.confirmado_por) if c.confirmado_por else '',
    }


def _serializar_cxc(cxc, con_cuotas=False):
    data = {
        'pk': cxc.pk,
        'cliente_pk': cxc.cliente_id,
        'cliente_nombre': cxc.cliente.get_nombre_display() if cxc.cliente_id else '',
        'descripcion': cxc.descripcion,
        'monto_original': str(cxc.monto_original),
        'porcentaje_interes': str(cxc.porcentaje_interes),
        'monto_total': str(cxc.monto_total),
        'moneda': cxc.moneda,
        'cantidad_cuotas': cxc.cantidad_cuotas,
        'cuotas_cobradas': cxc.cuotas_cobradas,
        'saldo_pendiente': str(cxc.saldo_pendiente),
        'fecha_inicio': cxc.fecha_inicio.isoformat(),
        'estado': cxc.estado,
        'estado_display': cxc.get_estado_display(),
        'notas': cxc.notas,
        'venta_numero': cxc.pago_venta.venta.numero if cxc.pago_venta_id else '',
        'creado_por': str(cxc.creado_por) if cxc.creado_por else '',
        'fecha_alta': cxc.fecha_alta.isoformat(),
    }
    if con_cuotas:
        data['cuotas'] = [_serializar_cuota(c) for c in cxc.cuotas.all()]
    return data


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Cuentas por cobrar
# ══════════════════════════════════════════════════════════════════

class CuentasCobrarView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/cuentas_cobrar.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_ver'] = True
        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, PERMISO_ELIMINAR)
        ctx['puede_confirmar'] = chequear_permiso(self.request.user, PERMISO_CONFIRMAR)

        ctx['monedas'] = Moneda.choices

        cuentas = CuentaCaja.objects.filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False).order_by('orden', 'nombre')
        ctx['cuentas_json'] = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda}
            for c in cuentas
        ])

        from django.urls import reverse
        ctx['url_listar'] = reverse('caja:listar_cuentas_cobrar')
        ctx['url_editar'] = reverse('caja:editar_cuenta_cobrar', args=[0])
        ctx['url_eliminar'] = reverse('caja:eliminar_cuenta_cobrar', args=[0])
        ctx['url_detalle'] = reverse('caja:detalle_cuenta_cobrar', args=[0])
        ctx['url_confirmar_cuota'] = reverse('caja:confirmar_cuota_cobro', args=[0])

        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listar (con filtros + paginación)
# ══════════════════════════════════════════════════════════════════

class ListarCuentasCobrarAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = CuentaPorCobrar.objects.all().select_related(
            'cliente', 'creado_por', 'pago_venta__venta',
        )

        estado = request.GET.get('estado', '').strip()
        moneda = request.GET.get('moneda', '').strip()
        q = request.GET.get('q', '').strip()

        if estado in EstadoDeuda.values:
            qs = qs.filter(estado=estado)
        if moneda:
            qs = qs.filter(moneda=moneda)
        if q:
            qs = qs.filter(
                Q(cliente__nombre__icontains=q) |
                Q(cliente__apellido__icontains=q) |
                Q(cliente__razon_social__icontains=q) |
                Q(descripcion__icontains=q)
            )

        try:
            pagina = max(int(request.GET.get('pagina', 1)), 1)
            por_pagina = min(max(int(request.GET.get('por_pagina', 50)), 1), 200)
        except ValueError:
            pagina, por_pagina = 1, 50

        total = qs.count()
        inicio = (pagina - 1) * por_pagina
        items = qs[inicio:inicio + por_pagina]

        data = [_serializar_cxc(c) for c in items]

        return JsonResponse({
            'results': data,
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Detalle (cuenta por cobrar + cuotas)
# ══════════════════════════════════════════════════════════════════

class DetalleCuentaCobrarAjax(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cxc = get_object_or_404(CuentaPorCobrar.objects.select_related('cliente', 'pago_venta__venta'), pk=pk)
        return JsonResponse({'cuenta_cobrar': _serializar_cxc(cxc, con_cuotas=True)})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Editar (solo notas — la cuenta nace de una venta, no se
#  recargan sus montos/cuotas a mano)
# ══════════════════════════════════════════════════════════════════

class EditarCuentaCobrarAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cxc = get_object_or_404(CuentaPorCobrar, pk=pk)

        try:
            data = json.loads(request.body)
            if 'notas' in data:
                cxc.notas = data.get('notas', '').strip()
            cxc.save(update_fields=['notas'])

            return JsonResponse({'success': True, 'cuenta_cobrar': _serializar_cxc(cxc, con_cuotas=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar
# ══════════════════════════════════════════════════════════════════

class EliminarCuentaCobrarAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cxc = get_object_or_404(CuentaPorCobrar, pk=pk)

        try:
            cxc.delete()
            return JsonResponse({'success': True})
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Confirmar el cobro de una cuota
# ══════════════════════════════════════════════════════════════════

class ConfirmarCuotaCobroAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cuota = get_object_or_404(CuotaCobro, pk=pk)

        try:
            data = json.loads(request.body)
            cuenta_pk = data.get('cuenta_pk')
            adelantar = bool(data.get('adelantar', False))

            cuota.confirmar(cuenta_pk, request.user, adelantar=adelantar)

            # En segundo plano: mismo criterio que ConfirmarCuotaAjax
            # (caja/views_deudas.py) para no colgar el pedido HTTP con
            # el ida y vuelta del SMTP.
            from asistencia.services.eventos import notificar_cuota_cobro_confirmada, enviar_en_background
            enviar_en_background(notificar_cuota_cobro_confirmada, cuota)

            return JsonResponse({'success': True, 'cuota': _serializar_cuota(cuota)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
