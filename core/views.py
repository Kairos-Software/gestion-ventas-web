from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse_lazy

from .models import DatosEmpresa
from .permisos import chequear_permiso


class CustomLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('core:home')

class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('core:login')

@login_required
def home(request):
    return render(request, 'core/home.html')

@login_required
def mi_perfil(request):
    return render(request, 'core/mi_perfil.html')

@login_required
def configuracion(request):
    return render(request, 'core/configuracion.html', {
        'datos_empresa':        DatosEmpresa.get_solo(),
        'puede_editar_empresa': chequear_permiso(request.user, 'editar_empresa'),
    })