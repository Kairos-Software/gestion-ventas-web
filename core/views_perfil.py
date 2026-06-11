# core/views_perfil.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect

from .forms_perfil import CambiarUsernameForm, CambiarPasswordForm


@login_required
def mi_perfil(request):
    usuario = request.user

    # Instancias vacías por defecto (GET)
    form_username = CambiarUsernameForm(usuario=usuario)
    form_password = CambiarPasswordForm()

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'username':
            form_username = CambiarUsernameForm(request.POST, usuario=usuario)
            if form_username.is_valid():
                nuevo_username = form_username.cleaned_data['username']
                usuario.username = nuevo_username
                usuario.save(update_fields=['username'])
                messages.success(request, 'Nombre de usuario actualizado correctamente.')
                return redirect('core:mi_perfil')
            # Si hay errores, caemos al render con el form con errores

        elif accion == 'password':
            form_password = CambiarPasswordForm(request.POST)
            if form_password.is_valid():
                usuario.set_password(form_password.cleaned_data['password_nueva'])
                usuario.save(update_fields=['password'])
                # Mantener la sesión activa después del cambio de contraseña
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, usuario)
                messages.success(request, 'Contraseña actualizada correctamente.')
                return redirect('core:mi_perfil')

    context = {
        'form_username': form_username,
        'form_password': form_password,
    }
    return render(request, 'core/mi_perfil.html', context)