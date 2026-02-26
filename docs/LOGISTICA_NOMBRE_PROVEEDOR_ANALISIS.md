# Análisis: "Nombre del Proveedor" en la pestaña Logística

**Objetivo:** Mostrar en la columna "Nombre del Proveedor" de la tabla de logística el **proveedor seleccionado en el formulario de venta** (VIVA, RUTA MAYA, TRAVELINN, PREMIER TOURS) en lugar del texto de "Opción de..." (ej. PIEDRA DE AGUA BOUTIQUE HOTEL, TRASLADO COMPARTIDO).

---

## 1. Flujo actual: dónde se guarda cada cosa

### 1.1 Formulario de nueva venta / edición (VentaViajeForm)

- **Proveedor por servicio:** El formulario tiene campos de tipo `ModelChoiceField` que apuntan al modelo `Proveedor`:
  - `proveedor_vuelo`
  - `proveedor_hospedaje`
  - `proveedor_traslado`
  - `proveedor_tour_y_actividades`
- **Opción por servicio:** Campos de texto tipo `proveedor_vuelo_opcion`, `proveedor_hospedaje_opcion`, etc. (ej. "PIEDRA DE AGUA BOUTIQUE HOTEL", "TRASLADO COMPARTIDO").

En `VentaViajeForm.save()` (forms.py ~1916–1982):

- Se construye **una línea por servicio** en `servicios_detalle` con el formato:
  ```text
  "Vuelo - Proveedor: VIVA - Opción: VIVA"
  "Hospedaje - Proveedor: RUTA MAYA - Opción: PIEDRA DE AGUA BOUTIQUE HOTEL"
  "Traslado - Proveedor: TRAVELINN - Opción: TRASLADO COMPARTIDO"
  "Tour y Actividades - Proveedor: PREMIER TOURS - Opción: COSTA NORTE + AVENTURA EN EL TREN MAYA"
  ```
- **Proveedor:** texto entre `" - Proveedor: "` y `" - Opción: "` (o hasta el final si no hay Opción).
- **Opción:** texto después de `" - Opción: "`.
- Eso se guarda en **`VentaViaje.servicios_detalle`** (TextField). No hay campos separados en BD por “proveedor de vuelo”, “proveedor de hospedaje”, etc.; todo va en ese texto.
- Además, el formulario asigna **un solo** `instance.proveedor` (FK a Proveedor) con el primer proveedor que encuentre.

Conclusión: el “proveedor seleccionado” por tipo de servicio **solo está persistido dentro del texto** `servicios_detalle`.

### 1.2 Sincronización con Logística (_sync_logistica_servicios)

- Se ejecuta al abrir la pestaña Logística del detalle de venta.
- Lee `venta.servicios_detalle` y extrae **solo la parte “Opción”** (después de `" - Opción: "`), no el nombre del proveedor.
- Con eso rellena **`LogisticaServicio.opcion_proveedor`** al crear o actualizar filas (views.py ~1325–1366).

Código relevante (views.py ~1325–1342):

```python
# Usar la OPCIÓN (texto después de " - Opción: ") para contrato/detalle; si no hay, fallback al proveedor.
if ' - Opción: ' in resto:
    opcion_texto = resto.split(' - Opción: ', 1)[1].strip()
else:
    opcion_texto = resto.strip()
if opcion_texto:
    opciones_por_servicio[nombre_servicio] = opcion_texto
```

- `nombre_servicio` aquí es "Vuelo", "Hospedaje", "Traslado", "Tour y Actividades" (nombre legible).
- Lo que se guarda en `LogisticaServicio` es **solo** `opcion_texto` (la opción), no el nombre del proveedor.

### 1.3 Tabla de la pestaña Logística

- Las filas vienen de **`build_service_rows`** (ventas/services/logistica.py): cada fila tiene `servicio` (objeto `LogisticaServicio`) y el `form` del formset.
- En el template (venta_detail.html ~684–706) la columna **"Nombre del Proveedor"** muestra:
  - `row.servicio.opcion_proveedor` (o el widget `row.form.opcion_proveedor` cuando es editable).
- Por tanto, hoy en esa columna se muestra la **opción** (ej. "PIEDRA DE AGUA BOUTIQUE HOTEL"), no el proveedor (ej. "RUTA MAYA").

### 1.4 Modelo LogisticaServicio

- **`opcion_proveedor`** (CharField): pensado como “opción elegida del proveedor” (aerolínea, hotel, etc.).
- No existe en este modelo un campo “nombre del proveedor” (el de la lista del formulario); ese dato solo está en `venta.servicios_detalle`.

---

## 2. Resumen del flujo

| Dato | Dónde se guarda | Dónde se usa en Logística |
|------|------------------|----------------------------|
| Proveedor seleccionado (VIVA, RUTA MAYA, etc.) | Solo dentro de `VentaViaje.servicios_detalle` (texto " - Proveedor: X") | No se usa; no se muestra en la tabla |
| Opción (PIEDRA DE AGUA, TRASLADO COMPARTIDO, etc.) | `LogisticaServicio.opcion_proveedor` (y también en `servicios_detalle` " - Opción: Y") | Se muestra en la columna "Nombre del Proveedor" |

Por eso la columna muestra la opción y no el proveedor.

---

## 3. Plan de corrección (solo cambio de lo que se muestra)

Objetivo: **no cambiar el flujo ni el guardado**, solo **qué se muestra** en la columna "Nombre del Proveedor": el proveedor del formulario (parseando `servicios_detalle`) en lugar de `opcion_proveedor`.

### 3.1 Extraer “proveedor por servicio” desde servicios_detalle

- En el mismo lugar donde se prepara el contexto de la pestaña Logística (p. ej. en `_prepare_logistica_finanzas_context` o en una función de soporte), parsear `venta.servicios_detalle` línea a línea.
- Por cada línea con formato `"NombreServicio - Proveedor: X - Opción: Y"` (o `"NombreServicio - Proveedor: X"`):
  - Nombre del servicio: texto antes de `" - Proveedor: "` (ej. "Vuelo", "Hospedaje").
  - Nombre del proveedor: texto entre `" - Proveedor: "` y `" - Opción: "` (o todo lo que sigue si no hay `" - Opción: "`).
- Construir un diccionario **`proveedor_por_nombre_servicio`**: clave = nombre del servicio (ej. "Vuelo"), valor = nombre del proveedor (ej. "VIVA"). Así se tiene el proveedor seleccionado por tipo de servicio.

### 3.2 Añadir “nombre a mostrar” en cada fila de la tabla

- En **`build_service_rows`** (o en la vista que arma las filas antes de pasarlas al template):
  - Recibir el diccionario `proveedor_por_nombre_servicio` (o la venta para derivarlo ahí).
  - Por cada fila, además de `servicio` y `form`, añadir un campo, por ejemplo **`nombre_proveedor_display`**:
    - Valor = `proveedor_por_nombre_servicio.get(servicio.nombre_servicio, '')` o, si se quiere fallback al comportamiento actual, `proveedor_por_nombre_servicio.get(servicio.nombre_servicio) or (servicio.opcion_proveedor or '')`.
- Así cada fila sabe qué texto mostrar como “Nombre del Proveedor” sin cambiar lo que está guardado en `opcion_proveedor`.

### 3.3 Cambiar el template

- En la columna "Nombre del Proveedor" (venta_detail.html):
  - Donde ahora se muestra `row.servicio.opcion_proveedor` (o el input del form), usar **`row.nombre_proveedor_display`** para el texto visible.
  - Mantener un **hidden** con el valor actual de `row.servicio.opcion_proveedor` y el nombre del campo del form (`row.form.opcion_proveedor.name`) para que el POST siga enviando `opcion_proveedor` y el guardado no cambie.
- Si en algún caso se sigue mostrando el input editable de `opcion_proveedor`, se puede decidir:
  - Opción A: En esa columna solo mostrar siempre el proveedor (read-only) + hidden de `opcion_proveedor` (flujo más simple y alineado con “solo cambiar lo que se muestra”).
  - Opción B: Mostrar proveedor cuando la celda es solo lectura y, cuando sea editable, seguir mostrando el input de opción; en ese caso haría falta seguir pasando `nombre_proveedor_display` para el modo solo lectura.

Recomendación: **Opción A** (columna = proveedor + hidden para `opcion_proveedor`) para que el comportamiento sea claro y no se pierda el valor actual de `opcion_proveedor` al guardar.

### 3.4 Radar de Logística (logistica_pendiente)

- Las tarjetas usan **`build_logistica_card`**, que lee `servicio.opcion_proveedor` para el texto del servicio.
- Si se desea que ahí también se vea el “proveedor seleccionado” en lugar de la opción, habría que:
  - Pasar la venta (o un mapa proveedor por servicio) a `build_logistica_card` / `build_logistica_card` recibir la venta y derivar el mapa desde `venta.servicios_detalle`, y
  - Usar ese mapa por `codigo_servicio` / `nombre_servicio` para el texto mostrado en la tarjeta.
- Esto es opcional y se puede dejar para una segunda fase si solo se quiere cambiar primero la tabla del detalle de venta.

---

## 4. Archivos a tocar

| Archivo | Cambio |
|---------|--------|
| **ventas/views.py** | En `_prepare_logistica_finanzas_context` (o función auxiliar): parsear `venta.servicios_detalle` y construir `proveedor_por_nombre_servicio`; pasarlo al contexto o a `build_service_rows`. |
| **ventas/services/logistica.py** | En `build_service_rows`: aceptar un argumento opcional `proveedor_por_nombre_servicio` (o `venta`) y añadir en cada elemento de la lista el campo `nombre_proveedor_display`. |
| **ventas/templates/ventas/venta_detail.html** | En la columna "Nombre del Proveedor": mostrar `row.nombre_proveedor_display` y mantener un hidden con `opcion_proveedor` para el POST. |

---

## 5. Consideraciones

- **Servicios con varias filas (ej. varios TOU):** Si hay varias filas del mismo tipo (mismo `nombre_servicio`), todas mostrarán el mismo proveedor del formulario (porque en `servicios_detalle` hay una sola línea por tipo "Tour y Actividades" con un solo "Proveedor: X"). Es coherente con “proveedor seleccionado en el formulario”.
- **Ventas antiguas sin formato " - Proveedor: ":** Si `servicios_detalle` no tiene ese formato, `proveedor_por_nombre_servicio` no tendrá entrada y se puede usar el fallback `servicio.opcion_proveedor` para no dejar la celda vacía.
- **No se añaden migraciones ni campos nuevos:** Solo se usa información ya existente en `servicios_detalle` y se cambia la presentación en la tabla.

Con esto el flujo actual de guardado se mantiene y la columna "Nombre del Proveedor" pasa a mostrar el proveedor seleccionado (VIVA, RUTA MAYA, TRAVELINN, PREMIER TOURS) en lugar de la opción.
