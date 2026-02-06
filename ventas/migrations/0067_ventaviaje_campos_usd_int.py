# Migración: campos en USD para ventas internacionales (fuente de verdad)

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0066_allow_multiple_tou_logisticaservicio'),
    ]

    operations = [
        migrations.AddField(
            model_name='ventaviaje',
            name='cantidad_apertura_usd',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Para ventas internacionales: monto de apertura en dólares.',
                max_digits=12,
                null=True,
                verbose_name='Cantidad de Apertura/Anticipo (USD)',
            ),
        ),
        migrations.AddField(
            model_name='ventaviaje',
            name='costo_venta_final_usd',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Para ventas internacionales: precio total que paga el cliente en dólares.',
                max_digits=12,
                null=True,
                verbose_name='Precio total (USD)',
            ),
        ),
        migrations.AddField(
            model_name='ventaviaje',
            name='costo_neto_usd',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Para ventas internacionales: costo real del viaje en dólares.',
                max_digits=12,
                null=True,
                verbose_name='Costo neto (USD)',
            ),
        ),
        migrations.AddField(
            model_name='ventaviaje',
            name='costo_modificacion_usd',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Para ventas internacionales: costo de modificación en dólares.',
                max_digits=12,
                null=True,
                verbose_name='Costo de modificación (USD)',
            ),
        ),
        migrations.AlterField(
            model_name='ventaviaje',
            name='tipo_cambio',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                default=Decimal('0.0000'),
                help_text='Tipo de cambio del día (solo referencia; ventas internacionales se manejan en USD sin conversión automática).',
                max_digits=10,
                null=True,
                verbose_name='Tipo de Cambio (referencia)',
            ),
        ),
    ]
