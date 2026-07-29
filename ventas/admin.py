from django.contrib import admin
from .models import RecargoMedioPago, TarjetaPago


@admin.register(TarjetaPago)
class TarjetaPagoAdmin(admin.ModelAdmin):
    list_display  = ('nombre', 'acepta_debito', 'acepta_credito', 'acepta_qr', 'acepta_transferencia', 'activa', 'orden')
    list_filter   = ('activa',)
    ordering      = ('orden', 'nombre')


@admin.register(RecargoMedioPago)
class RecargoMedioPagoAdmin(admin.ModelAdmin):
    list_display  = ('tarjeta', 'medio', 'cantidad_pagos', 'nombre_plan', 'recargo_pct', 'activo', 'orden')
    list_filter   = ('medio', 'activo', 'tarjeta')
    ordering      = ('tarjeta', 'medio', 'cantidad_pagos')
