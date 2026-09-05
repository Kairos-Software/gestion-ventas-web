"""
Elimina la tabla huérfana `catalogo_tiledestacadobentocatalogo`.

Es una versión vieja del modelo de tiles destacados (después renombrado
a TileDestacadoCatalogo). Quedó en la base sin modelo ni migración que
la maneje: no la referencia nada del código, pero su FK a
ConfiguracionCatalogo bloquea el borrado de esa tabla (rompía la
herramienta de "Reiniciar datos").

`IF EXISTS` para que corra sin problema en cualquier base, la tenga o no.
Irreversible a propósito (no hay nada que restaurar).
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0035_configuracioncatalogo_color_marca_editorial_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql='DROP TABLE IF EXISTS catalogo_tiledestacadobentocatalogo CASCADE;',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
