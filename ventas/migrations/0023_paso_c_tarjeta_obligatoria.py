# Paso C de la migración a TarjetaPago (ver 0021 y 0022): ya con todos los
# datos migrados (todas las filas de RecargoMedioPago tienen tarjeta_id
# seteado), se vuelve `tarjeta` obligatorio y se borra el campo `cuenta`
# viejo. Escrita a mano porque `makemigrations` pide confirmación
# interactiva para el "not null" que no se puede dar en un shell no
# interactivo (los datos ya están backfilleados por la migración 0022).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0022_paso_b_migrar_datos_a_tarjetapago'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recargomediopago',
            name='tarjeta',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recargos', to='ventas.tarjetapago'),
        ),
        migrations.RemoveField(
            model_name='recargomediopago',
            name='cuenta',
        ),
    ]
