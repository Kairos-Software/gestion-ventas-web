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
    Cheque, CuentaCaja, TipoCaja, TipoCheque, EstadoCheque,
)


PERMISO_VER       = 'ver_cheques'
PERMISO_CREAR     = 'crear_cheques'
PERMISO_EDITAR    = 'editar_cheques'
PERMISO_ELIMINAR  = 'eliminar_cheques'
PERMISO_CONFIRMAR = 'confirmar_cheques'


def _cuenta_valida(cuenta_pk, moneda):
    if not cuenta_pk:
        return None
    return CuentaCaja.objects.filter(
        pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True, es_credito=False, moneda=moneda,
    ).first()


def _serializar_cheque(c):
    return {
        'pk': c.pk,
        'tipo': c.tipo,
        'tipo_display': c.get_tipo_display(),
        'numero_cheque': c.numero_cheque,
        'monto': str(c.monto),
        'moneda': c.moneda,
        'fecha_emision': c.fecha_emision.isoformat(),
        'fecha_cobro': c.fecha_cobro.isoformat(),
        'cuenta_origen_pk': c.cuenta_origen_id,
        'cuenta_origen_nombre': c.cuenta_origen.nombre if c.cuenta_origen_id else '',
        'banco_librador': c.banco_librador,
        'titular_librador': c.titular_librador,
        'cuenta_destino_pk': c.cuenta_destino_id,
        'cuenta_destino_nombre': c.cuenta_destino.nombre if c.cuenta_destino_id else '',
        'contraparte': c.contraparte,
        'estado': c.estado,
        'estado_display': c.get_estado_display(),
        'notas': c.notas,
        'fecha_confirmacion': c.fecha_confirmacion.isoformat() if c.fecha_confirmacion else '',
        'confirmado_por': str(c.confirmado_por) if c.confirmado_por else '',
        'creado_por': str(c.creado_por) if c.creado_por else '',
        'fecha_alta': c.fecha_alta.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Cheques
# ══════════════════════════════════════════════════════════════════

class ChequesView(LoginRequiredMixin, TemplateView):
    template_name = 'caja/cheques.html'

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
        ctx['tipos_cheque'] = TipoCheque.choices

        cuentas = CuentaCaja.objects.filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False).order_by('orden', 'nombre')
        ctx['cuentas_json'] = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda}
            for c in cuentas
        ])
        ctx['today'] = timezone.now().date().isoformat()

        from django.urls import reverse
        ctx['url_listar'] = reverse('caja:listar_cheques')
        ctx['url_crear'] = reverse('caja:crear_cheque')
        ctx['url_editar'] = reverse('caja:editar_cheque', args=[0])
        ctx['url_eliminar'] = reverse('caja:eliminar_cheque', args=[0])
        ctx['url_confirmar'] = reverse('caja:confirmar_cheque', args=[0])
        ctx['url_rechazar'] = reverse('caja:rechazar_cheque', args=[0])

        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listar (con filtros + paginación)
# ══════════════════════════════════════════════════════════════════

class ListarChequesAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Cheque.objects.all().select_related('cuenta_origen', 'cuenta_destino', 'creado_por')

        tipo = request.GET.get('tipo', '').strip()
        estado = request.GET.get('estado', '').strip()
        moneda = request.GET.get('moneda', '').strip()
        q = request.GET.get('q', '').strip()

        if tipo in TipoCheque.values:
            qs = qs.filter(tipo=tipo)
        if estado in EstadoCheque.values:
            qs = qs.filter(estado=estado)
        if moneda:
            qs = qs.filter(moneda=moneda)
        if q:
            qs = qs.filter(numero_cheque__icontains=q) | qs.filter(contraparte__icontains=q)

        try:
            pagina = max(int(request.GET.get('pagina', 1)), 1)
            por_pagina = min(max(int(request.GET.get('por_pagina', 50)), 1), 200)
        except ValueError:
            pagina, por_pagina = 1, 50

        total = qs.count()
        inicio = (pagina - 1) * por_pagina
        items = qs[inicio:inicio + por_pagina]

        data = [_serializar_cheque(c) for c in items]

        return JsonResponse({
            'results': data,
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear
# ══════════════════════════════════════════════════════════════════

class CrearChequeAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            data = json.loads(request.body)

            tipo = data.get('tipo')
            if tipo not in TipoCheque.values:
                return JsonResponse({'error': 'Tipo de cheque inválido.'}, status=400)

            try:
                monto = Decimal(str(data.get('monto')))
                if monto <= 0:
                    return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({'error': 'Monto inválido.'}, status=400)

            moneda = data.get('moneda', Moneda.ARS)

            fecha_emision_raw = data.get('fecha_emision')
            fecha_cobro_raw = data.get('fecha_cobro')
            if not fecha_emision_raw or not fecha_cobro_raw:
                return JsonResponse({'error': 'Indicá fecha de emisión y de cobro.'}, status=400)
            try:
                fecha_emision = date.fromisoformat(str(fecha_emision_raw))
                fecha_cobro = date.fromisoformat(str(fecha_cobro_raw))
            except ValueError:
                return JsonResponse({'error': 'Fechas inválidas.'}, status=400)

            cuenta_origen = None
            if tipo == TipoCheque.A_PAGAR:
                cuenta_origen = _cuenta_valida(data.get('cuenta_origen_pk'), moneda)
                if not cuenta_origen:
                    return JsonResponse({'error': 'Elegí la cuenta propia (chequera) de la que sale el cheque.'}, status=400)

            cheque = Cheque.objects.create(
                tipo=tipo,
                numero_cheque=data.get('numero_cheque', '').strip(),
                monto=monto,
                moneda=moneda,
                fecha_emision=fecha_emision,
                fecha_cobro=fecha_cobro,
                cuenta_origen=cuenta_origen,
                banco_librador=data.get('banco_librador', '').strip(),
                titular_librador=data.get('titular_librador', '').strip(),
                contraparte=data.get('contraparte', '').strip(),
                notas=data.get('notas', '').strip(),
                creado_por=request.user,
            )

            return JsonResponse({'success': True, 'cheque': _serializar_cheque(cheque)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Editar
# ══════════════════════════════════════════════════════════════════

class EditarChequeAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cheque = get_object_or_404(Cheque, pk=pk)

        try:
            data = json.loads(request.body)

            if cheque.estado != EstadoCheque.PENDIENTE:
                # Ya confirmado/rechazado/anulado: solo notas.
                if 'notas' in data:
                    cheque.notas = data.get('notas', '').strip()
                cheque.save(update_fields=['notas'])
                return JsonResponse({'success': True, 'cheque': _serializar_cheque(cheque)})

            if 'numero_cheque' in data:
                cheque.numero_cheque = data.get('numero_cheque', '').strip()
            if 'monto' in data:
                try:
                    monto = Decimal(str(data.get('monto')))
                    if monto <= 0:
                        return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)
                    cheque.monto = monto
                except (InvalidOperation, ValueError, TypeError):
                    return JsonResponse({'error': 'Monto inválido.'}, status=400)
            if 'moneda' in data:
                cheque.moneda = data.get('moneda')
            if 'fecha_emision' in data:
                try:
                    cheque.fecha_emision = date.fromisoformat(str(data.get('fecha_emision')))
                except ValueError:
                    return JsonResponse({'error': 'Fecha de emisión inválida.'}, status=400)
            if 'fecha_cobro' in data:
                try:
                    cheque.fecha_cobro = date.fromisoformat(str(data.get('fecha_cobro')))
                except ValueError:
                    return JsonResponse({'error': 'Fecha de cobro inválida.'}, status=400)
            if cheque.tipo == TipoCheque.A_PAGAR and 'cuenta_origen_pk' in data:
                cuenta_origen = _cuenta_valida(data.get('cuenta_origen_pk'), cheque.moneda)
                if not cuenta_origen:
                    return JsonResponse({'error': 'Elegí una cuenta válida.'}, status=400)
                cheque.cuenta_origen = cuenta_origen
            if 'banco_librador' in data:
                cheque.banco_librador = data.get('banco_librador', '').strip()
            if 'titular_librador' in data:
                cheque.titular_librador = data.get('titular_librador', '').strip()
            if 'contraparte' in data:
                cheque.contraparte = data.get('contraparte', '').strip()
            if 'notas' in data:
                cheque.notas = data.get('notas', '').strip()

            cheque.save()

            return JsonResponse({'success': True, 'cheque': _serializar_cheque(cheque)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar
# ══════════════════════════════════════════════════════════════════

class EliminarChequeAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cheque = get_object_or_404(Cheque, pk=pk)

        try:
            cheque.delete()
            return JsonResponse({'success': True})
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Confirmar / Rechazar
# ══════════════════════════════════════════════════════════════════

class ConfirmarChequeAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cheque = get_object_or_404(Cheque, pk=pk)

        try:
            data = json.loads(request.body) if request.body else {}
            cuenta_pk = data.get('cuenta_pk')

            cheque.confirmar(request.user, cuenta_pk=cuenta_pk)

            return JsonResponse({'success': True, 'cheque': _serializar_cheque(cheque)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class RechazarChequeAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cheque = get_object_or_404(Cheque, pk=pk)

        try:
            cheque.rechazar()
            return JsonResponse({'success': True, 'cheque': _serializar_cheque(cheque)})
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
