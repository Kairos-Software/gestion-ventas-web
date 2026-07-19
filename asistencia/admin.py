from django.contrib import admin

from .models import HistorialNotificacion, PreferenciaAsistencia


@admin.register(PreferenciaAsistencia)
class PreferenciaAsistenciaAdmin(admin.ModelAdmin):
    list_display = ('canal', 'recibir_reporte_mensual', 'recibir_reporte_semanal')

    def has_add_permission(self, request):
        # Singleton: no se crean registros nuevos desde el admin.
        return not PreferenciaAsistencia.objects.exists()


@admin.register(HistorialNotificacion)
class HistorialNotificacionAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'referencia', 'destinatario', 'exito', 'enviado_el')
    list_filter = ('tipo', 'exito', 'canal')
    search_fields = ('destinatario', 'referencia', 'asunto')
    readonly_fields = [f.name for f in HistorialNotificacion._meta.fields]
