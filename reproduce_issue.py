
import re
import json

def process_post(post_data, tipo_plantilla):
    datos = {}
    escalas = []
    
    # Logic copied from CrearPlantillaConfirmacionView.post
    
    # 1. First loop: simple fields
    for key, value in post_data.items():
        if key.startswith('escalas[') and not key.startswith('escalas_ida[') and not key.startswith('escalas_regreso['):
            continue
        elif key.startswith('escalas_ida[') or key.startswith('escalas_regreso[') or key.startswith('traslados['):
            continue
        elif key not in ['csrfmiddlewaretoken']:
            datos[key] = value

    # 2. Process scales for VUELO_REDONDO
    if tipo_plantilla == 'VUELO_REDONDO':
        # Escalas de Ida
        escalas_ida_dict = {}
        for key, value in post_data.items():
            if key.startswith('escalas_ida['):
                match = re.match(r'escalas_ida\[(\d+)\]\[(\w+)\]', key)
                if match:
                    idx = int(match.group(1))
                    campo = match.group(2)
                    if idx not in escalas_ida_dict:
                        escalas_ida_dict[idx] = {}
                    escalas_ida_dict[idx][campo] = value
        
        if escalas_ida_dict:
            escalas_ida = []
            for i in sorted(escalas_ida_dict.keys()):
                escalas_ida.append(escalas_ida_dict[i])
            datos['escalas_ida'] = escalas_ida
        else:
            datos['escalas_ida'] = []
            
        print(f"Processed escalas_ida: {len(datos['escalas_ida'])}")
        
        # Escalas de Regreso
        escalas_regreso_dict = {}
        for key, value in post_data.items():
            if key.startswith('escalas_regreso['):
                match = re.match(r'escalas_regreso\[(\d+)\]\[(\w+)\]', key)
                if match:
                    idx = int(match.group(1))
                    campo = match.group(2)
                    if idx not in escalas_regreso_dict:
                        escalas_regreso_dict[idx] = {}
                    escalas_regreso_dict[idx][campo] = value
        
        if escalas_regreso_dict:
            escalas_regreso = []
            for i in sorted(escalas_regreso_dict.keys()):
                escalas_regreso.append(escalas_regreso_dict[i])
            datos['escalas_regreso'] = escalas_regreso
        else:
            datos['escalas_regreso'] = []

    return datos

# Mock POST data
mock_post = {
    'tipo_vuelo_ida': 'Escalas',
    'aerolinea_ida': 'Test Airline',
    'escalas_ida[0][ciudad]': 'City1',
    'escalas_ida[0][aeropuerto]': 'Airport1',
    'escalas_ida[0][hora_llegada]': '10:00',
    'escalas_ida[1][ciudad]': 'City2',
    'escalas_ida[1][aeropuerto]': 'Airport2',
    'csrfmiddlewaretoken': 'token',
    # Valid field but starting with escala...
    'escalador': 'Should be kept' 
}

result = process_post(mock_post, 'VUELO_REDONDO')
print(json.dumps(result, indent=2))

# Verify logic for generating docx
if result.get('tipo_vuelo_ida') == 'Escalas' and result.get('escalas_ida'):
    print("Condition met: Scales would be printed.")
else:
    print("Condition FAILED: Scales would NOT be printed.")
