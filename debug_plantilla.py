
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agencia.settings')
django.setup()

from ventas.models import PlantillaConfirmacion

def inspect_latest_plantilla():
    # Get the latest VUELO_REDONDO template
    plantilla = PlantillaConfirmacion.objects.filter(tipo='VUELO_REDONDO').order_by('-fecha_creacion').first()
    
    if not plantilla:
        print("No VUELO_REDONDO template found.")
        return

    print(f"Plantilla ID: {plantilla.pk}")
    print(f"Tipo: {plantilla.tipo}")
    print(f"Venta ID: {plantilla.venta_id}")
    
    datos = plantilla.datos
    
    print("\n--- DATOS RAW ---")
    print(json.dumps(datos, indent=2, ensure_ascii=False))
    
    print("\n--- ANALYSIS ---")
    tipo_ida = datos.get('tipo_vuelo_ida')
    escalas_ida = datos.get('escalas_ida')
    
    print(f"tipo_vuelo_ida: '{tipo_ida}'")
    
    if escalas_ida is None:
        print("escalas_ida is None")
    elif isinstance(escalas_ida, list):
        print(f"escalas_ida is List with {len(escalas_ida)} items")
    else:
        print(f"escalas_ida is type {type(escalas_ida)}")

    # Check for consistency
    if tipo_ida == 'Escalas' and (not escalas_ida or len(escalas_ida) == 0):
        print("ALERT: tipo_vuelo_ida is 'Escalas' but escalas_ida is empty!")
    
    if tipo_ida != 'Escalas' and escalas_ida and len(escalas_ida) > 0:
        print("INFO: escalas_ida has data, but tipo_vuelo_ida is NOT 'Escalas'. This is why strict check failed.")

if __name__ == '__main__':
    inspect_latest_plantilla()
