# caja/views_bienes.py
#
# Bienes del negocio (patrimonio): muebles, vehículos, terrenos, casas,
# departamentos, etc. Un registro simple de qué tiene el negocio y,
# opcionalmente, cuánto vale — sin stock, sin caja, sin lógica contable.
# Mismo patrón que core/views_notas.py (el módulo más chico y autocontenido
# del sistema): una vista de página + listar/crear-editar/eliminar por AJAX.

import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Sum
from django.utils import timezone

from .models import Bien, TIPOS_BIEN_SUGERIDOS
from core.permisos import chequear_permiso

PERMISO_VER      = 'ver_bienes'
PERMISO_CREAR    = 'crear_bienes'
PERMISO_EDITAR   = 'editar_bienes'
PERMISO_ELIMINAR = 'eliminar_bienes'


def _nombre(usuario):
    return usuario.get_full_name() if usuario else '—'


def _tipos_disponibles():
    """Categorías para el autocompletado y el filtro: las que ya están
    en uso + las sugeridas de fábrica, sin repetir y ordenadas. El campo
    es libre, esto es solo para ayudar a no reescribir lo mismo."""
    usados = (
        Bien.objects.exclude(tipo='')
        .order_by().values_list('tipo', flat=True).distinct()
    )
    combinados = {t.strip() for t in usados if t and t.strip()}
    combinados.update(TIPOS_BIEN_SUGERIDOS)
    return sorted(combinados, key=str.lower)


class BienesView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'caja/bienes.html', {
            'puede_ver':      chequear_permiso(request.user, PERMISO_VER),
            'puede_crear':    chequear_permiso(request.user, PERMISO_CREAR),
            'puede_editar':   chequear_permiso(request.user, PERMISO_EDITAR),
            'puede_eliminar': chequear_permiso(request.user, PERMISO_ELIMINAR),
            'tipos':          _tipos_disponibles(),
        })


class BienesListarAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, PERMISO_VER):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Bien.objects.select_related('creado_por', 'modificado_por').all()

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))

        tipo = request.GET.get('tipo', '').strip()
        if tipo:
            qs = qs.filter(tipo__iexact=tipo)

        estado = request.GET.get('estado', '').strip()
        if estado == 'activos':
            qs = qs.filter(activo=True)
        elif estado == 'inactivos':
            qs = qs.filter(activo=False)

        resultados = [
            {
                'pk':                 b.pk,
                'nombre':             b.nombre,
                'tipo':               b.tipo,
                'valor':              str(b.valor) if b.valor is not None else '',
                'descripcion':        b.descripcion,
                'activo':             b.activo,
                'creado_por':         _nombre(b.creado_por),
                'modificado_por':     _nombre(b.modificado_por) if b.modificado_por else '',
                'fecha_alta':         timezone.localtime(b.fecha_alta).strftime('%d/%m/%Y %H:%M'),
                'fecha_modificacion': timezone.localtime(b.fecha_modificacion).strftime('%d/%m/%Y %H:%M'),
            }
            for b in qs
        ]

        # Valor total de lo que sigue en pie — el mismo conjunto filtrado
        # que ve el usuario (no solo lo cargado, sino según el filtro
        # activo/tipo/búsqueda actual), para que el número de arriba
        # siempre coincida con lo que se ve en la tabla de abajo.
        total_valorizado = qs.filter(activo=True, valor__isnull=False).aggregate(
            total=Sum('valor')
        )['total'] or Decimal('0')

        return JsonResponse({
            'results':          resultados,
            'total_valorizado': str(total_valorizado),
            'tipos':            _tipos_disponibles(),
        })


class BienAccionesAjax(LoginRequiredMixin, View):
    """POST JSON. Si trae 'pk', edita; si no, crea."""

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nombre = (body.get('nombre') or '').strip()
        if not nombre:
            return JsonResponse({'error': 'Ponele un nombre al bien.'}, status=400)

        tipo = (body.get('tipo') or '').strip()[:60]

        raw_valor = body.get('valor')
        valor = None
        if raw_valor not in (None, ''):
            try:
                valor = Decimal(str(raw_valor))
            except InvalidOperation:
                return JsonResponse({'error': 'El valor es inválido.'}, status=400)
            if valor < 0:
                return JsonResponse({'error': 'El valor no puede ser negativo.'}, status=400)

        descripcion = (body.get('descripcion') or '').strip()

        pk = body.get('pk')
        if pk:
            if not chequear_permiso(request.user, PERMISO_EDITAR):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)
            bien = get_object_or_404(Bien, pk=pk)
            bien.modificado_por = request.user
        else:
            if not chequear_permiso(request.user, PERMISO_CREAR):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)
            bien = Bien(creado_por=request.user)

        bien.nombre      = nombre
        bien.tipo        = tipo
        bien.valor       = valor
        bien.descripcion = descripcion
        bien.activo      = bool(body.get('activo', True))
        bien.save()

        return JsonResponse({'ok': True, 'pk': bien.pk})


class BienEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, PERMISO_ELIMINAR):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        bien = get_object_or_404(Bien, pk=body.get('pk'))
        bien.delete()
        return JsonResponse({'ok': True})
