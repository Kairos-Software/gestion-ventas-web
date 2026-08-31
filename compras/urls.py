from django.urls import path
from . import views
from . import views_historial
from . import views_acciones
from . import views_inventario
from . import views_factura_inicial

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
    path('guardar-borrador/',   views.GuardarBorradorAjax.as_view(),    name='guardar_borrador'),
    path('actualizar-borrador/', views.ActualizarBorradorAjax.as_view(), name='actualizar_borrador'),
    path('confirmar/',          views.ConfirmarCompraAjax.as_view(),    name='confirmar_compra'),
    path('eliminar-borrador/',  views.EliminarBorradorAjax.as_view(),   name='eliminar_borrador'),

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

    # ══════════════════════════════════════════════════════════════════
    #  HERRAMIENTA — Factura inicial (compra real sin caja, historial propio)
    # ══════════════════════════════════════════════════════════════════
    path('factura-inicial/',                    views_factura_inicial.FacturaInicialView.as_view(),               name='factura_inicial'),
    path('factura-inicial/historial/',          views_factura_inicial.FacturaInicialHistorialView.as_view(),      name='factura_inicial_historial'),
    path('factura-inicial/buscar/productos/',   views_factura_inicial.FacturaInicialBuscarProductoAjax.as_view(), name='factura_inicial_buscar_producto'),
    path('factura-inicial/buscar/proveedores/', views_factura_inicial.FacturaInicialBuscarProveedorAjax.as_view(),name='factura_inicial_buscar_proveedor'),
    path('factura-inicial/crear/',              views_factura_inicial.FacturaInicialCrearAjax.as_view(),          name='factura_inicial_crear'),
    path('factura-inicial/listar/',             views_factura_inicial.FacturaInicialListarAjax.as_view(),         name='factura_inicial_listar'),
    path('factura-inicial/reimprimir/',         views_factura_inicial.FacturaInicialReimprimirAjax.as_view(),     name='factura_inicial_reimprimir'),
    path('factura-inicial/anular/',             views_factura_inicial.FacturaInicialAnularAjax.as_view(),         name='factura_inicial_anular'),
    path('factura-inicial/eliminar/',           views_factura_inicial.FacturaInicialEliminarAjax.as_view(),       name='factura_inicial_eliminar'),

    # ══════════════════════════════════════════════════════════════════
    #  INVENTARIO
    # ══════════════════════════════════════════════════════════════════
    path('inventario/',               views_inventario.InventarioView.as_view(),         name='inventario'),
    path('inventario/listar/',        views_inventario.ListarLotesAjax.as_view(),         name='inventario_listar'),
    path('inventario/buscar-codigo/', views_inventario.BuscarLotePorCodigoAjax.as_view(), name='inventario_buscar_codigo'),
    path('inventario/perdida/registrar/', views_inventario.RegistrarPerdidaAjax.as_view(), name='inventario_perdida_registrar'),
    path('inventario/perdidas/',          views_inventario.ListarPerdidasAjax.as_view(),   name='inventario_perdidas_listar'),

    # ══════════════════════════════════════════════════════════════════
    #  INVENTARIO — Fraccionamiento
    # ══════════════════════════════════════════════════════════════════
    path('inventario/fraccionar/buscar-productos/', views_inventario.BuscarProductosFraccionarAjax.as_view(), name='inventario_fraccionar_buscar'),
    path('inventario/fraccionar/',                   views_inventario.FraccionarAjax.as_view(),                name='inventario_fraccionar'),
    path('inventario/fraccionamientos/',              views_inventario.ListarFraccionamientosAjax.as_view(),   name='inventario_fraccionamientos_listar'),
]