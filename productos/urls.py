from django.urls import path
from . import views_proveedores, views_productos, views_stock

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

    # ══════════════════════════════════════════════════════════════════
    #  CATEGORÍAS
    # ══════════════════════════════════════════════════════════════════
    path('categorias/',           views_productos.CategoriaListaAjax.as_view(),        name='categoria_lista'),
    path('categorias/acciones/',  views_productos.CategoriaAccionesAjax.as_view(),     name='categoria_acciones'),
    path('categorias/eliminar/',  views_productos.CategoriaEliminarAjax.as_view(),     name='categoria_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  TIPOS
    # ══════════════════════════════════════════════════════════════════
    path('tipos/',                views_productos.TipoListaAjax.as_view(),             name='tipo_lista'),
    path('tipos/acciones/',       views_productos.TipoAccionesAjax.as_view(),          name='tipo_acciones'),
    path('tipos/eliminar/',       views_productos.TipoEliminarAjax.as_view(),          name='tipo_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  STOCK
    # ══════════════════════════════════════════════════════════════════
    path('stock/',           views_stock.StockView.as_view(),        name='stock'),
    path('stock/ajuste/',    views_stock.StockAjusteAjax.as_view(),  name='stock_ajuste'),
    path('stock/historial/', views_stock.StockHistorialAjax.as_view(), name='stock_historial'),
]