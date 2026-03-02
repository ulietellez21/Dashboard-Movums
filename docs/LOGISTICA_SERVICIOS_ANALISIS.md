# Análisis: Flujo de añadir servicios extras en Logística (Venta detalle)

## Resumen del problema

En la pestaña **Logística** del detalle de venta, al añadir una fila extra de Vuelo, Hospedaje o Tour, completar datos y guardar:

- El servicio **sí se persiste** (la suma de montos planificados lo refleja).
- La fila recién guardada **no se muestra** en la tabla tras el guardado.
- Solo al volver a pedir "1 fila vacía" de ese tipo, se ve la fila anterior con los datos ya guardados.

Además se detectan otros bugs menores en el mismo flujo.

---

## Causas identificadas

### 1. **Fila nueva no visible tras guardar (redirect + lectura de datos)**

**Hipótesis principal:** Tras el `redirect()` después de guardar, la siguiente petición GET puede estar usando datos cacheados o una lectura que no ve el commit reciente.

- La vista usa `@transaction.atomic` en `post()`. El commit ocurre al salir de la vista, antes de enviar la respuesta; en principio el GET debería ver los datos.
- En GET, `get_context_data` limpia el prefetch de `servicios_logisticos` y llama a `_prepare_logistica_finanzas_context`. Ahí se usa `LogisticaServicio.objects.filter(venta_id=venta.pk).order_by('orden', 'pk')` para construir la tabla. Es una consulta independiente de la relación, pero el objeto `venta` puede venir de un queryset con `prefetch_related('servicios_logisticos')` y en algunos entornos (o con caché de app) podría influir.
- **Posible caché de respuesta:** El navegador podría estar mostrando una respuesta GET cacheada de la misma URL, por lo que la tabla no incluiría el servicio recién creado.

**Medidas aplicadas:**

- Refrescar la venta desde BD antes de preparar el contexto de logística en GET (`venta.refresh_from_db()`).
- Usar siempre una consulta explícita por `venta_id` para la tabla (ya se hacía; se mantiene y se documenta).
- Añadir un parámetro de “cache bust” en la URL del redirect (`?tab=logistica&_=timestamp`) para reducir la probabilidad de que el navegador sirva una respuesta cacheada.

### 2. **Campo "Pagado" no se guarda en servicios nuevos**

En el bucle que crea servicios desde los formularios extra (TOU/VUE/HOS), solo se pasan `monto_planeado` y `opcion_proveedor` a `LogisticaServicio.objects.create()`. No se pasa `pagado` ni `fecha_pagado`.

**Consecuencia:** Aunque el usuario marque "Pagado" en la fila nueva, al guardar el servicio se crea siempre con `pagado=False`.

**Solución:** Leer `pagado` del `cleaned_data` del form y, si es True, asignar también `fecha_pagado=timezone.now()` en el `create()`.

### 3. **Condición para crear servicio desde fila extra**

La condición para no crear es:

```python
if not cd.get('opcion_proveedor') and not cd.get('monto_planeado'):
    continue
```

- Si el usuario deja monto vacío, `clean_monto_planeado` devuelve `Decimal('0.00')`, que es “falsy”, por lo que se considera “sin monto” y está bien.
- Si solo rellena monto o solo proveedor, se crea el servicio. Comportamiento correcto.

No se requiere cambio aquí; solo documentar.

### 4. **Eliminación de filas “vacías”**

Tras guardar, se eliminan TOU/VUE/HOS con monto ≤ 0 y sin nombre de proveedor. Un servicio recién creado con monto y proveedor no debe eliminarse. Comportamiento actual correcto.

### 5. **Orden de formas en el formset y filas extra**

El formset se arma con:

- Formas iniciales = una por cada servicio existente en el queryset.
- Formas extra = 3 TOU + 3 VUE + 3 HOS (según servicios contratados).

El template debe iterar en el mismo orden: primero filas de `build_service_rows(servicios_qs, ...)` (una por servicio en BD) y luego las filas “extra” con `es_extra_tou`, `es_extra_vue`, `es_extra_hos`. Los `input type="hidden" ... tipo_extra` deben corresponder al índice correcto del form (prefix). El código actual respeta este orden; el bug de “no se ve la fila” no viene de un desajuste de índices sino de la consulta/caché en GET.

### 6. **`_sync_logistica_servicios` y múltiples filas del mismo tipo**

Se usa:

```python
existentes = {serv.codigo_servicio: serv for serv in venta.servicios_logisticos.all()}
```

Con varios servicios del mismo código (varios VUE, varios HOS), solo queda uno por código en `existentes`. Eso está bien para “crear uno por tipo si no existe” y para actualizar orden/nombre; no se usa `existentes` para borrar. El borrado es `venta.servicios_logisticos.exclude(codigo_servicio__in=servicios_codes).delete()`, por lo que no se eliminan los extras. No se requiere cambio en esta parte.

---

## Resumen de cambios realizados

1. **Vista (POST):** Al crear TOU/VUE/HOS desde forms extra, asignar también `pagado` y `fecha_pagado` desde el formulario.
2. **Vista (redirect):** Añadir parámetro de cache bust en la URL del redirect a `?tab=logistica`.
3. **Vista (GET):** Antes de preparar el contexto de logística, llamar a `venta.refresh_from_db()` y seguir usando `LogisticaServicio.objects.filter(venta_id=venta.pk).order_by('orden', 'pk')` para la tabla.

Con esto se corrigen el guardado de “Pagado” en servicios nuevos y se reduce el riesgo de no ver la fila nueva por caché o lectura obsoleta. Si tras estos cambios el problema persiste, el siguiente paso sería revisar caché de aplicación (si existe) o cabeceras HTTP de la respuesta GET (Cache-Control, etc.).
