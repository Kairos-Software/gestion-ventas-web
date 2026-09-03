import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.views import View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from productos.models import Moneda
from core.permisos import chequear_permiso

from django.db.models import Count

from .models import (
    Gasto, CuentaCaja, TipoCaja, TipoMovimientoCaja, sincronizar_movimiento_gasto,
    MovimientoProgramado, InstanciaProgramada, FrecuenciaProgramado, TipoMontoProgramado,
    EstadoInstanciaProgramada, generar_instancias_pendientes, ConceptoGasto,
    _normalizar_concepto_gasto,
)


PERMISO_VER    = 'ver_gastos'
PERMISO_CREAR  = 'crear_gastos'
PERMISO_EDITAR = 'editar_gastos'
PERMISO_ELIMINAR = 'eliminar_gastos'


def _cuenta_valida(cuenta_pk):
    """Resuelve una cuenta activa de caja grande, o None si no es válida."""
    if not cuenta_pk:
        return None
    return CuentaCaja.objects.filter(pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True).first()


def _serializar_gasto(g):
    return {
        'pk': g.pk,
        'tipo': g.tipo,
        'fecha': g.fecha.isoformat() if hasattr(g.fecha, 'isoformat') else str(g.fecha),
        'hora': g.hora.strftime('%H:%M') if g.hora and hasattr(g.hora, 'strftime') else str(g.hora) if g.hora else '',
        'monto': str(g.monto),
        'moneda': g.moneda,
        'descripcion': g.descripcion,
        'cuenta_pk': g.cuenta_id,
        'cuenta_nombre': g.cuenta.nombre if g.cuenta_id else '',
        'creado_por': str(g.creado_por) if g.creado_por else '',
        'fecha_alta': g.fecha_alta.isoformat() if hasattr(g.fecha_alta, 'isoformat') else str(g.fecha_alta),
        # Movimiento de caja diaria (efectivo del cajón de un turno): se
        # carga y se borra desde la pantalla de Caja Diaria, solo con el
        # turno abierto. Acá se muestra pero no se edita/borra.
        'es_caja_diaria': g.turno_id is not None,
        'turno_numero': g.turno.numero if g.turno_id else None,
        'turno_abierto': (g.turno.estado == 'abierto') if g.turno_id else False,
        'concepto': g.concepto.nombre if g.concepto_id else '',
    }


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL — Ingresos y egresos
# ══════════════════════════════════════════════════════════════════

class GastosView(LoginRequiredMixin, TemplateView):
    """
    Pantalla de ingresos y egresos manuales: historial + modal para
    crear/editar. (Nombre interno de archivo/URLs sin cambiar por
    compatibilidad — ver Gasto en models.py.)
    """
    template_name = 'caja/gastos.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        if not chequear_permiso(self.request.user, PERMISO_VER):
            ctx['sin_permiso'] = True
            return ctx

        ctx['puede_ver'] = True
        ctx['puede_crear'] = chequear_permiso(self.request.user, PERMISO_CREAR)
        ctx['puede_editar'] = chequear_permiso(self.request.user, PERMISO_EDITAR)
        ctx['puede_eliminar'] = chequear_permiso(self.request.user, PERMISO_ELIMINAR)

        from .models import asegurar_cuentas_efectivo
        asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE)

        ctx['monedas'] = Moneda.choices
        ctx['tipos_movimiento'] = TipoMovimientoCaja.choices
        ctx['frecuencias_programado'] = FrecuenciaProgramado.choices
        cuentas = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True)
            .order_by('orden', 'nombre')
        )
        ctx['cuentas'] = cuentas
        ctx['cuentas_json'] = json.dumps([
            {
                'pk': c.pk,
                'nombre': c.nombre,
                'moneda': c.moneda,
                'es_credito': c.es_credito,
                'titular': c.titular,
                'preferida': c.preferida,
            }
            for c in cuentas
        ])
        ctx['today'] = timezone.localtime().date().isoformat()

        from django.urls import reverse
        ctx['url_listar'] = reverse('caja:listar_gastos')
        ctx['url_crear'] = reverse('caja:crear_gasto')
        # Las URLs de editar y eliminar se construyen dinámicamente en el JS
        ctx['url_editar'] = reverse('caja:editar_gasto', args=[0])  # Placeholder
        ctx['url_eliminar'] = reverse('caja:eliminar_gasto', args=[0])  # Placeholder
        ctx['url_conceptos_sugerencias'] = reverse('caja:conceptos_sugerencias')

        ctx['url_listar_programados']    = reverse('caja:listar_programados')
        ctx['url_crear_programado']      = reverse('caja:crear_programado')
        ctx['url_editar_programado']     = reverse('caja:editar_programado', args=[0])
        ctx['url_eliminar_programado']   = reverse('caja:eliminar_programado', args=[0])
        ctx['url_toggle_programado']     = reverse('caja:toggle_programado', args=[0])
        ctx['url_confirmar_instancia']   = reverse('caja:confirmar_instancia_programada', args=[0])
        ctx['url_anular_instancia']      = reverse('caja:anular_instancia_programada', args=[0])

        return ctx


# ══════════════════════════════════════════════════════════════════
#  AJAX — Listar (con filtros + paginación)
# ══════════════════════════════════════════════════════════════════

class ListarGastosAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Gasto.objects.all().select_related('creado_por', 'cuenta', 'turno', 'concepto')

        # Filtros
        desde = request.GET.get('desde', '').strip()
        hasta = request.GET.get('hasta', '').strip()
        moneda = request.GET.get('moneda', '').strip()
        tipo = request.GET.get('tipo', '').strip()
        cuenta_pk = request.GET.get('cuenta', '').strip()
        origen = request.GET.get('origen', '').strip()
        q = request.GET.get('q', '').strip()

        if desde:
            qs = qs.filter(fecha__gte=desde)
        if hasta:
            qs = qs.filter(fecha__lte=hasta)
        if moneda:
            qs = qs.filter(moneda=moneda)
        if tipo in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
            qs = qs.filter(tipo=tipo)
        if cuenta_pk:
            qs = qs.filter(cuenta_id=cuenta_pk)
        if origen == 'caja_grande':
            qs = qs.filter(turno__isnull=True)
        elif origen == 'caja_diaria':
            qs = qs.filter(turno__isnull=False)
        if q:
            qs = qs.filter(descripcion__icontains=q)

        # Paginación
        try:
            pagina = max(int(request.GET.get('pagina', 1)), 1)
            por_pagina = min(max(int(request.GET.get('por_pagina', 50)), 1), 200)
        except ValueError:
            pagina, por_pagina = 1, 50

        total = qs.count()
        inicio = (pagina - 1) * por_pagina
        items = qs[inicio:inicio + por_pagina]

        data = [_serializar_gasto(g) for g in items]

        return JsonResponse({
            'results': data,
            'total': total,
            'pagina': pagina,
            'por_pagina': por_pagina,
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Crear
# ══════════════════════════════════════════════════════════════════

class CrearGastoAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            data = json.loads(request.body)

            fecha = data.get('fecha')
            monto = data.get('monto')
            moneda = data.get('moneda', 'ARS')
            descripcion = data.get('descripcion', '').strip()
            tipo = data.get('tipo', TipoMovimientoCaja.EGRESO)
            cuenta_pk = data.get('cuenta_pk') or data.get('cuenta')

            if not fecha or not monto:
                return JsonResponse({'error': 'Faltan datos obligatorios: fecha, monto'}, status=400)

            if tipo not in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
                return JsonResponse({'error': 'El tipo debe ser "ingreso" o "egreso".'}, status=400)

            cuenta = _cuenta_valida(cuenta_pk)
            if not cuenta:
                return JsonResponse({'error': 'Elegí una cuenta válida.'}, status=400)

            try:
                monto = Decimal(monto)
                if monto <= 0:
                    return JsonResponse({'error': 'El monto debe ser mayor a 0'}, status=400)
            except (InvalidOperation, ValueError):
                return JsonResponse({'error': 'Monto inválido'}, status=400)

            gasto = Gasto.objects.create(
                tipo=tipo,
                cuenta=cuenta,
                fecha=fecha,
                monto=monto,
                moneda=moneda,
                descripcion=descripcion,
                creado_por=request.user,
            )

            return JsonResponse({'success': True, 'gasto': _serializar_gasto(gasto)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Editar
# ══════════════════════════════════════════════════════════════════

class EditarGastoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        gasto = get_object_or_404(Gasto, pk=pk)
        if gasto.turno_id:
            return JsonResponse({
                'error': 'Este es un ingreso/egreso de caja diaria — se edita desde la '
                         'pantalla de Caja Diaria, y solo mientras el turno está abierto.'
            }, status=400)

        try:
            data = json.loads(request.body)

            fecha = data.get('fecha')
            monto = data.get('monto')
            moneda = data.get('moneda')
            descripcion = data.get('descripcion', '').strip()
            tipo = data.get('tipo')
            cuenta_pk = data.get('cuenta_pk') or data.get('cuenta')

            if fecha:
                gasto.fecha = fecha
            if monto:
                try:
                    monto = Decimal(monto)
                    if monto <= 0:
                        return JsonResponse({'error': 'El monto debe ser mayor a 0'}, status=400)
                    gasto.monto = monto
                except (InvalidOperation, ValueError):
                    return JsonResponse({'error': 'Monto inválido'}, status=400)
            if moneda:
                gasto.moneda = moneda
            if descripcion:
                gasto.descripcion = descripcion
            if tipo:
                if tipo not in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
                    return JsonResponse({'error': 'El tipo debe ser "ingreso" o "egreso".'}, status=400)
                gasto.tipo = tipo
            if cuenta_pk:
                cuenta = _cuenta_valida(cuenta_pk)
                if not cuenta:
                    return JsonResponse({'error': 'Elegí una cuenta válida.'}, status=400)
                gasto.cuenta = cuenta

            gasto.save()

            # Sincronizar movimiento de caja
            sincronizar_movimiento_gasto(gasto)

            return JsonResponse({'success': True, 'gasto': _serializar_gasto(gasto)})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Eliminar
# ══════════════════════════════════════════════════════════════════

class EliminarGastoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        gasto = get_object_or_404(Gasto, pk=pk)
        if gasto.turno_id:
            return JsonResponse({
                'error': 'Este es un ingreso/egreso de caja diaria — se elimina desde la '
                         'pantalla de Caja Diaria, y solo mientras el turno está abierto.'
            }, status=400)

        try:
            gasto.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════
#  AJAX — Sugerencias de concepto (autocompletado de la descripción)
# ══════════════════════════════════════════════════════════════════

class ConceptosSugerenciasAjax(LoginRequiredMixin, View):
    """GET ?q=<texto>&tipo=<ingreso|egreso> → hasta 8 conceptos del
    catálogo que contienen ese texto, los más usados primero. Alimenta
    el desplegable de la descripción en el modal de Ingresos y egresos."""

    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        q = _normalizar_concepto_gasto(request.GET.get('q', ''))
        tipo = request.GET.get('tipo', '').strip()

        qs = ConceptoGasto.objects.filter(activo=True).annotate(usos=Count('gastos'))
        if q:
            qs = qs.filter(nombre_normalizado__icontains=q)

        if tipo in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
            # El tipo es solo una preferencia de orden: primero los del
            # tipo elegido, después el resto (no se esconden — un mismo
            # concepto puede usarse en los dos sentidos).
            conceptos = sorted(
                qs, key=lambda c: (c.tipo != tipo, -c.usos, c.nombre.lower()))[:8]
        else:
            conceptos = list(qs.order_by('-usos', 'nombre')[:8])

        return JsonResponse({
            'sugerencias': [
                {'nombre': c.nombre, 'tipo': c.tipo, 'usos': c.usos}
                for c in conceptos
            ],
        })


# ══════════════════════════════════════════════════════════════════
#  MOVIMIENTOS PROGRAMADOS — ingresos/egresos recurrentes
# ══════════════════════════════════════════════════════════════════

def _serializar_programado(p):
    return {
        'pk': p.pk,
        'tipo': p.tipo,
        'descripcion': p.descripcion,
        'cuenta_pk': p.cuenta_id,
        'cuenta_nombre': p.cuenta.nombre if p.cuenta_id else '',
        'moneda': p.moneda,
        'tipo_monto': p.tipo_monto,
        'monto_fijo': str(p.monto_fijo) if p.monto_fijo is not None else '',
        'frecuencia': p.frecuencia,
        'frecuencia_display': p.get_frecuencia_display(),
        'proxima_fecha': p.proxima_fecha.isoformat() if hasattr(p.proxima_fecha, 'isoformat') else str(p.proxima_fecha),
        'activo': p.activo,
    }


def _serializar_instancia(i):
    return {
        'pk': i.pk,
        'programado_pk': i.programado_id,
        'descripcion': i.programado.descripcion,
        'tipo': i.programado.tipo,
        'fecha_vencimiento': i.fecha_vencimiento.isoformat() if hasattr(i.fecha_vencimiento, 'isoformat') else str(i.fecha_vencimiento),
        'monto': str(i.monto) if i.monto is not None else '',
        'tipo_monto': i.programado.tipo_monto,
        'moneda': i.programado.moneda,
        'cuenta_pk': i.programado.cuenta_id,
        'cuenta_nombre': i.programado.cuenta.nombre if i.programado.cuenta_id else '',
        'estado': i.estado,
    }


class ListarProgramadosAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        generar_instancias_pendientes()

        programados = MovimientoProgramado.objects.select_related('cuenta').order_by('-activo', 'proxima_fecha')
        pendientes = InstanciaProgramada.objects.filter(
            estado=EstadoInstanciaProgramada.PENDIENTE,
        ).select_related('programado', 'programado__cuenta').order_by('fecha_vencimiento')

        return JsonResponse({
            'programados': [_serializar_programado(p) for p in programados],
            'pendientes': [_serializar_instancia(i) for i in pendientes],
        })


def _validar_datos_programado(data):
    """Valida el payload de crear/editar programado. Devuelve (campos_dict, None) u (None, error_str)."""
    tipo          = data.get('tipo')
    descripcion   = (data.get('descripcion') or '').strip()
    cuenta_pk     = data.get('cuenta_pk') or data.get('cuenta')
    moneda        = data.get('moneda', Moneda.ARS)
    tipo_monto    = data.get('tipo_monto')
    monto_fijo    = data.get('monto_fijo')
    frecuencia    = data.get('frecuencia')
    proxima_fecha = data.get('proxima_fecha')

    if tipo not in (TipoMovimientoCaja.INGRESO, TipoMovimientoCaja.EGRESO):
        return None, 'El tipo debe ser "ingreso" o "egreso".'
    if not descripcion:
        return None, 'La descripción es obligatoria.'
    if tipo_monto not in (TipoMontoProgramado.FIJO, TipoMontoProgramado.VARIABLE):
        return None, 'Elegí si el monto es fijo o variable.'
    if frecuencia not in FrecuenciaProgramado.values:
        return None, 'Frecuencia inválida.'
    if not proxima_fecha:
        return None, 'Falta la próxima fecha.'

    cuenta = _cuenta_valida(cuenta_pk)
    if not cuenta:
        return None, 'Elegí una cuenta válida.'

    monto_fijo_dec = None
    if tipo_monto == TipoMontoProgramado.FIJO:
        if monto_fijo in (None, ''):
            return None, 'Ingresá el monto fijo.'
        try:
            monto_fijo_dec = Decimal(str(monto_fijo))
            if monto_fijo_dec <= 0:
                return None, 'El monto debe ser mayor a 0.'
        except InvalidOperation:
            return None, 'Monto inválido.'

    return dict(
        tipo=tipo, descripcion=descripcion, cuenta=cuenta, moneda=moneda,
        tipo_monto=tipo_monto, monto_fijo=monto_fijo_dec,
        frecuencia=frecuencia, proxima_fecha=proxima_fecha,
    ), None


class CrearProgramadoAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        campos, error = _validar_datos_programado(data)
        if error:
            return JsonResponse({'error': error}, status=400)

        programado = MovimientoProgramado.objects.create(creado_por=request.user, **campos)
        return JsonResponse({'success': True, 'programado': _serializar_programado(programado)})


class EditarProgramadoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        programado = get_object_or_404(MovimientoProgramado, pk=pk)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        campos, error = _validar_datos_programado(data)
        if error:
            return JsonResponse({'error': error}, status=400)

        for campo, valor in campos.items():
            setattr(programado, campo, valor)
        programado.save()

        return JsonResponse({'success': True, 'programado': _serializar_programado(programado)})


class ToggleActivoProgramadoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        programado = get_object_or_404(MovimientoProgramado, pk=pk)
        programado.activo = not programado.activo
        programado.save(update_fields=['activo'])
        return JsonResponse({'success': True, 'activo': programado.activo})


class EliminarProgramadoAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        programado = get_object_or_404(MovimientoProgramado, pk=pk)
        try:
            programado.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


class ConfirmarInstanciaProgramadaAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        instancia = get_object_or_404(InstanciaProgramada, pk=pk)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        monto = data.get('monto')
        fecha = data.get('fecha')
        cuenta_pk = data.get('cuenta_pk') or data.get('cuenta')

        if not monto or not fecha:
            return JsonResponse({'error': 'Faltan datos obligatorios: monto, fecha'}, status=400)

        cuenta = _cuenta_valida(cuenta_pk)
        if not cuenta:
            return JsonResponse({'error': 'Elegí una cuenta válida.'}, status=400)

        try:
            instancia.confirmar(monto=monto, cuenta=cuenta, fecha=fecha, usuario=request.user)
        except (ValueError, InvalidOperation) as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({'success': True})


class AnularInstanciaProgramadaAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, PERMISO_EDITAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        instancia = get_object_or_404(InstanciaProgramada, pk=pk)
        try:
            instancia.anular()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)

        return JsonResponse({'success': True})
