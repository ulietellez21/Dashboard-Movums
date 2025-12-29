import os
import django
import json
from decimal import Decimal

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agencia.settings')
django.setup()

from ventas.models import Cotizacion

def debug_last_cotizacion():
    # Obtener la última cotización creada
    cot = Cotizacion.objects.last()
    if not cot:
        print("No hay cotizaciones.")
        return

    print(f"--- DEBUG COTIZACION: {cot.slug} ---")
    print(f"Tipo: {cot.propuestas.get('tipo', 'Desconocido')}")
    
    propuestas = cot.propuestas
    vuelos = propuestas.get('vuelos', [])
    
    print(f"\n--- ESTRUCTURA DE VUELOS (Tipo: {type(vuelos)}) ---")
    if isinstance(vuelos, list):
        print(f"Es una LISTA con {len(vuelos)} elementos.")
        for i, v in enumerate(vuelos):
            print(f"  Índice [{i}]: Total={v.get('total', 'NO TIENE TOTAL')}")
    elif isinstance(vuelos, dict):
        print(f"Es un DICCIONARIO con claves: {list(vuelos.keys())}")
        for k, v in vuelos.items():
            print(f"  Clave '{k}': Total={v.get('total', 'NO TIENE TOTAL')}")
    else:
        print("Ni lista ni diccionario:", vuelos)

    # Simular la lógica de extracción para índice 2
    indice_buscado = 2
    print(f"\n--- SIMULACIÓN DE EXTRACCIÓN (Índice {indice_buscado}) ---")
    
    vuelo_seleccionado = {}
    if isinstance(vuelos, list):
        if 0 <= indice_buscado < len(vuelos):
            vuelo_seleccionado = vuelos[indice_buscado]
            print(f"Logró extraer por lista: {vuelo_seleccionado.get('total')}")
        else:
            print("FALLÓ: Índice fuera de rango en lista.")
    else:
        # Intentar claves probables
        keys_to_try = [str(indice_buscado), f'propuesta_{indice_buscado+1}', f'propuesta_{indice_buscado}']
        print(f"Probando claves diccionario: {keys_to_try}")
        for k in keys_to_try:
            if k in vuelos:
                vuelo_seleccionado = vuelos[k]
                print(f"Logró extraer con clave '{k}': {vuelo_seleccionado.get('total')}")
                break
        if not vuelo_seleccionado:
            print("FALLÓ: No encontró ninguna clave compatible.")

if __name__ == '__main__':
    debug_last_cotizacion()
