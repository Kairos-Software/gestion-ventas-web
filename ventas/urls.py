from django.urls import path
from . import views
from . import views_historial
from . import views_acciones

app_name = 'ventas'

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════
    #  PÁGINAS
    # ══════════════════════════════════════════════════════════════════
    path('nueva/',      views.NuevaVentaView.as_view(),                name='nueva_venta'),
    path('historial/',  views_historial.HistorialVentasView.as_view(), name='historial_ventas'),
    path('detalle/<int:pk>/', views.DetalleVentaView.as_view(),        name='detalle_venta'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Crear venta
    # ══════════════════════════════════════════════════════════════════
    path('buscar/productos/',  views.BuscarProductoAjax.as_view(),    name='buscar_producto'),
    path('buscar/clientes/',   views.BuscarClienteAjax.as_view(),     name='buscar_cliente'),
    path('buscar/lote/',       views.BuscarLoteVentaAjax.as_view(),   name='buscar_lote'),
    path('guardar-borrador/',  views.GuardarBorradorAjax.as_view(),   name='guardar_borrador'),
    path('confirmar/',         views.ConfirmarVentaAjax.as_view(),    name='confirmar_venta'),
    path('eliminar-borrador/', views.EliminarBorradorAjax.as_view(),  name='eliminar_borrador'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Historial
    # ══════════════════════════════════════════════════════════════════
    path('historial/listar/',  views_historial.ListarVentasAjax.as_view(), name='listar_ventas'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Acciones sobre ventas existentes
    # ══════════════════════════════════════════════════════════════════
    path('anular/',     views_acciones.AnularVentaAjax.as_view(),    name='anular_venta'),
    path('reactivar/',  views_acciones.ReactivarVentaAjax.as_view(), name='reactivar_venta'),
    path('eliminar/',   views_acciones.EliminarVentaAjax.as_view(),  name='eliminar_venta'),
    path('editar/',     views_acciones.EditarVentaAjax.as_view(),    name='editar_venta'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Documentos adjuntos
    # ══════════════════════════════════════════════════════════════════
    path('documentos/subir/',    views.VentaDocumentoSubirAjax.as_view(),    name='documento_subir'),
    path('documentos/eliminar/', views.VentaDocumentoEliminarAjax.as_view(), name='documento_eliminar'),
]