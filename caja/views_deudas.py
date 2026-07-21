import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import (
    Deuda, CuotaDeuda, CuentaCaja, TipoCaja, TipoDeuda, EstadoDeuda,
)


PERMISO_VER       = 'ver_deudas'
PERMISO_CREAR     = 'crear_deudas'
PERMISO_EDITAR    = 'editar_deudas'
PERMISO_ELIMINAR  = 'eliminar_deudas'
PERMISO_CONFIRMAR = 'confirmar_cuotas_deuda'


def _cuenta_valida(cuenta_pk, es_credito):
    if not cuenta_pk:
        return None
    return CuentaCaja.objects.filter(
        pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True, es_credito=es_credito,
    ).first()


def _serializar_cuota(c):
    return {
        'pk': c.pk,
        'numero': c.numero,
        'monto': str(c.monto),
        'fecha_vencimiento': c.fecha_vencimiento.isoformat(),
        'estado': c.estado,
        'habilitada': c.habilitada,
        'cuenta_pago_pk': c.cuenta_pago_id,
        'cuenta_pago_nombre': c.cuenta_pago.nombre if c.cuenta_pago_id else '',
        'fecha_confirmacion': c.fecha_confirmacion.isoformat() if c.fecha_confirmacion else '',
        'confirmado_por': str(c.confirmado_por) if c.confirmado_por else '',
    }


def _serializar_deuda(d, con_cuotas=False):
    data = {
        'pk': d.pk,
        'tipo': d.tipo,
        'tipo_display': d.get_tipo_display(),
        'descripcion': d.descripcion,
        'cuenta_tarjeta_pk': d.cuenta_tarjeta_id,
        'cuenta_tarjeta_nombre': d.cuenta_tarjeta.nombre if d.cuenta_tarjeta_id else '',
        'cuenta_acreditacion_pk': d.cuenta_acreditacion_id,
        'cuenta_acreditacion_nombre': d.cuenta_acreditacion.nombre if d.cuenta_acreditacion_id else '',
        'monto_original': str(d.monto_original),
        'porcentaje_interes': str(d.porcentaje_interes),
        'monto_total': str(d.monto_total),
        'moneda': d.moneda,
        'cantidad_cuotas': d.cantidad_cuotas,
        'cuotas_pagadas': d.cuotas_pagadas,
        'saldo_pendiente': str(d.saldo_pendiente),
        'fecha_inicio': d.fecha_inicio.isoformat(),
        'estado': d.estado,
        'estado_display': d.get_estado_display(),
        'notas': d.notas,
        'compra_numero': d.pago_compra.compra.numero if d.pago_compra_id else '',
        'creado_por': str(d.creado_por) if d.creado_por else '',
        'fecha_alta': d.fecha_alta.isoformat(),
    }
    if con_cuotas:
        data['cuotas'] = [_serializar_cuota(c) for c in d.cuotas.all()]
    return data


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Créditos y préstamos
# ══════════════════════════════════════════════════════════════════

class DeudasView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/deudas.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_ver'] = True
        ctx['puede_crear'] = chequear_permiso(self.request.user, PERMISO_CREAR)
        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, PERMISO_ELIMINAR)
        ctx['puede_confirmar'] = chequear_permiso(self.request.user, PERMISO_CONFIRMAR)

        from .models import asegurar_cuentas_efectivo
        asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE)

        ctx['monedas'] = Moneda.choices
        ctx['tipos_deuda'] = TipoDeuda.choices

        cuentas = CuentaCaja.objects.filter(caja=TipoCaja.GRANDE, activa=True).order_by('orden', 'nombre')
        ctx['cuentas_json'] = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'es_credito': c.es_credito}
            for c in cuentas
        ])
        ctx['today'] = timezone.now().date().isoformat()

        from django.urls import reverse
        ctx['url_listar'] = reverse('caja:listar_deudas')
        ctx['url_crear'] = reverse('caja:crear_deuda')
        ctx['url_editar'] = reverse('caja:editar_deuda', args=[0])
        ctx['url_eliminar'] = reverse('caja:eliminar_deuda', args=[0])
        ctx['url_detalle'] = reverse('caja:detalle_deuda', args=[0])
        ctx['url_confirmar_cuota'] = reverse('caja:confirmar_cuota_deuda', args=[0])

        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listar (con filtros + paginación)
# ══════════════════════════════════════════════════════════════════

class ListarDeudasAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Deuda.objects.all().select_related(
            'cuenta_tarjeta', 'cuenta_acreditacion', 'creado_por', 'pago_compra__compra',
        )

        tipo = request.GET.get('tipo', '').strip()
        estado = request.GET.get('estado', '').strip()
        moneda = request.GET.get('moneda', '').strip()
        q = request.GET.get('q', '').strip()

        if tipo in TipoDeuda.values:
            qs = qs.filter(tipo=tipo)
        if estado in EstadoDeuda.values:
            qs = qs.filter(estado=estado)
        if moneda:
            qs = qs.filter(moneda=moneda)
        if q:
            qs = qs.filter(descripcion__icontains=q)

        try:
            pagina = max(int(request.GET.get('pagina', 1)), 1)
            por_pagina = min(max(int(request.GET.get('por_pagina', 50)), 1), 200)
        except ValueError:
            pagina, por_pagina = 1, 50

        total = qs.count()
        inicio = (pagina - 1) * por_pagina
        items = qs[inicio:inicio + por_pagina]

        data = [_serializar_deuda(d) for d in items]

        return JsonResponse({
            'results': data,
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Detalle (deuda + cuotas)
# ══════════════════════════════════════════════════════════════════

class DetalleDeudaAjax(LoginRequiredMixin, View):
    def get(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        deuda = get_object_or_404(Deuda.objects.select_related('cuenta_tarjeta', 'cuenta_acreditacion'), pk=pk)
        return JsonResponse({'deuda': _serializar_deuda(deuda, con_cuotas=True)})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear (alta manual: préstamo, o crédito sin compra)
# ══════════════════════════════════════════════════════════════════

class CrearDeudaAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            data = json.loads(request.body)

            tipo = data.get('tipo')
            if tipo not in TipoDeuda.values:
                return JsonResponse({'error': 'Tipo de deuda inválido.'}, status=400)

            descripcion = data.get('descripcion', '').strip()
            notas = data.get('notas', '').strip()
            moneda = data.get('moneda', Moneda.ARS)

            try:
                monto_original = Decimal(str(data.get('monto_original')))
                if monto_original <= 0:
                    return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({'error': 'Monto inválido.'}, status=400)

            try:
                interes_pct = Decimal(str(data.get('porcentaje_interes', 0) or 0))
                if interes_pct < 0:
                    return JsonResponse({'error': 'El interés no puede ser negativo.'}, status=400)
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({'error': 'Porcentaje de interés inválido.'}, status=400)

            try:
                cantidad_cuotas = int(data.get('cantidad_cuotas', 0))
            except (ValueError, TypeError):
                cantidad_cuotas = 0
            if cantidad_cuotas < 1:
                return JsonResponse({'error': 'Indicá la cantidad de cuotas.'}, status=400)

            fecha_inicio_raw = data.get('fecha_inicio')
            if not fecha_inicio_raw:
                return JsonResponse({'error': 'Indicá la fecha de inicio.'}, status=400)
            try:
                fecha_inicio = date.fromisoformat(str(fecha_inicio_raw))
            except ValueError:
                return JsonResponse({'error': 'Fecha de inicio inválida.'}, status=400)

            cuenta_tarjeta = cuenta_acreditacion = None
            if tipo == TipoDeuda.COMPRA_CREDITO:
                cuenta_tarjeta = _cuenta_valida(data.get('cuenta_tarjeta_pk'), es_credito=True)
                if not cuenta_tarjeta:
                    return JsonResponse({'error': 'Elegí la tarjeta con la que se pagó.'}, status=400)
                if not descripcion:
                    return JsonResponse({'error': 'La descripción es obligatoria.'}, status=400)
            else:
                cuenta_acreditacion = _cuenta_valida(data.get('cuenta_acreditacion_pk'), es_credito=False)
                if not cuenta_acreditacion:
                    return JsonResponse({'error': 'Elegí la cuenta que recibe el préstamo.'}, status=400)
                if not descripcion:
                    return JsonResponse({'error': 'La descripción es obligatoria.'}, status=400)

            deuda = Deuda.crear_con_cuotas(
                tipo=tipo, monto_original=monto_original, porcentaje_interes=interes_pct,
                cantidad_cuotas=cantidad_cuotas, fecha_inicio=fecha_inicio, moneda=moneda,
                descripcion=descripcion, notas=notas,
                cuenta_tarjeta=cuenta_tarjeta, cuenta_acreditacion=cuenta_acreditacion,
                creado_por=request.user,
            )

            from asistencia.services.eventos import notificar_cuotas_deuda_si_proximas, enviar_en_background
            enviar_en_background(notificar_cuotas_deuda_si_proximas, deuda)

            return JsonResponse({'success': True, 'deuda': _serializar_deuda(deuda, con_cuotas=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Editar (limitado si ya hay cuotas confirmadas)
# ══════════════════════════════════════════════════════════════════

class EditarDeudaAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        deuda = get_object_or_404(Deuda, pk=pk)

        try:
            data = json.loads(request.body)

            if 'descripcion' in data:
                deuda.descripcion = data.get('descripcion', '').strip()
            if 'notas' in data:
                deuda.notas = data.get('notas', '').strip()
            deuda.save(update_fields=['descripcion', 'notas'])

            return JsonResponse({'success': True, 'deuda': _serializar_deuda(deuda, con_cuotas=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar
# ══════════════════════════════════════════════════════════════════

class EliminarDeudaAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        deuda = get_object_or_404(Deuda, pk=pk)

        try:
            deuda.delete()
            return JsonResponse({'success': True})
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Confirmar el pago de una cuota
# ══════════════════════════════════════════════════════════════════

class ConfirmarCuotaAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cuota = get_object_or_404(CuotaDeuda, pk=pk)

        try:
            data = json.loads(request.body)
            cuenta_pk = data.get('cuenta_pk')

            cuota.confirmar(cuenta_pk, request.user)

            # En segundo plano: si esperáramos a que el mail salga acá,
            # el pedido HTTP se queda 1-2s colgado por el ida y vuelta
            # del SMTP, y del lado del navegador se siente como que el
            # sistema se trabó.
            from asistencia.services.eventos import notificar_deuda_pagada, enviar_en_background
            enviar_en_background(notificar_deuda_pagada, cuota)

            return JsonResponse({'success': True, 'cuota': _serializar_cuota(cuota)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
