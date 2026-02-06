# Migración de datos: rellenar campos USD en ventas internacionales existentes

from decimal import Decimal
from django.db import migrations


def backfill_ventas_int_usd(apps, schema_editor):
    VentaViaje = apps.get_model('ventas', 'VentaViaje')
    AbonoPago = apps.get_model('ventas', 'AbonoPago')

    for venta in VentaViaje.objects.filter(tipo_viaje='INT'):
        tc = venta.tipo_cambio
        if not tc or tc <= 0:
            continue

        # Rellenar campos USD desde MXN usando tipo_cambio (referencia del día de la venta)
        if venta.cantidad_apertura and venta.cantidad_apertura_usd is None:
            venta.cantidad_apertura_usd = (venta.cantidad_apertura / tc).quantize(Decimal('0.01'))
        if venta.costo_venta_final and venta.costo_venta_final_usd is None:
            venta.costo_venta_final_usd = (venta.costo_venta_final / tc).quantize(Decimal('0.01'))
        if venta.costo_neto and venta.costo_neto_usd is None:
            venta.costo_neto_usd = (venta.costo_neto / tc).quantize(Decimal('0.01'))
        if venta.costo_modificacion is not None and venta.costo_modificacion_usd is None:
            venta.costo_modificacion_usd = (venta.costo_modificacion / tc).quantize(Decimal('0.01'))

        venta.save(update_fields=[
            'cantidad_apertura_usd', 'costo_venta_final_usd', 'costo_neto_usd', 'costo_modificacion_usd'
        ])

    # Abonos de ventas INT: asegurar monto_usd y tipo_cambio_aplicado (referencia del día del abono)
    for abono in AbonoPago.objects.select_related('venta').filter(venta__tipo_viaje='INT'):
        venta = abono.venta
        tc_abono = abono.tipo_cambio_aplicado or venta.tipo_cambio
        if not tc_abono or tc_abono <= 0:
            continue
        if abono.monto_usd is None and abono.monto:
            abono.monto_usd = (abono.monto / tc_abono).quantize(Decimal('0.01'))
        if abono.tipo_cambio_aplicado is None and venta.tipo_cambio:
            abono.tipo_cambio_aplicado = venta.tipo_cambio
        abono.save(update_fields=['monto_usd', 'tipo_cambio_aplicado'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0067_ventaviaje_campos_usd_int'),
    ]

    operations = [
        migrations.RunPython(backfill_ventas_int_usd, noop),
    ]
