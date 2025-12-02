# Asesoría: Extracción de Datos con IA desde Capturas de Vuelos y Hoteles

## 📋 Resumen del Proyecto

El objetivo es implementar una funcionalidad que permita extraer automáticamente información estructurada desde capturas de pantalla de páginas de vuelos y hoteles, y pre-llenar el formulario de venta (`VentaViajeForm`) con esos datos.

---

## 🎯 Datos a Extraer del Formulario Actual

Basado en el análisis del código, estos son los campos que necesitamos extraer:

### **Información Principal:**
- **Cliente** (debe seleccionarse manualmente o del sistema)
- **Pasajeros** (nombres completos)
- **Tipo de Viaje** (Nacional/Internacional)
- **Fechas:**
  - Fecha de Inicio (Ida)
  - Fecha de Fin (Regreso)
  - Fecha de Vencimiento de Pago

### **Servicios:**
- **Servicios Seleccionados** (Vuelo, Hospedaje, Tour, etc.)
- **Proveedores por Servicio:**
  - Proveedor de Vuelo (Volaris, Aeroméxico, etc.)
  - Proveedor de Hospedaje (Hotel específico)
  - Otros proveedores según servicios

### **Información Financiera:**
- **Costo Neto**
- **Costo de Venta Final**
- **Cantidad de Apertura**
- **Modo de Pago de Apertura** (Efectivo, Transferencia, Tarjeta)

### **Detalles Adicionales:**
- **Servicios Detalle** (descripción detallada del viaje)

---

## 🛠️ Opciones Tecnológicas

### **Opción 1: OpenAI GPT-4 Vision API** ⭐ (RECOMENDADA)

**Ventajas:**
- ✅ Excelente para extraer datos estructurados desde imágenes
- ✅ Puede entender contexto y patrones complejos
- ✅ Devuelve datos en formato JSON estructurado
- ✅ No requiere entrenamiento previo
- ✅ Maneja diferentes layouts y formatos de páginas web

**Desventajas:**
- ❌ Tiene costo por imagen procesada (~$0.01 - $0.03 por imagen)
- ❌ Requiere conexión a internet
- ❌ Privacidad: las imágenes se envían a servidores de OpenAI

**Costo Estimado:**
- ~$0.01 - $0.03 por captura procesada
- Para 100 capturas/mes: ~$1-3 USD/mes

**Implementación:**
```python
# Ejemplo básico con OpenAI
import openai
import base64

def extract_data_from_image(image_path):
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """Extrae la siguiente información de esta captura de vuelo/hotel y devuélvela en formato JSON:
                        {
                            "fecha_ida": "YYYY-MM-DD",
                            "fecha_regreso": "YYYY-MM-DD",
                            "aerolinea": "nombre",
                            "hotel": "nombre",
                            "pasajeros": ["nombre1", "nombre2"],
                            "costo_total": 0.00,
                            "servicios": ["Vuelo", "Hospedaje"],
                            ...
                        }"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }
        ],
        max_tokens=1000
    )
    
    return json.loads(response.choices[0].message.content)
```

---

### **Opción 2: Google Cloud Vision API + Document AI**

**Ventajas:**
- ✅ OCR muy preciso
- ✅ Document AI especializado en documentos estructurados
- ✅ Opción de procesamiento local (Vertex AI)

**Desventajas:**
- ❌ Más complejo de implementar
- ❌ Requiere configuración de Google Cloud
- ❌ Costo similar o mayor que OpenAI
- ❌ Menos flexible para diferentes layouts

**Costo Estimado:**
- OCR: ~$1.50 por 1000 imágenes
- Document AI: ~$15 por 1000 documentos

---

### **Opción 3: Tesseract OCR (Open Source) + LLM Local**

**Ventajas:**
- ✅ Gratis y open source
- ✅ Procesamiento local (privacidad total)
- ✅ Sin dependencia de servicios externos

**Desventajas:**
- ❌ Menor precisión que soluciones comerciales
- ❌ Requiere configuración y entrenamiento
- ❌ Procesamiento más lento
- ❌ Dificultad para extraer datos estructurados

**Implementación:**
```python
# Usando Tesseract + LlamaIndex/Ollama para procesamiento local
import pytesseract
from PIL import Image
import json

def extract_with_tesseract(image_path):
    # Extraer texto
    text = pytesseract.image_to_string(Image.open(image_path))
    
    # Usar LLM local (Ollama) para estructurar
    # ... procesamiento adicional
```

---

## 📐 Arquitectura Recomendada

### **Flujo de Usuario:**

```
1. Usuario sube captura de pantalla (vuelo/hotel)
   ↓
2. Sistema muestra preview de la imagen
   ↓
3. Usuario hace clic en "Extraer Datos con IA"
   ↓
4. Backend envía imagen a API de IA
   ↓
5. IA devuelve datos estructurados (JSON)
   ↓
6. Sistema valida y muestra datos extraídos
   ↓
7. Usuario revisa/edita los datos
   ↓
8. Usuario confirma y se pre-llenan los campos del formulario
```

### **Componentes Necesarios:**

1. **Nuevo Modelo Django** (opcional, para cache):
   ```python
   class ExtraccionIA(models.Model):
       imagen = models.ImageField(upload_to='extracciones/')
       datos_extraidos = models.JSONField()
       fecha_creacion = models.DateTimeField(auto_now_add=True)
       usuario = models.ForeignKey(User, on_delete=models.CASCADE)
   ```

2. **Nueva Vista Django:**
   - Vista para subir imagen
   - Vista AJAX para procesar extracción
   - Vista para validar y aplicar datos

3. **Servicio de Extracción:**
   - Clase Python que maneja comunicación con API de IA
   - Parser de JSON a campos del formulario
   - Validador de datos extraídos

4. **Frontend (JavaScript):**
   - Drag & Drop para imágenes
   - Preview de imagen
   - Botón "Extraer con IA"
   - Modal para revisar/editar datos extraídos
   - Auto-fill del formulario

---

## 🚀 Plan de Implementación Recomendado

### **Fase 1: Prototipo Básico (1-2 semanas)**

1. **Instalar dependencias:**
   ```bash
   pip install openai pillow django-cors-headers
   ```

2. **Configurar OpenAI API Key:**
   - Crear cuenta en OpenAI
   - Obtener API key
   - Guardar en variables de entorno

3. **Crear servicio básico de extracción:**
   - Función para enviar imagen a OpenAI
   - Prompt estructurado para extraer datos
   - Parser básico de respuesta JSON

4. **Integrar en formulario de venta:**
   - Botón "Extraer con IA" en `venta_form.html`
   - Endpoint AJAX para procesar
   - Pre-llenar campos básicos (fechas, costos)

### **Fase 2: Mejoras y Validación (1-2 semanas)**

1. **Mejorar prompts de IA:**
   - Prompts específicos para vuelos
   - Prompts específicos para hoteles
   - Manejo de múltiples formatos

2. **Validación de datos:**
   - Validar formatos de fecha
   - Validar montos numéricos
   - Validar que campos requeridos estén presentes

3. **UI/UX mejorada:**
   - Preview de datos antes de aplicar
   - Edición inline de datos extraídos
   - Indicadores de confianza/certeza

### **Fase 3: Optimización (1 semana)**

1. **Cache de extracciones:**
   - Guardar extracciones previas
   - Reutilizar si imagen es similar

2. **Manejo de errores:**
   - Fallbacks si IA falla
   - Mensajes de error claros
   - Opción de reintentar

3. **Métricas y monitoreo:**
   - Tracking de extracciones exitosas
   - Costo por extracción
   - Feedback del usuario

---

## 💡 Recomendación Final

**Usar OpenAI GPT-4 Vision API** por las siguientes razones:

1. ✅ **Rápida implementación** - API simple y bien documentada
2. ✅ **Alta precisión** - Entiende contexto y diferentes layouts
3. ✅ **Bajo costo** - Para el volumen típico de una agencia de viajes (~100-500 capturas/mes = $1-15 USD/mes)
4. ✅ **Flexibilidad** - Fácil ajustar prompts para diferentes casos de uso
5. ✅ **Mantenimiento mínimo** - No requiere entrenamiento o configuración compleja

---

## 🔐 Consideraciones de Privacidad

- ⚠️ Las imágenes se envían a servidores de OpenAI
- ✅ OpenAI no usa los datos para entrenar modelos (si configurado correctamente)
- 💡 Opción: Implementar procesamiento local con Ollama/LlamaIndex para datos sensibles

---

## 📝 Próximos Pasos

1. **Decidir tecnología** (recomiendo OpenAI)
2. **Crear cuenta y obtener API key**
3. **Implementar prototipo básico**
4. **Probar con capturas reales**
5. **Iterar y mejorar**

---

## 📚 Recursos

- [OpenAI Vision API Docs](https://platform.openai.com/docs/guides/vision)
- [Django File Upload](https://docs.djangoproject.com/en/5.2/topics/http/file-uploads/)
- [Pillow (Image Processing)](https://pillow.readthedocs.io/)

---

¿Quieres que proceda con la implementación del prototipo básico usando OpenAI Vision API?




