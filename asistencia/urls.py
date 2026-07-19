from django.urls import path

from . import views

app_name = 'asistencia'

urlpatterns = [
    path('preferencias/guardar/', views.PreferenciaAsistenciaGuardarAjax.as_view(), name='preferencias_guardar'),
]
