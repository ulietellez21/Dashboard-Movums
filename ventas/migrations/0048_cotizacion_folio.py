from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0047_cotizacion_y_fk_venta'),
    ]

    operations = [
        migrations.AddField(
            model_name='cotizacion',
            name='folio',
            field=models.CharField(blank=True, help_text='Identificador único de la cotización. Formato: COT-AAAAMMDD-XX', max_length=20, null=True, unique=True, verbose_name='Folio de Cotización'),
        ),
    ]



