# Generated manually — renombra campos de Cheque para que "emisor",
# "receptor" y "banco" apliquen simétricamente a A_COBRAR y A_PAGAR,
# y agrega numero_factura. RenameField preserva los datos existentes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('caja', '0019_cuentacaja_acepta_credito_cuentacaja_acepta_debito_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='cheque',
            old_name='contraparte',
            new_name='receptor',
        ),
        migrations.RenameField(
            model_name='cheque',
            old_name='titular_librador',
            new_name='emisor',
        ),
        migrations.RenameField(
            model_name='cheque',
            old_name='banco_librador',
            new_name='banco',
        ),
        migrations.AddField(
            model_name='cheque',
            name='numero_factura',
            field=models.CharField(blank=True, max_length=30,
                help_text='N° de factura asociada al cheque, si corresponde.'),
        ),
        migrations.AlterField(
            model_name='cheque',
            name='banco',
            field=models.CharField(blank=True, max_length=100,
                help_text='Banco de la chequera. Informativo.'),
        ),
        migrations.AlterField(
            model_name='cheque',
            name='emisor',
            field=models.CharField(blank=True, max_length=150,
                help_text='Quién emite el cheque (A_PAGAR: nuestra empresa/firmante. A_COBRAR: quién lo entregó).'),
        ),
        migrations.AlterField(
            model_name='cheque',
            name='receptor',
            field=models.CharField(blank=True, max_length=150,
                help_text='Quién recibe el cheque (A_PAGAR: a quién se le paga. A_COBRAR: normalmente la propia empresa).'),
        ),
    ]
