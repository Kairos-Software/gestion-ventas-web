from django.contrib import admin

from .models import ConfiguracionCatalogo, ImagenInstitucional, SlideHeroCatalogo


class SlideHeroCatalogoInline(admin.TabularInline):
    model = SlideHeroCatalogo
    extra = 0
    fields = ('orden', 'imagen', 'eyebrow', 'titulo', 'descripcion', 'cta_texto')


class ImagenInstitucionalInline(admin.TabularInline):
    model = ImagenInstitucional
    extra = 0
    fields = ('orden', 'imagen', 'titulo')


@admin.register(ConfiguracionCatalogo)
class ConfiguracionCatalogoAdmin(admin.ModelAdmin):
    """
    Respaldo/inspección por /admin — la vía principal de edición es
    Configuración → Catálogo online (ver core/views.py:catalogo_online).
    """
    fieldsets = (
        (None, {'fields': ('plantilla', 'color_marca')}),
        ('Hero (plantilla "Almacén")', {'fields': ('hero_titulo', 'hero_subtitulo', 'hero_imagen')}),
        ('Menú', {'fields': ('nav_catalogo_label', 'nav_ofertas_label', 'nav_combos_label', 'nav_tienda_label')}),
        ('Página institucional — "La tienda"', {'fields': (
            'institucional_titulo', 'institucional_bajada', 'institucional_imagen',
            'destacado1_titulo', 'destacado1_texto',
            'destacado2_titulo', 'destacado2_texto',
            'destacado3_titulo', 'destacado3_texto',
            'horarios_texto', 'instagram_url', 'facebook_url', 'tiktok_url',
        )}),
        ('Textos', {'fields': ('sobre_nosotros', 'contacto_texto')}),
    )
    inlines = [SlideHeroCatalogoInline, ImagenInstitucionalInline]

    def has_add_permission(self, request):
        return not ConfiguracionCatalogo.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
