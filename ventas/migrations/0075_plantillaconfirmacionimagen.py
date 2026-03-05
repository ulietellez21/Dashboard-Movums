from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0074_cotizacionimagen_generica'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlantillaConfirmacionImagen',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(upload_to='confirmaciones/generica/%Y/%m/%d/', verbose_name='Imagen para plantilla genérica')),
                ('orden', models.PositiveIntegerField(default=0)),
                ('descripcion', models.CharField(blank=True, max_length=255)),
                ('plantilla', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='imagenes_generica', to='ventas.plantillaconfirmacion', verbose_name='Plantilla de Confirmación')),
            ],
            options={
                'verbose_name': 'Imagen de plantilla confirmación genérica',
                'verbose_name_plural': 'Imágenes de plantilla confirmación genérica',
                'ordering': ['orden', 'pk'],
            },
        ),
    ]
