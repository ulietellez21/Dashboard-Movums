# Análisis: Cotización adjudicada a otro perfil (vendedor de campo)

## Objetivo

Permitir que un perfil con permisos (agente de oficina, gerente o director) cree una cotización y la **adjudique** a un vendedor de campo, de modo que la cotización (y la venta que se genere después) cuente como del agente de campo, aunque quien la haya redactado sea otro usuario.

**Restricción deseada:** implementar sin modificar el formulario de nueva cotización (`cotizacion_form.html` / `CotizacionForm`) para no romper el flujo actual.

---

## Flujo actual (resumen)

### 1. Creación de cotización

- **Vista:** `CotizacionCreateView` (`ventas/views.py`, ~líneas 13484-13537).
- **URL:** `cotizaciones/nueva/` (`name='cotizacion_crear'`).
- **Asignación de vendedor:** en `form_valid()` se hace siempre:
  ```python
  form.instance.vendedor = self.request.user
  ```
- El **formulario** `CotizacionForm` **no** incluye el campo `vendedor` en `Meta.fields`; el vendedor se fija únicamente en la vista.

### 2. Modelo Cotizacion

- `Cotizacion.vendedor`: `ForeignKey(User, null=True, blank=True, related_name='cotizaciones_creadas')`.
- El campo ya permite cambiar de vendedor a nivel de modelo; no hace falta migración para “adjudicar”.

### 3. Permisos de cotizaciones

- **Ver lista/detalle/editar:** `get_cotizaciones_queryset_base()` en `usuarios/permissions.py`:
  - **Vendedor (rol VENDEDOR):** solo cotizaciones donde `vendedor == request.user`.
  - **Gerente / Director / Jefe / etc.:** todas las cotizaciones.
- Quien puede **editar** una cotización se define por si está en el queryset de la vista (vendedor solo edita las propias; gerente/director editan cualquiera). No hay función tipo `can_edit_cotizacion` explícita.

### 4. Conversión cotización → venta

- **Vista:** `VentaViajeCreateView.form_valid()` (~2260-2295).
- Al crear la venta se asigna **siempre**:
  ```python
  instance.vendedor = self.request.user
  ```
- **No** se usa `cotizacion_origen.vendedor`. Por tanto, aunque la cotización estuviera adjudicada al agente de campo, al convertir la venta quedaría del usuario que convierte (ej. gerente). Para que la adjudicación sea efectiva, habría que usar el vendedor de la cotización cuando exista `cotizacion_origen`.

### 5. Comisiones y reportes

- `ventas/services/cotizaciones_campo.py`: usa `cotizacion.vendedor` para saber si es asesor de campo (`es_asesor_campo(cotizacion.vendedor)`) y aplicar ajustes. Si la cotización se adjudica a un vendedor de campo, esto funcionaría correctamente.
- PDFs y otros reportes que lean `cotizacion.vendedor` reflejarían al vendedor adjudicado.

### 6. Detalle de cotización

- En `cotizacion_detail.html` **no** se muestra actualmente el vendedor asignado. Sería útil mostrarlo cuando exista adjudicación o para claridad.

---

## Opciones de implementación (sin tocar el formulario de nueva cotización)

### Opción A — Adjudicar después de crear (recomendada)

**Idea:** El flujo de “Nueva cotización” no cambia. Quien crea la cotización queda como vendedor al guardar. Luego, desde el **detalle** (o lista) de la cotización, un usuario con permiso puede ejecutar la acción “Adjudicar a vendedor” y elegir al asesor de campo.

**Ventajas:**

- No se toca `CotizacionForm` ni `cotizacion_form.html`.
- No se cambia la lógica de `CotizacionCreateView` (solo se añade una acción nueva en otra vista).
- Flujo claro: crear → (opcional) adjudicar.

**Implementación sugerida:**

1. **Nueva vista (o acción):** por ejemplo `CotizacionAdjudicarView` (POST o GET+form).
   - Recibe `slug` de la cotización y un `vendedor_id` (o un formulario con un único campo: vendedor).
   - Permisos: solo usuarios que no sean “solo vendedor” (gerente, director, jefe) o, si se desea, vendedores que puedan adjudicar a compañeros (según regla de negocio).
   - Validar que el destino sea un usuario con rol VENDEDOR (y opcionalmente filtrar por `tipo_vendedor == 'CAMPO'`).
   - Hacer `cotizacion.vendedor = usuario_seleccionado` y `cotizacion.save(update_fields=['vendedor'])`.

2. **En el detalle de cotización:** botón “Adjudicar a vendedor” que abra un modal o lleve a una página con un desplegable de vendedores (por ejemplo solo asesores de campo). Al enviar el form se llama a la vista de adjudicación.

3. **Conversión a venta:** en `VentaViajeCreateView.form_valid()`, cuando exista `cot` (cotización origen), asignar:
   - `instance.vendedor = cot.vendedor` si `cot.vendedor` está definido; si no, mantener `instance.vendedor = self.request.user`. Así la venta hereda el vendedor de la cotización cuando está adjudicada.

4. **Opcional:** mostrar en `cotizacion_detail.html` el vendedor actual (y si se desea, “Creada por” por auditoría en el futuro si se agrega ese dato).

---

### Opción B — Parámetro en URL al crear

**Idea:** Sin cambiar el formulario en sí, en `CotizacionCreateView` se lee un parámetro opcional `?adjudicar_a=<user_id>`. Si viene y el usuario actual tiene permiso para adjudicar, en `form_valid()` se asigna `form.instance.vendedor = User.objects.get(pk=adjudicar_a)` en lugar de `self.request.user`.

**Ventajas:**

- Un solo paso: “Crear cotización para [vendedor]” desde un enlace.
- El formulario de cotización sigue igual; solo cambia la lógica en la vista.

**Consideraciones:**

- Validar permisos (solo gerente/director/jefe o quien definan).
- Validar que `adjudicar_a` sea un usuario permitido (ej. rol VENDEDOR y opcionalmente tipo CAMPO).
- Evitar que un vendedor se adjudique a sí mismo de forma confusa; se puede permitir o no según reglas de negocio.

**Implementación sugerida:**

1. En `CotizacionCreateView.get_form_kwargs()` o `form_valid()`:
   - Si `request.GET.get('adjudicar_a')` y el usuario tiene permiso para adjudicar:
     - Resolver el usuario por PK, validar rol (y opcionalmente tipo_vendedor).
     - En `form_valid()`: `form.instance.vendedor = usuario_adjudicado` en lugar de `self.request.user`.
2. En lista de cotizaciones (o en un menú): enlace tipo “Nueva cotización para [Asesor de campo]” que apunte a `{% url 'cotizacion_crear' %}?adjudicar_a=<id>`.
3. Misma regla de conversión a venta que en A: usar `cot.vendedor` cuando exista cotización origen.

---

### Opción C — Vista intermedia “Crear cotización para…”

**Idea:** Página o modal previo: “Seleccione el vendedor al que se adjudicará la cotización” (lista de asesores de campo o todos los vendedores). Al elegir, redirige a `cotizacion_crear?adjudicar_a=<id>`. La lógica en el servidor es la de la opción B.

**Ventajas:**

- No se toca el formulario de cotización.
- UX clara para “crear en nombre de otro”.

---

### Opción D — Solo edición / detalle (cambiar vendedor después)

**Idea:** No permitir adjudicación al crear, solo **después**: en el detalle de la cotización, acción “Cambiar vendedor” / “Adjudicar a vendedor” (form con un campo `vendedor`). Misma idea que la opción A pero sin la variante de URL al crear.

- El flujo sería: oficina crea cotización (queda como vendedor quien crea) → entra al detalle → “Adjudicar a asesor de campo” → elige vendedor → guardar.
- No se toca el formulario de nueva cotización.

---

## Recomendación

- **Implementación principal:** **Opción A** (adjudicar desde el detalle) para no tocar el formulario de nueva cotización y dar un flujo explícito y auditable.
- **Complemento opcional:** **Opción B** (o C) para quien prefiera “crear ya adjudicada” desde el inicio (solo cambios en la vista y enlaces, sin tocar el form).
- **Cambio necesario en ambos casos:** en **conversión a venta**, usar `cotizacion_origen.vendedor` cuando exista, para que la venta quede del agente de campo cuando la cotización esté adjudicada.

---

## Resumen de puntos a modificar (sin tocar el form de nueva cotización)

| Área | Cambio |
|------|--------|
| **Nueva acción “Adjudicar”** | Vista (POST) + permiso (ej. gerente/director/jefe) que reciba `slug` + `vendedor_id` y actualice `Cotizacion.vendedor`. |
| **Detalle cotización** | Botón “Adjudicar a vendedor” (modal o página) + mostrar vendedor actual si se desea. |
| **Conversión a venta** | En `VentaViajeCreateView.form_valid()`, si hay `cot` y `cot.vendedor`, usar `instance.vendedor = cot.vendedor`; si no, `instance.vendedor = self.request.user`. |
| **Opcional (Opción B/C)** | En `CotizacionCreateView.form_valid()`, si viene `adjudicar_a` y el usuario tiene permiso, asignar `form.instance.vendedor` al usuario indicado. Enlaces “Nueva cotización para [vendedor]” en lista o menú. |

Con esto se puede implementar la adjudicación a un perfil de vendedor de campo sin modificar el formulario de nueva cotización y manteniendo el flujo actual intacto.
