# Análisis del Flujo: Radar de Logística (Logística Pendiente)

**Fecha:** 18 Feb 2025  
**Objetivo:** Identificar inconsistencias en el flujo del Radar de Logística, especialmente sobre ventas con pagos pendientes y completadas que no aparecen correctamente.

---

## 1. Resumen Ejecutivo

El Radar de Logística muestra solo las ventas que **ya tienen al menos un registro en `LogisticaServicio`**. Las ventas que nunca han pasado por la pestaña Logística del detalle (o que tienen `servicios_seleccionados` vacío) **nunca aparecen**, independientemente de su estado de pago. Además hay inconsistencias con permisos por rol, ventas canceladas y ausencia de prefetch que pueden afectar la correcta visualización.

---

## 1.1 [CAUSA RAÍZ CRÍTICA] Paginación sin controles de navegación

**Problema:** La vista `LogisticaPendienteView` usa `paginate_by = 30`, pero el template **no renderiza ningún control de paginación** (no hay links "Siguiente", "Página 2", etc.).

**Consecuencia directa:** Solo se muestran las **primeras 30 ventas** del queryset. Cualquier venta que quede en la página 2, 3, etc. **no es visible** y el usuario no tiene forma de llegar a ella.

**Orden del queryset:** `order_by('fecha_inicio_viaje')` — **ascendente** (las fechas más antiguas primero).

**Ejemplo concreto (VAR-20260203-04):**
- La venta tiene logística creada y pagos listos para pagar.
- Su `fecha_inicio_viaje` probablemente es Feb 2026 o cercana.
- Con orden ascendente, las ventas con viajes en 2024, 2025, etc. aparecen primero.
- Si hay 30 o más ventas con `fecha_inicio_viaje` anterior a la de VAR-20260203-04, esta venta queda en la **página 2 o posterior**.
- Como no hay controles de paginación, el usuario **solo ve la página 1** y la venta parece "no estar".

**Evidencia en el código:**
- `ventas/views.py` línea 3021: `paginate_by = 30`
- `ventas/views.py` línea 3055: `order_by('fecha_inicio_viaje')` (ascendente)
- `ventas/templates/ventas/logistica_pendiente.html`: No existe `page_obj`, `paginator`, ni enlaces de paginación (a diferencia de `venta_list.html` y `cotizacion_list.html`, que sí los tienen)

---

## 2. Flujo Actual

### 2.1 Cuándo se crean `LogisticaServicio`

Los registros en `LogisticaServicio` se crean **solo** cuando:

1. Un usuario con permiso entra al **detalle de venta** y abre la **pestaña Logística**.
2. En `get_context_data` se llama a `_prepare_logistica_finanzas_context` → `_sync_logistica_servicios(venta)`.
3. `_sync_logistica_servicios` crea **una fila por cada código** en `venta.servicios_seleccionados` (ej: VUE, HOS, TOU, TRA).

**Condiciones para que se creen filas:**
- `venta.servicios_seleccionados` debe contener al menos un código (ej: `"VUE,HOS"`).
- Si `servicios_seleccionados` está vacío o `None`, `servicios_codes = []` y **no se crea ninguna fila**.
- Una venta que nunca ha tenido la pestaña Logística abierta **no tendrá** registros en `servicios_logisticos`.

### 2.2 Criterio de aparición en el Radar

```python
# ventas/views.py - LogisticaPendienteView.get_queryset()
queryset = self.model.objects.filter(servicios_logisticos__isnull=False)...
```

**Consecuencia directa:** Una venta solo aparece en el Radar si `venta.servicios_logisticos.exists()` es True. Las ventas sin ningún `LogisticaServicio` **no aparecen nunca**, aunque:
- Tengan pagos pendientes.
- Estén completamente pagadas.
- Sean activas y relevantes para logística.

---

## 3. Problemas Identificados

### 3.1 [CRÍTICO] Ventas ausentes por falta de `servicios_logisticos`

| Escenario | ¿Aparece en el Radar? | Motivo |
|-----------|------------------------|--------|
| Venta con pagos pendientes, nunca abrió pestaña Logística | ❌ No | No tiene filas en `LogisticaServicio` |
| Venta completada (pagada), nunca abrió Logística | ❌ No | Igual |
| Venta con `servicios_seleccionados` vacío | ❌ No | El sync no crea filas |
| Venta con Logística abierta al menos una vez y con servicios | ✅ Sí | Tiene `LogisticaServicio` |

**Impacto:** Muchas ventas con pagos pendientes o ya completadas que el usuario espera ver en el Radar no aparecen porque dependen de que alguien haya entrado a la pestaña Logística.

---

### 3.2 [IMPORTANTE] Queryset no usa `get_ventas_queryset_base`

Otras vistas (Lista de ventas, Reporte financiero) usan:

```python
base_ventas = perm.get_ventas_queryset_base(VentaViaje, user, self.request)
```

`LogisticaPendienteView` construye el queryset manualmente:

```python
queryset = self.model.objects.filter(servicios_logisticos__isnull=False)...
if self.user_role == 'VENDEDOR':
    queryset = queryset.filter(vendedor=self.request.user)
```

**Inconsistencias:**

| Rol | Comportamiento esperado (get_ventas_queryset_base) | Comportamiento actual en Logística Pendiente |
|-----|----------------------------------------------------|---------------------------------------------|
| VENDEDOR | Solo sus ventas | ✅ Correcto (filtro manual) |
| GERENTE | Solo ventas de su oficina | ❌ Ve **todas** las ventas (no filtra por oficina) |
| JEFE, CONTADOR, Directores | Todas las ventas | ✅ Correcto |

---

### 3.3 [IMPORTANTE] Ventas canceladas aparecen en el Radar

El queryset **no filtra** por `estado != 'CANCELADA'`. Las ventas canceladas con `servicios_logisticos` existentes aparecen en el Radar.

En contraste, la lista de ventas separa activas/cerradas y muestra las canceladas en "Contratos Cerrados".

---

### 3.4 Falta de prefetch para evitar N+1

`build_logistica_card` llama a `build_financial_summary`, que usa:
- `venta.total_pagado` → itera sobre `venta.abonos` (y apertura)
- `venta.abonos_proveedor.filter(...)` → consulta a BD

El queryset actual hace:
```python
.prefetch_related('servicios_logisticos')
```

**No incluye** `abonos` ni `abonos_proveedor`. Con muchas ventas en el tablero, hay múltiples consultas adicionales por venta.

---

### 3.5 Orden de ventas

```python
.order_by('fecha_inicio_viaje')  # Ascendente
```

Las ventas más antiguas aparecen primero. Otras vistas (lista de ventas, etc.) usan `-fecha_inicio_viaje` (más recientes primero). Puede ser preferible unificar criterios.

---

### 3.6 Moneda no indicada en el template

El template muestra montos como `${{ card.resumen.total_venta|floatformat:2|intcomma }}` sin indicar si es USD o MXN. Si hay ventas internacionales (USD) y nacionales (MXN) mezcladas, puede generar confusión.

---

### 3.7 Servicios con `monto_planeado = 0`

En `build_logistica_card` y `build_service_rows`:
- Si `monto_planeado = 0` y `pagado = False` → `saldo_disponible >= 0` → estado `'ready'` ("Listo para pagar").
- Un servicio con monto 0 sin pagar se marca como "Listo para pagar", lo cual es coherente (no falta dinero) pero puede resultar confuso si el usuario espera verlo como "pendiente de definir monto".

---

## 4. Flujo de Estados (pendiente / listo / pagado)

La lógica en `build_logistica_card` y `build_service_rows` es coherente:

| Condición | Estado |
|-----------|--------|
| `servicio.pagado == True` | `paid` (Pagado) |
| `monto > 0` y `saldo_disponible >= monto` | `ready` (Listo para pagar) |
| Resto | `pending` (Pendiente) |

El problema no parece estar en la clasificación de estados, sino en:
1. Las ventas que no llegan al Radar por falta de `servicios_logisticos`.
2. Posibles errores en `build_financial_summary` si `total_pagado`, `costo_neto` o `abonos_proveedor_comprometidos` no coinciden con la realidad (requeriría revisión con datos reales).

---

## 5. Resumen de Problemas por Prioridad

| Prioridad | Problema | Afectación |
|-----------|----------|------------|
| **Crítico** | **Paginación (30 por página) sin controles de navegación en el template** | Ventas en página 2+ son invisibles (ej: VAR-20260203-04 con viaje futuro). Causa principal del síntoma "tiene logística y no se muestra". |
| Crítico | Solo aparecen ventas con `servicios_logisticos`; las que nunca abrieron Logística no se muestran | Ventas con pagos pendientes y completadas ausentes |
| Importante | GERENTE ve ventas de todas las oficinas (no usa `get_ventas_queryset_base`) | Incumplimiento de permisos por oficina |
| Importante | Ventas canceladas aparecen en el Radar | Ruido y confusión |
| Media | Sin prefetch de `abonos` y `abonos_proveedor` | Posible degradación de rendimiento |
| Menor | Orden ascendente por fecha (más antiguas primero) | UX |
| Menor | Moneda (USD/MXN) no indicada en montos | Claridad para el usuario |

---

## 6. Posibles Enfoques de Corrección (para discutir)

### Opción 0: Corregir paginación (causa del caso VAR-20260203-04)

- **A.** Añadir controles de paginación al template (como en `venta_list.html`) usando `page_obj` y `paginator` que ListView ya pone en el contexto.
- **B.** Cambiar el orden a `order_by('-fecha_inicio_viaje')` (más recientes primero), de modo que las ventas con viajes próximos aparezcan en página 1.
- **C.** Desactivar paginación (`paginate_by = None`) si el volumen no es excesivo, para mostrar todas las ventas.

La opción **0** corrige directamente el caso donde ventas con logística creada (como VAR-20260203-04) no aparecen.

### Opción A: Crear `servicios_logisticos` de forma proactiva

- Al crear/guardar una venta con `servicios_seleccionados` definido, ejecutar `_sync_logistica_servicios` (o equivalente) para crear las filas iniciales.
- Así, cualquier venta con servicios tendría filas y podría aparecer en el Radar sin depender de abrir la pestaña Logística.

### Opción B: Mostrar ventas con `servicios_seleccionados` aunque no tengan `LogisticaServicio`

- Cambiar el queryset para incluir ventas con `servicios_seleccionados` no vacío.
- En `build_logistica_card`, si no hay `servicios_logisticos`, crear un contexto mínimo o invocar el sync al vuelo (con cuidado de no afectar la vista ni el rendimiento).

### Opción C: Usar `get_ventas_queryset_base` y aplicar filtros adicionales

- Base: `perm.get_ventas_queryset_base(...)`
- Luego: `.filter(servicios_logisticos__isnull=False)` (o el criterio que se defina)
- Excluir: `.exclude(estado='CANCELADA')`
- Con esto se corrigen permisos (incluido GERENTE) y ventas canceladas.

### Opción D: Comando de migración/sincronización

- Crear un comando de management que recorra ventas con `servicios_seleccionados` no vacío y cree `LogisticaServicio` faltantes.
- Útil para datos existentes; el flujo nuevo podría combinarse con Opción A o B.

---

## 7. Archivos Relevantes

| Archivo | Relevancia |
|---------|------------|
| `ventas/views.py` | `LogisticaPendienteView` (líneas ~3048–3088), `_sync_logistica_servicios` (~1315) |
| `ventas/services/logistica.py` | `build_logistica_card`, `build_financial_summary`, `build_service_rows` |
| `ventas/templates/ventas/logistica_pendiente.html` | Template del Radar |
| `usuarios/permissions.py` | `get_ventas_queryset_base`, roles |

---

**Nota:** Este documento es solo análisis. No se han aplicado cambios al código.
