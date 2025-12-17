# 🎨 Cómo Editar las Plantillas de Documentos .docx

## 📍 Ubicación de los Archivos

Los métodos que generan los documentos están en:
**`ventas/views.py`** - Clase `GenerarDocumentoConfirmacionView`

## 🛠️ Formas de Personalizar

### **Opción 1: Editar el Código Python Directamente** (Actual)

#### Archivo: `ventas/views.py`

Busca los métodos que generan cada tipo de plantilla:

1. **Vuelo Único**: Línea ~2329 → `def _agregar_vuelo_unico()`
2. **Vuelo Redondo**: Línea ~2389 → `def _agregar_vuelo_redondo()`
3. **Hospedaje**: Línea ~2494 → `def _agregar_hospedaje()`
4. **Traslado**: Línea ~2572 → `def _agregar_traslado()`
5. **Genérica**: Línea ~2607 → `def _agregar_generica()`

#### Ejemplo: Cómo Modificar el Formato de Hospedaje

```python
def _agregar_hospedaje(self, doc, datos):
    """Agrega contenido de hospedaje al documento."""
    from docx.shared import Pt, RGBColor
    
    # TÍTULO DE SECCIÓN
    seccion = doc.add_heading('Información del Alojamiento', level=3)
    seccion.paragraph_format.space_before = Pt(4)  # ← Cambia este valor
    seccion.paragraph_format.space_after = Pt(2)   # ← Cambia este valor
    seccion.runs[0].font.size = Pt(11)             # ← Tamaño de fuente
    seccion.runs[0].font.color.rgb = RGBColor(0, 74, 142)  # ← Color RGB
    
    # CAMPOS EN LÍNEA (Múltiples campos en una sola línea)
    self._agregar_info_inline(doc,
        ('Campo 1', datos.get('campo1', '')),
        ('Campo 2', datos.get('campo2', '')),
        ('Campo 3', datos.get('campo3', ''))
    )
    
    # CAMPO INDIVIDUAL
    self._agregar_info_line(doc, 'Etiqueta', datos.get('valor', ''))
```

### **Opción 2: Métodos de Formato Disponibles**

#### `_agregar_info_inline()` - Múltiples campos en una línea
```python
self._agregar_info_inline(doc,
    ('Etiqueta 1', 'Valor 1'),
    ('Etiqueta 2', 'Valor 2'),
    separador=' | '  # ← Puedes cambiar el separador
)
```
**Resultado**: `Etiqueta 1: Valor 1 | Etiqueta 2: Valor 2`

#### `_agregar_info_line()` - Un campo por línea
```python
self._agregar_info_line(doc, 'Etiqueta', 'Valor')
```
**Resultado**: 
```
Etiqueta: Valor
```

### **Opción 3: Crear Párrafos Personalizados**

```python
# Crear un párrafo personalizado
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(2)  # Espacio después (puntos)
p.paragraph_format.line_spacing = 1.1   # Interlineado (1.1 = 110%)

# Agregar texto con formato
run = p.add_run('Texto en negrita')
run.bold = True
run.font.size = Pt(12)  # Tamaño en puntos
run.font.color.rgb = RGBColor(0, 74, 142)  # Color (R, G, B)
```

### **Opción 4: Tablas para Organizar Información**

```python
from docx.shared import Inches

# Crear tabla
table = doc.add_table(rows=2, cols=2)
table.style = 'Light Grid Accent 1'

# Agregar datos
row = table.rows[0]
row.cells[0].text = 'Campo 1'
row.cells[1].text = 'Valor 1'

row = table.rows[1]
row.cells[0].text = 'Campo 2'
row.cells[1].text = 'Valor 2'
```

## 🎯 Personalizaciones Comunes

### Reducir Saltos de Línea

Busca `space_after` y reduce el valor:
```python
p.paragraph_format.space_after = Pt(1)  # En lugar de Pt(2)
```

### Agrupar Más Campos en Una Línea

Usa `_agregar_info_inline()` con más campos:
```python
self._agregar_info_inline(doc,
    ('Campo 1', valor1),
    ('Campo 2', valor2),
    ('Campo 3', valor3),
    ('Campo 4', valor4)  # ← Agrega más campos aquí
)
```

### Cambiar Colores

```python
# Azul Movums
RGBColor(0, 74, 142)

# Gris
RGBColor(100, 100, 100)

# Negro
RGBColor(0, 0, 0)
```

### Cambiar Tamaños de Fuente

```python
run.font.size = Pt(8)   # Muy pequeño
run.font.size = Pt(10)  # Pequeño (actual)
run.font.size = Pt(12)  # Normal
run.font.size = Pt(14)  # Grande
run.font.size = Pt(16)  # Muy grande
```

## 📝 Ejemplo Completo: Modificar Hospedaje

```python
def _agregar_hospedaje(self, doc, datos):
    """Agrega contenido de hospedaje al documento."""
    from docx.shared import Pt, RGBColor
    
    # TÍTULO
    titulo = doc.add_heading('HOSPEDAJE', level=2)
    titulo.paragraph_format.space_before = Pt(6)
    titulo.paragraph_format.space_after = Pt(4)
    for run in titulo.runs:
        run.font.color.rgb = RGBColor(0, 74, 142)
        run.font.size = Pt(14)
        run.font.bold = True
    
    # TODA LA INFORMACIÓN EN UNA SOLA LÍNEA (ultra compacto)
    self._agregar_info_inline(doc,
        ('Alojamiento', datos.get('nombre_alojamiento', '')),
        ('Referencia', datos.get('numero_referencia', '')),
        ('Viajero', datos.get('viajero_principal', '')),
        ('Habitación', datos.get('tipo_habitacion', '')),
        ('Check-in', datos.get('fecha_checkin', '')),
        ('Check-out', datos.get('fecha_checkout', ''))
    )
    
    # OCUPACIÓN Y RÉGIMEN EN UNA LÍNEA
    adultos = datos.get('adultos', '0')
    ninos = datos.get('ninos', '0')
    ocupacion = f"{adultos}A, {ninos}N" if int(ninos) > 0 else f"{adultos}A"
    
    self._agregar_info_inline(doc,
        ('Ocupación', ocupacion),
        ('Régimen', datos.get('regimen', ''))
    )
```

## 🔄 Pasos para Aplicar Cambios

1. **Abre** `ventas/views.py` en tu editor
2. **Busca** el método que quieres modificar (ej: `_agregar_hospedaje`)
3. **Edita** el código según tus necesidades
4. **Guarda** el archivo
5. **Prueba** generando un documento desde la interfaz web
6. **Ajusta** según sea necesario

## 💡 Consejos

- **Prueba con valores pequeños primero**: Empieza con cambios pequeños y prueba
- **Usa `_agregar_info_inline()` para compactar**: Agrupa campos relacionados
- **Reduce `space_after` para menos saltos**: Cambia `Pt(2)` a `Pt(1)` o `Pt(0)`
- **Guarda una copia**: Haz backup antes de cambios grandes

## 🆘 ¿Necesitas Ayuda?

Si quieres un formato específico y no sabes cómo implementarlo, describe:
1. Qué campos quieres mostrar
2. Cómo quieres organizarlos (en líneas, columnas, etc.)
3. Qué estilos quieres aplicar

Y puedo ayudarte a implementarlo.










