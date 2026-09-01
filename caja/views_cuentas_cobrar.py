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
from django.db.models import Q, Sum

from productos.models import Moneda
from core.models import Cliente
from core.permisos import chequear_permiso

from .models import (
    CuentaPorCobrar, CuotaCobro, CuentaCaja, TipoCaja, EstadoDeuda, EstadoCuota,
    CuentaPorCobrarDocumento, ModoCuotas, _calcular_plan_cuotas,
    Cheque, EstadoCheque, TipoCheque,
)


PERMISO_VER       = 'ver_cuentas_cobrar'
PERMISO_CREAR     = 'crear_cuentas_cobrar'
PERMISO_EDITAR    = 'editar_cuentas_cobrar'
PERMISO_ELIMINAR  = 'eliminar_cuentas_cobrar'
PERMISO_CONFIRMAR = 'confirmar_cuotas_cobro'

DOCUMENTO_TAMANIO_MAXIMO = 10 * 1024 * 1024
DOCUMENTO_EXTENSIONES_PERMITIDAS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf'}


def _cuenta_valida(cuenta_pk):
    if not cuenta_pk:
        return None
    return CuentaCaja.objects.filter(
        pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True, es_credito=False,
    ).first()


def _parsear_pago_historico(item):
    """
    Extrae de un dict de cuota/abono histórico (carga inicial) cómo se
    cobró, a lo sumo de una de tres formas: cuenta_pago_historica_pk (real,
    solo informativa), cheque_historico (crea un Cheque real A_COBRAR
    es_historico=True) o medio_pago (nota libre). Ninguna es obligatoria.
    """
    resultado = {'medio_pago': str(item.get('medio_pago', '') or '').strip()[:100]}
    cuenta_pk = item.get('cuenta_pago_historica_pk')
    if cuenta_pk:
        cuenta = _cuenta_valida(cuenta_pk)
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
        'cuenta_cobro_pk': c.cuenta_cobro_id,
        'cuenta_cobro_nombre': c.cuenta_cobro.nombre if c.cuenta_cobro_id else '',
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


def _serializar_cxc(cxc, con_cuotas=False):
    data = {
        'pk': cxc.pk,
        'cliente_pk': cxc.cliente_id,
        'cliente_nombre': cxc.cliente.get_nombre_display() if cxc.cliente_id else '',
        'descripcion': cxc.descripcion,
        'numero_comprobante': cxc.numero_comprobante,
        'es_carga_inicial': cxc.es_carga_inicial,
        'modo_cuotas': cxc.modo_cuotas,
        'modo_cuotas_display': cxc.get_modo_cuotas_display(),
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
        data['documentos'] = [_serializar_documento(doc) for doc in cxc.documentos.all()]
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
        ctx['puede_crear'] = chequear_permiso(self.request.user, PERMISO_CREAR)
        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, PERMISO_ELIMINAR)
        ctx['puede_confirmar'] = chequear_permiso(self.request.user, PERMISO_CONFIRMAR)

        ctx['monedas'] = Moneda.choices
        ctx['today'] = timezone.localtime().date().isoformat()

        cuentas = CuentaCaja.objects.filter(caja=TipoCaja.GRANDE, activa=True, es_credito=False).order_by('orden', 'nombre')
        ctx['cuentas_json'] = json.dumps([
            {'pk': c.pk, 'nombre': c.nombre, 'moneda': c.moneda, 'tipo': c.tipo,
             'titular': c.titular, 'preferida': c.preferida}
            for c in cuentas
        ])

        from django.urls import reverse
        ctx['url_listar'] = reverse('caja:listar_cuentas_cobrar')
        ctx['url_crear'] = reverse('caja:crear_cuenta_cobrar')
        ctx['url_editar'] = reverse('caja:editar_cuenta_cobrar', args=[0])
        ctx['url_eliminar'] = reverse('caja:eliminar_cuenta_cobrar', args=[0])
        ctx['url_detalle'] = reverse('caja:detalle_cuenta_cobrar', args=[0])
        ctx['url_confirmar_cuota'] = reverse('caja:confirmar_cuota_cobro', args=[0])
        ctx['url_registrar_abono'] = reverse('caja:registrar_abono_cobro', args=[0])
        ctx['url_previsualizar_cuotas'] = reverse('caja:previsualizar_cuotas_cobro')
        ctx['url_documento_subir'] = reverse('caja:cuenta_cobrar_documento_subir')
        ctx['url_documento_eliminar'] = reverse('caja:cuenta_cobrar_documento_eliminar')
        ctx['url_buscar_cliente'] = reverse('caja:buscar_cliente_cobrar')
        ctx['url_cliente_perfil_base'] = reverse('core:estadisticas_cliente_perfil', args=[0])[:-2]

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
                Q(descripcion__icontains=q) |
                Q(numero_comprobante__icontains=q)
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

        # Total a cobrar por moneda: siempre global (no depende de los
        # filtros/paginación de arriba), para la barra "Te deben" de la pantalla.
        # Cuotas fijas: el saldo está representado por cuotas CuotaCobro
        # PENDIENTE reales, así que alcanza con sumarlas por SQL. Cuotas
        # libres NO tienen cuotas futuras pre-generadas (se cobran de a
        # abonos sueltos) — su saldo no existe como fila en la tabla, solo
        # como la property `saldo_pendiente` calculada en Python, así que
        # hay que sumarlas aparte iterando las cuentas activas en modo libre.
        # Cheques A_COBRAR pendientes (de una cuota o directo de una venta,
        # ver pago_venta en Cheque) también son plata que todavía no se
        # cobró de verdad — sin esto, un cheque que paga una venta entera
        # (no una cuota) quedaba invisible en este total.
        totales_pendientes = {}
        agregado_fijas = (
            CuotaCobro.objects
            .filter(estado=EstadoCuota.PENDIENTE, cuenta_por_cobrar__estado=EstadoDeuda.ACTIVA,
                    cuenta_por_cobrar__modo_cuotas=ModoCuotas.FIJAS)
            .values('cuenta_por_cobrar__moneda')
            .annotate(total=Sum('monto'))
        )
        for row in agregado_fijas:
            moneda = row['cuenta_por_cobrar__moneda']
            totales_pendientes[moneda] = totales_pendientes.get(moneda, Decimal('0')) + row['total']

        cuentas_libres = CuentaPorCobrar.objects.filter(
            estado=EstadoDeuda.ACTIVA, modo_cuotas=ModoCuotas.LIBRE
        )
        for cxc_libre in cuentas_libres:
            saldo = cxc_libre.saldo_pendiente
            if saldo:
                totales_pendientes[cxc_libre.moneda] = totales_pendientes.get(cxc_libre.moneda, Decimal('0')) + saldo

        # Ojo: un cheque con cuota_cobro_id ya está representado en
        # agregado_fijas/cuentas_libres de arriba — la cuota que paga
        # sigue PENDIENTE mientras el cheque está en trámite (ver
        # CuotaCobro.confirmar_con_cheque), así que sumarlo de nuevo acá
        # sería contar la misma plata dos veces. Solo entran los cheques
        # que son la ÚNICA representación de esa deuda: los que pagan una
        # venta directo (pago_venta) o los cargados sueltos a mano.
        agregado_cheques = (
            Cheque.objects
            .filter(
                tipo=TipoCheque.A_COBRAR, estado=EstadoCheque.PENDIENTE, es_historico=False,
                cuota_cobro_id__isnull=True,
            )
            .values('moneda')
            .annotate(total=Sum('monto'))
        )
        for row in agregado_cheques:
            moneda = row['moneda']
            totales_pendientes[moneda] = totales_pendientes.get(moneda, Decimal('0')) + row['total']

        totales_pendientes = {moneda: str(total) for moneda, total in totales_pendientes.items() if total}

        return JsonResponse({
            'results': data,
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
            'totales_pendientes': totales_pendientes,
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
#  AJAX — Crear (alta manual: carga inicial de un cliente que ya debía)
# ══════════════════════════════════════════════════════════════════

class CrearCuentaCobrarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            data = json.loads(request.body)

            cliente = Cliente.objects.filter(pk=data.get('cliente_pk')).first()
            if not cliente:
                return JsonResponse({'error': 'Elegí un cliente válido.'}, status=400)

            descripcion = data.get('descripcion', '').strip()
            if not descripcion:
                return JsonResponse({'error': 'La descripción es obligatoria.'}, status=400)
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

            cxc = CuentaPorCobrar.crear_con_cuotas(
                cliente=cliente, monto_original=monto_original, porcentaje_interes=interes_pct,
                cantidad_cuotas=cantidad_cuotas, fecha_inicio=fecha_inicio, moneda=moneda,
                descripcion=descripcion, notas=notas, numero_comprobante=numero_comprobante,
                creado_por=request.user, modo_cuotas=modo_cuotas,
                es_carga_inicial=es_carga_inicial, cuotas_historicas=cuotas_historicas,
                abonos_historicos=abonos_historicos,
            )

            return JsonResponse({'success': True, 'cuenta_cobrar': _serializar_cxc(cxc, con_cuotas=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Editar
# ══════════════════════════════════════════════════════════════════

class EditarCuentaCobrarAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cxc = get_object_or_404(CuentaPorCobrar, pk=pk)

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

            cxc.editar(**kwargs)

            return JsonResponse({'success': True, 'cuenta_cobrar': _serializar_cxc(cxc, con_cuotas=True)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
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
            adelantar = bool(data.get('adelantar', False))

            if data.get('cheque'):
                # Cobrada con cheque: todavía no es un cobro real (ver
                # CuotaCobro.confirmar_con_cheque) — el mail de "cobro
                # confirmado" se manda recién cuando ESE cheque se
                # deposita de verdad (ver ConfirmarChequeAjax en
                # views_cheques.py).
                cuota.confirmar_con_cheque(data.get('cheque'), request.user, adelantar=adelantar)
            else:
                cuota.confirmar(data.get('cuenta_pk'), request.user, adelantar=adelantar)

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


# ══════════════════════════════════════════════════════════════════
#  AJAX — Registrar un abono (solo cuentas modo_cuotas=libre)
# ══════════════════════════════════════════════════════════════════

class RegistrarAbonoCobroAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CONFIRMAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cxc = get_object_or_404(CuentaPorCobrar, pk=pk)

        if cxc.modo_cuotas != ModoCuotas.LIBRE:
            return JsonResponse({'error': 'Esta cuenta no es de cuotas libres.'}, status=400)

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
                # Cobrado con cheque: el mail se manda recién cuando ESE
                # cheque se deposita de verdad (ver ConfirmarChequeAjax
                # en views_cheques.py).
                cuota = cxc.registrar_abono(
                    monto=monto, usuario=request.user, cheque_data=data.get('cheque'), fecha=fecha,
                )
            else:
                cuota = cxc.registrar_abono(
                    monto=monto, usuario=request.user, cuenta_pk=data.get('cuenta_pk'), fecha=fecha,
                )
                from asistencia.services.eventos import notificar_cuota_cobro_confirmada, enviar_en_background
                enviar_en_background(notificar_cuota_cobro_confirmada, cuota)

            return JsonResponse({
                'success': True,
                'cuota': _serializar_cuota(cuota),
                'cuenta_cobrar': _serializar_cxc(cxc, con_cuotas=True),
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

class PrevisualizarCuotasCobroAjax(LoginRequiredMixin, View):
    """
    Calcula el plan de cuotas sin crear nada, usando la misma función pura
    que Deudas (`_calcular_plan_cuotas` es genérica, no específica de una
    deuda ni de una cuenta por cobrar) — se usa en el modal de alta para
    que, al marcar "carga inicial", el usuario pueda tildar qué cuotas ya
    están cobradas viendo el monto y vencimiento reales de cada una.
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
#  AJAX — Documentos adjuntos de una cuenta por cobrar
# ══════════════════════════════════════════════════════════════════

class CuentaCobrarDocumentoSubirAjax(LoginRequiredMixin, View):
    """POST multipart → sube un documento a una cuenta por cobrar existente. Campos: cuenta_pk, archivo, tipo, descripcion."""

    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        cuenta_pk = request.POST.get('cuenta_pk')
        if not cuenta_pk:
            return JsonResponse({'error': 'cuenta_pk requerido.'}, status=400)

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

        cxc = get_object_or_404(CuentaPorCobrar, pk=cuenta_pk)

        doc = CuentaPorCobrarDocumento(
            cuenta_por_cobrar=cxc, archivo=archivo,
            tipo=request.POST.get('tipo', 'otro'),
            descripcion=request.POST.get('descripcion', ''),
            subido_por=request.user,
        )
        doc.save()

        return JsonResponse({'ok': True, 'documento': _serializar_documento(doc)})


class CuentaCobrarDocumentoEliminarAjax(LoginRequiredMixin, View):
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

        doc = get_object_or_404(CuentaPorCobrarDocumento, pk=pk)

        if doc.archivo and os.path.isfile(doc.archivo.path):
            os.remove(doc.archivo.path)

        doc.delete()
        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Buscar cliente (para el selector del alta manual)
# ══════════════════════════════════════════════════════════════════

class BuscarClienteCobrarAjax(LoginRequiredMixin, View):
    """
    Mismo query que ventas.views_nueva_venta.BuscarClienteAjax, pero
    gateado por el permiso de esta pantalla (crear_cuentas_cobrar) en vez
    de crear_ventas, para no acoplar el permiso de Cuentas por cobrar al
    de Ventas.
    """

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q = request.GET.get('q', '').strip()
        qs = Cliente.objects.filter(estado='activo').order_by('nombre')
        if q:
            qs = qs.filter(
                Q(nombre__icontains=q) | Q(apellido__icontains=q) |
                Q(dni__icontains=q) | Q(cuil__icontains=q) |
                Q(razon_social__icontains=q) | Q(nombre_comercial__icontains=q) |
                Q(cuit__icontains=q)
            )
        data = [
            {
                'pk': c.pk,
                'nombre': c.get_nombre_display(),
                'codigo': c.codigo or '',
                'doc': c.dni or c.cuit or c.cuil or '',
            }
            for c in qs[:20]
        ]
        return JsonResponse({'results': data})
