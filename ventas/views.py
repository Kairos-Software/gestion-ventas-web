# ══════════════════════════════════════════════════════════════════
#  VIEWS PRINCIPAL - Ventas
#  Este archivo gestiona e importa los demás scripts de views
# ══════════════════════════════════════════════════════════════════

from .views_nueva_venta import (
    NuevaVentaView,
    BuscarProductoAjax,
    BuscarClienteAjax,
    GuardarBorradorAjax,
    ConfirmarVentaAjax,
    EliminarBorradorAjax,
    VentaDocumentoSubirAjax,
    VentaDocumentoEliminarAjax,
    DetalleVentaView,
)

from .views_historial import (
    HistorialVentasView,
    ListarVentasAjax,
)

from .views_acciones import (
    AnularVentaAjax,
    ReactivarVentaAjax,
    EliminarVentaAjax,
    EditarVentaAjax,
)

# Exportar todas las vistas para que urls.py pueda importarlas
__all__ = [
    # Nueva venta
    'NuevaVentaView',
    'BuscarProductoAjax',
    'BuscarClienteAjax',
    'GuardarBorradorAjax',
    'ConfirmarVentaAjax',
    'EliminarBorradorAjax',
    'VentaDocumentoSubirAjax',
    'VentaDocumentoEliminarAjax',
    'DetalleVentaView',
    # Historial
    'HistorialVentasView',
    'ListarVentasAjax',
    # Acciones
    'AnularVentaAjax',
    'ReactivarVentaAjax',
    'EliminarVentaAjax',
    'EditarVentaAjax',
]
