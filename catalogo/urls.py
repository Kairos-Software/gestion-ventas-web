from django.urls import path

from . import views
from . import views_demo
from . import views_pedidos

app_name = 'catalogo'

urlpatterns = [
    path('', views.CatalogoHomeView.as_view(), name='home'),
    path('producto/<int:pk>/', views.ProductoDetalleView.as_view(), name='producto_detalle'),

    # Público — el carrito del catálogo confirma el pedido acá.
    path('pedidos/crear/', views_pedidos.CrearPedidoAjax.as_view(), name='pedido_crear'),

    # Interno — campanita de notificaciones (ver core/base.html).
    path('pedidos/lista/', views_pedidos.PedidosListaAjax.as_view(), name='pedido_lista'),
    path('pedidos/no-leidos/', views_pedidos.PedidosNoLeidosAjax.as_view(), name='pedido_no_leidos'),
    path('pedidos/<int:pk>/vender/', views_pedidos.PedidoVenderAjax.as_view(), name='pedido_vender'),

    # Interno — historial completo de pedidos (ver todos, descartar, borrar).
    path('pedidos/historial/', views_pedidos.PedidosHistorialView.as_view(), name='pedidos_historial'),
    path('pedidos/<int:pk>/cambiar-estado/', views_pedidos.PedidoCambiarEstadoAjax.as_view(), name='pedido_cambiar_estado'),
    path('pedidos/<int:pk>/eliminar/', views_pedidos.PedidoEliminarAjax.as_view(), name='pedido_eliminar'),

    # Herramienta de desarrollo (admin) — datos de prueba para previsualizar el catálogo.
    path('demo/cargar/', views_demo.CargarDatosDemoAjax.as_view(), name='demo_cargar'),
    path('demo/eliminar/', views_demo.EliminarDatosDemoAjax.as_view(), name='demo_eliminar'),
]
