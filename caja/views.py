# ══════════════════════════════════════════════════════════════════
#  VIEWS PRINCIPAL - Caja
#  Este archivo gestiona e importa los demás scripts de views
# ══════════════════════════════════════════════════════════════════

from .views_caja_grande import (
    CajaGrandeView,
    BalanceGrandeAjax,
    CrearConceptoAjax,
)

from .views_caja_diaria import (
    CajaDiariaView,
    AbrirTurnoAjax,
    CerrarTurnoAjax,
    EstadoCajaDiariaAjax,
    HistorialTurnosAjax,
    HistorialTurnosView,
    HistorialDiarioView,
    EliminarHistorialAjax,
)

from .views_transacciones import (
    CuentasDisponiblesAjax,
    CalcularTransaccionAjax,
    CrearTransaccionAjax,
    ListarTransaccionesAjax,
    DetalleTransaccionAjax,
    AnularTransaccionAjax,
)

__all__ = [
    # Caja grande
    'CajaGrandeView',
    'BalanceGrandeAjax',
    'CrearConceptoAjax',
    # Caja diaria
    'CajaDiariaView',
    'AbrirTurnoAjax',
    'CerrarTurnoAjax',
    'EstadoCajaDiariaAjax',
    'HistorialTurnosAjax',
    'HistorialTurnosView',
    'HistorialDiarioView',
    'EliminarHistorialAjax',
    # Transacciones
    'CuentasDisponiblesAjax',
    'CalcularTransaccionAjax',
    'CrearTransaccionAjax',
    'ListarTransaccionesAjax',
    'DetalleTransaccionAjax',
    'AnularTransaccionAjax',
]