# Análisis: Pegar capturas en el mismo campo de texto (plantilla genérica)

## Objetivo
En lugar de un campo aparte para “imágenes”, permitir **pegar capturas de pantalla dentro del mismo campo de texto** en la plantilla genérica, tanto en **cotizaciones** como en **confirmaciones**. El contenido pasaría a ser texto + imágenes en el orden que el usuario quiera (por ejemplo: párrafo, imagen pegada, más texto, otra imagen).

---

## Estado actual

### Cotizaciones (plantilla genérica)

| Aspecto | Estado actual |
|--------|----------------|
| **Formulario** | `cotizacion_form.html`: sección `data-section="generica"` con (1) **Contenido de la Cotización**: `<textarea name="generica_contenido">` (texto plano), (2) **Imágenes (opcional)**: `<input type="file" name="generica_imagenes" multiple>`. |
| **Envío** | JS arma `propuestas.generica.contenido` desde `generica_contenido` (trim). El form tiene `enctype="multipart/form-data"`; las imágenes van en `FILES['generica_imagenes']`. |
| **Guardado** | `CotizacionCreateView`/`CotizacionUpdateView`: guardan `propuestas` (incluye `generica.contenido` como texto). `_guardar_imagenes_generica()` crea registros en **CotizacionImagen** (FK a cotización, `imagen` FileField, `orden`). |
| **PDF** | `cotizacion_generica_pdf.html`: muestra `propuestas.generica.contenido` con `|linebreaks` y, en bloque aparte, `imagenes_generica_urls` (URLs `file://` construidas desde `CotizacionImagen` en `_preparar_contexto`). |
| **DOCX** | Texto de `generica.contenido` línea a línea; luego imágenes de `cot.imagenes_generica.all()` con `doc.add_picture()`. |

### Confirmaciones (plantilla genérica)

| Aspecto | Estado actual |
|--------|----------------|
| **Formulario** | `ventas/plantillas/generica.html`: (1) **Título**, (2) **Contenido**: `<textarea name="contenido">` (texto plano), (3) **Imágenes / Capturas**: `<input type="file" name="generica_imagenes" multiple>`. Form con `enctype="multipart/form-data"`. |
| **Guardado** | `CrearPlantillaConfirmacionView.post()`: arma `datos` desde POST (`titulo`, `contenido`); hace get_or_create/update de **PlantillaConfirmacion**; si tipo GENERICA, guarda `FILES.getlist('generica_imagenes')` en **PlantillaConfirmacionImagen**. |
| **PDF** | `GenerarDocumentoConfirmacionView`: para cada plantilla GENERICA construye `imagenes_urls` desde `plantilla.imagenes_generica.all()` (file://) y llama `_generar_html_generica(datos, imagenes_urls)`. El método genera una card con título, contenido (texto → `\n` → `<br>`) y luego un bloque de `<img>` con esas URLs. |

### Resumen de datos

- **Cotizaciones**: `propuestas.generica.contenido` = texto plano. Imágenes = tabla `CotizacionImagen` (orden separado del texto).
- **Confirmaciones**: `plantilla.datos['contenido']` = texto plano. Imágenes = tabla `PlantillaConfirmacionImagen`.

---

## Propuesta de implementación

### Idea central
- **Un solo campo “contenido”** que acepte texto y imágenes pegadas (Ctrl+V).
- El contenido se guarda como **HTML** (texto + `<img src="...">`), de modo que el orden texto/imagen quede fiel al que el usuario eligió.
- Las imágenes pegadas se **suben al servidor** en el momento del pegado; en el HTML solo se guarda la URL (p. ej. `/media/...`). No hace falta seguir usando los modelos `CotizacionImagen` / `PlantillaConfirmacionImagen` para contenido nuevo (se pueden mantener para compatibilidad con datos antiguos).

### 1. Frontend: campo único “rico” (texto + pegar imagen)

- **Sustituir el textarea** por un área editable que permita:
  - Escribir y pegar texto (comportamiento normal).
  - Al pegar (Ctrl+V) **si el portapapeles trae una imagen**: interceptar el evento, subir la imagen por AJAX, recibir la URL y **insertar en el contenido** un `<img src="...">` (en la posición del cursor o al final).
- Opciones de implementación:
  - **A) contenteditable + paste handler (recomendada)**: Un `div` con `contenteditable`, sin librerías. En el evento `paste` se lee `clipboardData`; si hay imagen se envía con `fetch` a un endpoint de subida, se recibe la URL y se inserta `<img src="url">`. Al enviar el formulario, el valor enviado es el `innerHTML` de ese div (p. ej. en un `input` oculto que se rellena desde JS).
  - **B) Editor rico (Quill/TinyMCE, etc.)**: Soporta pegar imágenes y devuelve HTML. Más peso y posible impacto en el resto del layout; solo tiene sentido si se busca un editor más completo.
- **Cotizaciones**: en la sección genérica, un solo bloque “Contenido” (contenteditable o editor), sin el `<input type="file" generica_imagenes>`. El nombre del campo enviado puede seguir siendo `generica_contenido` y su valor será HTML.
- **Confirmaciones**: igual, un solo bloque “Contenido” (contenteditable), sin el input `generica_imagenes`; el valor se envía como `contenido` (HTML).

### 2. Backend: endpoint para subir imagen al pegar

- **Nuevo endpoint** (p. ej. POST) que:
  - Reciba un archivo de imagen (multipart o base64).
  - La guarde en `MEDIA_ROOT` con una ruta predecible, por ejemplo:
    - Cotizaciones: `cotizaciones/generica/inline/%Y/%m/%d/<uuid>.jpg`
    - Confirmaciones: `confirmaciones/generica/inline/%Y/%m/%d/<uuid>.jpg`
  - No cree filas en `CotizacionImagen` ni `PlantillaConfirmacionImagen` para estas imágenes “inline”.
  - Responda JSON: `{ "url": "/media/cotizaciones/generica/inline/..." }` (o la ruta que corresponda).
- Se puede usar un solo endpoint con un parámetro `tipo=cotizacion|confirmacion` para elegir la carpeta, o dos URLs distintas; lo importante es devolver una URL que el front inserte en el `<img>`.

### 3. Guardado del contenido (HTML)

- **Cotizaciones**: `propuestas.generica.contenido` pasa a poder ser **HTML** (con `<p>`, `<br>`, `<img>`, etc.). El formulario/JS ya envía `generica_contenido`; solo hay que aceptar que ese valor pueda contener HTML y guardarlo tal cual (con sanitización mínima, ver más abajo).
- **Confirmaciones**: `plantilla.datos['contenido']` pasa a poder ser HTML; mismo criterio.
- **Compatibilidad hacia atrás**: registros antiguos tienen `contenido` en texto plano. En PDF/DOCX se puede detectar: si el contenido incluye algo como `<img` (o una etiqueta HTML), tratarlo como HTML; si no, seguir mostrándolo como texto con saltos de línea como hasta ahora.

### 4. Sanitización del HTML (seguridad)

- Permitir solo etiquetas seguras para evitar XSS, por ejemplo: `<p>`, `<br>`, `<strong>`, `<em>`, `<img src="...">` (solo `src` de URLs que empiecen por `/media/` o el dominio conocido). Se puede usar una librería (p. ej. `bleach`) o una whitelist simple al guardar.

### 5. Generación de PDF (WeasyPrint)

- WeasyPrint necesita que las imágenes tengan URL con esquema **file://** (ruta absoluta en disco).
- **Flujo**:
  - En la vista que prepara el contexto del PDF (cotizaciones: `_preparar_contexto`; confirmaciones: donde se arma el HTML de la card genérica), tomar el campo de contenido (que ahora puede ser HTML con `<img src="/media/...">`).
  - Recorrer cada `src` que sea `/media/...`, resolver la ruta real con `settings.MEDIA_ROOT` y construir la URL `file:///ruta/absoluta`.
  - Sustituir en el HTML esas `src` por las URLs `file://` y pasar ese HTML ya resuelto al template (o a `_generar_html_generica`).
- **Cotizaciones**: en el template de PDF genérico, en lugar de `{{ propuestas.generica.contenido|linebreaks }}`, usar algo como `{{ propuestas.generica.contenido_html_resuelto|safe }}` (el “contenido_html_resuelto” sería el contenido ya con `file://` en las imágenes). Mantener el bloque de `imagenes_generica_urls` solo para datos antiguos que sigan teniendo imágenes en `CotizacionImagen`.
- **Confirmaciones**: en `_generar_html_generica`, si `datos['contenido']` es HTML (p. ej. contiene `<img`), no generar solo texto con `<br>`, sino inyectar ese HTML (tras reemplazar `/media/` por `file://`) dentro de la card; y seguir mostrando, si existe, el bloque legacy de `imagenes_urls` para plantillas viejas.

### 6. Generación DOCX (solo cotizaciones hoy)

- Hoy: párrafos de texto desde `generica.contenido` + imágenes desde `imagenes_generica`.
- Con contenido HTML: hacer un “mini parser” del HTML: recorrer el contenido; para nodos de texto, añadir párrafos; para cada `<img src="...">`, resolver `src` a ruta en disco y usar `doc.add_picture(ruta)`. Así se mantiene el orden texto/imagen. Para contenido antiguo (solo texto), mantener la lógica actual más el bloque de imágenes de `imagenes_generica`.

### 7. Qué quitar (sin tocar modelos)

- **Cotizaciones**: en `cotizacion_form.html`, quitar el `<input type="file" name="generica_imagenes">` y su etiqueta. En las vistas, se puede dejar de llamar a `_guardar_imagenes_generica()` (o dejarlo por si en el futuro se envía algo por ese nombre); en la práctica, al no haber input, no llegarán archivos nuevos por ese nombre.
- **Confirmaciones**: en `plantillas/generica.html`, quitar el bloque del input `generica_imagenes`. En `CrearPlantillaConfirmacionView.post()`, quitar (o no ejecutar) el bloque que hace `PlantillaConfirmacionImagen.objects.create(...)` para `generica_imagenes`.
- Los modelos **CotizacionImagen** y **PlantillaConfirmacionImagen** se mantienen para no romper datos ya guardados y para seguir mostrando esas imágenes en PDF/DOCX cuando no haya imágenes inline en el HTML.

### 8. Orden sugerido de cambios

1. **Backend**: Crear endpoint de subida de imagen (upload por paste), guardar en `media/.../inline/...`, devolver `{ "url": "..." }`.
2. **Frontend cotización**: En la sección genérica, reemplazar textarea por contenteditable (o editor); JS: manejar `paste`, subir imagen, insertar `<img>`. En submit, enviar `generica_contenido` = innerHTML (o valor del editor). Quitar input `generica_imagenes`.
3. **Frontend confirmación**: Igual en `plantillas/generica.html`: contenido único con contenteditable + paste → upload → insert img; quitar input de archivos.
4. **Backend guardado**: Aceptar que `generica.contenido` y `datos['contenido']` puedan ser HTML; opcionalmente sanitizar con whitelist (bleach o similar).
5. **PDF cotizaciones**: En `_preparar_contexto`, si `generica.contenido` tiene `<img`, construir HTML con `src` en file:// y pasarlo al template; en el template usar ese HTML con |safe. Mantener bloque de `imagenes_generica_urls` para registros antiguos.
6. **PDF confirmaciones**: En `_generar_html_generica`, si `contenido` tiene `<img`, resolver URLs y emitir ese HTML dentro de la card; si no, comportamiento actual (texto + bloque de imagenes_urls).
7. **DOCX cotizaciones**: Al generar la sección genérica, si `generica.contenido` es HTML, parsear (texto + img en orden) y generar párrafos e imágenes; si no, lógica actual.
8. **Pruebas**: Crear/editar cotización y confirmación genérica, pegar texto e imágenes, guardar, generar PDF y (cotización) DOCX; revisar que el orden y las imágenes se vean bien y que datos antiguos sigan funcionando.

---

## Resumen

| Qué | Cómo |
|-----|------|
| Campo único | Un solo “contenido” editable (contenteditable o editor) donde se escribe y se pega texto e imágenes. |
| Imágenes pegadas | Al pegar imagen: subir a servidor vía endpoint, recibir URL, insertar `<img src="url">` en el contenido. |
| Almacenamiento | Contenido = HTML (texto + img). Sin usar CotizacionImagen/PlantillaConfirmacionImagen para imágenes nuevas. |
| PDF | Resolver `/media/...` en el HTML a URLs `file://` y renderizar ese HTML; mantener lógica actual para imágenes “legacy”. |
| DOCX | Parsear HTML del contenido (texto + img en orden) y generar párrafos e imágenes. |
| Retrocompatibilidad | Si contenido no tiene HTML, seguir mostrando como texto + bloque de imágenes de las tablas actuales. |

Si quieres, el siguiente paso puede ser bajar esto a cambios concretos por archivo (parches o listado de funciones a tocar en `views.py`, `forms.py`, templates y JS).
