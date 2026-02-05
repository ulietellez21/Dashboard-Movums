# Generated manually: permitir múltiples filas TOU (Tour) por venta en Logística

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0065_apertura_confirmada_contador'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='logisticaservicio',
            unique_together=set(),
        ),
    ]
