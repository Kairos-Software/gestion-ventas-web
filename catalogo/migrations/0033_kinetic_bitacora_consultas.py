from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0032_alter_configuracioncatalogo_plantilla'),
    ]

    operations = [
        migrations.CreateModel(
            name='EntradaBitacoraKineticCatalogo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(blank=True, max_length=20, verbose_name='Etiqueta')),
                ('titulo', models.CharField(max_length=100, verbose_name='Titulo')),
                ('texto', models.CharField(blank=True, max_length=280, verbose_name='Detalle (opcional)')),
                ('enlace_texto', models.CharField(blank=True, max_length=40, verbose_name='Texto del enlace (opcional)')),
                ('url', models.CharField(blank=True, max_length=300, verbose_name='Link (opcional)')),
                ('activo', models.BooleanField(default=True)),
                ('orden', models.PositiveIntegerField(default=0)),
                ('configuracion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bitacora_kinetic', to='catalogo.configuracioncatalogo')),
            ],
            options={
                'verbose_name': 'Entrada de bitacora (Kinetic)',
                'verbose_name_plural': 'Entradas de bitacora (Kinetic)',
                'ordering': ['orden', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ConsultaKineticCatalogo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('pregunta', models.CharField(max_length=140, verbose_name='Pregunta')),
                ('respuesta', models.TextField(max_length=700, verbose_name='Respuesta')),
                ('activo', models.BooleanField(default=True)),
                ('orden', models.PositiveIntegerField(default=0)),
                ('configuracion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='consultas_kinetic', to='catalogo.configuracioncatalogo')),
            ],
            options={
                'verbose_name': 'Consulta frecuente (Kinetic)',
                'verbose_name_plural': 'Consultas frecuentes (Kinetic)',
                'ordering': ['orden', 'id'],
            },
        ),
    ]
