# Implementación de ReportLab para Cotizaciones PDF

## Resumen

Se ha implementado **ReportLab** como alternativa a WeasyPrint para generar PDFs de cotizaciones, proporcionando **control preciso** sobre el formato y acomodo de tablas.

## ¿Por qué ReportLab?

### Ventajas para tu caso específico:

1. **Control Total sobre Tablas**
   - Anchos de columna precisos en centímetros o puntos
   - Estilos personalizados por celda o fila
   - Control de saltos de página dentro de tablas
   - Encabezados repetidos en cada página automáticamente

2. **Mejor Rendimiento**
   - Generación más rápida que WeasyPrint
   - No requiere renderizar HTML/CSS primero
   - Menor uso de memoria

3. **Posicionamiento Preciso**
   - Control exacto de márgenes y espaciado
   - No depende de la interpretación de CSS
   - Layout predecible y consistente

4. **Sin Dependencias Externas**
   - No requiere bibliotecas del sistema (GTK, Cairo, etc.)
   - Instalación simple con pip
   - Compatible con diferentes sistemas operativos

### Comparación con WeasyPrint:

| Característica | WeasyPrint | ReportLab |
|----------------|------------|-----------|
| Control de tablas | Limitado | Excelente |
| Posicionamiento | Mediante CSS | Directo |
| Velocidad | Media | Alta |
| Dependencias | Múltiples | Mínimas |
| Curva de aprendizaje | Baja | Media |
| Flexibilidad | Alta (HTML/CSS) | Muy Alta (Programático) |

## Estructura de la Implementación

### Archivos Creados/Modificados:

1. **`ventas/reportlab_utils.py`** (NUEVO)
   - Módulo con todas las funciones helper para ReportLab
   - Generadores de tablas por tipo de cotización
   - Estilos personalizados

2. **`ventas/views.py`** (MODIFICADO)
   - Método `_generar_pdf()` actualizado para usar ReportLab
   - Fallback automático a WeasyPrint si ReportLab no está disponible

3. **`requirements.txt`** (MODIFICADO)
   - Agregado `reportlab==4.2.2`

## Funcionalidades Implementadas

### 1. Generadores de Tablas por Tipo

Cada tipo de cotización tiene su propio generador:

- **`generate_vuelos_table()`**: Para cotizaciones de vuelos
- **`generate_hospedaje_table()`**: Para hospedaje
- **`generate_paquete_table()`**: Para paquetes completos
- **`generate_tours_table()`**: Para tours
- **`generate_traslados_table()`**: Para traslados
- **`generate_renta_autos_table()`**: Para renta de autos
- **`generate_generica_table()`**: Para cotizaciones genéricas

### 2. Estilos Personalizados

El módulo define estilos consistentes:

- **TituloPrincipal**: Título principal del documento
- **SubtituloSeccion**: Subtítulos de secciones
- **InfoCliente**: Información del cliente
- **TextoNormal**: Texto normal
- **Total**: Totales en verde y negrita
- **EncabezadoTabla**: Encabezados de tablas
- **CeldaTabla**: Celdas de datos

### 3. Funciones Helper

- **`format_currency()`**: Formatea valores como moneda mexicana
- **`format_date()`**: Formatea fechas
- **`safe_get()`**: Obtiene valores de diccionarios anidados de forma segura
- **`create_info_table()`**: Crea tablas con encabezado personalizable
- **`create_simple_info_table()`**: Crea tablas de dos columnas (Etiqueta | Valor)

## Cómo Usar

### Instalación

```bash
pip install -r requirements.txt
```

### Uso Automático

La implementación es **transparente**. Al hacer clic en "Descargar PDF" en el detalle de una cotización, automáticamente se usará ReportLab si está disponible, o WeasyPrint como fallback.

### Uso Manual (desde código)

```python
from ventas.reportlab_utils import generate_cotizacion_pdf

# Obtener la cotización
cotizacion = Cotizacion.objects.get(slug='mi-cotizacion')

# Generar PDF
pdf_buffer = generate_cotizacion_pdf(cotizacion)

# Guardar o enviar como respuesta
with open('cotizacion.pdf', 'wb') as f:
    f.write(pdf_buffer.getvalue())
```

## Personalización de Tablas

### Ajustar Anchos de Columna

En `reportlab_utils.py`, puedes modificar las funciones `create_info_table()` o `create_simple_info_table()`:

```python
# Ejemplo: Modificar ancho de columnas en create_simple_info_table
col_widths=[7*cm, 10*cm]  # Etiqueta más ancha, valor más estrecho
```

### Cambiar Estilos de Tablas

En las funciones `create_*_table()`, puedes ajustar los estilos:

```python
table_style_overrides = [
    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f0f0f0')),  # Color de fondo
    ('FONTSIZE', (0, 1), (-1, -1), 10),  # Tamaño de fuente
    ('GRID', (0, 0), (-1, -1), 1, colors.black),  # Bordes más gruesos
]
```

### Agregar Más Información a las Tablas

Modifica las funciones `generate_*_table()` para agregar más campos:

```python
def generate_vuelos_table(propuestas):
    # ... código existente ...
    
    # Agregar nuevo campo
    info_data["Clase"] = safe_get(vuelo, 'clase', default="-")
    
    # ... resto del código ...
```

## Estructura del PDF Generado

1. **Encabezado**
   - Título: "COTIZACIÓN DE SERVICIOS TURÍSTICOS"
   - Folio y Fecha de generación

2. **Información del Cliente**
   - Nombre completo
   - Tipo (Empresa/Particular)
   - Asesor

3. **Datos del Viaje**
   - Origen/Destino (según tipo)
   - Fechas (si aplica)
   - Días/Noches

4. **Pasajeros**
   - Total, Adultos, Menores
   - Edades de menores (si aplica)

5. **Notas** (si existen)

6. **Propuestas** (según tipo de cotización)
   - Tablas formateadas con toda la información

7. **Total Estimado** (si existe)

8. **Estado**

## Ventajas Específicas para Tablas

### 1. Control de Anchos
```python
col_widths = [6*cm, 11*cm]  # Control exacto
```

### 2. Encabezados Repetidos
```python
repeatRows=1  # Encabezado se repite en cada página
```

### 3. Evitar Saltos de Página
```python
KeepTogether(table)  # No corta la tabla en medio
```

### 4. Estilos por Celda/Fila
```python
('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#004a8e')),  # Solo encabezado
('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),  # Filas alternadas
```

## Troubleshooting

### Error: "No module named 'reportlab'"
**Solución**: Instala ReportLab:
```bash
pip install reportlab
```

### Error: "InvalidOperation" en format_currency
**Solución**: El valor debe ser convertible a Decimal. Verifica que los valores en `propuestas` sean numéricos.

### Tablas no se ven bien alineadas
**Solución**: Ajusta los `col_widths` en las funciones de creación de tablas. La suma debe aproximarse al ancho disponible (aproximadamente 17cm para A4 con márgenes de 1.5cm).

### PDF se genera pero está vacío
**Solución**: Verifica que la cotización tenga datos en `propuestas`. Revisa los logs para errores específicos.

## Próximos Pasos Sugeridos

1. **Agregar Logo/Membrete**: Modifica `generate_cotizacion_pdf()` para incluir imagen
2. **Footer con página**: Implementa PageTemplate para agregar número de página
3. **Firmas**: Agrega sección de firmas al final del PDF
4. **Más tipos de cotización**: Extiende los generadores si agregas nuevos tipos

## Recursos

- [Documentación oficial de ReportLab](https://www.reportlab.com/docs/reportlab-userguide.pdf)
- [Guía de TableStyle](https://www.reportlab.com/docs/reportlab-userguide.pdf#page=67)
- [Ejemplos de ReportLab](https://www.reportlab.com/opensource/)

## Notas Importantes

- **Sin Membrete**: Como solicitaste, el membrete fue removido para lograr mejor acomodo
- **Compatibilidad**: La implementación mantiene compatibilidad con WeasyPrint como fallback
- **Extensible**: Fácil agregar nuevos tipos de cotización o modificar formatos existentes


