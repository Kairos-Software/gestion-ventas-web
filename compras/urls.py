from django.urls import path
from . import views
from . import views_historial
from . import views_acciones

app_name = 'compras'

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════
    #  PÁGINAS
    # ══════════════════════════════════════════════════════════════════
    path('nueva/',      views.NuevaCompraView.as_view(),                name='nueva_compra'),
    path('historial/',  views_historial.HistorialComprasView.as_view(), name='historial_compras'),
    path('detalle/<int:pk>/', views.DetalleCompraView.as_view(),        name='detalle_compra'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Crear compra
    # ══════════════════════════════════════════════════════════════════
    path('buscar/productos/',   views.BuscarProductoAjax.as_view(),     name='buscar_producto'),
    path('buscar/proveedores/', views.BuscarProveedorAjax.as_view(),    name='buscar_proveedor'),
    path('guardar-borrador/',   views.GuardarBorradorAjax.as_view(),    name='guardar_borrador'),    # ← NUEVO
    path('confirmar/',          views.ConfirmarCompraAjax.as_view(),    name='confirmar_compra'),
    path('eliminar-borrador/',  views.EliminarBorradorAjax.as_view(),   name='eliminar_borrador'),   # ← NUEVO

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Historial
    # ══════════════════════════════════════════════════════════════════
    path('historial/listar/',   views_historial.ListarComprasAjax.as_view(), name='listar_compras'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Acciones sobre compras existentes
    # ══════════════════════════════════════════════════════════════════
    path('anular/',     views_acciones.AnularCompraAjax.as_view(),    name='anular_compra'),
    path('reactivar/',  views_acciones.ReactivarCompraAjax.as_view(), name='reactivar_compra'),
    path('eliminar/',   views_acciones.EliminarCompraAjax.as_view(),  name='eliminar_compra'),
    path('editar/',     views_acciones.EditarCompraAjax.as_view(),    name='editar_compra'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Documentos adjuntos
    # ══════════════════════════════════════════════════════════════════
    path('documentos/subir/',    views.CompraDocumentoSubirAjax.as_view(),    name='documento_subir'),
    path('documentos/eliminar/', views.CompraDocumentoEliminarAjax.as_view(), name='documento_eliminar'),
]