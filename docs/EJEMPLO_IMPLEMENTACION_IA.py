"""
Ejemplo de implementación básica para extracción de datos con IA.
Este es un prototipo funcional que puedes adaptar a tu proyecto.
"""

import os
import json
import base64
from decimal import Decimal
from datetime import datetime
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

# Instalar: pip install openai
try:
    import openai
except ImportError:
    openai = None


class ExtractorDatosIA:
    """
    Clase para extraer datos estructurados de imágenes usando OpenAI Vision API.
    """
    
    def __init__(self, api_key=None):
        """
        Inicializa el extractor con la API key de OpenAI.
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if openai:
            openai.api_key = self.api_key
    
    def extraer_de_vuelo(self, imagen_path):
        """
        Extrae datos específicos de una captura de vuelo.
        """
        prompt = """Analiza esta captura de pantalla de una reserva de vuelo y extrae la siguiente información en formato JSON válido:

{
    "fecha_ida": "YYYY-MM-DD",
    "fecha_regreso": "YYYY-MM-DD o null",
    "aerolinea": "nombre de la aerolínea",
    "numero_vuelo_ida": "número o null",
    "numero_vuelo_regreso": "número o null",
    "origen": "ciudad de origen",
    "destino": "ciudad de destino",
    "pasajeros": ["Nombre Completo 1", "Nombre Completo 2"],
    "costo_total": 0.00,
    "servicios_incluidos": ["Vuelo"],
    "hora_salida_ida": "HH:MM o null",
    "hora_llegada_ida": "HH:MM o null",
    "hora_salida_regreso": "HH:MM o null",
    "hora_llegada_regreso": "HH:MM o null",
    "clase": "Económica, Ejecutiva, Primera o null"
}

IMPORTANTE:
- Las fechas deben estar en formato YYYY-MM-DD
- Los costos deben ser números decimales (sin símbolo de moneda)
- Si algún campo no está disponible, usa null
- Devuelve SOLO el JSON, sin explicaciones adicionales"""

        return self._extraer_datos(imagen_path, prompt)
    
    def extraer_de_hotel(self, imagen_path):
        """
        Extrae datos específicos de una captura de reserva de hotel.
        """
        prompt = """Analiza esta captura de pantalla de una reserva de hotel y extrae la siguiente información en formato JSON válido:

{
    "fecha_checkin": "YYYY-MM-DD",
    "fecha_checkout": "YYYY-MM-DD",
    "nombre_hotel": "nombre del hotel",
    "ubicacion_hotel": "ciudad, país",
    "pasajeros": ["Nombre Completo 1", "Nombre Completo 2"],
    "numero_habitaciones": 1,
    "tipo_habitacion": "tipo o null",
    "costo_total": 0.00,
    "servicios_incluidos": ["Hospedaje"],
    "numero_reserva": "número de reserva o null",
    "incluye_desayuno": true/false/null,
    "politica_cancelacion": "texto o null"
}

IMPORTANTE:
- Las fechas deben estar en formato YYYY-MM-DD
- Los costos deben ser números decimales (sin símbolo de moneda)
- Si algún campo no está disponible, usa null
- Devuelve SOLO el JSON, sin explicaciones adicionales"""

        return self._extraer_datos(imagen_path, prompt)
    
    def extraer_generico(self, imagen_path):
        """
        Extrae datos genéricos de cualquier captura de vuelo/hotel.
        """
        prompt = """Analiza esta captura de pantalla (puede ser vuelo, hotel o ambos) y extrae toda la información relevante en formato JSON válido:

{
    "tipo_servicio": "Vuelo, Hotel, o Paquete",
    "fecha_ida": "YYYY-MM-DD o null",
    "fecha_regreso": "YYYY-MM-DD o null",
    "fecha_checkin": "YYYY-MM-DD o null",
    "fecha_checkout": "YYYY-MM-DD o null",
    "aerolinea": "nombre o null",
    "nombre_hotel": "nombre o null",
    "origen": "ciudad o null",
    "destino": "ciudad o null",
    "pasajeros": ["Nombre 1", "Nombre 2"],
    "costo_total": 0.00,
    "servicios_incluidos": ["Vuelo", "Hospedaje"],
    "detalles_adicionales": "texto descriptivo o null"
}

IMPORTANTE:
- Las fechas deben estar en formato YYYY-MM-DD
- Los costos deben ser números decimales (sin símbolo de moneda)
- Si algún campo no está disponible, usa null
- Devuelve SOLO el JSON, sin explicaciones adicionales"""

        return self._extraer_datos(imagen_path, prompt)
    
    def _extraer_datos(self, imagen_path, prompt):
        """
        Método interno que realiza la llamada a OpenAI Vision API.
        """
        if not openai:
            return {"error": "OpenAI no está instalado. Ejecuta: pip install openai"}
        
        if not self.api_key:
            return {"error": "OPENAI_API_KEY no está configurada"}
        
        try:
            # Leer y codificar la imagen
            with open(imagen_path, "rb") as imagen_file:
                imagen_base64 = base64.b64encode(imagen_file.read()).decode('utf-8')
            
            # Llamar a OpenAI Vision API
            response = openai.ChatCompletion.create(
                model="gpt-4-vision-preview",  # o "gpt-4o" para mejor rendimiento
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{imagen_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1  # Baja temperatura para respuestas más consistentes
            )
            
            # Extraer el texto de la respuesta
            texto_respuesta = response.choices[0].message.content.strip()
            
            # Limpiar el texto (remover markdown code blocks si existen)
            if texto_respuesta.startswith("```json"):
                texto_respuesta = texto_respuesta[7:]
            if texto_respuesta.startswith("```"):
                texto_respuesta = texto_respuesta[3:]
            if texto_respuesta.endswith("```"):
                texto_respuesta = texto_respuesta[:-3]
            texto_respuesta = texto_respuesta.strip()
            
            # Parsear JSON
            datos = json.loads(texto_respuesta)
            
            return {"success": True, "datos": datos}
            
        except json.JSONDecodeError as e:
            return {"error": f"Error al parsear JSON: {str(e)}", "respuesta_cruda": texto_respuesta}
        except Exception as e:
            return {"error": f"Error al procesar imagen: {str(e)}"}


def mapear_a_formulario_venta(datos_extraidos):
    """
    Mapea los datos extraídos por IA a los campos del formulario VentaViajeForm.
    
    Args:
        datos_extraidos: Diccionario con los datos extraídos por IA
        
    Returns:
        Diccionario con los campos del formulario pre-llenados
    """
    campos_formulario = {}
    
    # Fechas
    if datos_extraidos.get('fecha_ida'):
        campos_formulario['fecha_inicio_viaje'] = datos_extraidos['fecha_ida']
    
    # Fecha de regreso puede venir de diferentes campos
    fecha_regreso = (
        datos_extraidos.get('fecha_regreso') or 
        datos_extraidos.get('fecha_checkout')
    )
    if fecha_regreso:
        campos_formulario['fecha_fin_viaje'] = fecha_regreso
    
    # Pasajeros
    if datos_extraidos.get('pasajeros'):
        campos_formulario['pasajeros'] = '\n'.join(datos_extraidos['pasajeros'])
    
    # Servicios seleccionados
    servicios = datos_extraidos.get('servicios_incluidos', [])
    servicios_codigos = []
    for servicio in servicios:
        # Mapear nombres a códigos del modelo
        mapeo = {
            'Vuelo': 'VUE',
            'Hospedaje': 'HOS',
            'Hotel': 'HOS',
            'Tour': 'TOU',
            'Traslado': 'TRA',
            'Seguro': 'SEG',
        }
        if servicio in mapeo:
            servicios_codigos.append(mapeo[servicio])
    
    if servicios_codigos:
        campos_formulario['servicios_seleccionados'] = servicios_codigos
    
    # Costo total
    if datos_extraidos.get('costo_total'):
        campos_formulario['costo_venta_final'] = Decimal(str(datos_extraidos['costo_total']))
        campos_formulario['costo_neto'] = Decimal(str(datos_extraidos['costo_total']))  # Ajustar según lógica de negocio
    
    # Servicios detalle (texto descriptivo)
    detalles = []
    if datos_extraidos.get('aerolinea'):
        detalles.append(f"Aerolínea: {datos_extraidos['aerolinea']}")
    if datos_extraidos.get('nombre_hotel'):
        detalles.append(f"Hotel: {datos_extraidos['nombre_hotel']}")
    if datos_extraidos.get('origen') and datos_extraidos.get('destino'):
        detalles.append(f"Ruta: {datos_extraidos['origen']} → {datos_extraidos['destino']}")
    if datos_extraidos.get('numero_vuelo_ida'):
        detalles.append(f"Vuelo ida: {datos_extraidos['numero_vuelo_ida']}")
    if datos_extraidos.get('numero_vuelo_regreso'):
        detalles.append(f"Vuelo regreso: {datos_extraidos['numero_vuelo_regreso']}")
    
    if detalles:
        campos_formulario['servicios_detalle'] = '\n'.join(detalles)
    
    # Determinar tipo de viaje (simple heurística)
    if datos_extraidos.get('destino') and datos_extraidos.get('origen'):
        # Aquí podrías mejorar la lógica con una base de datos de ciudades
        campos_formulario['tipo_viaje'] = 'NAC'  # Por defecto nacional
    
    return campos_formulario


# ==========================================
# VISTA DJANGO PARA INTEGRAR EN EL PROYECTO
# ==========================================

@require_http_methods(["POST"])
def extraer_datos_ia(request):
    """
    Vista AJAX para procesar una imagen y extraer datos.
    
    Espera un archivo en request.FILES['imagen']
    Opcionalmente, puede recibir 'tipo': 'vuelo', 'hotel', o 'generico'
    
    Returns JSON con los datos extraídos o error.
    """
    if 'imagen' not in request.FILES:
        return JsonResponse({"error": "No se recibió ninguna imagen"}, status=400)
    
    imagen = request.FILES['imagen']
    tipo_extraccion = request.POST.get('tipo', 'generico')  # 'vuelo', 'hotel', o 'generico'
    
    # Guardar imagen temporalmente
    ruta_temporal = default_storage.save(
        f'temp_extracciones/{imagen.name}',
        ContentFile(imagen.read())
    )
    ruta_completa = default_storage.path(ruta_temporal)
    
    try:
        # Inicializar extractor
        extractor = ExtractorDatosIA()
        
        # Extraer datos según el tipo
        if tipo_extraccion == 'vuelo':
            resultado = extractor.extraer_de_vuelo(ruta_completa)
        elif tipo_extraccion == 'hotel':
            resultado = extractor.extraer_de_hotel(ruta_completa)
        else:
            resultado = extractor.extraer_generico(ruta_completa)
        
        if 'error' in resultado:
            return JsonResponse(resultado, status=500)
        
        # Mapear a campos del formulario
        datos_formulario = mapear_a_formulario_venta(resultado['datos'])
        
        # Limpiar archivo temporal
        default_storage.delete(ruta_temporal)
        
        return JsonResponse({
            "success": True,
            "datos_originales": resultado['datos'],
            "datos_formulario": datos_formulario
        })
        
    except Exception as e:
        # Limpiar archivo temporal en caso de error
        if default_storage.exists(ruta_temporal):
            default_storage.delete(ruta_temporal)
        
        return JsonResponse({
            "error": f"Error al procesar: {str(e)}"
        }, status=500)








