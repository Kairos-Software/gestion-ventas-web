from django.urls import path
from . import views

app_name = 'presupuestos'

urlpatterns = [
    path('', views.NuevoPresupuestoView.as_view(), name='nuevo'),

    path('buscar/productos/', views.BuscarProductoAjax.as_view(), name='buscar_producto'),
    path('buscar/clientes/',  views.BuscarClienteAjax.as_view(),  name='buscar_cliente'),
    path('crear/',            views.CrearPresupuestoAjax.as_view(), name='crear'),
    path('actualizar/',       views.ActualizarPresupuestoAjax.as_view(), name='actualizar'),
    path('datos/',            views.PresupuestoDatosAjax.as_view(), name='datos'),
    path('eliminar/',         views.EliminarPresupuestoAjax.as_view(), name='eliminar'),

    path('historial/',        views.HistorialPresupuestosView.as_view(), name='historial'),
    path('historial/listar/', views.ListarPresupuestosAjax.as_view(),    name='listar'),
]
