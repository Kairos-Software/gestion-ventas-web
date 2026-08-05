# core/views_recuperacion.py — recuperar contraseña por código de mail
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms_recuperacion import NuevaPasswordForm, SolicitarRecuperacionForm, VerificarCodigoForm
from .models import CodigoRecuperacionPassword
from .services_email import enviar_codigo_recuperacion

Usuario = get_user_model()


def _generar_codigo():
    return f'{secrets.randbelow(1_000_000):06d}'


def _ofuscar_email(email):
    usuario_parte, _, dominio = email.partition('@')
    visible = usuario_parte[:2]
    return f'{visible}{"*" * max(len(usuario_parte) - len(visible), 3)}@{dominio}'


def solicitar_recuperacion(request):
    """Paso 1: pide usuario/email. Si no está registrado o no tiene mail cargado, avisa
    explícitamente (sistema interno de uso conocido — no hace falta ocultar existencia
    de usuarios como en un producto público)."""
    form = SolicitarRecuperacionForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        identificador = form.cleaned_data['identificador']
        usuario = Usuario.objects.filter(
            Q(username__iexact=identificador)
            | Q(email__iexact=identificador)
            | Q(email_personal__iexact=identificador)
        ).first()

        if not usuario:
            form.add_error('identificador', 'Ese usuario o correo no está registrado en el sistema.')
        else:
            destino = usuario.email or usuario.email_personal or None
            if not destino:
                form.add_error(
                    'identificador',
                    'Ese usuario no tiene un correo cargado — pedile a un administrador que le cargue uno.',
                )
            else:
                CodigoRecuperacionPassword.objects.filter(
                    usuario=usuario, usado=False
                ).update(usado=True)
                codigo = _generar_codigo()
                CodigoRecuperacionPassword.objects.create(usuario=usuario, codigo=codigo)
                enviar_codigo_recuperacion(usuario, destino, codigo)
                request.session['recup_usuario_id'] = usuario.id
                request.session['recup_pedido'] = True
                messages.info(request, f'Te mandamos un código de verificación a {_ofuscar_email(destino)}.')
                return redirect('core:recuperar_codigo')

    return render(request, 'core/recuperar_solicitar.html', {'form': form})


def verificar_codigo_recuperacion(request):
    """Paso 2: valida el código de 6 dígitos recibido por mail."""
    if not request.session.get('recup_pedido'):
        return redirect('core:recuperar_password')

    usuario_id = request.session.get('recup_usuario_id')
    error = None

    if request.method == 'POST':
        form = VerificarCodigoForm(request.POST)
        if form.is_valid():
            codigo_ingresado = form.cleaned_data['codigo']
            registro = None
            if usuario_id:
                registro = CodigoRecuperacionPassword.objects.filter(
                    usuario_id=usuario_id, usado=False
                ).order_by('-creado').first()

            if registro and registro.vigente() and registro.codigo == codigo_ingresado:
                registro.usado = True
                registro.save(update_fields=['usado'])
                request.session['recup_verificado_id'] = usuario_id
                request.session.pop('recup_usuario_id', None)
                request.session.pop('recup_pedido', None)
                return redirect('core:recuperar_nueva_password')

            if registro and not registro.usado:
                registro.intentos += 1
                if registro.intentos >= 5:
                    registro.usado = True
                registro.save(update_fields=['intentos', 'usado'])

            error = 'Código incorrecto o vencido.'
    else:
        form = VerificarCodigoForm()

    return render(request, 'core/recuperar_codigo.html', {'form': form, 'error': error})


def nueva_password_recuperacion(request):
    """Paso 3: código ya verificado — carga la contraseña nueva."""
    usuario_id = request.session.get('recup_verificado_id')
    if not usuario_id:
        return redirect('core:recuperar_password')

    usuario = get_object_or_404(Usuario, pk=usuario_id)

    if request.method == 'POST':
        form = NuevaPasswordForm(request.POST)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['password_nueva'])
            usuario.save(update_fields=['password'])
            request.session.pop('recup_verificado_id', None)
            messages.success(request, 'Contraseña actualizada. Ya podés iniciar sesión.')
            return redirect('core:login')
    else:
        form = NuevaPasswordForm()

    return render(request, 'core/recuperar_nueva.html', {'form': form, 'usuario': usuario})
