# Generated for the "cuenta corriente" mode flag (fase 1 — infra, sin cambio de comportamiento).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_cliente_foto_pagare_cliente_numero_pagare_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuracionventas',
            name='modo_cobranza',
            field=models.CharField(
                choices=[
                    ('individual', 'Deudas individuales (cuotas por venta)'),
                    ('cuenta_corriente', 'Cuenta corriente (un saldo por cliente)'),
                ],
                default='individual',
                help_text=(
                    'Individual (por defecto): cada venta financiada es una deuda '
                    'aparte con su plan de cuotas. Cuenta corriente: el cliente '
                    'tiene un solo saldo que sube y baja, y el cobro se imputa a '
                    'las deudas más viejas primero. No reescribe ninguna venta '
                    'existente — solo cambia cómo se ve y se cobra.'
                ),
                max_length=20,
                verbose_name='Modo de cobranza',
            ),
        ),
    ]
