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
)

# Exportar todas las vistas para que urls.py pueda importarlas
__all__ = [
    # Caja grande
    'CajaGrandeView',
    'BalanceGrandeAjax',
    'CrearConceptoAjax',
    # Caja diaria
    'CajaDiariaView',
]