from django.db import migrations, models
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0027_ejecutivo_tipo_vendedor'),
        ('crm', '0004_cliente_cotizaciones_generadas'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='fecha_ultimo_bono_cumple',
            field=models.DateField(blank=True, null=True, verbose_name='Último bono de cumpleaños aplicado'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='kilometros_acumulados',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='Kilómetros acumulados históricos'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='kilometros_disponibles',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='Kilómetros disponibles'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='participa_kilometros',
            field=models.BooleanField(default=True, verbose_name='Participa en Kilómetros Movums'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='referencia_programa',
            field=models.CharField(blank=True, help_text='Código o nota interna para el programa de lealtad.', max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='cliente',
            name='referido_por',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='referidos', to='crm.cliente', verbose_name='Referido por'),
        ),
        migrations.AddField(
            model_name='cliente',
            name='ultima_fecha_km',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Última acumulación de kilómetros'),
        ),
        migrations.CreateModel(
            name='HistorialKilometros',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_evento', models.CharField(choices=[('COMPRA', 'Compra de servicios'), ('REFERIDO', 'Bonificación por referido'), ('CUMPLE', 'Bonificación por cumpleaños'), ('CAMPANIA', 'Campaña especial'), ('AJUSTE', 'Ajuste manual'), ('REDENCION', 'Redención aplicada'), ('EXPIRACION', 'Expiración de kilómetros')], max_length=12)),
                ('descripcion', models.CharField(blank=True, max_length=255, null=True)),
                ('kilometros', models.DecimalField(decimal_places=2, max_digits=12)),
                ('multiplicador', models.DecimalField(decimal_places=2, default=Decimal('1.00'), max_digits=6)),
                ('valor_equivalente', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12)),
                ('fecha_registro', models.DateTimeField(auto_now_add=True)),
                ('fecha_expiracion', models.DateTimeField(blank=True, null=True)),
                ('es_redencion', models.BooleanField(default=False)),
                ('cliente', models.ForeignKey(on_delete=models.CASCADE, related_name='historial_kilometros', to='crm.cliente')),
                ('venta', models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name='movimientos_kilometros', to='ventas.ventaviaje')),
            ],
            options={
                'ordering': ['-fecha_registro'],
            },
        ),
    ]

