# 📄 Implementación de PDFs para Cotizaciones

## 📋 Resumen Ejecutivo

Se ha implementado un sistema completo de generación de PDFs para cotizaciones usando **WeasyPrint** (HTML/CSS → PDF), reemplazando el sistema anterior basado en DOCX. La implementación incluye:

- ✅ **Plantillas modulares** (componentes reutilizables)
- ✅ **Sistema de cache** (mejora de rendimiento)
- ✅ **Soporte para todos los tipos de cotización** (Vuelos, Hospedaje, Paquete, Tours, Traslados, Renta de Autos, Genérica)
- ✅ **Diseño moderno** con iconos, colores y formato tipo tarjeta
- ✅ **Respeto del membrete** existente

---

## 🏗️ Arquitectura de la Solución

### Stack Tecnológico
- **Backend**: Django (Python)
- **Generación PDF**: WeasyPrint 66.0
- **Templates**: Django Templates (HTML)
- **Estilos**: CSS3 (Flexbox, Grid)
- **Cache**: Sistema de archivos (media/cache/pdfs/)

### Flujo de Generación

```
Usuario solicita PDF
    ↓
Verificar Cache (¿existe y está actualizado?)
    ↓
    ├─ SÍ → Servir desde cache (rápido)
    └─ NO → Generar nuevo PDF
            ↓
        Renderizar HTML con Django Templates
            ↓
        Aplicar CSS (cotizacion_pdf.css)
            ↓
        Convertir HTML → PDF con WeasyPrint
            ↓
        Guardar en cache
            ↓
        Servir PDF al usuario
```

---

## 📁 Estructura de Archivos

```
agencia-web-project/
├── static/
│   ├── css/
│   │   └── cotizacion_pdf.css          # Estilos para PDFs
│   └── img/
│       └── membrete.png                # Imagen del membrete extraída
│
├── ventas/
│   ├── templates/
│   │   └── ventas/
│   │       └── pdf/
│   │           ├── base_cotizacion_pdf.html      # Plantilla base
│   │           ├── cotizacion_vuelos_pdf.html     # Vuelos
│   │           ├── cotizacion_hospedaje_pdf.html # Hospedaje
│   │           ├── cotizacion_paquete_pdf.html   # Paquete
│   │           ├── cotizacion_tours_pdf.html     # Tours
│   │           ├── cotizacion_traslados_pdf.html  # Traslados
│   │           ├── cotizacion_renta_autos_pdf.html # Renta de Autos
│   │           ├── cotizacion_generica_pdf.html   # Genérica
│   │           └── components/                   # Componentes modulares
│   │               ├── header.html                # Membrete
│   │               ├── info_cliente.html          # Info del cliente/viaje
│   │               ├── footer.html                # Footer y notas
│   │               ├── seccion_vuelo.html         # Sección de vuelo
│   │               ├── seccion_hotel.html         # Sección de hotel
│   │               ├── seccion_tour.html          # Sección de tour
│   │               ├── seccion_traslado.html     # Sección de traslado
│   │               └── seccion_renta_autos.html  # Sección de renta de autos
│   │
│   └── views.py
│       └── CotizacionPDFView                      # Nueva vista PDF
│
├── media/
│   └── cache/
│       └── pdfs/                                  # Cache de PDFs generados
│
└── scripts/
    └── extract_membrete_image.py                  # Script para extraer membrete
```

---

## 🔧 Componentes Implementados

### 1. Vista PDF (`CotizacionPDFView`)

**Ubicación**: `ventas/views.py` (línea ~6520)

**Características**:
- ✅ Sistema de cache inteligente
- ✅ Invalidación automática cuando la cotización se actualiza
- ✅ Soporte para todos los tipos de cotización
- ✅ Manejo de errores robusto

**Métodos principales**:
- `get()`: Punto de entrada, verifica cache y genera PDF
- `_get_cache_path()`: Genera ruta única del cache basada en slug y timestamp
- `_preparar_contexto()`: Prepara datos para la plantilla
- `_generar_pdf()`: Renderiza HTML y convierte a PDF
- `_crear_respuesta_pdf()`: Crea respuesta HTTP con PDF

**Ejemplo de uso**:
```python
# URL: /ventas/cotizaciones/<slug>/pdf/
# Vista: CotizacionPDFView
# Template: Determina automáticamente según tipo de cotización
```

### 2. Plantilla Base

**Archivo**: `ventas/templates/ventas/pdf/base_cotizacion_pdf.html`

**Estructura**:
```html
<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="{% static 'css/cotizacion_pdf.css' %}">
</head>
<body>
    {% include "ventas/pdf/components/header.html" %}
    <div class="cotizacion-container">
        {% include "ventas/pdf/components/info_cliente.html" %}
        {% block content %}{% endblock %}
        {% include "ventas/pdf/components/footer.html" %}
    </div>
</body>
</html>
```

### 3. Componentes Modulares

#### Header (`components/header.html`)
- Muestra el membrete como imagen de fondo
- Posicionado en la parte superior de cada página

#### Info Cliente (`components/info_cliente.html`)
- Tabla con información del cliente
- Origen/Destino (adaptado según tipo)
- Fechas, pasajeros, días/noches
- Fecha de cotización

#### Footer (`components/footer.html`)
- Notas de la cotización (si existen)
- Información legal y de contacto

#### Secciones Específicas
Cada tipo de servicio tiene su componente:
- `seccion_vuelo.html`: Información de vuelos
- `seccion_hotel.html`: Información de hoteles
- `seccion_tour.html`: Información de tours
- `seccion_traslado.html`: Información de traslados
- `seccion_renta_autos.html`: Información de renta de autos

### 4. CSS para PDFs

**Archivo**: `static/css/cotizacion_pdf.css`

**Características**:
- Variables CSS para colores Movums
- Diseño tipo tarjeta (cards)
- Iconos y elementos visuales
- Responsive (se adapta al tamaño de página)
- Soporte para tablas, listas, badges

**Colores principales**:
```css
--movums-blue: #004a8e;
--movums-light-blue: #5c8dd6;
--text-color: #2f2f2f;
--border-color: #e0e0e0;
```

---

## 🚀 Cómo Funciona

### 1. Solicitud de PDF

Cuando un usuario hace clic en "Descargar PDF" en el detalle de cotización:

```python
# URL: /ventas/cotizaciones/<slug>/pdf/
# Vista: CotizacionPDFView.get()
```

### 2. Verificación de Cache

```python
# Genera ruta única basada en slug y timestamp de actualización
cache_path = f"media/cache/pdfs/cotizacion_{slug}_{timestamp}.pdf"

# Verifica si existe y está actualizado
if os.path.exists(cache_path):
    if cache_mtime >= cotizacion.actualizada_en.timestamp():
        # Cache válido, servir desde disco
        return servir_desde_cache(cache_path)
```

### 3. Generación de PDF

Si no hay cache válido:

```python
# 1. Preparar contexto
context = {
    'cotizacion': cotizacion,
    'propuestas': propuestas,
    'tipo': tipo,
    'template_name': template_segun_tipo
}

# 2. Renderizar HTML
html_string = render_to_string(template_name, context)

# 3. Convertir a PDF
html = HTML(string=html_string, base_url=base_url)
css = CSS(filename=css_path)
html.write_pdf(pdf_buffer, stylesheets=[css])

# 4. Guardar en cache
guardar_en_cache(pdf_buffer, cache_path)

# 5. Retornar PDF
return HttpResponse(pdf_content, content_type='application/pdf')
```

---

## 📝 Plantillas por Tipo de Cotización

### Vuelos (`cotizacion_vuelos_pdf.html`)
- Muestra cada vuelo en una tarjeta separada
- Información: Aerolínea, Salida, Regreso, Incluye, Forma de Pago, Total

### Hospedaje (`cotizacion_hospedaje_pdf.html`)
- Muestra cada hotel en una tarjeta separada
- Información: Nombre, Habitación, Dirección, Plan, Notas, Forma de Pago, Total

### Paquete (`cotizacion_paquete_pdf.html`)
- Combina vuelo, hotel y tours
- Muestra total del paquete
- Forma de pago del paquete

### Tours (`cotizacion_tours_pdf.html`)
- Muestra cada tour en una tarjeta separada
- Si hay múltiples tours, muestra total general
- Información: Nombre, Especificaciones, Forma de Pago, Total

### Traslados (`cotizacion_traslados_pdf.html`)
- Información: Tipo, Modalidad, Desde/Hasta
- Si es redondo: Fechas y horarios de ida/regreso
- Descripción, Forma de Pago, Total

### Renta de Autos (`cotizacion_renta_autos_pdf.html`)
- Información: Arrendadora, Punto de Origen/Regreso
- Horas de Pickup/Devolución
- Forma de Pago, Total

### Genérica (`cotizacion_generica_pdf.html`)
- Muestra contenido libre en formato de texto

---

## 🎨 Características de Diseño

### Elementos Visuales

1. **Cards/Tarjetas**
   - Fondo blanco con borde sutil
   - Sombra ligera
   - Border radius de 8px
   - Padding de 20px

2. **Iconos**
   - ✈️ Vuelos
   - 🏨 Hospedaje
   - 🗺️ Tours
   - 🚗 Traslados
   - 🚙 Renta de Autos
   - 📄 Genérica

3. **Colores**
   - Azul Movums (#004a8e) para títulos y elementos destacados
   - Texto oscuro (#2f2f2f) para contenido
   - Bordes grises (#e0e0e0) para separación

4. **Tipografía**
   - Fuente: Arial
   - Tamaños: 10pt (texto), 12pt (normal), 14pt (subtítulos), 16-18pt (títulos)

5. **Total Destacado**
   - Fondo gris claro
   - Borde izquierdo azul
   - Texto grande y subrayado
   - Color azul Movums

---

## 💾 Sistema de Cache

### Estrategia de Cache

**Clave de cache**: `cotizacion_{slug}_{timestamp_actualizacion}.pdf`

**Ventajas**:
- ✅ Invalidación automática cuando la cotización se actualiza
- ✅ Cache único por versión de cotización
- ✅ No requiere limpieza manual

**Ubicación**: `media/cache/pdfs/`

**Comportamiento**:
1. Primera solicitud: Genera PDF y guarda en cache
2. Solicitudes subsecuentes: Sirve desde cache (10-50x más rápido)
3. Si la cotización se actualiza: El timestamp cambia, se genera nuevo PDF

### Limpieza de Cache (Opcional)

Si necesitas limpiar el cache manualmente:

```bash
# Eliminar todos los PDFs cacheados
rm -rf media/cache/pdfs/*

# O desde Python
import os
import shutil
cache_dir = 'media/cache/pdfs'
if os.path.exists(cache_dir):
    shutil.rmtree(cache_dir)
    os.makedirs(cache_dir)
```

---

## 🔗 URLs y Endpoints

### Nueva URL PDF
```
/ventas/cotizaciones/<slug>/pdf/
```
- **Vista**: `CotizacionPDFView`
- **Nombre**: `cotizacion_pdf`
- **Método**: GET
- **Autenticación**: Requerida (LoginRequiredMixin)

### URL DOCX (Deprecated)
```
/ventas/cotizaciones/<slug>/docx/
```
- **Vista**: `CotizacionDocxView` (mantenida por compatibilidad)
- **Estado**: Deprecated, pero funcional

### Actualización en Template

El botón de descarga en `cotizacion_detail.html` ahora apunta a:
```html
<a href="{% url 'cotizacion_pdf' slug=cotizacion.slug %}" 
   class="btn btn-primary" 
   target="_blank">
    <i class="fas fa-file-pdf"></i> Descargar PDF
</a>
```

---

## 🧪 Testing y Validación

### Casos de Prueba

1. **Generación de PDF por tipo**:
   - ✅ Vuelos (múltiples opciones)
   - ✅ Hospedaje (múltiples opciones)
   - ✅ Paquete (vuelo + hotel + tours)
   - ✅ Tours (múltiples tours)
   - ✅ Traslados (simple y redondo)
   - ✅ Renta de Autos
   - ✅ Genérica

2. **Sistema de Cache**:
   - ✅ Primera generación crea cache
   - ✅ Segunda solicitud sirve desde cache
   - ✅ Actualización de cotización invalida cache

3. **Membrete**:
   - ✅ Se muestra correctamente en cada página
   - ✅ No interfiere con el contenido

4. **Formato y Estilos**:
   - ✅ Colores correctos
   - ✅ Iconos visibles
   - ✅ Tablas bien formateadas
   - ✅ Totales destacados

---

## 🐛 Troubleshooting

### Problema: PDF no se genera

**Posibles causas**:
1. WeasyPrint no está instalado
   ```bash
   pip install weasyprint
   ```

2. Dependencias del sistema faltantes (Linux)
   ```bash
   # Ubuntu/Debian
   sudo apt-get install python3-cffi python3-brotli libpango-1.0-0 libpangoft2-1.0-0
   ```

3. Archivo CSS no encontrado
   - Verificar que `static/css/cotizacion_pdf.css` existe
   - Ejecutar `python manage.py collectstatic` si es necesario

### Problema: Membrete no aparece

**Solución**:
1. Verificar que `static/img/membrete.png` existe
2. Si no existe, ejecutar:
   ```bash
   python scripts/extract_membrete_image.py
   ```

### Problema: Cache no funciona

**Solución**:
1. Verificar permisos de escritura en `media/cache/pdfs/`
2. Verificar que `MEDIA_ROOT` está configurado correctamente en `settings.py`

### Problema: Estilos no se aplican

**Solución**:
1. Verificar que el CSS está en `static/css/cotizacion_pdf.css`
2. Verificar que WeasyPrint puede acceder al archivo CSS
3. Revisar la ruta `base_url` en la generación del PDF

---

## 📊 Rendimiento

### Métricas Esperadas

- **Primera generación**: 1-3 segundos (depende de complejidad)
- **Desde cache**: 50-200ms (10-50x más rápido)
- **Tamaño promedio PDF**: 100-500KB

### Optimizaciones Implementadas

1. ✅ **Cache de archivos**: Evita regeneración innecesaria
2. ✅ **Invalidación inteligente**: Solo regenera cuando es necesario
3. ✅ **Plantillas modulares**: Reutilización de código
4. ✅ **CSS optimizado**: Estilos eficientes

---

## 🔄 Migración desde DOCX

### Cambios Realizados

1. **Nueva vista**: `CotizacionPDFView` reemplaza funcionalidad de `CotizacionDocxView`
2. **Nuevo endpoint**: `/pdf/` en lugar de `/docx/`
3. **Template actualizado**: Botón ahora apunta a PDF
4. **DOCX mantenido**: Por compatibilidad, pero deprecated

### Compatibilidad

- ✅ La URL `/docx/` sigue funcionando (no se rompe código existente)
- ✅ Se recomienda migrar a `/pdf/` gradualmente
- ✅ Los PDFs tienen mejor formato y son más ligeros

---

## 📚 Referencias y Recursos

### Documentación

- **WeasyPrint**: https://weasyprint.org/
- **Django Templates**: https://docs.djangoproject.com/en/stable/topics/templates/
- **CSS para Impresión**: https://www.w3.org/TR/css-print/

### Archivos Clave

- Vista PDF: `ventas/views.py` (línea ~6520)
- CSS: `static/css/cotizacion_pdf.css`
- Plantilla base: `ventas/templates/ventas/pdf/base_cotizacion_pdf.html`
- URLs: `ventas/urls.py` (línea ~79)

---

## ✅ Checklist de Implementación

- [x] Extraer imagen del membrete desde DOCX
- [x] Crear estructura de directorios
- [x] Crear CSS para PDFs
- [x] Crear componentes modulares
- [x] Crear plantilla base
- [x] Crear plantillas por tipo de cotización
- [x] Implementar vista PDF con WeasyPrint
- [x] Implementar sistema de cache
- [x] Actualizar URLs
- [x] Actualizar template de detalle
- [x] Testing de todos los tipos
- [x] Documentación completa

---

## 🎯 Próximos Pasos (Opcionales)

### Mejoras Futuras

1. **Preview Web**: Mostrar PDF en navegador antes de descargar
2. **Sistema de Temas**: Configuración de colores desde admin
3. **Optimización de Imágenes**: Comprimir membrete para PDFs más ligeros
4. **Múltiples Idiomas**: Soporte para PDFs en inglés/español
5. **Firmas Digitales**: Añadir firma del vendedor al PDF

---

## 📞 Soporte

Si encuentras algún problema o necesitas modificar el diseño:

1. **Modificar estilos**: Editar `static/css/cotizacion_pdf.css`
2. **Modificar plantillas**: Editar archivos en `ventas/templates/ventas/pdf/`
3. **Modificar lógica**: Editar `CotizacionPDFView` en `ventas/views.py`

---

**Última actualización**: Diciembre 2024
**Versión**: 1.0
**Estado**: ✅ Implementación Completa
