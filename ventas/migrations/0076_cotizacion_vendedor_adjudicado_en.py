from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0075_plantillaconfirmacionimagen'),
    ]

    operations = [
        migrations.AddField(
            model_name='cotizacion',
            name='vendedor_adjudicado_en',
            field=models.DateTimeField(
                blank=True,
                help_text='Fecha/hora en que se adjudicó por primera vez a un vendedor. Pasado 1 día o tras esta adjudicación, solo un director puede cambiar el vendedor.',
                null=True,
                verbose_name='Adjudicada a vendedor en'
            ),
        ),
    ]
