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
    path('buscar/sugerencias/', views.BuscarSugerenciasAjax.as_view(), name='buscar_sugerencias'),

    # Interno — pantalla de Configuración del sistema (ver core/views.py:configuracion).
    path('config/guardar/', views_config.CatalogoConfigGuardarAjax.as_view(), name='config_guardar'),
    path('config/hero-imagen/', views_config.CatalogoConfigHeroImagenAjax.as_view(), name='config_hero_imagen'),
    path('config/hero-spot1-imagen/', views_config.CatalogoConfigHeroSpot1ImagenAjax.as_view(), name='config_hero_spot1_imagen'),
    path('config/hero-spot2-imagen/', views_config.CatalogoConfigHeroSpot2ImagenAjax.as_view(), name='config_hero_spot2_imagen'),
    path('config/cta-final-imagen/', views_config.CatalogoConfigCtaFinalImagenAjax.as_view(), name='config_cta_final_imagen'),
    path('config/kinetic-hero-fondo/', views_config.CatalogoKineticHeroFondoAjax.as_view(), name='config_kinetic_hero_fondo'),
    path('config/slides/guardar/', views_config.CatalogoSlideGuardarAjax.as_view(), name='config_slide_guardar'),
    path('config/slides/imagen/', views_config.CatalogoSlideImagenAjax.as_view(), name='config_slide_imagen'),
    path('config/slides/eliminar/', views_config.CatalogoSlideEliminarAjax.as_view(), name='config_slide_eliminar'),
    path('config/banners/guardar/', views_config.CatalogoBannerGuardarAjax.as_view(), name='config_banner_guardar'),
    path('config/banners/imagen/', views_config.CatalogoBannerImagenAjax.as_view(), name='config_banner_imagen'),
    path('config/banners/eliminar/', views_config.CatalogoBannerEliminarAjax.as_view(), name='config_banner_eliminar'),
    path('config/tiles/guardar/', views_config.CatalogoTileGuardarAjax.as_view(), name='config_tile_guardar'),
    path('config/tiles/imagen/', views_config.CatalogoTileImagenAjax.as_view(), name='config_tile_imagen'),
    path('config/tiles/eliminar/', views_config.CatalogoTileEliminarAjax.as_view(), name='config_tile_eliminar'),
    path('config/banners-bento/guardar/', views_config.CatalogoBannerBentoGuardarAjax.as_view(), name='config_banner_bento_guardar'),
    path('config/banners-bento/imagen/', views_config.CatalogoBannerBentoImagenAjax.as_view(), name='config_banner_bento_imagen'),
    path('config/banners-bento/eliminar/', views_config.CatalogoBannerBentoEliminarAjax.as_view(), name='config_banner_bento_eliminar'),
    path('config/ticker/guardar/', views_config.CatalogoTickerGuardarAjax.as_view(), name='config_ticker_guardar'),
    path('config/ticker/eliminar/', views_config.CatalogoTickerEliminarAjax.as_view(), name='config_ticker_eliminar'),
    path('config/ticker-kinetic/guardar/', views_config.CatalogoTickerKineticGuardarAjax.as_view(), name='config_ticker_kinetic_guardar'),
    path('config/ticker-kinetic/eliminar/', views_config.CatalogoTickerKineticEliminarAjax.as_view(), name='config_ticker_kinetic_eliminar'),
    path('config/banners-kinetic/guardar/', views_config.CatalogoBannerKineticGuardarAjax.as_view(), name='config_banner_kinetic_guardar'),
    path('config/banners-kinetic/imagen/', views_config.CatalogoBannerKineticImagenAjax.as_view(), name='config_banner_kinetic_imagen'),
    path('config/banners-kinetic/eliminar/', views_config.CatalogoBannerKineticEliminarAjax.as_view(), name='config_banner_kinetic_eliminar'),
    path('config/marcas/guardar/', views_config.CatalogoMarcaGuardarAjax.as_view(), name='config_marca_guardar'),
    path('config/marcas/imagen/', views_config.CatalogoMarcaImagenAjax.as_view(), name='config_marca_imagen'),
    path('config/marcas/eliminar/', views_config.CatalogoMarcaEliminarAjax.as_view(), name='config_marca_eliminar'),
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
