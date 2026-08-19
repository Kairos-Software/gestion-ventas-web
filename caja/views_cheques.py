import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import (
    Cheque, CuentaCaja, TipoCaja, TipoCuenta, TipoCheque, EstadoCheque,
    cuenta_chequera_valida as _cuenta_chequera_valida,
    cuenta_caja_valida as _cuenta_valida,
    validar_cuenta_financiadora as _validar_financiadora,
    fondear_chequera as _fondear_chequera,
)


PERMISO_VER       = 'ver_cheques'
PERMISO_CREAR     = 'crear_cheques'
PERMISO_EDITAR    = 'editar_cheques'
PERMISO_ELIMINAR  = 'eliminar_cheques'
PERMISO_CONFIRMAR = 'confirmar_cheques'


def _serializar_cheque(c):
    return {
        'pk': c.pk,
        'tipo': c.tipo,
        'tipo_display': c.get_tipo_display(),
        'numero_cheque': c.numero_cheque,
        'numero_factura': c.numero_factura,
        'monto': str(c.monto),
        'moneda': c.moneda,
        'fecha_emision': c.fecha_emision.isoformat(),
        'fecha_cobro': c.fecha_cobro.isoformat(),
        'cuenta_origen_pk': c.cuenta_origen_id,
        'cuenta_origen_nombre': c.cuenta_origen.nombre if c.cuenta_origen_id else '',
        'banco': c.banco,
        'emisor': c.emisor,
        'cuenta_destino_pk': c.cuenta_destino_id,
        'cuenta_destino_nombre': c.cuenta_destino.nombre if c.cuenta_destino_id else '',
        'receptor': c.receptor,
        'estado': c.estado,
        'estado_display': c.get_estado_display(),
        'notas': c.notas,
        'fecha_confirmacion': c.fecha_confirmacion.isoformat() if c.fecha_confirmacion else '',
        'confirmado_por': str(c.confirmado_por) if c.confirmado_por else '',
        'creado_por': str(c.creado_por) if c.creado_por else '',
        'fecha_alta': c.fecha_alta.isoformat(),
        # Si nació de una venta/compra/cuota (no cargado a mano), eliminarlo
        # directo borra el historial de esa operación — el frontend usa esto
        # para sugerir "Rechazar" en su lugar antes de confirmar el borrado.
        'tiene_origen_real': bool(
            c.pago_venta_id or c.pago_compra_id or c.cuota_deuda_id or c.cuota_cobro_id
        ),
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
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'tipo': c.tipo, 'titular': c.titular}
            for c in cuentas
        ])
        ctx['today'] = timezone.localtime().date().isoformat()

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
            qs = (
                qs.filter(numero_cheque__icontains=q)
                | qs.filter(numero_factura__icontains=q)
                | qs.filter(receptor__icontains=q)
                | qs.filter(emisor__icontains=q)
            )

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
            financiadora = None
            if tipo == TipoCheque.A_PAGAR:
                cuenta_origen = _cuenta_chequera_valida(data.get('cuenta_origen_pk'), moneda)
                if not cuenta_origen:
                    return JsonResponse({'error': 'Elegí la cuenta bancaria (chequera) de la que sale el cheque.'}, status=400)

                if data.get('cuenta_financiadora_pk'):
                    financiadora, error = _validar_financiadora(
                        data.get('cuenta_financiadora_pk'), cuenta_origen, moneda, monto,
                    )
                    if error:
                        return JsonResponse({'error': error}, status=400)

            with transaction.atomic():
                cheque = Cheque.objects.create(
                    tipo=tipo,
                    numero_cheque=data.get('numero_cheque', '').strip(),
                    numero_factura=data.get('numero_factura', '').strip(),
                    monto=monto,
                    moneda=moneda,
                    fecha_emision=fecha_emision,
                    fecha_cobro=fecha_cobro,
                    cuenta_origen=cuenta_origen,
                    banco=data.get('banco', '').strip(),
                    emisor=data.get('emisor', '').strip(),
                    receptor=data.get('receptor', '').strip(),
                    notas=data.get('notas', '').strip(),
                    creado_por=request.user,
                )

                if financiadora:
                    _fondear_chequera(financiadora, cuenta_origen, monto, fecha_emision, cheque, request.user)

            from asistencia.services.eventos import notificar_cheque_si_proximo, enviar_en_background
            enviar_en_background(notificar_cheque_si_proximo, cheque)

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

            # Un cheque que nació solo de una venta/compra/cuota (no cargado
            # a mano) no puede tener su monto real alterado — desincroniza
            # lo que esa operación registró de verdad. Los datos puramente
            # descriptivos (número, banco, emisor/receptor, notas) siguen
            # editables igual.
            campos_plan = {'monto', 'moneda', 'fecha_emision', 'fecha_cobro', 'cuenta_origen_pk'}
            tiene_origen_real = bool(
                cheque.pago_venta_id or cheque.pago_compra_id
                or cheque.cuota_deuda_id or cheque.cuota_cobro_id
            )
            if tiene_origen_real and campos_plan & data.keys():
                return JsonResponse({
                    'error': 'Este cheque nació de una venta/compra/cuota — no se puede editar '
                             'su monto, moneda, fechas ni cuenta.',
                }, status=400)

            # numero_factura: en un cheque A_PAGAR es la factura real del
            # proveedor (tipeada a mano, puede tener un typo) — sigue
            # editable siempre. En un cheque A_COBRAR con origen real es
            # nuestro propio N° de venta, generado por el sistema — no
            # tiene sentido de negocio que se edite a mano (mismo criterio
            # que CuentaPorCobrar.editar() con numero_comprobante).
            if tiene_origen_real and cheque.tipo == TipoCheque.A_COBRAR and 'numero_factura' in data:
                return JsonResponse({
                    'error': 'Este cheque nació de una venta — su N° de comprobante lo generó '
                             'el sistema y no se puede editar.',
                }, status=400)

            if 'numero_cheque' in data:
                cheque.numero_cheque = data.get('numero_cheque', '').strip()
            if 'numero_factura' in data:
                cheque.numero_factura = data.get('numero_factura', '').strip()
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
                cuenta_origen = _cuenta_chequera_valida(data.get('cuenta_origen_pk'), cheque.moneda)
                if not cuenta_origen:
                    return JsonResponse({'error': 'Elegí una cuenta bancaria válida.'}, status=400)
                cheque.cuenta_origen = cuenta_origen
            if 'banco' in data:
                cheque.banco = data.get('banco', '').strip()
            if 'emisor' in data:
                cheque.emisor = data.get('emisor', '').strip()
            if 'receptor' in data:
                cheque.receptor = data.get('receptor', '').strip()
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

            # Si este cheque pagaba/cobraba una cuota de Deuda/CxC, recién
            # ahora esa cuota quedó CONFIRMADA de verdad (ver
            # Cheque.confirmar() -> _sincronizar_cuota_desde_cheque) — el
            # mail de "pagada/cobrada" se manda en este momento, no cuando
            # se emitió el cheque.
            if cheque.cuota_deuda_id:
                from asistencia.services.eventos import notificar_deuda_pagada, enviar_en_background
                enviar_en_background(notificar_deuda_pagada, cheque.cuota_deuda)
            elif cheque.cuota_cobro_id:
                from asistencia.services.eventos import notificar_cuota_cobro_confirmada, enviar_en_background
                enviar_en_background(notificar_cuota_cobro_confirmada, cheque.cuota_cobro)

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
