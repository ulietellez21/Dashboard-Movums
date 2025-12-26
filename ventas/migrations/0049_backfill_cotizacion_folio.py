from django.db import migrations
from django.utils import timezone


def backfill_folio(apps, schema_editor):
    Cotizacion = apps.get_model('ventas', 'Cotizacion')
    today = timezone.localdate()
    for cot in Cotizacion.objects.filter(folio__isnull=True).order_by('creada_en'):
        fecha = cot.creada_en.date() if cot.creada_en else today
        fecha_str = fecha.strftime('%Y%m%d')
        consecutivo = Cotizacion.objects.filter(creada_en__date=fecha).exclude(folio__isnull=True).exclude(folio='').count() + 1
        folio = f"COT-{fecha_str}-{consecutivo:02d}"
        while Cotizacion.objects.filter(folio=folio).exclude(pk=cot.pk).exists():
            consecutivo += 1
            folio = f"COT-{fecha_str}-{consecutivo:02d}"
        cot.folio = folio
        cot.save(update_fields=['folio'])


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0048_cotizacion_folio'),
    ]

    operations = [
        migrations.RunPython(backfill_folio, migrations.RunPython.noop),
    ]

