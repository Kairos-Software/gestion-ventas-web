# Data migration: desactiva los lotes que quedaron huérfanos (producto=None)
# de productos borrados antes de que Producto.delete() los desactivara solo.
# Un LoteCompra sin producto solo puede venir de un SET_NULL al borrar el
# producto — nunca es un estado válido de un lote "vivo".

from django.db import migrations


def desactivar_lotes_huerfanos(apps, schema_editor):
    LoteCompra = apps.get_model('compras', 'LoteCompra')
    LoteCompra.objects.filter(producto__isnull=True, activo=True).update(activo=False)


class Migration(migrations.Migration):

    dependencies = [
        ('compras', '0020_compra_alicuota_iva_compra_iva_incluido_and_more'),
    ]

    operations = [
        migrations.RunPython(desactivar_lotes_huerfanos, migrations.RunPython.noop),
    ]
