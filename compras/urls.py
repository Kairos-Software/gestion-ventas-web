from django.urls import path
from . import views
from . import views_historial

app_name = 'compras'

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════
    #  PÁGINAS
    # ══════════════════════════════════════════════════════════════════
    path('nueva/',             views.NuevaCompraView.as_view(),                name='nueva_compra'),
    path('historial/',         views_historial.HistorialComprasView.as_view(), name='historial_compras'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Compras
    # ══════════════════════════════════════════════════════════════════
    path('buscar/productos/',  views.BuscarProductoAjax.as_view(),             name='buscar_producto'),
    path('buscar/proveedores/',views.BuscarProveedorAjax.as_view(),            name='buscar_proveedor'),
    path('confirmar/',         views.ConfirmarCompraAjax.as_view(),            name='confirmar_compra'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Historial
    # ══════════════════════════════════════════════════════════════════
    path('historial/listar/',  views_historial.ListarComprasAjax.as_view(),    name='listar_compras'),
]