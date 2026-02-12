
import os
import django
import sys

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agencia_web.settings')
django.setup()

from ventas.models import VentaViaje

# Get the most recent sales to debug
print("--- Debugging Recent Sales ---")
ventas = VentaViaje.objects.all().order_by('-pk')[:5]

for venta in ventas:
    print(f"ID: {venta.pk} - Cliente: {venta.cliente}")
    print(f"  Tipo Viaje: '{venta.tipo_viaje}'")
    print(f"  Servicios Seleccionados (Raw): '{venta.servicios_seleccionados}'")
    print(f"  Servicios Seleccionados (Display): '{venta.servicios_seleccionados_display}'")
    print(f"  Is 'PAQ' in servicios? {'PAQ' in (venta.servicios_seleccionados or '')}")
    print(f"  Cotizacion Origen ID: {venta.cotizacion_origen.pk if venta.cotizacion_origen else 'None'}")
    if venta.cotizacion_origen:
        print(f"    Cotizacion Propuestas (Preview): {str(venta.cotizacion_origen.propuestas)[:100]}")
    print("-" * 30)
