from django.contrib import admin

from .models import ConfiguracionCatalogo


@admin.register(ConfiguracionCatalogo)
class ConfiguracionCatalogoAdmin(admin.ModelAdmin):
    """
    Edición temporal por /admin de los textos del catálogo público
    (hero, sobre nosotros, contacto) hasta que exista la pantalla
    propia dentro de Configuración.
    """
    fieldsets = (
        (None, {'fields': ('plantilla',)}),
        ('Hero', {'fields': ('hero_titulo', 'hero_subtitulo', 'hero_imagen')}),
        ('Textos', {'fields': ('sobre_nosotros', 'contacto_texto')}),
    )

    def has_add_permission(self, request):
        return not ConfiguracionCatalogo.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
