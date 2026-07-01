from django.contrib import admin
from .models import Compra, ItemCompra, LoteCompra, CompraDocumento


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ['numero', 'fecha', 'estado', 'total', 'fecha_alta']
    list_filter = ['estado', 'fecha']
    search_fields = ['numero', 'notas']
    readonly_fields = ['numero', 'fecha_alta', 'fecha_modificacion']
    date_hierarchy = 'fecha'


@admin.register(ItemCompra)
class ItemCompraAdmin(admin.ModelAdmin):
    list_display = ['get_producto_nombre', 'cantidad', 'costo_unitario', 'subtotal', 'fecha_vencimiento']
    list_filter = ['fecha_vencimiento', 'moneda', 'condicion_pago']
    search_fields = ['producto_nombre', 'producto_codigo', 'proveedor_nombre']
    readonly_fields = ['producto_nombre', 'producto_codigo', 'proveedor_nombre', 'combinacion_descripcion']

    def get_producto_nombre(self, obj):
        return obj.producto_nombre_display
    get_producto_nombre.short_description = 'Producto'


@admin.register(LoteCompra)
class LoteCompraAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'producto', 'cantidad_actual', 'cantidad_inicial', 'porcentaje_restante', 'fecha_vencimiento', 'fecha_compra', 'activo']
    list_filter = ['activo', 'fecha_vencimiento', 'fecha_compra']
    search_fields = ['codigo', 'producto__nombre', 'producto__codigo']
    readonly_fields = ['codigo', 'fecha_alta', 'fecha_modificacion', 'porcentaje_restante']
    date_hierarchy = 'fecha_compra'

    fieldsets = (
        ('Identificación', {
            'fields': ('codigo', 'item_compra', 'producto', 'combinacion')
        }),
        ('Datos del lote', {
            'fields': ('cantidad_inicial', 'cantidad_actual', 'costo_unitario', 'porcentaje_restante')
        }),
        ('Fechas', {
            'fields': ('fecha_vencimiento', 'fecha_compra')
        }),
        ('Estado', {
            'fields': ('activo',)
        }),
        ('Auditoría', {
            'fields': ('fecha_alta', 'fecha_modificacion'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CompraDocumento)
class CompraDocumentoAdmin(admin.ModelAdmin):
    list_display = ['compra', 'tipo', 'descripcion', 'subido_el', 'subido_por']
    list_filter = ['tipo', 'subido_el']
    search_fields = ['compra__numero', 'descripcion']
