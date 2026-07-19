# core/views_notas.py
#
# Anotador (Herramientas): bloques de notas globales del sistema.
# Públicas por defecto; una nota privada solo la ve quien la creó.

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.db.models import Q

from .models import Nota
from .permisos import chequear_permiso


def _nombre(usuario):
    return usuario.get_full_name() if usuario else '—'


class NotasView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, 'core/notas.html', {
            'puede_ver':              chequear_permiso(request.user, 'ver_notas'),
            'puede_crear':            chequear_permiso(request.user, 'crear_notas'),
            'puede_crear_privadas':   chequear_permiso(request.user, 'crear_notas_privadas'),
        })


class NotasListarAjax(LoginRequiredMixin, View):
    def get(self, request):
        if not chequear_permiso(request.user, 'ver_notas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        qs = Nota.objects.select_related('creado_por', 'modificado_por').filter(
            Q(es_privada=False) | Q(creado_por=request.user)
        )

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(titulo__icontains=q) | Q(contenido__icontains=q))

        puede_editar    = chequear_permiso(request.user, 'editar_notas')
        puede_eliminar  = chequear_permiso(request.user, 'eliminar_notas')

        resultados = []
        for n in qs:
            es_propia = n.creado_por_id == request.user.id
            resultados.append({
                'pk':                 n.pk,
                'titulo':             n.titulo,
                'contenido':          n.contenido,
                'es_privada':         n.es_privada,
                'es_propia':          es_propia,
                'creado_por':         _nombre(n.creado_por),
                'modificado_por':     _nombre(n.modificado_por) if n.modificado_por else '',
                'fecha_alta':         n.fecha_alta.strftime('%d/%m/%Y %H:%M'),
                'fecha_modificacion': n.fecha_modificacion.strftime('%d/%m/%Y %H:%M'),
                'puede_editar':       puede_editar and (es_propia or not n.es_privada),
                'puede_eliminar':     puede_eliminar and (es_propia or not n.es_privada),
            })

        return JsonResponse({'results': resultados})


class NotaCrearEditarAjax(LoginRequiredMixin, View):
    """POST JSON. Si trae 'pk', edita; si no, crea."""

    def post(self, request):
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        titulo = (body.get('titulo') or '').strip()
        if not titulo:
            return JsonResponse({'error': 'Ponele un título a la nota.'}, status=400)

        contenido = (body.get('contenido') or '').strip()
        if not contenido:
            return JsonResponse({'error': 'La nota no puede estar vacía.'}, status=400)

        es_privada = bool(body.get('es_privada'))
        if es_privada and not chequear_permiso(request.user, 'crear_notas_privadas'):
            return JsonResponse({'error': 'No tenés permiso para marcar notas como privadas.'}, status=403)

        pk = body.get('pk')
        if pk:
            if not chequear_permiso(request.user, 'editar_notas'):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)
            nota = get_object_or_404(Nota, pk=pk)
            if nota.es_privada and nota.creado_por_id != request.user.id:
                return JsonResponse({'error': 'Esta nota es privada de otro usuario.'}, status=403)
            nota.titulo         = titulo
            nota.contenido      = contenido
            nota.es_privada     = es_privada
            nota.modificado_por = request.user
            nota.save()
        else:
            if not chequear_permiso(request.user, 'crear_notas'):
                return JsonResponse({'error': 'Sin permiso.'}, status=403)
            nota = Nota.objects.create(
                titulo=titulo, contenido=contenido, es_privada=es_privada, creado_por=request.user,
            )

        return JsonResponse({'ok': True, 'pk': nota.pk})


class NotaEliminarAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'eliminar_notas'):
            return JsonResponse({'error': 'Sin permiso.'}, status=403)

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'JSON inválido.'}, status=400)

        nota = get_object_or_404(Nota, pk=body.get('pk'))
        if nota.es_privada and nota.creado_por_id != request.user.id:
            return JsonResponse({'error': 'Esta nota es privada de otro usuario.'}, status=403)

        nota.delete()
        return JsonResponse({'ok': True})
