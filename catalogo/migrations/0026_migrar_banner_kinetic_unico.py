"""
Pasa el banner único de Kinetic (kinetic_banner_imagen/_titulo/_texto/
_cta_texto/_cta_url, campos sueltos en ConfiguracionCatalogo) a una fila de
BannerKineticCatalogo — antes de que la migración siguiente borre esos
campos. Si el dueño ya tenía un banner cargado, no se pierde: queda como el
primer banner del rail nuevo.
"""
from django.db import migrations


def migrar_banner(apps, schema_editor):
    ConfiguracionCatalogo = apps.get_model('catalogo', 'ConfiguracionCatalogo')
    BannerKineticCatalogo = apps.get_model('catalogo', 'BannerKineticCatalogo')

    for config in ConfiguracionCatalogo.objects.all():
        tiene_imagen = bool(config.kinetic_banner_imagen)
        tiene_titulo = bool((config.kinetic_banner_titulo or '').strip())
        if not (tiene_imagen or tiene_titulo):
            continue
        BannerKineticCatalogo.objects.create(
            configuracion=config,
            imagen=config.kinetic_banner_imagen if tiene_imagen else None,
            titulo=config.kinetic_banner_titulo or '',
            texto=config.kinetic_banner_texto or '',
            cta_texto=config.kinetic_banner_cta_texto or '',
            cta_url=config.kinetic_banner_cta_url or '',
            activo=True,
            orden=0,
        )


def revertir(apps, schema_editor):
    """No hay vuelta atrás automática — el campo único ya no existe cuando se revierte esto en la práctica."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0025_bannerkineticcatalogo_and_more'),
    ]

    operations = [
        migrations.RunPython(migrar_banner, revertir),
    ]
