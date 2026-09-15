# caja/views_celulares.py
#
# Celulares (Herramientas): datos de SIM (PIN/PUK/activación) + control
# de recargas de crédito, con recordatorio por línea. Mismo patrón chico
# y autocontenido que views_bienes.py / core/views_notas.py: una vista
# de página + listar/crear-editar/eliminar por AJAX.
#
# La particularidad de este módulo es RecargaCelular: cada recarga que
# se registra genera, en el mismo guardado, un Gasto (egreso) en caja
# grande — ver Celular/RecargaCelular en models.py para el porqué.

import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from productos.models import Moneda
from core.permisos import chequear_permiso

from .models import (
    Celular, RecargaCelular, Gasto, CuentaCaja, TipoCaja, TipoMovimientoCaja,
    sincronizar_movimiento_gasto, asegurar_cuentas_efectivo,
)

PERMISO_VER      = 'ver_celulares'
PERMISO_CREAR    = 'crear_celulares'
PERMISO_EDITAR   = 'editar_celulares'
PERMISO_ELIMINAR = 'eliminar_celulares'


def _nombre(usuario):
    return usuario.get_full_name() if usuario else '—'


def _cuenta_valida(cuenta_pk):
    """Resuelve una cuenta activa de caja grande, o None si no es válida."""
    if not cuenta_pk:
        return None
    return CuentaCaja.objects.filter(pk=cuenta_pk, caja=TipoCaja.GRANDE, activa=True).first()


def _descripcion_recarga(celular):
    """Genérica a propósito (sin el número) para que todas las recargas
    de una misma línea compartan un solo ConceptoGasto — ver docstring
    de RecargaCelular en models.py."""
    if celular.titular:
        return f'Recarga celular ({celular.titular})'
    return 'Recarga celular'


def _serializar_celular(c):
    ultima = c.ultima_recarga
    return {
        'pk': c.pk,
        'numero': c.numero,
        'titular': c.titular,
        'compania': c.compania,
        'pin': c.pin,
        'puk': c.puk,
        'iccid': c.iccid,
        'imei': c.imei,
        'fecha_activacion': c.fecha_activacion.isoformat() if c.fecha_activacion else '',
        'frecuencia_recarga_dias': c.frecuencia_recarga_dias,
        'notas': c.notas,
        'activo': c.activo,
        'ultima_recarga_fecha': ultima.fecha.isoformat() if ultima else '',
        'ultima_recarga_monto': str(ultima.monto) if ultima else '',
        'proxima_fecha_recarga': c.proxima_fecha_recarga.isoformat() if c.proxima_fecha_recarga else '',
        'dias_para_recarga': c.dias_para_recarga,
        'creado_por': _nombre(c.creado_por),
        'modificado_por': _nombre(c.modificado_por) if c.modificado_por else '',
        'fecha_alta': timezone.localtime(c.fecha_alta).strftime('%d/%m/%Y %H:%M'),
        'fecha_modificacion': timezone.localtime(c.fecha_modificacion).strftime('%d/%m/%Y %H:%M'),
    }


def _serializar_recarga(r):
    return {
        'pk': r.pk,
        # Justo después de crear/editar, `fecha` puede seguir siendo el
        # string que vino del JSON (Django recién la convierte a date en
        # el próximo fetch) — mismo fallback que _serializar_gasto.
        'fecha': r.fecha.isoformat() if hasattr(r.fecha, 'isoformat') else str(r.fecha),
        'monto': str(r.monto),
        'cuenta_pk': r.gasto.cuenta_id if r.gasto_id else None,
        'cuenta_nombre': r.gasto.cuenta.nombre if r.gasto_id else '',
        # Hoy en día no debería poder pasar (el Gasto está protegido
        # mientras la recarga lo referencie — ver models.py), pero deja
        # el aviso por si hay recargas de antes de ese cambio con el
        # gasto ya perdido.
        'sin_egreso': not r.gasto_id,
        'creado_por': _nombre(r.creado_por),
        'fecha_alta': timezone.localtime(r.fecha_alta).strftime('%d/%m/%Y %H:%M'),
    }


# ══════════════════════════════════════════════════════════════════
#  VISTA PRINCIPAL
# ══════════════════════════════════════════════════════════════════

class CelularesView(LoginRequiredMixin, View):
    def get(self, request):
        asegurar_cuentas_efectivo(caja=TipoCaja.GRANDE)
        cuentas = (
            CuentaCaja.objects
            .filter(caja=TipoCaja.GRANDE, activa=True)
            .order_by('orden', 'nombre')
        )
        return render(request, 'caja/celulares.html', {
            'puede_ver':      chequear_permiso(request.user, PERMISO_VER),
            'puede_crear':    chequear_permiso(request.user, PERMISO_CREAR),
            'puede_editar':   chequear_permiso(request.user, PERMISO_EDITAR),
            'puede_eliminar': chequear_permiso(request.user, PERMISO_ELIMINAR),
            'cuentas':        cuentas,
            'today':          timezone.localtime().date().isoformat(),
        })


# ══════════════════════════════════════════════════════════════════
#  AJAX — Celulares: listar / crear-editar / eliminar
# ══════════════════════════════════════════════════════════════════

class CelularesListarAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Celular.objects.select_related('creado_por', 'modificado_por').all()

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(numero__icontains=q) | Q(titular__icontains=q) | Q(compania__icontains=q))

        estado = request.GET.get('estado', '').strip()
        if estado == 'activos':
            qs = qs.filter(activo=True)
        elif estado == 'inactivos':
            qs = qs.filter(activo=False)

        resultados = [_serializar_celular(c) for c in qs]
        # Más urgente primero: vencidas/próximas antes que las que no
        # tienen recordatorio configurado (esas van al final).
        resultados.sort(key=lambda c: 999999 if c['dias_para_recarga'] is None else c['dias_para_recarga'])

        return JsonResponse({'results': resultados})


class CelularAccionesAjax(LoginRequiredMixin, View):
    """POST JSON. Si trae 'pk', edita; si no, crea."""

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        numero = (body.get('numero') or '').strip()
        if not numero:
            return JsonResponse({'error': 'Ponele el número de línea.'}, status=400)

        raw_frecuencia = body.get('frecuencia_recarga_dias')
        frecuencia = None
        if raw_frecuencia not in (None, ''):
            try:
                frecuencia = int(raw_frecuencia)
            except (TypeError, ValueError):
                return JsonResponse({'error': 'La frecuencia de recarga debe ser un número de días.'}, status=400)
            if frecuencia <= 0:
                return JsonResponse({'error': 'La frecuencia de recarga debe ser mayor a 0.'}, status=400)

        fecha_activacion = (body.get('fecha_activacion') or '').strip() or None

        pk = body.get('pk')
        if pk:
            if not chequear_permiso(request.user, PERMISO_EDITAR):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)
            celular = get_object_or_404(Celular, pk=pk)
            celular.modificado_por = request.user
        else:
            if not chequear_permiso(request.user, PERMISO_CREAR):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)
            celular = Celular(creado_por=request.user)

        celular.numero = numero
        celular.titular = (body.get('titular') or '').strip()[:120]
        celular.compania = (body.get('compania') or '').strip()[:60]
        celular.pin = (body.get('pin') or '').strip()[:20]
        celular.puk = (body.get('puk') or '').strip()[:20]
        celular.iccid = (body.get('iccid') or '').strip()[:25]
        celular.imei = (body.get('imei') or '').strip()[:20]
        celular.fecha_activacion = fecha_activacion
        celular.frecuencia_recarga_dias = frecuencia
        celular.notas = (body.get('notas') or '').strip()
        celular.activo = bool(body.get('activo', True))
        celular.save()

        return JsonResponse({'ok': True, 'pk': celular.pk})


class CelularEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        celular = get_object_or_404(Celular, pk=body.get('pk'))
        # Celular.delete() ya se encarga de borrar cada recarga de a una
        # (y con eso, sus Gasto) antes de borrarse a sí mismo — ver models.py.
        celular.delete()

        return JsonResponse({'ok': True})


# ══════════════════════════════════════════════════════════════════
#  AJAX — Recargas de un celular: listar / crear-editar / eliminar
# ══════════════════════════════════════════════════════════════════

class RecargasListarAjax(LoginRequiredMixin, View):
    def get(self, request, celular_pk):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        celular = get_object_or_404(Celular, pk=celular_pk)
        recargas = celular.recargas.select_related('gasto', 'gasto__cuenta', 'creado_por').all()

        return JsonResponse({'results': [_serializar_recarga(r) for r in recargas]})


class RecargaAccionesAjax(LoginRequiredMixin, View):
    """POST JSON contra un celular puntual. Si trae 'pk', edita esa
    recarga (y su Gasto); si no, crea una recarga nueva + su Gasto."""

    def post(self, request, celular_pk):
        celular = get_object_or_404(Celular, pk=celular_pk)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        fecha = (body.get('fecha') or '').strip()
        if not fecha:
            return JsonResponse({'error': 'Falta la fecha de la recarga.'}, status=400)

        try:
            monto = Decimal(str(body.get('monto')))
            if monto <= 0:
                return JsonResponse({'error': 'El monto debe ser mayor a 0.'}, status=400)
        except (InvalidOperation, ValueError, TypeError):
            return JsonResponse({'error': 'Monto inválido.'}, status=400)

        cuenta = _cuenta_valida(body.get('cuenta_pk'))
        if not cuenta:
            return JsonResponse({'error': 'Elegí de qué cuenta sale la plata de la recarga.'}, status=400)

        pk = body.get('pk')
        if not chequear_permiso(request.user, PERMISO_EDITAR if pk else PERMISO_CREAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        # Atómico: crear/editar la recarga y su Gasto son dos escrituras
        # separadas — si la segunda falla, no queremos la primera
        # suelta (un Gasto sin recarga, o una recarga con datos que ya
        # no coinciden con su egreso). El permiso ya se chequeó arriba,
        # así este bloque no tiene ningún `return` a mitad de camino que
        # pudiera confundirse con un rollback (un `return` sin excepción
        # adentro de un `atomic()` COMMITEA lo que se haya hecho hasta
        # ahí, no lo deshace).
        with transaction.atomic():
            if pk:
                recarga = get_object_or_404(RecargaCelular, pk=pk, celular=celular)
                recarga.fecha = fecha
                recarga.monto = monto
                recarga.save()

                if recarga.gasto_id:
                    recarga.gasto.fecha = fecha
                    recarga.gasto.monto = monto
                    recarga.gasto.cuenta = cuenta
                    recarga.gasto.save()
                    sincronizar_movimiento_gasto(recarga.gasto)
            else:
                gasto = Gasto.objects.create(
                    tipo=TipoMovimientoCaja.EGRESO,
                    cuenta=cuenta,
                    fecha=fecha,
                    monto=monto,
                    moneda=Moneda.ARS,
                    descripcion=_descripcion_recarga(celular),
                    creado_por=request.user,
                )
                recarga = RecargaCelular.objects.create(
                    celular=celular, fecha=fecha, monto=monto,
                    gasto=gasto, creado_por=request.user,
                )

        return JsonResponse({'ok': True, 'recarga': _serializar_recarga(recarga)})


class RecargaEliminarAjax(LoginRequiredMixin, View):
    def post(self, request, celular_pk):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        celular = get_object_or_404(Celular, pk=celular_pk)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        recarga = get_object_or_404(RecargaCelular, pk=body.get('pk'), celular=celular)
        recarga.delete()

        return JsonResponse({'ok': True})
