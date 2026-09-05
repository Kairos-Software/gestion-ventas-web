"""
Elimina la columna huérfana `tiles_destacados_titulo_bento` de
`catalogo_configuracioncatalogo`.

La agregó la migración 0021, pero después alguien borró a mano esa
operación del archivo (0021 quedó solo con el CreateModel de
BannerBentoCatalogo). Resultado: la columna sigue en la base como
NOT NULL sin default, pero ni el modelo ni el estado de migraciones
la conocen. Al recrear el singleton ConfiguracionCatalogo (pk=1) tras
un "Reiniciar datos", el INSERT de Django no le manda valor y Postgres
tira NotNullViolation.

El estado de migraciones ya está correcto (no tiene el campo), así que
esto solo alinea la base. `IF EXISTS` para que corra en cualquier base.
Irreversible (no hay nada que restaurar).
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0036_drop_orphan_tiledestacadobento'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'ALTER TABLE catalogo_configuracioncatalogo '
                'DROP COLUMN IF EXISTS tiles_destacados_titulo_bento;'
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
