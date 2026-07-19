from django.urls import path
from . import views_proveedores, views_productos, views_stock, views_ofertas, views_paquetes

app_name = 'productos'

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════
    #  PROVEEDORES
    # ══════════════════════════════════════════════════════════════════
    path('proveedores/',          views_proveedores.GestionProveedoresView.as_view(),   name='gestion_proveedores'),
    path('proveedores/acciones/', views_proveedores.ProveedorCrearEditarAjax.as_view(), name='proveedor_acciones'),
    path('proveedores/eliminar/', views_proveedores.ProveedorEliminarAjax.as_view(),    name='proveedor_eliminar'),
    path('proveedores/buscar/',   views_proveedores.ProveedorBuscarAjax.as_view(),      name='proveedor_buscar'),

    # ══════════════════════════════════════════════════════════════════
    #  PRODUCTOS
    # ══════════════════════════════════════════════════════════════════
    path('',                      views_productos.GestionProductosView.as_view(),       name='gestion_productos'),
    path('acciones/',             views_productos.ProductoCrearEditarAjax.as_view(),    name='producto_acciones'),
    path('eliminar/',             views_productos.ProductoEliminarAjax.as_view(),       name='producto_eliminar'),
    path('buscar/',               views_productos.ProductoBuscarAjax.as_view(),         name='producto_buscar'),

    # — Imágenes —
    path('imagenes/subir/',       views_productos.ProductoImagenSubirAjax.as_view(),    name='producto_imagen_subir'),
    path('imagenes/eliminar/',    views_productos.ProductoImagenEliminarAjax.as_view(), name='producto_imagen_eliminar'),
    path('imagenes/portada/',     views_productos.ProductoImagenPortadaAjax.as_view(),  name='producto_imagen_portada'),

    # — Variantes genéricas —
    path('variantes/',                 views_productos.VarianteListaAjax.as_view(),            name='variante_lista'),
    path('variantes/acciones/',        views_productos.VarianteAccionesAjax.as_view(),         name='variante_acciones'),
    path('variantes/eliminar/',        views_productos.VarianteEliminarAjax.as_view(),         name='variante_eliminar'),

    path('opciones-variantes/',       views_productos.OpcionVarianteListaAjax.as_view(),      name='opcion_variante_lista'),
    path('opciones-variantes/acciones/', views_productos.OpcionVarianteAccionesAjax.as_view(),   name='opcion_variante_acciones'),
    path('opciones-variantes/eliminar/', views_productos.OpcionVarianteEliminarAjax.as_view(),   name='opcion_variante_eliminar'),

    path('combinaciones/',            views_productos.CombinacionVarianteListaAjax.as_view(),  name='combinacion_variante_lista'),
    path('combinaciones/acciones/',   views_productos.CombinacionVarianteAccionesAjax.as_view(), name='combinacion_variante_acciones'),
    path('combinaciones/stock/',      views_productos.CombinacionVarianteStockAjax.as_view(),    name='combinacion_variante_stock'),
    path('combinaciones/toggle/',     views_productos.CombinacionVarianteToggleActivoAjax.as_view(), name='combinacion_variante_toggle'),

    # ══════════════════════════════════════════════════════════════════
    #  CATEGORÍAS
    # ══════════════════════════════════════════════════════════════════
    path('categorias/',           views_productos.CategoriaListaAjax.as_view(),        name='categoria_lista'),
    path('categorias/acciones/',  views_productos.CategoriaAccionesAjax.as_view(),     name='categoria_acciones'),
    path('categorias/eliminar/',  views_productos.CategoriaEliminarAjax.as_view(),     name='categoria_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  LISTAS DE DESCUENTO
    # ══════════════════════════════════════════════════════════════════
    path('listas-descuento/',           views_productos.ListaDescuentoListaAjax.as_view(),     name='lista_descuento_lista'),
    path('listas-descuento/acciones/',  views_productos.ListaDescuentoAccionesAjax.as_view(),  name='lista_descuento_acciones'),
    path('listas-descuento/eliminar/',  views_productos.ListaDescuentoEliminarAjax.as_view(),  name='lista_descuento_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  OFERTAS — sección propia (no vive dentro de Productos)
    # ══════════════════════════════════════════════════════════════════
    path('ofertas/',           views_ofertas.GestionOfertasView.as_view(),  name='gestion_ofertas'),
    path('ofertas/lista/',     views_ofertas.OfertaListaAjax.as_view(),     name='oferta_lista'),
    path('ofertas/acciones/',  views_ofertas.OfertaAccionesAjax.as_view(),  name='oferta_acciones'),
    path('ofertas/eliminar/',  views_ofertas.OfertaEliminarAjax.as_view(),  name='oferta_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  PAQUETES — combos de productos distintos (dentro de Catálogo)
    # ══════════════════════════════════════════════════════════════════
    path('paquetes/',           views_paquetes.GestionPaquetesView.as_view(), name='gestion_paquetes'),
    path('paquetes/lista/',     views_paquetes.PaqueteListaAjax.as_view(),    name='paquete_lista'),
    path('paquetes/acciones/',  views_paquetes.PaqueteAccionesAjax.as_view(), name='paquete_acciones'),
    path('paquetes/eliminar/',  views_paquetes.PaqueteEliminarAjax.as_view(), name='paquete_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  TIPOS
    # ══════════════════════════════════════════════════════════════════
    path('tipos/',                views_productos.TipoListaAjax.as_view(),             name='tipo_lista'),
    path('tipos/acciones/',       views_productos.TipoAccionesAjax.as_view(),          name='tipo_acciones'),
    path('tipos/eliminar/',       views_productos.TipoEliminarAjax.as_view(),          name='tipo_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  STOCK
    # ══════════════════════════════════════════════════════════════════
    path('stock/',           views_stock.StockView.as_view(),          name='stock'),
    path('stock/ajuste/',    views_stock.StockAjusteAjax.as_view(),    name='stock_ajuste'),
    path('stock/historial/', views_stock.StockHistorialAjax.as_view(), name='stock_historial'),
]