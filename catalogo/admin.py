from django.contrib import admin

from .models import ConfiguracionCatalogo, SlideHeroCatalogo


class SlideHeroCatalogoInline(admin.TabularInline):
    model = SlideHeroCatalogo
    extra = 0
    fields = ('orden', 'imagen', 'eyebrow', 'titulo', 'descripcion', 'cta_texto')


@admin.register(ConfiguracionCatalogo)
class ConfiguracionCatalogoAdmin(admin.ModelAdmin):
    """
    Respaldo/inspección por /admin — la vía principal de edición es
    Configuración → Catálogo público (ver core/views.py:configuracion).
    """
    fieldsets = (
        (None, {'fields': ('plantilla',)}),
        ('Hero (plantilla "Almacén")', {'fields': ('hero_titulo', 'hero_subtitulo', 'hero_imagen')}),
        ('Textos', {'fields': ('sobre_nosotros', 'contacto_texto')}),
    )
    inlines = [SlideHeroCatalogoInline]

    def has_add_permission(self, request):
        return not ConfiguracionCatalogo.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
