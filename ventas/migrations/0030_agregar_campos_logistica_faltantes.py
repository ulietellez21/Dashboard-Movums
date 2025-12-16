# Generated manually on 2025-12-06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0029_logisticaservicio'),
    ]

    operations = [
        migrations.AddField(
            model_name='logistica',
            name='seguro_emitido',
            field=models.BooleanField(default=False, verbose_name='Seguro de Viaje Emitido'),
        ),
        migrations.AddField(
            model_name='logistica',
            name='documentos_enviados',
            field=models.BooleanField(default=False, verbose_name='Documentación Final Enviada al Cliente'),
        ),
    ]


