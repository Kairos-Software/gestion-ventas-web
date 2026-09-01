import json
import os
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import (
    Deuda, CuotaDeuda, CuentaCaja, TipoCaja, TipoDeuda, EstadoDeuda, EstadoCuota,
    DeudaDocumento, ModoCuotas, _calcular_plan_cuotas,
)


PERMISO_VER       = 'ver_deudas'
PERMISO_CREAR     = 'crear_deudas'
PERMISO_EDITAR    = 'editar_deudas'
PERMISO_ELIMINAR  = 'eliminar_deudas'
PERMISO_CONFIRMAR = 'confirmar_cuotas_deuda'

DOCUMENTO_TAMANIO_MAXIMO = 10 * 1024 * 1024
DOCUMENTO_EXTENSIONES_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf'}


def _cuenta_valida(cuenta_pk, es_credito):
    if not cuenta_pk:
        return None
    return CuentaCaja.objects.filter(
        pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True, es_credito=es_credito,
    ).first()


def _parsear_pago_historico(item):
    """
    Extrae de un dict de cuota/abono histórico (carga inicial) cómo se
    pagó, a lo sumo de una de tres formas: cuenta_pago_historica (real,
    solo informativa), cheque_historico (crea un Cheque real
    es_historico=True) o medio_pago (nota libre). Ninguna es obligatoria.
    """
    resultado = {'medio_pago': str(item.get('medio_pago', '') or '').strip()[:100]}
    cuenta_pk = item.get('cuenta_pago_historica_pk')
    if cuenta_pk:
        cuenta = _cuenta_valida(cuenta_pk, es_credito=False)
        if not cuenta:
            raise ValueError('Cuenta de pago histórico inválida.')
        resultado['cuenta_pago_historica'] = cuenta
    cheque = item.get('cheque_historico')
    if isinstance(cheque, dict) and cheque:
        resultado['cheque_historico'] = cheque
    return resultado


def _serializar_cuota(c):
    cheque = c.cheques.exclude(estado='anulado').order_by('-fecha_alta').first()
    return {
        'pk': c.pk,
        'numero': c.numero,
        'monto': str(c.monto),
        'fecha_vencimiento': c.fecha_vencimiento.isoformat(),
        'estado': c.estado,
        'habilitada': c.habilitada,
        'es_historica': c.es_historica,
        'medio_pago_historico': c.medio_pago_historico,
        'cuenta_pago_historica_pk': c.cuenta_pago_historica_id,
        'cuenta_pago_historica_nombre': c.cuenta_pago_historica.nombre if c.cuenta_pago_historica_id else '',
        'cuenta_pago_pk': c.cuenta_pago_id,
        'cuenta_pago_nombre': c.cuenta_pago.nombre if c.cuenta_pago_id else '',
        'cheque_pk': cheque.pk if cheque else None,
        'cheque_numero': (cheque.numero_cheque or 's/n') if cheque else '',
        'cheque_estado': cheque.estado if cheque else '',
        'cheque_es_historico': cheque.es_historico if cheque else False,
        'fecha_confirmacion': c.fecha_confirmacion.isoformat() if c.fecha_confirmacion else '',
        'confirmado_por': str(c.confirmado_por) if c.confirmado_por else '',
    }


def _serializar_documento(doc):
    return {
        'pk': doc.pk,
        'nombre': doc.nombre_archivo,
        'url': doc.archivo.url,
        'tipo': doc.tipo,
        'tipo_label': doc.get_tipo_display(),
        'descripcion': doc.descripcion,
        'es_imagen': doc.es_imagen,
        'es_pdf': doc.es_pdf,
        'subido_el': doc.subido_el.strftime('%d/%m/%Y %H:%M'),
    }


def _serializar_deuda(d, con_cuotas=False):
    data = {
        'pk': d.pk,
        'tipo': d.tipo,
        'tipo_display': d.get_tipo_display(),
        'descripcion': d.descripcion,
        'numero_comprobante': d.numero_comprobante,
        'es_carga_inicial': d.es_carga_inicial,
        'modo_cuotas': d.modo_cuotas,
        'modo_cuotas_display': d.get_modo_cuotas_display(),
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
        data['documentos'] = [_serializar_documento(doc) for doc in d.documentos.all()]
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
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'es_credito': c.es_credito,
             'tipo': c.tipo, 'titular': c.titular, 'preferida': c.preferida}
            for c in cuentas
        ])
        ctx['today'] = timezone.localtime().date().isoformat()

        from django.urls import reverse
        ctx['url_listar'] = reverse('caja:listar_deudas')
        ctx['url_crear'] = reverse('caja:crear_deuda')
        ctx['url_editar'] = reverse('caja:editar_deuda', args=[0])
        ctx['url_eliminar'] = reverse('caja:eliminar_deuda', args=[0])
        ctx['url_detalle'] = reverse('caja:detalle_deuda', args=[0])
        ctx['url_confirmar_cuota'] = reverse('caja:confirmar_cuota_deuda', args=[0])
        ctx['url_registrar_abono'] = reverse('caja:registrar_abono_deuda', args=[0])
        ctx['url_previsualizar_cuotas'] = reverse('caja:previsualizar_cuotas_deuda')
        ctx['url_documento_subir'] = reverse('caja:deuda_documento_subir')
        ctx['url_documento_eliminar'] = reverse('caja:deuda_documento_eliminar')

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
            qs = qs.filter(descripcion__icontains=q) | qs.filter(numero_comprobante__icontains=q)

        try:
            pagina = max(int(request.GET.get('pagina', 1)), 1)
            por_pagina = min(max(int(request.GET.get('por_pagina', 50)), 1), 200)
        except ValueError:
            pagina, por_pagina = 1, 50

        total = qs.count()
        inicio = (pagina - 1) * por_pagina
        items = qs[inicio:inicio + por_pagina]

        data = [_serializar_deuda(d) for d in items]

        # Total adeudado por moneda: siempre global (no depende de los
        # filtros/paginación de arriba), para la barra "Debés" de la pantalla.
        # Cuotas fijas: el saldo está representado por cuotas CuotaDeuda
        # PENDIENTE reales, así que alcanza con sumarlas por SQL. Cuotas
        # libres NO tienen cuotas futuras pre-generadas (se pagan de a
        # abonos sueltos) — su saldo no existe como fila en la tabla, solo
        # como la property `saldo_pendiente` calculada en Python, así que
        # hay que sumarlas aparte iterando las deudas activas en modo libre.
        totales_pendientes = {}
        agregado_fijas = (
            CuotaDeuda.objects
            .filter(estado=EstadoCuota.PENDIENTE, deuda__estado=EstadoDeuda.ACTIVA,
                    deuda__modo_cuotas=ModoCuotas.FIJAS)
            .values('deuda__moneda')
            .annotate(total=Sum('monto'))
        )
        for row in agregado_fijas:
            moneda = row['deuda__moneda']
            totales_pendientes[moneda] = totales_pendientes.get(moneda, Decimal('0')) + row['total']

        deudas_libres = Deuda.objects.filter(estado=EstadoDeuda.ACTIVA, modo_cuotas=ModoCuotas.LIBRE)
        for deuda_libre in deudas_libres:
            saldo = deuda_libre.saldo_pendiente
            if saldo:
                totales_pendientes[deuda_libre.moneda] = totales_pendientes.get(deuda_libre.moneda, Decimal('0')) + saldo

        totales_pendientes = {moneda: str(total) for moneda, total in totales_pendientes.items() if total}

        return JsonResponse({
            'results': data,
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
            'totales_pendientes': totales_pendientes,
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
            numero_comprobante = data.get('numero_comprobante', '').strip()
            es_carga_inicial = bool(data.get('es_carga_inicial', False))

            modo_cuotas = data.get('modo_cuotas', ModoCuotas.FIJAS)
            if modo_cuotas not in ModoCuotas.values:
                return JsonResponse({'error': 'Modo de cuotas inválido.'}, status=400)
            es_libre = modo_cuotas == ModoCuotas.LIBRE

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

            cantidad_cuotas = None
            if not es_libre:
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
            elif tipo == TipoDeuda.PRESTAMO:
                cuenta_acreditacion = _cuenta_valida(data.get('cuenta_acreditacion_pk'), es_credito=False)
                if not cuenta_acreditacion:
                    return JsonResponse({'error': 'Elegí la cuenta que recibe el préstamo.'}, status=400)
                if not descripcion:
                    return JsonResponse({'error': 'La descripción es obligatoria.'}, status=400)
            else:  # CHEQUE — no requiere tarjeta ni cuenta de acreditación, cada cuota se paga sola después
                if not descripcion:
                    return JsonResponse({'error': 'La descripción es obligatoria.'}, status=400)

            cuotas_historicas = []
            abonos_historicos = []
            if es_carga_inicial:
                if es_libre:
                    for ab in (data.get('abonos_historicos') or []):
                        try:
                            monto_ab = Decimal(str(ab.get('monto')))
                            fecha_pago = date.fromisoformat(str(ab.get('fecha_pago')))
                        except (TypeError, ValueError, InvalidOperation):
                            return JsonResponse({'error': 'Abono histórico con monto o fecha inválidos.'}, status=400)
                        if monto_ab <= 0:
                            return JsonResponse({'error': 'El monto de un abono histórico debe ser mayor a 0.'}, status=400)
                        entry = {'monto': monto_ab, 'fecha_pago': fecha_pago}
                        entry.update(_parsear_pago_historico(ab))
                        abonos_historicos.append(entry)
                else:
                    for ch in (data.get('cuotas_historicas') or []):
                        try:
                            numero = int(ch.get('numero'))
                            fecha_pago = date.fromisoformat(str(ch.get('fecha_pago')))
                        except (TypeError, ValueError):
                            return JsonResponse({'error': 'Cuota histórica con número o fecha inválidos.'}, status=400)
                        entry = {'numero': numero, 'fecha_pago': fecha_pago}
                        entry.update(_parsear_pago_historico(ch))
                        cuotas_historicas.append(entry)

            deuda = Deuda.crear_con_cuotas(
                tipo=tipo, monto_original=monto_original, porcentaje_interes=interes_pct,
                cantidad_cuotas=cantidad_cuotas, fecha_inicio=fecha_inicio, moneda=moneda,
                descripcion=descripcion, notas=notas, numero_comprobante=numero_comprobante,
                cuenta_tarjeta=cuenta_tarjeta, cuenta_acreditacion=cuenta_acreditacion,
                creado_por=request.user, modo_cuotas=modo_cuotas,
                es_carga_inicial=es_carga_inicial, cuotas_historicas=cuotas_historicas,
                abonos_historicos=abonos_historicos,
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

            kwargs = {}
            if 'descripcion' in data:
                kwargs['descripcion'] = data.get('descripcion', '').strip()
            if 'notas' in data:
                kwargs['notas'] = data.get('notas', '').strip()
            if 'numero_comprobante' in data:
                kwargs['numero_comprobante'] = data.get('numero_comprobante', '').strip()

            if 'monto_original' in data:
                try:
                    kwargs['monto_original'] = Decimal(str(data.get('monto_original')))
                except (InvalidOperation, ValueError, TypeError):
                    return JsonResponse({'error': 'Monto inválido.'}, status=400)
            if 'porcentaje_interes' in data:
                try:
                    kwargs['porcentaje_interes'] = Decimal(str(data.get('porcentaje_interes', 0) or 0))
                except (InvalidOperation, ValueError, TypeError):
                    return JsonResponse({'error': 'Porcentaje de interés inválido.'}, status=400)
            if 'cantidad_cuotas' in data:
                try:
                    kwargs['cantidad_cuotas'] = int(data.get('cantidad_cuotas', 0))
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Cantidad de cuotas inválida.'}, status=400)
            if 'fecha_inicio' in data:
                try:
                    kwargs['fecha_inicio'] = date.fromisoformat(str(data.get('fecha_inicio')))
                except (ValueError, TypeError):
                    return JsonResponse({'error': 'Fecha de inicio inválida.'}, status=400)
            if 'moneda' in data:
                kwargs['moneda'] = data.get('moneda')
            if 'cuenta_tarjeta_pk' in data:
                cuenta_tarjeta = _cuenta_valida(data.get('cuenta_tarjeta_pk'), es_credito=True)
                if not cuenta_tarjeta:
                    return JsonResponse({'error': 'Elegí la tarjeta con la que se pagó.'}, status=400)
                kwargs['cuenta_tarjeta'] = cuenta_tarjeta
            if 'cuenta_acreditacion_pk' in data:
                cuenta_acreditacion = _cuenta_valida(data.get('cuenta_acreditacion_pk'), es_credito=False)
                if not cuenta_acreditacion:
                    return JsonResponse({'error': 'Elegí la cuenta que recibe el préstamo.'}, status=400)
                kwargs['cuenta_acreditacion'] = cuenta_acreditacion

            deuda.editar(**kwargs)

            return JsonResponse({'success': True, 'deuda': _serializar_deuda(deuda, con_cuotas=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
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
            adelantar = bool(data.get('adelantar', False))

            if data.get('cheque'):
                # Pagada con cheque: todavía no es un pago real (ver
                # CuotaDeuda.confirmar_con_cheque) — el mail de "deuda
                # pagada" se manda recién cuando ESE cheque se cobra de
                # verdad (ver ConfirmarChequeAjax en views_cheques.py).
                cuota.confirmar_con_cheque(data.get('cheque'), request.user, adelantar=adelantar)
            else:
                cuota.confirmar(data.get('cuenta_pk'), request.user, adelantar=adelantar)

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


# ══════════════════════════════════════════════════════════════════
#  AJAX — Registrar un abono (solo deudas modo_cuotas=libre)
# ══════════════════════════════════════════════════════════════════

class RegistrarAbonoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        deuda = get_object_or_404(Deuda, pk=pk)

        if deuda.modo_cuotas != ModoCuotas.LIBRE:
            return JsonResponse({'error': 'Esta deuda no es de cuotas libres.'}, status=400)

        try:
            data = json.loads(request.body)

            try:
                monto = Decimal(str(data.get('monto')))
                if monto <= 0:
                    return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({'error': 'Monto inválido.'}, status=400)

            fecha = None
            if data.get('fecha'):
                try:
                    fecha = date.fromisoformat(str(data.get('fecha')))
                except ValueError:
                    return JsonResponse({'error': 'Fecha inválida.'}, status=400)

            if data.get('cheque'):
                # Pagado con cheque: el mail de "deuda pagada" se manda
                # recién cuando ESE cheque se cobra de verdad (ver
                # ConfirmarChequeAjax en views_cheques.py).
                cuota = deuda.registrar_abono(
                    monto=monto, usuario=request.user, cheque_data=data.get('cheque'), fecha=fecha,
                )
            else:
                cuota = deuda.registrar_abono(
                    monto=monto, usuario=request.user, cuenta_pk=data.get('cuenta_pk'), fecha=fecha,
                )
                from asistencia.services.eventos import notificar_deuda_pagada, enviar_en_background
                enviar_en_background(notificar_deuda_pagada, cuota)

            return JsonResponse({
                'success': True,
                'cuota': _serializar_cuota(cuota),
                'deuda': _serializar_deuda(deuda, con_cuotas=True),
            })

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Previsualizar el plan de cuotas (antes de guardar)
# ══════════════════════════════════════════════════════════════════

class PrevisualizarCuotasAjax(LoginRequiredMixin, View):
    """
    Calcula el plan de cuotas sin crear nada, usando la misma función
    que `generar_cuotas` — se usa en el modal de alta para que, al
    marcar "carga inicial", el usuario pueda tildar qué cuotas ya
    están pagadas viendo el monto y vencimiento reales de cada una.
    """

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            data = json.loads(request.body)

            try:
                monto_original = Decimal(str(data.get('monto_original')))
                if monto_original <= 0:
                    return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({'error': 'Monto inválido.'}, status=400)

            try:
                interes_pct = Decimal(str(data.get('porcentaje_interes', 0) or 0))
            except (InvalidOperation, ValueError, TypeError):
                return JsonResponse({'error': 'Porcentaje de interés inválido.'}, status=400)

            try:
                cantidad_cuotas = int(data.get('cantidad_cuotas', 0))
            except (ValueError, TypeError):
                cantidad_cuotas = 0
            if cantidad_cuotas < 1:
                return JsonResponse({'error': 'Indicá la cantidad de cuotas.'}, status=400)

            try:
                fecha_inicio = date.fromisoformat(str(data.get('fecha_inicio')))
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Fecha de inicio inválida.'}, status=400)

            plan = _calcular_plan_cuotas(monto_original, interes_pct, cantidad_cuotas, fecha_inicio)
            cuotas = [
                {
                    'numero': c['numero'],
                    'monto': str(c['monto']),
                    'fecha_vencimiento': c['fecha_vencimiento'].isoformat(),
                }
                for c in plan
            ]
            return JsonResponse({'cuotas': cuotas})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Documentos adjuntos de una deuda
# ══════════════════════════════════════════════════════════════════

class DeudaDocumentoSubirAjax(LoginRequiredMixin, View):
    """POST multipart → sube un documento a una deuda existente. Campos: deuda_pk, archivo, tipo, descripcion."""

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        deuda_pk = request.POST.get('deuda_pk')
        if not deuda_pk:
            return JsonResponse({'error': 'deuda_pk requerido.'}, status=400)

        archivo = request.FILES.get('archivo')
        if not archivo:
            return JsonResponse({'error': 'No se recibió ningún archivo.'}, status=400)

        if archivo.size > DOCUMENTO_TAMANIO_MAXIMO:
            return JsonResponse({'error': 'El archivo supera el límite de 10 MB.'}, status=400)

        ext = os.path.splitext(archivo.name)[1].lower()
        if ext not in DOCUMENTO_EXTENSIONES_PERMITIDAS:
            return JsonResponse(
                {'error': 'Tipo de archivo no permitido. Usá JPG, PNG, WEBP, GIF o PDF.'},
                status=400,
            )

        deuda = get_object_or_404(Deuda, pk=deuda_pk)

        doc = DeudaDocumento(
            deuda=deuda, archivo=archivo,
            tipo=request.POST.get('tipo', 'otro'),
            descripcion=request.POST.get('descripcion', ''),
            subido_por=request.user,
        )
        doc.save()

        return JsonResponse({'ok': True, 'documento': _serializar_documento(doc)})


class DeudaDocumentoEliminarAjax(LoginRequiredMixin, View):
    """POST JSON { pk } → elimina el documento y el archivo del disco."""

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        pk = body.get('pk')
        if not pk:
            return JsonResponse({'error': 'pk requerido.'}, status=400)

        doc = get_object_or_404(DeudaDocumento, pk=pk)

        if doc.archivo and os.path.isfile(doc.archivo.path):
            os.remove(doc.archivo.path)

        doc.delete()
        return JsonResponse({'ok': True})
