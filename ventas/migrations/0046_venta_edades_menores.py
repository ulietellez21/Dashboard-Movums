from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0045_alter_ventaviaje_modo_pago_apertura'),
    ]

    operations = [
        migrations.AddField(
            model_name='ventaviaje',
            name='edades_menores',
            field=models.TextField(blank=True, help_text='Lista de edades de los menores que viajan (ej. 5, 8, 12).', verbose_name='Edades de los menores'),
        ),
    ]

