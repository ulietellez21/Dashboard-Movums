# Plan: Imágenes en plantilla genérica de confirmaciones

## Objetivo
Permitir añadir imágenes (capturas de pantalla) a la plantilla genérica de confirmaciones, de forma análoga a la implementación ya existente en cotizaciones genéricas.

## Flujo actual (antes del cambio)
1. **Crear/editar plantilla genérica**: El usuario entra a "Genérica (Cualquier captura)" desde listar confirmaciones. El formulario (`ventas/plantillas/generica.html`) tiene solo **Título** y **Contenido** (textarea). El POST lo maneja `CrearGenericaView` (hereda de `CrearPlantillaConfirmacionView`).
2. **Guardado**: `CrearPlantillaConfirmacionView.post()` construye `datos = { titulo, contenido }` desde el POST, hace `get_or_create(venta, tipo='GENERICA')` y guarda/actualiza `plantilla.datos`.
3. **PDF**: `GenerarDocumentoConfirmacionView.get()` obtiene todas las plantillas de la venta, para cada una genera HTML (para genérica llama a `_generar_html_generica(datos)` que solo muestra título y contenido en una card). El HTML se concatena y se pasa a WeasyPrint para generar el PDF.

## Plan de implementación (aplicado)

### 1. Modelo de imágenes
- **Modelo**: `PlantillaConfirmacionImagen` (FK a `PlantillaConfirmacion`, `imagen` ImageField, `orden`, `descripcion` opcional), con `related_name='imagenes_generica'`.
- **Migración**: `0075_plantillaconfirmacionimagen.py`.

### 2. Formulario plantilla genérica
- Añadir `enctype="multipart/form-data"` al `<form>` en `ventas/plantillas/generica.html`.
- Añadir campo de subida múltiple: `<input type="file" name="generica_imagenes" multiple accept="image/*">`.

### 3. Guardado de imágenes (crear y editar)
- En `CrearPlantillaConfirmacionView.post()`, después de guardar/actualizar la plantilla, si `tipo_plantilla == 'GENERICA'`:
  - Obtener `request.FILES.getlist('generica_imagenes')`.
  - Para cada archivo, crear `PlantillaConfirmacionImagen(plantilla=plantilla, imagen=archivo, orden=orden_inicial + idx)`.
  - En edición, `orden_inicial = plantilla.imagenes_generica.count()` para añadir después de las existentes.

### 4. PDF con imágenes
- En `GenerarDocumentoConfirmacionView.get()`, en el bucle de plantillas, cuando `tipo == 'GENERICA'`:
  - Construir lista de URLs absolutas `file://` desde `plantilla.imagenes_generica.all()` (usar `img.imagen.path` y `os.path.abspath`; en Windows `file:///` con barras).
  - Llamar a `_generar_html_generica(datos, imagenes_urls=imagenes_urls)`.
- En `_generar_html_generica(datos, imagenes_urls=None)`:
  - Aceptar parámetro opcional `imagenes_urls`.
  - Tras el bloque de contenido de texto, si hay `imagenes_urls`, añadir un bloque HTML con un `<img src="{{ url }}">` por cada URL (estilo inline para WeasyPrint: `max-width: 100%; height: auto`).

## Archivos modificados/creados
- `ventas/models.py`: modelo `PlantillaConfirmacionImagen`.
- `ventas/migrations/0075_plantillaconfirmacionimagen.py`: nueva migración.
- `ventas/templates/ventas/plantillas/generica.html`: form enctype y input de imágenes.
- `ventas/views.py`: import de `PlantillaConfirmacionImagen`; en `CrearPlantillaConfirmacionView.post` lógica de guardado de imágenes; en `GenerarDocumentoConfirmacionView.get` construcción de `imagenes_urls` y llamada a `_generar_html_generica(datos, imagenes_urls)`; firma y cuerpo de `_generar_html_generica(datos, imagenes_urls=None)` para incluir imágenes en el HTML.

## Notas
- No existe flujo de descarga DOCX para confirmaciones en la UI actual; solo PDF. Si en el futuro se añade DOCX de confirmaciones que use `_agregar_generica`, se puede extender para insertar imágenes de la plantilla genérica de forma similar a cotizaciones.
- Comportamiento al editar: las imágenes ya guardadas se mantienen; las nuevas se añaden con el mismo input `generica_imagenes` y se ordenan después de las existentes.
