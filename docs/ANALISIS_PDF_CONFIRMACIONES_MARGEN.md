# Análisis: Tablas en PDF de Confirmaciones y problema de margen en última página

**Objetivo:** Documentar qué tipos de tablas/contenido se generan para confirmaciones, cómo se estructuran, y opciones de solución para el margen superior en páginas 2+ (sin modificar código aún).

---

## 1. Dónde se genera el PDF de confirmaciones

| Aspecto | Detalle |
|--------|---------|
| **Vista** | `GenerarConfirmacionesPDFView` en `ventas/views.py` (aprox. líneas 9114–9235) |
| **Template** | `ventas/templates/ventas/confirmaciones_pdf.html` (único template para este PDF) |
| **Render** | `render_to_string('ventas/confirmaciones_pdf.html', context, request=request)` |
| **Contexto** | `venta`, `fecha_generacion`, `plantillas_html`, `membrete_url`, `STATIC_URL` |
| **Nota** | En confirmaciones **no** se pasa variable `tipo` al template (a diferencia de `base_cotizacion_pdf.html` para cotizaciones). |

---

## 2. Tipos de “tablas” / bloques que se generan para confirmaciones

El contenido del PDF se arma en la vista: se recorre cada **PlantillaConfirmacion** de la venta (orden: Vuelo Único → Vuelo Redondo → Hospedaje → Traslado → Genérica) y se llama al método correspondiente. El HTML resultante se acumula en `plantillas_html` y luego se inyecta en el template dentro de `confirmaciones-container`.

Resumen por tipo de plantilla:

| Tipo plantilla | Método en views.py | Estructura HTML generada | Clases CSS relevantes |
|----------------|--------------------|---------------------------|------------------------|
| **VUELO_UNICO** | `_generar_html_vuelo_unico` | 1 bloque: `div.card` → `div.card-header` + `table.data-table`. Opcional 2ª card “Información completa del vuelo” con `page-break-before: always`. | `.card`, `.card-header`, `.data-table` |
| **VUELO_REDONDO** | `_generar_html_vuelo_redondo` | 1ª card “Vuelo de Ida” (card + data-table). Luego `div.vuelo-regreso-nueva-pagina` (page-break-before: always, padding-top: 184px) + 2ª card “Vuelo de Regreso” (card + data-table). | `.card`, `.data-table`, `.vuelo-regreso-nueva-pagina` |
| **HOSPEDAJE** | `_generar_html_hospedaje` | 1 bloque: `div.card` → `div.card-header` + `table.data-table` (+ opcional imagen `.hospedaje-imagen`). | `.card`, `.card-header`, `.data-table`, `.hospedaje-imagen` |
| **TRASLADO** | `_generar_html_traslado` | **Una card por traslado** en `datos['traslados']`. Primera: envuelta en `div.traslado-primera-espacio`; siguientes: envueltas en `div.traslado-tabla-grande`. Cada una: `div.card` + `div.card-header` + `table.data-table`. | `.traslado-primera-espacio`, `.traslado-tabla-grande`, `.card`, `.data-table` |
| **GENERICA** | `_generar_html_generica` | 1 bloque: `div.card` → `div.card-header` + `div` con texto (sin tabla). | `.card`, `.card-header` (sin `.data-table`) |

En el template, el primer ítem de `plantillas_html` se imprime sin wrapper; los siguientes se envuelven en `div.content-wrapper` (margin-top: 24px).

---

## 3. Tipos de tablas en el sentido estricto (elementos `<table>`)

En el PDF de confirmaciones solo hay **dos** clases de tabla:

1. **`info-table`**  
   - **Una sola** en todo el documento.  
   - Ubicación: bloque fijo de “CONFIRMACIONES DE VIAJE” (cliente + fecha de generación).  
   - Estructura: `table.info-table` con filas de datos (ej. “Fecha de Generación”).

2. **`data-table`**  
   - **Varias**, una por cada card de servicio (vuelo único, ida, regreso, hospedaje, cada traslado).  
   - Estructura: `table.data-table` dentro de `div.card`, con filas de etiqueta/valor (Clave de Reserva, Aerolínea, Fecha, etc., o equivalente por tipo).

La **genérica** no usa tabla; es solo texto dentro de la card.

---

## 4. Cómo se “acomodan” hoy (contenedores y espaciado)

- **Primera plantilla:** se imprime directamente (sin `content-wrapper`).
- **Plantillas 2, 3, …:** envueltas en `div.content-wrapper` (margin-top: 24px; page-break-before: auto).
- **Traslados:**  
  - Primera tabla de traslado: `div.traslado-primera-espacio` (margin-top: 120px).  
  - Segunda y siguientes: `div.traslado-tabla-grande` (margin-top: 24px).
- **Vuelo redondo:** bloque “Vuelo de Regreso” dentro de `div.vuelo-regreso-nueva-pagina` (page-break-before: always; padding-top: 184px).
- **Cards:** `page-break-inside: avoid` para no partir la card entre páginas.

Con esto, las “tablas” (cards + data-tables) se acomodan por flujo: primera al inicio, siguientes con separación y, en traslados, con clases específicas para la primera vs el resto.

---

## 5. Por qué el margen falla en la última (y en general en la 2ª+) página

- En **confirmaciones** el template usa **una sola regla `@page`**: con membrete `margin: 0`, sin membrete `margin: 1.5cm`. No se usan **páginas nombradas** ni `@page :first` vs `@page` para diferenciar página 1 y siguientes.
- El **margen superior “visual”** en la primera página lo da el **body**: `padding-top: 3.5cm` (y laterales/abajo). En medios paginados (WeasyPrint), ese padding suele aplicarse al **primer fragmento** del contenido. El contenido que **fluye** a la página 2 (y siguientes) cae en el **área de contenido de `@page`** sin que el padding del body se repita arriba de esa página. Resultado: en página 2+ el contenido puede quedar pegado al borde superior (sobre todo si el primer elemento de la nueva página es una card/tabla con poco o ningún margin-top efectivo en ese contexto).
- Las clases `.traslado-tabla-grande`, `.content-wrapper`, etc. solo añaden `margin-top` en el flujo; no cambian el `@page`. Si WeasyPrint, al cortar la página, no aplica bien ese margen al primer elemento de la nueva página (p. ej. por cómo trata los saltos de página o los bloques con `page-break-inside: avoid`), el efecto “pegado” persiste.

---

## 6. Soluciones posibles (para decidir después, sin tocar código aún)

### A) Márgenes en `@page` (recomendado para consistencia)

- Definir **márgenes en la regla `@page`** para todas las páginas, de modo que el área de contenido ya tenga el hueco superior (y no depender del padding del body en página 2+).
- **Con membrete:**  
  - Opción 1: `@page { margin: 3.5cm 2cm 2.5cm 2cm; }` (y quitar o reducir padding del body para no duplicar).  
  - Opción 2: Mantener membrete como ahora y añadir solo `@page { margin-top: 3.5cm; }` (y el resto igual), para que página 2+ tengan al menos ese margen superior.
- **Sin membrete:** equivalente con 1.5cm o el valor que se desee.
- Ventaja: mismo comportamiento en página 1 y siguientes. Desventaja: hay que coordinar con el diseño del membrete (si debe ser full-bleed o no).

### B) Páginas nombradas (como en cotizaciones)

- Introducir una **página nombrada** (p. ej. `@page confirmaciones`) con `margin-top` mayor en páginas que no son la primera.
- Asignar `page: confirmaciones` al `body` (o a un contenedor que envuelva todo el contenido del PDF).
- Definir `@page confirmaciones:first` con márgenes de la primera página y `@page confirmaciones` con márgenes para página 2+ (p. ej. margin-top: 4.77cm).
- Ventaja: control explícito primera vs siguientes. Desventaja: WeasyPrint a veces tiene comportamientos raros con `@page :first` (ver referencias abajo).

### C) Refuerzo con `margin-top` en el flujo

- Aumentar `margin-top` en los contenedores que pueden ser **primer elemento** en una nueva página: p. ej. `.content-wrapper`, `.traslado-tabla-grande`, y/o la primera card que sigue a un salto de página.
- Ventaja: cambio mínimo. Desventaja: no garantiza el mismo “margen de página” en todas las páginas; depende del elemento que quede primero tras el corte.

### D) Running header / área fija superior

- Usar **margin boxes** de `@page` (p. ej. `@top-center`) con un bloque de altura fija (aunque sea “vacío”) para reservar espacio superior en todas las páginas. Menos habitual en WeasyPrint y más complejo de mantener.

### E) Revisar versión y bugs de WeasyPrint

- Documentación y foros indican que variar márgenes con `@page :first` puede afectar a las demás páginas en algunos motores. Conviene revisar changelog y issues de WeasyPrint por “margin”, “@page :first”, “second page” para ver si hay fix o workaround recomendado en tu versión.

---

## 7. Resumen de “tipos de tablas” para confirmaciones

| Tipo | Descripción | Dónde aparece |
|------|-------------|----------------|
| **info-table** | Tabla de datos del cliente / fecha de generación | Una vez, al inicio del PDF (bloque fijo). |
| **data-table (vuelo único)** | Tabla de datos del vuelo único | Dentro de la card “VUELO ÚNICO”. |
| **data-table (vuelo ida)** | Tabla del vuelo de ida | Dentro de la card “VUELO DE IDA”. |
| **data-table (vuelo regreso)** | Tabla del vuelo de regreso | Dentro de la card “VUELO DE REGRESO” (en .vuelo-regreso-nueva-pagina). |
| **data-table (hospedaje)** | Tabla del hospedaje | Dentro de la card de hospedaje. |
| **data-table (traslado)** | Tabla de cada traslado | Una por cada ítem en `traslados`, cada una en su card (primera en .traslado-primera-espacio, siguientes en .traslado-tabla-grande). |
| **Genérica** | Sin tabla | Solo card con título y texto en un `div`. |

Para “acomodar” márgenes, los bloques críticos son los que pueden ser **primer contenido en una nueva página**: sobre todo las cards envueltas en `.content-wrapper` y `.traslado-tabla-grande`, y el bloque `.vuelo-regreso-nueva-pagina`.

---

## 8. Referencias útiles

- WeasyPrint: **Adjust Document Dimensions** – recomienda usar `@page` para márgenes:  
  https://doc.courtbouillon.org/weasyprint/stable/common_use_cases.html  
- `@page` y pseudo-clases (`:first`, etc.):  
  https://developer.mozilla.org/en-US/docs/Web/CSS/@page  
- Páginas nombradas (WeasyPrint soportado en print-css.rocks):  
  https://print-css.rocks/lesson/lesson-named-pages  
- Problema conocido: “Changing print margins using CSS @page :first causes other pages to cut off text”:  
  https://stackoverflow.com/questions/68732901  

---

*Documento generado a partir del análisis del código en `ventas/views.py` y `ventas/templates/ventas/confirmaciones_pdf.html`. No se ha modificado ningún archivo del proyecto.*
