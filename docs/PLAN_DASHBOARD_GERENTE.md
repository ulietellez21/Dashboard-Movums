# Plan de implementación: Dashboard GERENTE (Dueño de Franquicia)

**Objetivo:** Rentabilidad de oficina y productividad del equipo.

**Alcance:** El gerente ve solo los datos de **su oficina** (Perfil.oficina). Las ventas se filtran por `vendedor__ejecutivo_asociado__oficina_id = oficina_gerente`. Cotizaciones y demás KPIs deben filtrarse por vendedores de esa misma oficina.

**Fecha:** 2 Mar 2026

---

## 1. Estado actual en el sistema

### 1.1 Rol y alcance
- **Perfil.oficina:** el gerente tiene una oficina asignada.
- **perm.get_ventas_queryset_base:** para GERENTE devuelve `VentaViaje.objects.filter(vendedor__ejecutivo_asociado__oficina_id=oficina_id)`.
- **Cotizaciones:** hoy `get_cotizaciones_queryset_base` no filtra por oficina para gerente (devuelve todas). Para el dashboard gerente habrá que filtrar por `vendedor__ejecutivo_asociado__oficina_id = oficina_gerente`.
- **Vendedores de la oficina:** `User` con `ejecutivo_asociado.oficina_id = oficina_gerente` (o Ejecutivo.objects.filter(oficina=oficina_gerente)).

### 1.2 Modelos disponibles
| Dato | Origen | Notas |
|------|--------|--------|
| Ventas oficina | VentaViaje + filtro por oficina del vendedor | Ya existe en permissions |
| Utilidad / margen | VentaViaje: costo_venta_final, costo_neto (y USD para INT) | Calcular utilidad = venta - costo_neto; margen = utilidad/venta |
| Comisiones | ComisionVenta (por venta), ComisionMensual | comision_calculada, comision_pagada |
| Cancelaciones | VentaViaje.estado == 'CANCELADA' o SolicitudCancelacion | Contar por mes/fecha |
| Cuentas por cobrar | saldo_restante por venta (no canceladas) | Suma por oficina |
| Ventas con riesgo | fecha_vencimiento_pago vencida o por vencer, saldo > 0 | Igual que dashboard vendedor pero scope oficina |

### 1.3 Lo que NO existe hoy
| Requerimiento | Estado | Acción |
|---------------|--------|--------|
| **Gastos por oficina / segmento** | No hay modelo ni campos en Oficina | “Al dar de alta las oficinas, implementar rubro de gastos por segmento” → nuevo modelo o campos |
| **Costo operativo vs utilidad** | Depende de gastos por oficina | Tras tener gastos, KPI = costo_operativo vs utilidad |
| **ROI de marketing local** | No hay registro de gasto en marketing por oficina | Depende de gastos por segmento (ej. segmento “Marketing”) |
| **Penalidades pagadas** | No hay modelo “Penalidad” ni campo en venta/oficina | Definir si es campo en venta, tabla nueva o se deja para fase posterior |
| **Comparativo vs otras oficinas / Ranking nacional** | No hay vista agregada por oficina | Construir en servicio: agregar por oficina y comparar |
| **Margen vs estándar corporativo** | No hay constante “estándar” | Definir valor (ej. 15%) y dónde configurarlo |

---

## 2. Bloques del dashboard y plan por fases

### 2.1 KPIs clave (sin gastos ni penalidades)
- **Ventas totales oficina:** suma de ventas (MXN) del periodo, filtro por oficina.
- **Utilidad:** suma (costo_venta_final - costo_neto) en MXN por ventas de la oficina en el periodo.
- **Margen promedio:** promedio de margen por venta (margen = utilidad/venta) en el periodo.
- **Ticket promedio:** ventas_totales_mxn / cantidad_ventas.
- **% Conversión global oficina:** (ventas con cotizacion_origen en periodo) / (cotizaciones generadas en periodo por vendedores de la oficina).
- **Ventas por vendedor:** desglose por vendedor (nombre, total MXN, cantidad) en el periodo.
- **Comisiones pagadas vs generadas:** suma comision_pagada y suma comision_calculada (o comision_calculada) del mes para vendedores de la oficina.

**Implementación:** Servicio `dashboard_gerente.py` (o sección en un módulo común) con funciones que reciban `oficina_id` y `fecha_inicio`/`fecha_fin`; reutilizar lógica de conversión INT→MXN y margen del dashboard vendedor. Vista: si `user_rol == 'GERENTE'`, obtener `oficina_id` del perfil, calcular periodo (semanal/mensual/mes anterior como en vendedor) y pasar KPIs al contexto. Template: bloque `{% if user_rol == 'GERENTE' %}` con cards y tabla “Ventas por vendedor”.

### 2.2 Productividad (parcial sin gastos)
- **Ventas por empleado:** ventas_totales_oficina / número de vendedores (o ejecutivos) de la oficina en el periodo (o activos a fecha).
- **Costo operativo vs utilidad:** requiere **gastos por oficina**. Sin modelo de gastos, dejar placeholder o texto “Próximamente” y preparar el lugar en el layout.
- **ROI de marketing local:** requiere **gastos por segmento (marketing)** por oficina. Igual: dejar para cuando exista el rubro de gastos.

**Implementación:** “Ventas por empleado” ya se puede implementar. Los otros dos KPIs se documentan y se dejan para la fase de “Gastos por oficina”.

### 2.3 Cartera
- **Cuentas por cobrar:** suma de `saldo_restante` de ventas de la oficina (no canceladas).
- **Ventas con riesgo:** ventas de la oficina con fecha_vencimiento_pago vencida o por vencer (ej. 7 días) y saldo_restante > 0 (lista o count).
- **Cancelaciones del mes:** count de ventas de la oficina con estado CANCELADA y fecha de cancelación (o fecha_actualizacion / SolicitudCancelacion.fecha_aprobacion) en el mes; o count de SolicitudCancelacion aprobadas en el mes para ventas de la oficina.
- **Penalidades pagadas:** sin modelo actual. Opciones: (A) no mostrar hasta tener modelo; (B) campo futuro en VentaViaje u otra tabla; (C) registro manual por oficina. Dejar como **pregunta** y placeholder en el plan.

**Implementación:** Servicio con funciones cartera_gerente(oficina_id, mes, anio) o (oficina_id, fecha_inicio, fecha_fin). Vista y template con cards y, si aplica, lista de “ventas con riesgo”.

### 2.4 Inteligencia
- **Comparativo vs otras oficinas:** por periodo, agregar por oficina (ventas MXN, margen promedio, conversión, etc.) y mostrar la oficina del gerente vs el resto (nombres o “Oficina 2”, “Oficina 3” según política de privacidad).
- **Ranking nacional:** ranking de oficinas por ventas (o por margen, etc.) en el periodo; posición de la oficina del gerente.
- **Margen vs estándar corporativo:** estándar = constante o setting (ej. 15%); mostrar margen promedio de la oficina vs ese valor.
- **Rentabilidad por tipo de producto:** utilidad (o margen) desglosada por tipo_viaje (NAC, INT, INT_MXN) para la oficina en el periodo.

**Implementación:** Servicio que agregue por oficina (solo oficinas con ventas en el periodo) y calcule rankings; vista que pase “comparativo” y “ranking” al template. Template: sección Inteligencia con comparativo, posición en ranking, margen vs estándar y tabla/gráfica por tipo de producto.

---

## 3. Fases de implementación propuestas

### Fase 0 – Preparación
- Crear `ventas/services/dashboard_gerente.py` con helpers de periodo (reutilizar o alinear con `_fechas_periodo` semanal/mensual/mes_anterior).
- En la vista del dashboard, detectar `user_rol == 'GERENTE'`, obtener `oficina_id` (y validar que no sea None); pasar al contexto `periodo_gerente`, `fecha_inicio`, `fecha_fin`, `oficina_gerente` (objeto o nombre).
- En el template, bloque inicial “Mi Oficina: {{ oficina_gerente.nombre }}” y selector de periodo (Esta semana / Este mes / Mes anterior), sin KPIs aún.

**Criterio de listo:** Gerente entra al dashboard, ve su oficina y el selector de periodo; no se muestran KPIs de gerente todavía.

---

### Fase 1 – KPIs clave (ventas, utilidad, margen, ticket, conversión, ventas por vendedor, comisiones)
- En `dashboard_gerente.py`: funciones que reciban `oficina_id` y rango de fechas:
  - `kpis_ventas_oficina(oficina_id, fecha_inicio, fecha_fin)`: total MXN, utilidad total, margen promedio, ticket promedio, count ventas.
  - `kpis_conversion_oficina(oficina_id, fecha_inicio, fecha_fin)`: cotizaciones generadas por vendedores de la oficina, ventas con cotizacion_origen, % conversión.
  - `ventas_por_vendedor_oficina(oficina_id, fecha_inicio, fecha_fin)`: lista de { vendedor, total_mxn, count }.
  - `kpis_comisiones_oficina(oficina_id, mes, anio)`: comision_pagada total, comision_calculada (o proyectada) total.
- Vista: llamar a estas funciones cuando rol sea GERENTE y pasar resultados al contexto.
- Template: sección “KPIs clave” con cards y tabla “Ventas por vendedor”.

**Criterio de listo:** El gerente ve ventas totales, utilidad, margen promedio, ticket promedio, % conversión, desglose por vendedor y comisiones pagadas vs generadas para su oficina.

---

### Fase 2 – Productividad (ventas por empleado; placeholders para costo operativo y ROI)
- Servicio: `ventas_por_empleado(oficina_id, fecha_inicio, fecha_fin)`: total ventas MXN / cantidad de vendedores de la oficina (Ejecutivo activos con esa oficina, o usuarios con ventas en el periodo).
- Template: card “Ventas por empleado”; cards “Costo operativo vs utilidad” y “ROI marketing local” con texto “Próximamente (requiere registro de gastos por oficina)” o similar.

**Criterio de listo:** Se muestra ventas por empleado; los otros dos KPIs tienen placeholder claro.

---

### Fase 3 – Cartera (cuentas por cobrar, ventas con riesgo, cancelaciones del mes)
- Servicio: `cartera_oficina(oficina_id, fecha_inicio, fecha_fin o mes/anio)`:
  - Cuentas por cobrar: suma saldo_restante de ventas de la oficina no canceladas.
  - Ventas con riesgo: lista/count como en vendedor (fecha_vencimiento_pago y saldo > 0).
  - Cancelaciones del mes: count de ventas oficina con estado CANCELADA y cuya fecha de actualización o la solicitud de cancelación aprobada caiga en el mes.
- Template: sección Cartera con cards y, si hay riesgo, lista con enlace a venta.

**Criterio de listo:** El gerente ve cuentas por cobrar, número de ventas en riesgo y cancelaciones del mes. “Penalidades pagadas” se deja como pregunta o placeholder.

---

### Fase 4 – Inteligencia (comparativo, ranking, margen vs estándar, rentabilidad por tipo)
- Servicio:
  - `comparativo_oficinas(fecha_inicio, fecha_fin)`: agregar por oficina (ventas MXN, margen promedio, % conversión, etc.); devolver lista de oficinas con métricas y destacar la oficina del gerente.
  - `ranking_nacional_oficinas(fecha_inicio, fecha_fin, orden_por='ventas')`: ranking de oficinas; devolver posición y total para la oficina del gerente.
  - Constante o setting `MARGEN_ESTANDAR_CORPORATIVO` (ej. 0.15); en template o contexto mostrar margen oficina vs estándar.
  - Rentabilidad por tipo: misma lógica que “ventas por tipo” pero con utilidad o margen por tipo_viaje para la oficina.
- Vista: pasar comparativo, ranking, margen vs estándar y rentabilidad por tipo al contexto.
- Template: sección Inteligencia con comparativo (tabla o cards), “Tu oficina: posición X de N”, margen vs estándar y tabla por tipo de producto.

**Criterio de listo:** Gerente ve comparativo con otras oficinas, posición en ranking nacional, margen vs estándar y rentabilidad por tipo de producto.

---

### Fase 5 – Gastos por oficina (nuevo modelo / campos y uso en dashboard)
- **Modelo o campos:** Opción A: modelo `GastoOficina` (oficina, fecha, monto, segmento [ej. OPERATIVO, MARKETING, OTROS], concepto). Opción B: campos en Oficina por segmento (gasto_operativo_mensual, gasto_marketing_mensual, etc.) más histórico si se requiere. Definir con negocio.
- **Alta/edición de oficinas:** En el formulario o pantalla de oficinas, añadir rubro “Gastos por segmento” (o por tipo): captura por periodo (mes/año) y segmento; guardar en el nuevo modelo.
- **Dashboard gerente:**
  - Costo operativo: suma de gastos del segmento correspondiente para la oficina en el periodo.
  - Utilidad ya calculada en Fase 1; mostrar “Costo operativo vs utilidad” (y si se desea, “Utilidad neta” = utilidad - costo operativo).
  - ROI marketing local: (utilidad atribuible o ventas atribuibles) / gasto marketing en el periodo; definir fórmula con negocio.
- **Penalidades pagadas:** Si se define modelo o campo (por venta o por oficina/periodo), integrar en la sección Cartera en esta fase o en una siguiente.

**Criterio de listo:** Se registran gastos por oficina/segmento; el dashboard muestra costo operativo vs utilidad y ROI marketing (según definición acordada).

---

## 4. Preguntas para el negocio

1. **Periodo por defecto:** ¿El dashboard gerente abre en “Esta semana”, “Este mes” o “Mes anterior”?
2. **Cotizaciones para gerente:** Hoy las cotizaciones no se filtran por oficina a nivel global. Para “% Conversión global oficina” se filtrarán por vendedores de la oficina. ¿El gerente debe ver en el sistema solo cotizaciones de su oficina en listados/cotizaciones, o solo en el dashboard? (Si es en todo el sistema, habría que tocar permisos/cotizaciones.)
3. **Cancelaciones del mes:** ¿Contar ventas con estado CANCELADA cuya fecha de cambio a cancelada esté en el mes, o solicitudes de cancelación aprobadas en el mes? ¿Existe campo “fecha_cancelacion” en VentaViaje o solo se usa la fecha de la SolicitudCancelacion?
4. **Penalidades pagadas:** ¿Existe hoy algún registro de “penalidad pagada” (por venta, por cliente, por oficina) o debe diseñarse desde cero? Si es desde cero, ¿por venta cancelada, por oficina/periodo, o otro?
5. **Gastos por oficina:** Al dar de alta/editar oficinas, ¿los “gastos por segmento” son por periodo (ej. mensual) y se capturan mes a mes (histórico), o un solo monto vigente por segmento? ¿Qué segmentos se requieren además de Marketing y Operativo (ej. Nómina, Renta, Otros)?
6. **ROI de marketing local:** Fórmula deseada: ¿(Ventas del periodo atribuibles a la oficina) / (Gasto marketing del periodo), o (Utilidad) / (Gasto marketing), u otra?
7. **Comparativo vs otras oficinas:** ¿Se muestran nombres de oficinas o “Oficina 1”, “Oficina 2” por confidencialidad?
8. **Margen estándar corporativo:** ¿Qué valor usar (ej. 15%) y debe ser configurable por administrador en el futuro?
9. **Vendedores de la oficina:** Para “Ventas por empleado” y conteos, ¿contar solo usuarios con Ejecutivo.asociado a la oficina y que tengan ventas en el periodo, o todos los ejecutivos asignados a la oficina (activos) aunque no hayan vendido?

---

## 5. Resumen de archivos a tocar (estimado)

| Archivo | Cambio |
|---------|--------|
| `ventas/services/dashboard_gerente.py` | **Nuevo.** Funciones por bloque (KPIs, cartera, comparativo, ranking, etc.). |
| `ventas/views.py` | En `DashboardView.get_context_data`, bloque `user_rol == 'GERENTE'`: periodo, oficina, llamadas al servicio, contexto para template. |
| `templates/dashboard.html` | Bloque `{% if user_rol == 'GERENTE' %}`: selector periodo, secciones KPIs, Productividad, Cartera, Inteligencia. |
| `ventas/models.py` | Fase 5: modelo `GastoOficina` (o campos en Oficina) si se aprueba. |
| `ventas/forms.py` / pantalla oficinas | Fase 5: formulario o modal para gastos por segmento/periodo. |
| Config/settings | Opcional: `MARGEN_ESTANDAR_CORPORATIVO`, `DASHBOARD_GERENTE_PERIODO_DEFAULT`. |

---

## 6. Orden sugerido

Fase 0 → Fase 1 → Fase 2 → Fase 3 → Fase 4. Fase 5 (gastos y ROI) después de definir modelo y reglas de negocio con las preguntas anteriores. Con esto el dashboard gerente queda estructurado y ejecutable por fases; las preguntas permiten cerrar detalles antes de implementar gastos, penalidades y ROI.
