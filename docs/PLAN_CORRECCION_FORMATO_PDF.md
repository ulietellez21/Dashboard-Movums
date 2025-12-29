# Plan de Corrección de Formato PDF - Cotizaciones

## Problemas Identificados

1. **Membrete mal posicionado y pequeño**: El membrete aparece muy pequeño y desplazado a la izquierda
2. **Márgenes inconsistentes**: Los márgenes no están equilibrados, causando desplazamiento del contenido
3. **Formato diferente por tipo**: Cada tipo de cotización aplica el formato de forma diferente
4. **Falta de estandarización**: No hay una estructura base consistente entre todos los tipos

## Solución Propuesta

### 1. Corrección de Márgenes de Página
- **Márgenes equilibrados**: `60px` en todos los lados para centrado perfecto
- **Área de contenido**: Respetar el espacio del membrete (header) y footer

### 2. Estandarización del Membrete
- **Tamaño**: Ajustar a `max-height: 220px` para mejor visibilidad
- **Posicionamiento**: Centrado horizontal con `text-align: center`
- **Ancho**: `100%` del área disponible dentro de los márgenes
- **Espaciado**: `margin-bottom: 25px` para separación adecuada

### 3. Estructura Base Unificada
- **Contenedor principal**: `width: 100%`, sin restricciones de max-width
- **Cards**: Márgenes automáticos para centrado, padding consistente
- **Espaciado**: Valores estándar para todas las secciones

### 4. Estandarización de Templates
- Todos los templates deben usar las mismas clases CSS
- Estructura consistente en `base_cotizacion_pdf.html`
- Componentes modulares con estilos uniformes

## Implementación

### Archivos a Modificar

1. **`static/css/cotizacion_pdf.css`**
   - Ajustar `@page` margins
   - Corregir `.header` y `.membrete-img`
   - Estandarizar `.cotizacion-container`
   - Unificar estilos de `.card`

2. **`ventas/templates/ventas/pdf/components/header.html`**
   - Verificar estructura del membrete
   - Asegurar uso correcto de `membrete_base64`

3. **Verificar todos los templates de cotización**
   - Asegurar que todos extienden `base_cotizacion_pdf.html`
   - Verificar uso consistente de clases CSS

## Resultado Esperado

- Membrete visible, centrado y de tamaño adecuado
- Márgenes equilibrados en todos los lados
- Formato consistente entre todos los tipos de cotización
- Contenido centrado y bien espaciado
