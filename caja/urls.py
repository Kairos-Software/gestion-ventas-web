from django.urls import path
from . import views, views_gastos, views_caja_diaria, views_transacciones, views_deudas, views_cheques

app_name = 'caja'

urlpatterns = [

    # ══════════════════════════════════════════════════════════════════
    #  PÁGINAS
    # ══════════════════════════════════════════════════════════════════
    path('grande/',                  views.CajaGrandeView.as_view(),                  name='caja_grande'),
    path('diaria/',                  views_caja_diaria.CajaDiariaView.as_view(),      name='caja_diaria'),
    path('diaria/historial-turnos/', views_caja_diaria.HistorialTurnosView.as_view(), name='historial_turnos'),
    path('diaria/historial-diario/', views_caja_diaria.HistorialDiarioView.as_view(), name='historial_diario'),
    path('gastos/',                  views_gastos.GastosView.as_view(),               name='gastos'),
    path('transacciones/',           views_transacciones.TransaccionesPageView.as_view(), name='transacciones_listar_page'),
    path('deudas/',                  views_deudas.DeudasView.as_view(),               name='deudas'),
    path('cheques/',                 views_cheques.ChequesView.as_view(),             name='cheques'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Caja grande
    # ══════════════════════════════════════════════════════════════════
    path('grande/balance/', views.BalanceGrandeAjax.as_view(), name='balance_grande'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Gastos
    # ══════════════════════════════════════════════════════════════════
    path('gastos/listar/',            views_gastos.ListarGastosAjax.as_view(),    name='listar_gastos'),
    path('gastos/crear/',             views_gastos.CrearGastoAjax.as_view(),      name='crear_gasto'),
    path('gastos/editar/<int:pk>/',   views_gastos.EditarGastoAjax.as_view(),     name='editar_gasto'),
    path('gastos/eliminar/<int:pk>/', views_gastos.EliminarGastoAjax.as_view(),   name='eliminar_gasto'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Deudas (créditos y préstamos)
    # ══════════════════════════════════════════════════════════════════
    path('deudas/listar/',                   views_deudas.ListarDeudasAjax.as_view(),    name='listar_deudas'),
    path('deudas/crear/',                    views_deudas.CrearDeudaAjax.as_view(),      name='crear_deuda'),
    path('deudas/editar/<int:pk>/',          views_deudas.EditarDeudaAjax.as_view(),     name='editar_deuda'),
    path('deudas/eliminar/<int:pk>/',        views_deudas.EliminarDeudaAjax.as_view(),   name='eliminar_deuda'),
    path('deudas/<int:pk>/',                 views_deudas.DetalleDeudaAjax.as_view(),    name='detalle_deuda'),
    path('deudas/cuotas/<int:pk>/confirmar/', views_deudas.ConfirmarCuotaAjax.as_view(), name='confirmar_cuota_deuda'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Cheques
    # ══════════════════════════════════════════════════════════════════
    path('cheques/listar/',            views_cheques.ListarChequesAjax.as_view(),    name='listar_cheques'),
    path('cheques/crear/',             views_cheques.CrearChequeAjax.as_view(),      name='crear_cheque'),
    path('cheques/editar/<int:pk>/',   views_cheques.EditarChequeAjax.as_view(),     name='editar_cheque'),
    path('cheques/eliminar/<int:pk>/', views_cheques.EliminarChequeAjax.as_view(),   name='eliminar_cheque'),
    path('cheques/<int:pk>/confirmar/', views_cheques.ConfirmarChequeAjax.as_view(), name='confirmar_cheque'),
    path('cheques/<int:pk>/rechazar/',  views_cheques.RechazarChequeAjax.as_view(),  name='rechazar_cheque'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Comunes
    # ══════════════════════════════════════════════════════════════════
    path('concepto/crear/', views.CrearConceptoAjax.as_view(), name='crear_concepto'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Caja diaria
    # ══════════════════════════════════════════════════════════════════
    path('diaria/abrir/',              views_caja_diaria.AbrirTurnoAjax.as_view(),          name='abrir_turno'),
    path('diaria/cerrar/',             views_caja_diaria.CerrarTurnoAjax.as_view(),         name='cerrar_turno'),
    path('diaria/estado/',             views_caja_diaria.EstadoCajaDiariaAjax.as_view(),    name='estado_caja_diaria'),
    path('diaria/historial-ajax/',     views_caja_diaria.HistorialTurnosAjax.as_view(),     name='historial_turnos_ajax'),
    path('diaria/eliminar-historial/', views_caja_diaria.EliminarHistorialAjax.as_view(),   name='eliminar_historial'),

    # ══════════════════════════════════════════════════════════════════
    #  AJAX — Transacciones
    # ══════════════════════════════════════════════════════════════════
    path('transacciones/calcular/',          views_transacciones.CalcularTransaccionAjax.as_view(), name='transacciones_calcular'),
    path('transacciones/crear/',             views_transacciones.CrearTransaccionAjax.as_view(),    name='transacciones_crear'),
    path('transacciones/listar/',            views_transacciones.ListarTransaccionesAjax.as_view(), name='transacciones_listar'),
    path('transacciones/<int:pk>/',          views_transacciones.DetalleTransaccionAjax.as_view(),  name='transacciones_detalle'),
    path('transacciones/<int:pk>/anular/',   views_transacciones.AnularTransaccionAjax.as_view(),   name='transacciones_anular'),
]