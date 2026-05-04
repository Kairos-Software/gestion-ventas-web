# core/views_permisos.py
import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from .models import Usuario, Rol, PERMISOS_CHOICES
from .permisos import chequear_permiso, permisos_del_usuario, guardar_permisos_usuario


class GestionPermisosView(LoginRequiredMixin, View):
    def get(self, request, pk):
        # Sin permiso → volvemos a gestion_usuarios con mensaje, no página rota
        if not chequear_permiso(request.user, 'gestionar_permisos'):
            qs = Usuario.objects.filter(is_superuser=False).order_by('username')
            if not request.user.is_superuser:
                qs = qs.exclude(pk=request.user.pk)
            return render(request, 'core/gestion_usuarios.html', {
                'usuarios': qs,
                'sin_permiso': False,
                'puede_crear': chequear_permiso(request.user, 'crear_usuarios'),
                'puede_editar': chequear_permiso(request.user, 'editar_usuarios'),
                'puede_eliminar': chequear_permiso(request.user, 'eliminar_usuarios'),
                'puede_gestionar_permisos': False,
                'error_msg': 'No tenés permiso para gestionar permisos de otros usuarios.',
            }, status=403)

        usuario_obj = get_object_or_404(Usuario, pk=pk, is_superuser=False)
        estado = permisos_del_usuario(usuario_obj)

        modulos = {}
        for codigo, label in PERMISOS_CHOICES:
            partes = codigo.split('_')
            modulo = partes[-1].capitalize() if len(partes) > 1 else 'General'
            if modulo not in modulos:
                modulos[modulo] = []
            modulos[modulo].append({
                'codigo': codigo,
                'label': label,
                **estado[codigo],
            })

        context = {
            'usuario_obj': usuario_obj,
            'modulos': modulos.items(),
            'tiene_rol': usuario_obj.rol is not None,
            'rol_nombre': usuario_obj.rol.nombre if usuario_obj.rol else None,
        }
        return render(request, 'core/permisos_usuario.html', context)


class GuardarPermisosAjax(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not chequear_permiso(request.user, 'gestionar_permisos'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        usuario_obj = get_object_or_404(Usuario, pk=pk, is_superuser=False)

        try:
            body = json.loads(request.body)
            permisos_enviados = body.get('permisos', {})
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        permisos_bool = {k: bool(v) for k, v in permisos_enviados.items()}
        guardar_permisos_usuario(usuario_obj, permisos_bool)
        return JsonResponse({'success': True})


class GuardarPermisosRolAjax(LoginRequiredMixin, View):
    def post(self, request):
        if not chequear_permiso(request.user, 'gestionar_permisos'):
            return JsonResponse({'error': 'Sin permiso'}, status=403)

        try:
            body = json.loads(request.body)
            rol_pk = body.get('rol_pk')
            permisos_lista = body.get('permisos', [])
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'JSON inválido'}, status=400)

        rol = get_object_or_404(Rol, pk=rol_pk)
        rol.set_permisos(set(permisos_lista))
        return JsonResponse({'success': True})