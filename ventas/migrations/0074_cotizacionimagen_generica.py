from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0073_add_int_mxn_comision_tipo_venta'),
    ]

    operations = [
        migrations.CreateModel(
            name='CotizacionImagen',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imagen', models.ImageField(upload_to='cotizaciones/generica/%Y/%m/%d/', verbose_name='Imagen para plantilla genérica')),
                ('orden', models.PositiveIntegerField(default=0)),
                ('descripcion', models.CharField(blank=True, max_length=255)),
                ('cotizacion', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='imagenes_generica', to='ventas.cotizacion', verbose_name='Cotización')),
            ],
            options={
                'verbose_name': 'Imagen de cotización genérica',
                'verbose_name_plural': 'Imágenes de cotización genérica',
                'ordering': ['orden', 'pk'],
            },
        ),
    ]

