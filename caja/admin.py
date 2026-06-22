from django.contrib import admin
from .models import CuentaCaja, ConceptoMovimiento, MovimientoCaja


@admin.register(CuentaCaja)
class CuentaCajaAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'caja', 'tipo', 'moneda', 'saldo', 'activa')
    list_filter   = ('caja', 'tipo', 'moneda', 'activa')
    search_fields = ('nombre',)
    ordering      = ('caja', 'orden', 'nombre')


@admin.register(ConceptoMovimiento)
class ConceptoMovimientoAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'tipo_default', 'es_sistema', 'activo', 'orden')
    list_filter   = ('tipo_default', 'es_sistema', 'activo')
    search_fields = ('nombre',)
    ordering      = ('orden', 'nombre')


@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(admin.ModelAdmin):
    list_display  = ('fecha', 'caja', 'cuenta', 'concepto', 'tipo', 'monto', 'moneda', 'origen', 'referencia')
    list_filter   = ('caja', 'tipo', 'origen', 'moneda', 'cuenta')
    search_fields = ('referencia', 'descripcion')
    date_hierarchy = 'fecha'
    ordering      = ('-fecha', '-fecha_alta')
    readonly_fields = ('fecha_alta', 'fecha_modificacion')

    def has_change_permission(self, request, obj=None):
        # Los movimientos automáticos no se editan desde el admin tampoco.
        if obj is not None and obj.es_automatico:
            return False
        return super().has_change_permission(request, obj)