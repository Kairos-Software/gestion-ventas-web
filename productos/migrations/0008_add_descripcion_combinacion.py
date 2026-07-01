# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0007_delete_productocolor_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='combinacionvariante',
            name='descripcion_combinacion',
            field=models.CharField(blank=True, help_text='Descripción libre de la combinación (usado temporalmente mientras no hay variantes definidas).', max_length=200, verbose_name='Descripción de combinación'),
        ),
    ]
