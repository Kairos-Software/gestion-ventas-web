# core/urls.py  — versión extendida (agrega rutas de personal)
from django.urls import path
from . import views
from . import views_usuarios
from . import views_permisos
from . import views_clientes

app_name = 'core'

urlpatterns = [
    # ── Generales ─────────────────────────────────────────────────
    path('', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('home/', views.home, name='home'),

    # ── Usuarios — listado y acciones rápidas (modal) ─────────────
    path('usuarios/', views_usuarios.GestionUsuariosView.as_view(), name='gestion_usuarios'),
    path('usuarios/acciones/', views_usuarios.UsuarioCrearEditarAjax.as_view(), name='usuario_acciones'),
    path('usuarios/eliminar/', views_usuarios.UsuarioEliminarAjax.as_view(), name='usuario_eliminar'),

    # ── Usuarios — detalle y edición completa ─────────────────────
    path('usuarios/<int:pk>/', views_usuarios.DetalleUsuarioView.as_view(), name='detalle_usuario'),
    path('usuarios/<int:pk>/editar/', views_usuarios.EditarUsuarioDetalleAjax.as_view(), name='editar_usuario_detalle'),
    path('usuarios/<int:pk>/foto/', views_usuarios.UsuarioFotoAjax.as_view(), name='usuario_foto'),

    # ── Usuarios — sub-recursos ────────────────────────────────────
    path('usuarios/<int:pk>/estudios/', views_usuarios.UsuarioEstudioAjax.as_view(), name='usuario_estudios'),
    path('usuarios/<int:pk>/experiencias/', views_usuarios.UsuarioExperienciaAjax.as_view(), name='usuario_experiencias'),
    path('usuarios/<int:pk>/capacitaciones/', views_usuarios.UsuarioCapacitacionAjax.as_view(), name='usuario_capacitaciones'),
    path('usuarios/<int:pk>/documentos/', views_usuarios.UsuarioDocumentoAjax.as_view(), name='usuario_documentos'),

    # ── Permisos ──────────────────────────────────────────────────
    path('usuarios/<int:pk>/permisos/', views_permisos.GestionPermisosView.as_view(), name='gestion_permisos'),
    path('usuarios/<int:pk>/permisos/guardar/', views_permisos.GuardarPermisosAjax.as_view(), name='guardar_permisos'),
    path('roles/permisos/guardar/', views_permisos.GuardarPermisosRolAjax.as_view(), name='guardar_permisos_rol'),

    # ── Clientes ──────────────────────────────────────────────────
    path('clientes/', views_clientes.GestionClientesView.as_view(), name='gestion_clientes'),
    path('clientes/acciones/', views_clientes.ClienteCrearEditarAjax.as_view(), name='cliente_acciones'),
    path('clientes/eliminar/', views_clientes.ClienteEliminarAjax.as_view(), name='cliente_eliminar'),
    path('clientes/buscar/', views_clientes.ClienteBuscarAjax.as_view(), name='cliente_buscar'),
    path('clientes/<int:pk>/', views_clientes.ClienteDetalleView.as_view(), name='cliente_detalle'),
    path('clientes/<int:pk>/imagenes/', views_clientes.ClienteImagenAjax.as_view(), name='cliente_imagenes'),
    path('clientes/<int:pk>/contactos/', views_clientes.ClienteContactoAjax.as_view(), name='cliente_contactos'),
    path('clientes/<int:pk>/telefonos/', views_clientes.ClienteTelefonoAjax.as_view(), name='cliente_telefonos'),
    path('clientes/grupos/', views_clientes.GrupoFamiliarAjax.as_view(), name='grupo_familiar'),
]