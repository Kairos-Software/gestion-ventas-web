from django.urls import path

from . import views
from . import views_demo
from . import views_pedidos
from . import views_config

app_name = 'catalogo'

urlpatterns = [
    path('', views.CatalogoHomeView.as_view(), name='home'),
    path('la-tienda/', views.TiendaInstitucionalView.as_view(), name='institucional'),
    path('producto/<int:pk>/', views.ProductoDetalleView.as_view(), name='producto_detalle'),

    # Interno — pantalla de Configuración del sistema (ver core/views.py:configuracion).
    path('config/guardar/', views_config.CatalogoConfigGuardarAjax.as_view(), name='config_guardar'),
    path('config/hero-imagen/', views_config.CatalogoConfigHeroImagenAjax.as_view(), name='config_hero_imagen'),
    path('config/kinetic-hero-fondo/', views_config.CatalogoKineticHeroFondoAjax.as_view(), name='config_kinetic_hero_fondo'),
    path('config/slides/guardar/', views_config.CatalogoSlideGuardarAjax.as_view(), name='config_slide_guardar'),
    path('config/slides/imagen/', views_config.CatalogoSlideImagenAjax.as_view(), name='config_slide_imagen'),
    path('config/slides/eliminar/', views_config.CatalogoSlideEliminarAjax.as_view(), name='config_slide_eliminar'),
    path('config/institucional-imagen/', views_config.CatalogoInstitucionalImagenAjax.as_view(), name='config_institucional_imagen'),
    path('config/galeria/imagen/', views_config.CatalogoGaleriaImagenAjax.as_view(), name='config_galeria_imagen'),
    path('config/galeria/eliminar/', views_config.CatalogoGaleriaEliminarAjax.as_view(), name='config_galeria_eliminar'),

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
