# Rediseño: Flujo de servicios logísticos (tabla en pestaña Logística)

## Objetivo

Mantener la **misma utilidad** que ya funcionaba (tabla por servicio, monto planificado, estado, pagado, proveedor) pero con una **estructura simple y a prueba de errores**, sin formset con filas “extra” ocultas ni dropdowns que controlan visibilidad.

---

## 1. Lo que SÍ conservamos (y ya funcionaba bien)

| Elemento | Uso |
|----------|-----|
| **Modelo `LogisticaServicio`** | Sin cambios: venta, codigo_servicio, nombre_servicio, monto_planeado, pagado, fecha_pagado, opcion_proveedor, orden. |
| **`build_financial_summary(venta, servicios_qs)`** | Resumen (total venta, pagado, saldo, servicios planificados, montos cuadran, etc.). |
| **`build_service_rows(servicios_qs, resumen, formset_forms, venta)`** | Genera la lista de filas para la tabla: cada fila tiene `servicio`, `form`, `status`, `badge_class`, `status_label`, `status_hint`. Se puede simplificar a “1 fila = 1 servicio con su form” sin lógica de “extra”. |
| **Columnas de la tabla** | Servicio (nombre), Monto planificado, Estado (badge), Pagado (checkbox), Nombre del proveedor. |
| **Permisos y campos bloqueados** | Misma lógica: quien no puede editar restringidos ve campos deshabilitados y se envían con `<input type="hidden">` para que el POST no los pierda. |
| **Validaciones al guardar** | Suma de montos planificados = total servicios planificados; total marcado como pagado ≤ total pagado. |
| **Eliminar filas vacías** | Tras guardar, borrar TOU/VUE/HOS con monto 0 y sin nombre de proveedor. |
| **Servicios con múltiples proveedores** | Solo TOU, VUE y HOS pueden tener varias filas; el resto un registro por tipo. |

---

## 2. Lo que fallaba (y por qué)

| Problema | Causa |
|----------|--------|
| Formset inválido (“id es obligatorio”) | El template no renderizaba los `hidden_fields` del form (p. ej. `id`). |
| Servicios “extra” no se creaban | El formset tenía `extra=9` y lógica de “crear desde form sin PK”; mezcla de índices, `tipo_extra` y validación hacía que o no se enviaran datos o el formset fallara antes. |
| Filas “desaparecen” tras guardar | Dependencia de dropdown en 0 y filas “extra” ocultas con `d-none`; la tabla se construía con filas regulares + extra, y el dropdown reseteaba. |
| Sincronización confusa | `_sync_logistica_servicios` usa un dict `existentes` por código (una sola fila por código), pero TOU/VUE/HOS tienen varias; la lógica de “crear uno por tipo” y “añadir extras” se mezclaba con el formset. |

---

## 3. Principios del nuevo diseño

1. **Una sola fuente de verdad**  
   Las filas de la tabla = exactamente los registros de `LogisticaServicio` para esa venta. No hay “filas extra” vacías en el formset.

2. **Formset solo para editar lo que ya existe**  
   Formset con `queryset = servicios_qs` y `extra = 0`. Siempre hay un form por cada servicio en BD. El template siempre pinta `hidden_fields` y luego los campos visibles.

3. **Añadir fila = acción aparte**  
   “Añadir otro Vuelo/Hospedaje/Tour” es un botón (o enlace) que hace una petición que **solo crea un registro** y redirige a la misma pestaña. No se usa el formset para crear.

4. **Sync solo para “arranque”**  
   Asegurar que exista **al menos una** fila por cada código en `servicios_seleccionados`. No usar sync para crear “extras”; los extras los crea el usuario con “Añadir otro X”.

---

## 4. Flujo propuesto (paso a paso)

### 4.1 Al entrar a la pestaña Logística (GET)

1. Limpiar prefetch de `servicios_logisticos` en la venta (evitar caché).
2. **Sync (simplificado):**  
   Para cada código en `venta.servicios_seleccionados`:  
   - Si **no existe** ningún `LogisticaServicio` con ese código para la venta → crear **uno** con nombre y orden por defecto.  
   - No tocar filas que ya existan (no sobrescribir proveedor/monto).  
   Eliminar solo servicios cuyo `codigo_servicio` **no** esté en `servicios_seleccionados`.
3. `servicios_qs = LogisticaServicio.objects.filter(venta_id=venta.pk).order_by('orden', 'pk')`.
4. Formset: `modelformset_factory(..., extra=0)(queryset=servicios_qs, prefix='servicios')`.
5. `filas = build_service_rows(servicios_qs, resumen, list(formset.forms), venta)` — una fila por servicio, cada una con su form.
6. Contexto: formset, filas, resumen, permisos, y flags para “mostrar botón Añadir otro Vuelo/Hospedaje/Tour” (según si el código está en `servicios_seleccionados`).

### 4.2 Template de la tabla

- Un único formulario POST con `actualizar_servicios_logistica=1`.
- `{{ formset.management_form }}`.
- Para **cada** `row in servicios_logisticos_rows`:
  - **Siempre:** `{% for hidden in row.form.hidden_fields %}{{ hidden }}{% endfor %}` (incluye `id`).
  - Primera columna: nombre del servicio (`row.servicio.nombre_servicio`) + opcional “(nuevo)” o hint si se desea.
  - Resto: monto, estado (badge), pagado, proveedor usando `row.form` y la misma lógica de permisos/disabled/hidden que ahora.
- **Sin** dropdown “Filas vacías para otro(s) proveedor(es)”.  
- **Sin** filas ocultas con `d-none` ni JS que muestre/oculte filas.
- Debajo de la tabla, **botones** (solo si aplica y el usuario puede editar):
  - “Añadir otro Vuelo” (si venta tiene VUE).
  - “Añadir otro Hospedaje” (si venta tiene HOS).
  - “Añadir otro Tour” (si venta tiene TOU).
- Botón “Guardar ajustes” para enviar el formset.

### 4.3 POST “Guardar ajustes” (formset)

1. `servicios_qs = venta.servicios_logisticos.all().order_by('orden', 'pk')`.
2. Formset con `data=request.POST`, `queryset=servicios_qs`, `prefix='servicios'`.
3. Si **no** es válido: re-renderizar pestaña Logística con formset y errores (sin redirect).
4. Si **es** válido:
   - **No** crear nuevos servicios aquí (no hay forms “extra”).
   - Actualizar cada servicio existente con los datos del form correspondiente (monto, pagado, opcion_proveedor, fecha_pagado si aplica).
   - Validar suma de montos y total pagado (como ahora).
   - Guardar cambios.
   - Eliminar TOU/VUE/HOS vacíos (monto 0 y sin proveedor).
   - Redirect a `detalle_venta?tab=logistica` (o re-render sin redirect, según preferencia; redirect es más simple y evita dudas de caché).

### 4.4 POST “Añadir otro Vuelo/Hospedaje/Tour”

1. Parámetro ej. `añadir_servicio_logistica=1` y `tipo=VUE` (o HOS / TOU).
2. Comprobar que la venta tiene ese servicio en `servicios_seleccionados` y que el usuario puede gestionar logística.
3. Calcular `next_orden` para ese código (ej. `Max(orden) + 1`).
4. `LogisticaServicio.objects.create(venta=venta, codigo_servicio='VUE', nombre_servicio='Vuelo', orden=next_orden, monto_planeado=0, ...)`.
5. Redirect a `detalle_venta?tab=logistica`.

En el template, cada botón “Añadir otro X” puede ser un formulario con un único `<input type="hidden" name="tipo" value="VUE">` y `name="añadir_servicio_logistica" value="1"`, method POST, para que sea una sola petición y no mezclar con el formset.

---

## 5. Cambios concretos respecto al código actual

| Área | Quitar / Cambiar | Poner |
|------|-------------------|--------|
| **Formset** | `extra=9`, `_get_logistica_servicio_formset` con 3+3+3 extras. | `extra=0`, formset solo con `queryset=servicios_qs`. |
| **Vista** | Bucle que recorre forms “sin PK” y crea TOU/VUE/HOS según `tipo_extra`. | Eliminar ese bucle. Crear servicios solo en el handler “Añadir otro X”. |
| **Template** | Dropdown “Filas vacías…”, filas con `es_extra_tou/vue/hos` y `d-none`, JS que muestra/oculta. | Botones “Añadir otro Vuelo/Hospedaje/Tour” que envían POST con `tipo=...`. Siempre `{% for hidden in row.form.hidden_fields %}{{ hidden }}{% endfor %}` por fila. |
| **Contexto** | `cantidad_inicial_tou/vue/hos`, `tiene_tou_para_otro_proveedor` (para dropdown). | Mantener solo flags para “mostrar botón Añadir otro Vuelo/Hospedaje/Tour” (mismo dato: si venta tiene VUE/HOS/TOU). |
| **Sync** | `existentes = {codigo: serv}` (un solo servicio por código). | Por cada código en `servicios_seleccionados`, si `not venta.servicios_logisticos.filter(codigo_servicio=code).exists()` → crear **un** registro. No usar dict que pise múltiples filas. |
| **build_service_rows** | Recibir formset con N+9 forms y cortar `formset_forms[:len(servicios_qs)]`; luego añadir filas “extra” con `servicio=None`. | Recibir solo `servicios_qs` y `formset.forms` (mismo tamaño). Una fila por servicio; sin filas “extra”. |

---

## 6. Utilidad que se mantiene

- Misma tabla: servicio, monto planificado, estado, pagado, proveedor.
- Mismos permisos y campos bloqueados (monto/proveedor/pagado según rol).
- Misma validación de suma y de total pagado.
- Misma limpieza de filas vacías TOU/VUE/HOS.
- Posibilidad de tener **varios** Vuelos, Hospedajes o Tours: ahora añadidos con “Añadir otro X” en lugar del dropdown y las filas extra del formset.

---

## 7. Orden sugerido de implementación

1. **Sync:** ajustar `_sync_logistica_servicios` para “al menos una fila por código” sin pisar múltiples filas del mismo tipo.
2. **Vista:**  
   - Formset con `extra=0`.  
   - Handler POST “Añadir otro X” (crear un `LogisticaServicio` y redirect).  
   - POST “Guardar ajustes”: solo actualizar servicios existentes; quitar toda la lógica de crear desde forms “extra”.
3. **build_service_rows:** simplificar a “una fila por elemento de servicios_qs” con su form (mismo índice).
4. **Template:** quitar dropdown y filas extra; añadir siempre `hidden_fields`; añadir botones “Añadir otro Vuelo/Hospedaje/Tour” con formularios POST.
5. **Limpieza:** quitar debug logging, `cantidad_inicial_*`, y código muerto de “extra” y `tipo_extra`.

Con esto la tabla sigue siendo la misma utilidad, pero la estructura queda simple y estable: formset = solo edición de filas existentes; nuevas filas = una acción explícita que crea un registro y recarga.

---

## 8. Protección de campos bloqueados (prioridad alta)

**Objetivo:** Que los permisos por rol se respeten sin excepción: ningún guardado (edición de venta ni de logística) debe desbloquear ni resetear campos que el usuario no tiene permiso para editar.

### 8.1 Regla general

- **Campos bloqueados** = aquellos que, según el rol, no puede editar el usuario (ej. monto planificado ya llenado, pagado, nombre del proveedor en logística; costo_neto, cantidad_apertura, etc. en el formulario de venta).
- En el HTML, si un campo está bloqueado, debe enviarse igualmente al servidor (p. ej. `<input type="hidden">` con el valor actual además del input visible `readonly`/`disabled`, o no usar `disabled` y usar `readonly` + estilo).
- En el **servidor**, al guardar (form.save() o actualización manual), **nunca** persistir un valor para un campo bloqueado que provenga del POST si el usuario no tiene permiso: o bien no incluir ese campo en lo que se guarda, o bien **restaurar el valor actual desde la BD** justo antes del `save()` final.

### 8.2 Formulario de edición de venta (VentaViajeUpdateView)

**Problema actual:**  
`VentaViajeForm.save()` sobrescribe `instance` con todo lo que hay en `cleaned_data`. Si un campo está `disabled` en el template, no viene en el POST → `cleaned_data` no lo tiene o viene vacío → al hacer `instance.save()` se guarda vacío o incorrecto y se “resetea” el campo.

**Solución (a aplicar en la vista, no en el form):**

1. Antes de `form.save()`, guardar en variables los valores **actuales en BD** de todos los campos que el usuario no puede editar según permisos (ej. `perm.can_edit_campos_bloqueados`, campos financieros restringidos, etc.).
2. Llamar a `self.object = form.save()` como ahora.
3. Inmediatamente después, para cada campo restringido que el usuario no puede editar, asignar de nuevo al objeto el valor guardado en el paso 1 (o recargar desde BD con `self.object.refresh_from_db()` para esos campos y luego reasignar solo los que sí puede editar).
4. Llamar a `self.object.save(update_fields=[...])` con **solo** la lista de campos que el usuario sí puede editar (o hacer un único `save()` habiendo restaurado los restringidos).

Alternativa equivalente: en `form_valid`, después de `form.save()`, hacer  
`for field_name in CAMPOS_RESTRINGIDOS: if not perm.user_can_edit_field(user, field_name): setattr(self.object, field_name, getattr(venta_anterior, field_name))`  
y luego `self.object.save(update_fields=...)` con la lista correcta.

**Campos a proteger (ejemplos):**  
Según tu matriz de permisos: costo_neto, costo_venta_final, cantidad_apertura, costo_modificacion (si no es JEFE/Admin), campos USD en INT, y cualquier otro que ya marques como “solo JEFE/Director/Gerente” en el template. La lista exacta debe salir de la misma lógica que usas para poner `disabled`/readonly en el form.

**servicios_detalle y servicios_seleccionados:**  
Hoy el form reconstruye `servicios_detalle` desde los checkboxes y dropdowns de proveedores del formulario. Eso **sobrescribe** el texto completo y puede “perder” información que solo existe en la pestaña Logística (varios proveedores por tipo). Opciones:

- **Opción A (recomendada):** En la edición de venta, **no** sobrescribir `servicios_detalle` si la venta ya tiene `LogisticaServicio` con datos. Es decir: en `VentaViajeForm.save()`, si `instance.pk` existe y hay registros en `LogisticaServicio` para esa venta, no asignar `instance.servicios_detalle = ...` desde el form; dejar el valor actual o generarlo desde `LogisticaServicio` (método tipo `venta.servicios_detalle_desde_logistica` si lo tienes). Así la pestaña Logística es la **fuente de verdad** para proveedores por servicio y editar la venta no los resetea.
- **Opción B:** Mantener que el form actualice `servicios_detalle`, pero que ese texto sea **solo informativo** y que `_sync_logistica_servicios` **nunca** escriba en `LogisticaServicio.opcion_proveedor` (ni monto ni pagado) cuando el registro ya tiene valor; solo crear filas faltantes por código. Así al menos no se resetean los datos ya guardados en la tabla.

En el rediseño se recomienda **Opción A**: que el formulario de venta no pise `servicios_detalle` cuando ya hay datos de logística, y que la tabla de logística sea la única que edite proveedores/montos por servicio.

### 8.3 Pestaña Logística (guardado del formset)

- Ya se hace: campos bloqueados se envían con `<input type="hidden">` además del input visible deshabilitado, para que el POST traiga el valor.
- Asegurar que en la vista, al actualizar cada `LogisticaServicio`, **no** se use el valor del form para monto/pagado/opcion_proveedor si el usuario no tiene permiso para ese campo: usar la lógica actual de “si no puede editar restringidos, usar valor de `original`” y persistir solo lo permitido.

### 8.4 Sync (_sync_logistica_servicios)

- **No** debe asignar nunca `monto_planeado` ni `pagado` (esos solo se tocan en el formset de logística).
- **Sí** puede asignar `opcion_proveedor` **solo cuando está vacío** (como ahora), y solo para la “primera” fila por código si se usa para arranque inicial. En el rediseño, el sync solo crea filas faltantes (una por código) y opcionalmente pone nombre de proveedor inicial si el registro está recién creado y vacío; no debe tocar filas que el usuario ya editó en logística.

### 8.5 Resumen de implementación (bloqueo)

1. **VentaViajeUpdateView.form_valid:** después de `form.save()`, restaurar desde `venta_anterior` (o BD) todos los campos restringidos que el usuario no puede editar y hacer `save(update_fields=...)` con la lista correcta.
2. **VentaViajeForm.save:** si `instance.pk` existe y la venta tiene `LogisticaServicio` con datos, no sobrescribir `servicios_detalle` (y opcionalmente no tocar `servicios_seleccionados` si eso podría borrar tipos que ya tienen filas en logística); o documentar que la fuente de verdad para proveedores por servicio es la tabla de logística.
3. **_sync_logistica_servicios:** no escribir monto ni pagado; solo crear filas faltantes y, si se desea, rellenar `opcion_proveedor` solo cuando esté vacío en registros recién creados por el sync.
4. **Template venta_form.html:** donde haya campos bloqueados por rol, asegurar que el valor actual se envíe (hidden si hace falta) para que no se pierda por error; y que la vista siga la regla de no persistir cambios en campos no permitidos.
