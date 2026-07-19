from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import render
from django.urls import reverse_lazy
from django.utils import timezone

from .models import DatosEmpresa, Cliente, Usuario
from .permisos import chequear_permiso
from .services_estadisticas.ventas import resumen_ganancia

from caja.models import CuentaCaja, TipoCaja, CUENTA_EFECTIVO_DEFAULT_NOMBRE, TurnoCaja
from compras.models import LoteCompra
from productos.models import Moneda, Producto
from asistencia.models import CanalNotificacion, PreferenciaAsistencia


class CustomLoginView(LoginView):
    template_name = 'core/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('core:home')

class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('core:login')

@login_required
def home(request):
    user = request.user
    hoy = timezone.now().date()

    permisos = {
        'ventas':       chequear_permiso(user, 'ver_ventas'),
        'compras':      chequear_permiso(user, 'ver_compras'),
        'productos':    chequear_permiso(user, 'ver_productos'),
        'proveedores':  chequear_permiso(user, 'ver_proveedores'),
        'stock':        chequear_permiso(user, 'ver_stock'),
        'caja':         chequear_permiso(user, 'ver_caja'),
        'clientes':     chequear_permiso(user, 'ver_clientes'),
        'usuarios':     chequear_permiso(user, 'ver_usuarios'),
    }

    ctx = {
        'fecha_actual': hoy,
        'permisos': permisos,
    }

    # ── KPIs de hoy (ventas) ────────────────────────────────────────
    if permisos['ventas']:
        ctx['kpi_ventas_hoy'] = resumen_ganancia(hoy, hoy)

    # ── Estado de la caja diaria ─────────────────────────────────────
    if permisos['caja']:
        ctx['turno_actual'] = TurnoCaja.turno_actual()

    # ── Alertas de stock / vencimientos ──────────────────────────────
    if permisos['productos'] or permisos['stock']:
        ctx['stock_bajo_count'] = Producto.objects.filter(
            gestiona_stock=True, stock_actual__gt=0,
            stock_actual__lte=F('stock_minimo'),
        ).count()
        ctx['lotes_vencidos_count'] = LoteCompra.objects.filter(
            activo=True, cantidad_actual__gt=0, fecha_vencimiento__lt=hoy,
        ).count()
        ctx['lotes_por_vencer_count'] = LoteCompra.objects.filter(
            activo=True, cantidad_actual__gt=0,
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=hoy + timezone.timedelta(days=30),
        ).count()

    # ── Actividad reciente ────────────────────────────────────────────
    if permisos['clientes']:
        ctx['ultimos_clientes'] = Cliente.objects.order_by('-fecha_alta')[:5]
    if permisos['usuarios']:
        ctx['ultimos_usuarios'] = (
            Usuario.objects.filter(is_superuser=False).order_by('-date_joined')[:5]
        )

    return render(request, 'core/home.html', ctx)

@login_required
def mi_perfil(request):
    return render(request, 'core/mi_perfil.html')

@login_required
def configuracion(request):
    cuentas = (
        CuentaCaja.objects
        .filter(caja=TipoCaja.GRANDE)
        .exclude(nombre=CUENTA_EFECTIVO_DEFAULT_NOMBRE)
        .order_by('-activa', 'orden', 'nombre')
    )
    return render(request, 'core/configuracion.html', {
        'datos_empresa':        DatosEmpresa.get_solo(),
        'puede_editar_empresa': chequear_permiso(request.user, 'editar_empresa'),
        'cuentas':              cuentas,
        'puede_editar_cuentas': chequear_permiso(request.user, 'editar_cuentas'),
        'monedas':              Moneda.choices,
        # 'gestionar_notificaciones' está en PERMISOS_RESTRINGIDOS: solo
        # un superusuario puede otorgarlo (ver filtrar_permisos_otorgables),
        # pero una vez otorgado a alguien —típicamente el dueño del
        # negocio— esa persona puede configurar esto sin ser superusuario.
        'puede_editar_asistencia': chequear_permiso(request.user, 'gestionar_notificaciones'),
        'preferencia_asistencia': PreferenciaAsistencia.get_solo(),
        'canales_notificacion':   CanalNotificacion.choices,
    })