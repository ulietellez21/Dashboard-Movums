from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0013_cliente_monto_credito'),
        ('ventas', '0046_venta_edades_menores'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Cotizacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titulo', models.CharField(default='Cotización', max_length=200)),
                ('slug', models.SlugField(blank=True, max_length=255, unique=True)),
                ('origen', models.CharField(blank=True, max_length=150)),
                ('destino', models.CharField(blank=True, max_length=150)),
                ('dias', models.PositiveIntegerField(default=0)),
                ('noches', models.PositiveIntegerField(default=0)),
                ('fecha_inicio', models.DateField(blank=True, null=True)),
                ('fecha_fin', models.DateField(blank=True, null=True)),
                ('pasajeros', models.PositiveIntegerField(default=1)),
                ('adultos', models.PositiveIntegerField(default=1)),
                ('menores', models.PositiveIntegerField(default=0)),
                ('edades_menores', models.TextField(blank=True, help_text='Nombre y edad de los menores (ej. Juan - 5; Ana - 8)')),
                ('propuestas', models.JSONField(blank=True, default=dict)),
                ('notas', models.TextField(blank=True)),
                ('total_estimado', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('estado', models.CharField(choices=[('BORRADOR', 'Borrador'), ('ENVIADA', 'Enviada'), ('CONVERTIDA', 'Convertida a venta')], default='BORRADOR', max_length=20)),
                ('creada_en', models.DateTimeField(auto_now_add=True)),
                ('actualizada_en', models.DateTimeField(auto_now=True)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cotizaciones', to='crm.cliente')),
                ('vendedor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cotizaciones_creadas', to='auth.user')),
            ],
            options={
                'ordering': ['-creada_en'],
            },
        ),
        migrations.AddField(
            model_name='ventaviaje',
            name='cotizacion_origen',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ventas_generadas', to='ventas.cotizacion', verbose_name='Cotización origen'),
        ),
    ]



