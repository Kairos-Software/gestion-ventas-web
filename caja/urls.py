from django.urls import path
from . import views, views_gastos

app_name = 'caja'

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════
    #  PÁGINAS
    # ══════════════════════════════════════════════════════════════════
    path('grande/', views.CajaGrandeView.as_view(), name='caja_grande'),
    path('diaria/', views.CajaDiariaView.as_view(), name='caja_diaria'),
    path('gastos/', views_gastos.GastosView.as_view(), name='gastos'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Caja grande
    # ══════════════════════════════════════════════════════════════════
    path('grande/balance/',             views.BalanceGrandeAjax.as_view(),            name='balance_grande'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Gastos
    # ══════════════════════════════════════════════════════════════════
    path('gastos/listar/',    views_gastos.ListarGastosAjax.as_view(),    name='listar_gastos'),
    path('gastos/crear/',     views_gastos.CrearGastoAjax.as_view(),     name='crear_gasto'),
    path('gastos/editar/<int:pk>/',  views_gastos.EditarGastoAjax.as_view(),  name='editar_gasto'),
    path('gastos/eliminar/<int:pk>/', views_gastos.EliminarGastoAjax.as_view(), name='eliminar_gasto'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Comunes (conceptos, compartidos entre grande y diaria)
    # ══════════════════════════════════════════════════════════════════
    path('concepto/crear/', views.CrearConceptoAjax.as_view(), name='crear_concepto'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Caja diaria (pendiente)
    # ══════════════════════════════════════════════════════════════════
    # Se completa en el siguiente paso.
]