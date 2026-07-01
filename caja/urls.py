from django.urls import path
from . import views, views_gastos, views_caja_diaria, views_transacciones

app_name = 'caja'

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════
    #  PÁGINAS
    # ══════════════════════════════════════════════════════════════════
    path('grande/', views.CajaGrandeView.as_view(), name='caja_grande'),
    path('diaria/', views_caja_diaria.CajaDiariaView.as_view(), name='caja_diaria'),
    path('diaria/historial-turnos/', views_caja_diaria.HistorialTurnosView.as_view(), name='historial_turnos'),
    path('diaria/historial-diario/', views_caja_diaria.HistorialDiarioView.as_view(), name='historial_diario'),
    path('gastos/', views_gastos.GastosView.as_view(), name='gastos'),
    path('transacciones/', views_transacciones.TransaccionesPageView.as_view(), name='transacciones_listar_page'),  # ← NUEVO

    
    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Caja grande
    # ══════════════════════════════════════════════════════════════════
    path('grande/balance/',             views.BalanceGrandeAjax.as_view(),            name='balance_grande'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Gastos
    # ══════════════════════════════════════════════════════════════════
    path('gastos/listar/',              views_gastos.ListarGastosAjax.as_view(),       name='listar_gastos'),
    path('gastos/crear/',               views_gastos.CrearGastoAjax.as_view(),         name='crear_gasto'),
    path('gastos/editar/<int:pk>/',     views_gastos.EditarGastoAjax.as_view(),        name='editar_gasto'),
    path('gastos/eliminar/<int:pk>/',   views_gastos.EliminarGastoAjax.as_view(),      name='eliminar_gasto'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Comunes
    # ══════════════════════════════════════════════════════════════════
    path('concepto/crear/',             views.CrearConceptoAjax.as_view(),             name='crear_concepto'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Caja diaria
    # ══════════════════════════════════════════════════════════════════
    path('diaria/abrir/',               views_caja_diaria.AbrirTurnoAjax.as_view(),       name='abrir_turno'),
    path('diaria/cerrar/',              views_caja_diaria.CerrarTurnoAjax.as_view(),      name='cerrar_turno'),
    path('diaria/estado/',              views_caja_diaria.EstadoCajaDiariaAjax.as_view(), name='estado_caja_diaria'),
    path('diaria/historial-ajax/',      views_caja_diaria.HistorialTurnosAjax.as_view(), name='historial_turnos_ajax'),
    path('diaria/eliminar-historial/',  views_caja_diaria.EliminarHistorialAjax.as_view(), name='eliminar_historial'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Transacciones (caja grande)
    # ══════════════════════════════════════════════════════════════════
    path('transacciones/cuentas/',          views_transacciones.CuentasDisponiblesAjax.as_view(),  name='transacciones_cuentas'),
    path('transacciones/calcular/',         views_transacciones.CalcularTransaccionAjax.as_view(), name='transacciones_calcular'),
    path('transacciones/crear/',            views_transacciones.CrearTransaccionAjax.as_view(),    name='transacciones_crear'),
    path('transacciones/listar/',           views_transacciones.ListarTransaccionesAjax.as_view(), name='transacciones_listar'),
    path('transacciones/<int:pk>/',         views_transacciones.DetalleTransaccionAjax.as_view(),  name='transacciones_detalle'),
    path('transacciones/<int:pk>/anular/',  views_transacciones.AnularTransaccionAjax.as_view(),   name='transacciones_anular'),
]