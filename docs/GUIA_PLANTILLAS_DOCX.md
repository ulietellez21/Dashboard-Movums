# Guía para Personalizar Plantillas de Documentos .docx

## Opción 1: Editar Código Python (Avanzado)

Las plantillas están definidas en `ventas/views.py` en los métodos:
- `_agregar_vuelo_unico()`
- `_agregar_vuelo_redondo()`
- `_agregar_hospedaje()`
- `_agregar_traslado()`
- `_agregar_generica()`

### Métodos Disponibles para Formatear:

#### `_agregar_info_line(doc, etiqueta, valor)`
Agrega una línea con etiqueta en negrita y valor:
```python
self._agregar_info_line(doc, 'Campo', 'Valor')
```

#### `_agregar_info_inline(doc, *pares_etiqueta_valor, separador=' | ')`
Agrega múltiples campos en una sola línea:
```python
self._agregar_info_inline(doc,
    ('Campo 1', 'Valor 1'),
    ('Campo 2', 'Valor 2'),
    ('Campo 3', 'Valor 3')
)
```

#### Crear Párrafos Personalizados:
```python
p = doc.add_paragraph()
p.paragraph_format.space_after = Pt(2)  # Espaciado después
p.paragraph_format.line_spacing = 1.1   # Interlineado
run = p.add_run('Texto en negrita')
run.bold = True
run.font.size = Pt(10)
run.font.color.rgb = RGBColor(0, 74, 142)
```

## Opción 2: Usar Plantillas HTML (Recomendado - Próximamente)

Próximamente implementaremos un sistema donde puedes editar archivos HTML que se convierten automáticamente a Word. Esto te dará:
- Control total sobre el diseño
- Fácil edición con cualquier editor de texto
- Uso de CSS para estilizar
- Previsualización en navegador antes de generar Word

## Estructura Actual del Documento

1. **Encabezado**: Logo y título del documento
2. **Pie de página**: Información de contacto de Movums
3. **Cada servicio en una página nueva**: 
   - Vuelo Único/Redondo
   - Hospedaje
   - Traslado
   - Genérica

## Personalización Rápida

### Cambiar Espaciado:
En `_agregar_info_line()` y `_agregar_info_inline()`, ajusta:
```python
p.paragraph_format.space_after = Pt(2)  # Cambia 2 por el valor deseado
```

### Cambiar Tamaños de Fuente:
```python
run.font.size = Pt(10)  # Cambia 10 por el tamaño deseado
```

### Cambiar Colores:
```python
run.font.color.rgb = RGBColor(0, 74, 142)  # RGB en formato (R, G, B)
```

## Recomendaciones

1. **Para cambios simples**: Edita los métodos en `ventas/views.py`
2. **Para cambios complejos**: Espera la implementación de plantillas HTML
3. **Para agregar nuevos campos**: Modifica los métodos `_agregar_*()` correspondientes








