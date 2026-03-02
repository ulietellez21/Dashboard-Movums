# Plan de implementación: Dashboard de Vendedores

**Objetivo del dashboard:** Cerrar más y mejor. Margen sano. Cobranza eficiente.

**Alcance:** Los 3 tipos de vendedor (Asesor de Mostrador, Asesor de Campo, Asesor de Isla) comparten el mismo dashboard con KPIs filtrados por `vendedor=request.user`. Las diferencias por tipo se reflejan en comisiones y en la sección "Inteligencia" cuando existan otras oficinas/franquicias.

**Fecha:** 26 Feb 2026

---

## Índice de fases

| Fase | Nombre | Entregable principal |
|------|--------|----------------------|
| **0** | Preparación | Módulo `dashboard_vendedor.py` + selector periodo (sin KPIs nuevos) |
| **1** | Embudo y Ventas | KPIs embudo (5) + ventas cerradas MXN y por tipo |
| **2** | Cobranza y Comisiones | KPIs cobranza (4) + comisión proyectada/confirmada |
| **3** | Kilómetros Movums | Clientes fidelidad, km otorgados, recompras |
| **4** | Alertas automáticas | 4 alertas con lista y enlace |
| **5** | Competencia interna | Top 3 + posición del vendedor |
| **6** | Ajustes y pruebas | Configuración margen/días riesgo + tests |
| **7** | Inteligencia | Futuro (multi-oficina); solo documentado |

Las **preguntas para el negocio** están en la sección 4; conviene resolverlas antes o durante la Fase 1.

---

## 1. Estado actual del sistema

### 1.1 Dashboard actual
- **Vista:** `ventas/views.py` → `DashboardView` (template `templates/dashboard.html`).
- **Rol VENDEDOR:** Ya tiene bloque específico en `get_context_data` (líneas ~514-634):
  - Notificaciones propias.
  - `mi_saldo_pendiente`, `mis_ventas_cerradas`.
  - `cotizaciones_pendientes_vendedor` (cotizaciones no convertidas con días desde creación).
- **Filtro:** Queryset de ventas usa `perm.get_ventas_queryset_base`; para VENDEDOR filtra `vendedor=user`.
- No hay vista ni template dedicados solo a vendedores; el mismo dashboard muestra/u oculta secciones por rol.

### 1.2 Modelos y datos disponibles
| Dato | Modelo / Origen | Notas |
|------|-----------------|--------|
| Cotizaciones | `Cotizacion` (ventas) | `vendedor`, `creada_en`, `actualizada_en`, `estado` (BORRADOR, ENVIADA, CONVERTIDA) |
| Conversión cotización → venta | `VentaViaje.cotizacion_origen` | Una venta puede tener `cotizacion_origen_id` |
| Ventas | `VentaViaje` | `vendedor`, `costo_venta_final`, `costo_venta_final_usd`, `tipo_viaje` (NAC, INT, INT_MXN), `fecha_creacion`, `fecha_inicio_viaje` |
| Cobranza | `AbonoPago`, `cantidad_apertura` | `total_pagado` (propiedad), `fecha_vencimiento_pago` |
| Comisiones | `ComisionVenta`, `ComisionMensual` | Por vendedor, mes, año; comision_calculada, comision_pagada, comision_pendiente |
| Kilómetros Movums | `Cliente` (participa_kilometros, kilometros_disponibles), `HistorialKilometros` | `KilometrosService`, dashboard en `crm/kilometros_dashboard` |
| Cancelación | `SolicitudCancelacion` | estado PENDIENTE |
| Margen | No hay campo directo | Calcular: (costo_venta_final - costo_neto) / costo_venta_final * 100 (NAC); para INT usar costo_neto_usd y total USD |
| Tipo “corporativo” | No existe en modelo | Hoy solo NAC, INT, INT_MXN; definir si corporativo = etiqueta de cliente o futuro tipo_viaje |

### 1.3 Tipos de vendedor
- **Perfil.tipo_vendedor:** `MOSTRADOR`, `CAMPO`, `ISLA` (usado en comisiones; no cambia la vista del dashboard por ahora).
- **Ejecutivo:** vinculado a User (vendedor); tiene `tipo_vendedor`, `sueldo_base`, oficina.

---

## 2. Estructura del plan por bloques

### 2.1 KPIs obligatorios (vista diaria y mensual)

Se debe poder alternar **vista diaria** vs **vista mensual** (selector en el dashboard). Todos los KPIs se calculan para el periodo elegido (hoy vs mes actual).

| KPI | Definición | Fuente de datos | Vista |
|-----|------------|------------------|--------|
| **Cotizaciones generadas** | Cantidad de cotizaciones creadas por el vendedor en el periodo | `Cotizacion.objects.filter(vendedor=user, creada_en__date en periodo)` | Card + posible gráfica |
| **Cotizaciones activas** | Cotizaciones del vendedor no convertidas (estado ≠ CONVERTIDA) al cierre del periodo (o al día actual) | `Cotizacion.objects.filter(vendedor=user).exclude(estado='CONVERTIDA')` (filtro por fecha según criterio: creada_en en periodo o vigentes al corte) | Card |
| **% Conversión cotización → venta** | (Ventas del periodo con cotizacion_origen no null) / (Cotizaciones que “cerraron” en periodo o cotizaciones generadas en periodo) | Definir numerador: ventas con `cotizacion_origen` y `fecha_creacion` en periodo. Denominador: cotizaciones generadas en periodo (o cotizaciones enviadas que “podrían” cerrar en periodo). | Card |
| **Tiempo promedio de cierre** | Promedio de días entre `cotizacion_origen.creada_en` y `venta.fecha_creacion` para ventas del periodo con cotización | `VentaViaje` con `cotizacion_origen` + annotate días, luego Avg | Card |
| **Ticket promedio** | Sum(costo_venta_final en MXN) / count(ventas) en el periodo (INT convertido con tipo_cambio) | `VentaViaje` del vendedor en periodo; conversión INT → MXN ya usada en comisiones | Card |

**Implementación sugerida:**
- Añadir en `DashboardView.get_context_data` (dentro del bloque `user_rol == 'VENDEDOR'`) el cálculo de estos KPIs.
- Parámetros de periodo: `periodo = request.GET.get('periodo', 'mensual')` (valores: `mensual`, `diario`).
- Para “diario”: fecha_inicio = fecha_hasta = hoy.
- Para “mensual”: fecha_inicio = primer día del mes actual, fecha_hasta = último día del mes actual (o hoy si se prefiere “mes hasta hoy”).
- Crear un pequeño módulo de servicios opcional, p. ej. `ventas/services/dashboard_vendedor.py`, con funciones como `kpis_embudo(user, fecha_inicio, fecha_fin)` que devuelvan un dict con los KPIs del embudo para reutilizar y testear.

---

### 2.2 Ventas

| KPI | Definición | Fuente | Vista |
|-----|------------|--------|--------|
| **Ventas cerradas (MXN)** | Suma de `costo_venta_final` (y equivalentes en MXN para INT) de ventas del vendedor en el periodo con estado “cerrado”/liquidado (p. ej. total_pagado >= costo total) | `VentaViaje` filtrado por vendedor, fecha_creacion en periodo, y condición de liquidación | Card principal |
| **Ventas por tipo** | Desglose por tipo: Nacional, Internacional, Corporativo | Nacional = tipo_viaje NAC (e INT_MXN si se agrupa con nacional). Internacional = INT. Corporativo: a definir (¿cliente con flag corporativo o nuevo tipo?) | Cards o gráfica de barras |

**Implementación:**
- Reutilizar lógica de conversión INT→MXN que ya existe en comisiones.
- “Ventas cerradas” = ventas donde `total_pagado >= costo_total_con_modificacion` (o equivalente ya usado en el sistema).
- Si “corporativo” no existe, dejar sección preparada con NAC / INT / INT_MXN y añadir corporativo cuando el negocio lo defina.

---

### 2.3 Cobranza

| KPI | Definición | Fuente | Vista |
|-----|------------|--------|--------|
| **% ventas cobradas** | (Ventas del vendedor con total_pagado >= costo_total) / (Total ventas del vendedor) en periodo (por fecha de venta o por fecha de pago) | Mismo queryset de ventas del vendedor; contar liquidadas vs total | Card |
| **Monto pendiente de cobro** | Suma de saldo restante de ventas del vendedor (no canceladas) | `VentaViaje`: saldo_restante; filtrar vendedor, excluir estado CANCELADA | Card |
| **Anticipos** | Suma de `cantidad_apertura` (y apertura USD convertida si aplica) de ventas del vendedor en periodo o vigentes | `VentaViaje` del vendedor | Card |
| **Clientes en riesgo de cancelación por falta de pago** | Ventas del vendedor con saldo pendiente y fecha_vencimiento_pago &lt; hoy (o &lt; hoy + N días) | `VentaViaje` con `fecha_vencimiento_pago` pasado (y no canceladas) | Lista/alertas |

**Implementación:**
- Reutilizar `total_pagado` y `saldo_restante` de `VentaViaje`.
- Definir si “en riesgo” es solo vencido o también “por vencer en X días”; dejar parametrizable (ej. 7 días).

---

### 2.4 Comisiones

| KPI | Definición | Fuente | Vista |
|-----|------------|--------|--------|
| **Comisión proyectada** | Suma de comisiones calculadas (o pendientes de calcular) para el periodo (mes actual típicamente) | `ComisionVenta` por vendedor y mes/año, sum(comision_calculada); o cálculo en vivo si no hay registro aún | Card |
| **Comisión confirmada** | Parte ya pagada o confirmada (según regla de negocio) | `ComisionVenta`: sum(comision_pagada) o flag “confirmada” si existe en modelo | Card |

**Implementación:**
- Reutilizar lógica de `ComisionesVendedoresView` y `ventas/services/comisiones.py`.
- Para el dashboard, un solo número “comisión proyectada” (mes actual) y “comisión confirmada” (pagada o aprobada) del mes, sin duplicar toda la pantalla de comisiones.

---

### 2.5 Kilómetros Movums

| KPI | Definición | Fuente | Vista |
|-----|------------|--------|--------|
| **Clientes activos en fidelidad** | Clientes con `participa_kilometros=True` que tienen al menos una venta con este vendedor (o que el vendedor “atiende”) | Definir regla: p. ej. clientes cuya última venta es del vendedor, o clientes con al menos una venta del vendedor | Card / número |
| **Kilómetros otorgados** | Kilómetros acumulados por compras en ventas del vendedor (en el periodo o total) | `HistorialKilometros` con `venta__vendedor=user`, tipo_evento COMPRA (y no es_redencion) | Card |
| **Recompras generadas por fidelidad** | Clientes que tienen más de una venta y al menos una con este vendedor (recompra = 2ª venta en adelante atribuible al vendedor) | Clientes con count(ventas del vendedor) >= 2; o ventas donde el cliente ya tenía una venta previa (cualquier vendedor) y esta es del vendedor | Card |

**Implementación:**
- `HistorialKilometros` tiene `venta` FK; filtrar por `venta__vendedor=user`.
- “Clientes activos en fidelidad”: clientes con `participa_kilometros=True` y al menos una venta del vendedor.
- “Recompras”: contar ventas del vendedor donde el cliente ya tenía al menos una venta anterior (misma agencia); opcionalmente restringir a ventas que usaron kilómetros o promoción fidelidad.

---

### 2.6 Alertas automáticas

Todas las alertas deben ser para el vendedor logueado (sus cotizaciones, sus ventas, sus clientes).

| Alerta | Criterio | Fuente | Acción en UI |
|--------|----------|--------|--------------|
| **Cotización sin seguimiento > 48 hrs** | Cotizaciones del vendedor con estado ≠ CONVERTIDA y (now - actualizada_en) > 48 horas | `Cotizacion`: vendedor, actualizada_en | Lista con link a cotización |
| **Cliente con pago vencido** | Ventas del vendedor con fecha_vencimiento_pago &lt; hoy y saldo_restante > 0, no canceladas | `VentaViaje` | Lista con link a venta |
| **Venta con margen &lt; mínimo (15%)** | Margen = (costo_venta_final - costo_neto) / costo_venta_final &lt; 0.15 (para NAC; INT con costo_neto_usd y total USD) | `VentaViaje`: costo_neto, costo_venta_final (y USD si INT) | Lista con link a venta |
| **Cancelación solicitada** | Solicitudes de cancelación de ventas del vendedor en estado PENDIENTE | `SolicitudCancelacion` con venta__vendedor=user, estado=PENDIENTE | Lista con link a detalle/approval si aplica |

**Implementación:**
- Bloque de “Alertas” en el dashboard: una sección con 4 subbloques o pestañas.
- Cada alerta: queryset + lista en template con título, contador y enlace a la entidad.
- Margen mínimo: constante configurable (ej. 15%); dejarlo en settings o constante en el servicio del dashboard.

---

### 2.7 Inteligencia (fase posterior: cuando existan otras oficinas/franquicias)

Dejar **esqueleto o comentario** en el plan; implementación cuando el sistema tenga multi-oficina/franquicia.

| Elemento | Descripción |
|----------|-------------|
| Ranking personal vs otros vendedores | Posición del vendedor en ranking de ventas (o conversión) en su oficina/agencia |
| Margen promedio vs promedio general | Margen promedio del vendedor vs promedio de la oficina |
| Conversión por tipo de producto | % conversión desglosado por tipo (Nacional, Internacional, etc.) |
| Días promedio entre primer contacto y cierre | Promedio de días entre primera cotización/contacto y fecha_creacion de la venta |

**Nota:** Requiere definir “primer contacto” (¿primera cotización del cliente con el vendedor?) y scope (oficina vs global).

---

### 2.8 Competencia interna

| Elemento | Descripción | Fuente |
|----------|-------------|--------|
| Top 3 vendedores del mes | Ranking por ventas cerradas (MXN) en el mes | `VentaViaje` por vendedor, mes actual, orden por suma de ventas |
| Mejor conversión | Vendedor con mayor % conversión cotización→venta en el mes | Calcular % por vendedor y ordenar |
| Mejor margen | Vendedor con mayor margen promedio en el mes | Margen por venta, promedio por vendedor |
| Mayor recompra generada | Vendedor con más “recompras” (clientes con 2+ ventas donde la última o la recompra es del vendedor) | Lógica de recompras por vendedor |

**Implementación:**
- Para vendedores: mostrar “Tú estás en posición X” y los Top 3 (sin exponer montos de otros si no se desea; o sí según política).
- Querysets con `fecha_creacion` en mes actual; agrupar por vendedor. Scope: misma oficina cuando exista `Ejecutivo.oficina`; si no hay oficina, global.

---

## 3. Fases de implementación

Cada fase tiene entregables concretos y criterios de “listo”. Se puede validar y desplegar por fase.

---

### Fase 0 – Preparación (sin cambios de UI)

**Objetivo:** Dejar listo el módulo de servicio y el selector de periodo para vendedores.

**Entregables:**
- Crear `ventas/services/dashboard_vendedor.py` con:
  - Función auxiliar `_fechas_periodo(periodo)` que devuelve `(fecha_inicio, fecha_fin)` para `'diario'` y `'mensual'`.
  - Estructura de retorno estándar (dicts) para no romper la vista cuando se añadan KPIs.
- En `DashboardView.get_context_data` (bloque VENDEDOR):
  - Leer `periodo = request.GET.get('periodo', 'mensual')`.
  - Calcular `fecha_inicio`, `fecha_fin` con la función anterior.
  - Pasar al contexto: `periodo_vendedor`, `fecha_inicio`, `fecha_fin` (para el template).
- En `dashboard.html` (solo VENDEDOR): selector de periodo (diario / mensual) que recarga con `?periodo=diario` o `?periodo=mensual`.

**Criterio de listo:** Un vendedor ve el selector y al cambiar periodo la URL y el contexto cambian; aún no se muestran KPIs nuevos.

**Pregunta:** ¿Por defecto el dashboard del vendedor debe abrir en vista **diaria** o **mensual**?

---

### Fase 1 – Embudo comercial y Ventas

**Objetivo:** KPIs de embudo (cotizaciones, conversión, tiempo de cierre, ticket promedio) y de ventas (cerradas en MXN, por tipo).

**Entregables:**
- En `dashboard_vendedor.py`:
  - `kpis_embudo(user, fecha_inicio, fecha_fin)` → dict con: `cotizaciones_generadas`, `cotizaciones_activas`, `pct_conversion`, `tiempo_promedio_cierre_dias`, `ticket_promedio_mxn`.
  - `kpis_ventas(user, fecha_inicio, fecha_fin)` → dict con: `ventas_cerradas_mxn`, `ventas_cerradas_count`, desglose por tipo (`por_tipo`: ej. NAC, INT, INT_MXN).
- En `DashboardView`: llamar a ambas funciones y pasar resultados al contexto (ej. `kpis_embudo`, `kpis_ventas`).
- En `dashboard.html`: una fila de cards “Embudo” (5 números) y una fila “Ventas” (ventas cerradas MXN + desglose por tipo; por ahora sin “corporativo” si no existe en modelo).

**Criterio de listo:** El vendedor ve sus números de embudo y ventas según el periodo elegido; los números son coherentes con los datos en BD.

**Preguntas:**
- **Cotizaciones activas:** ¿Contamos solo las creadas en el periodo o todas las no convertidas vigentes a la fecha de corte?
- **% Conversión:** ¿Denominador = cotizaciones generadas en el periodo, o cotizaciones enviadas (estado ENVIADA) en el periodo?
- **Ventas por tipo:** ¿Mostramos solo NAC, INT e INT_MXN por ahora y dejamos “Corporativo” para cuando exista en el sistema?

---

### Fase 2 – Cobranza y Comisiones

**Objetivo:** KPIs de cobranza (% cobrado, pendiente, anticipos, clientes en riesgo) y de comisiones (proyectada, confirmada).

**Entregables:**
- En `dashboard_vendedor.py`:
  - `kpis_cobranza(user, fecha_inicio, fecha_fin)` → `pct_ventas_cobradas`, `monto_pendiente_cobro`, `anticipos_mxn`, lista `clientes_riesgo` (ventas con fecha_vencimiento_pago vencida y saldo > 0).
  - `kpis_comisiones(user, mes, anio)` → `comision_proyectada`, `comision_confirmada` (usar `ComisionVenta`/`ComisionMensual` del mes).
- Vista: llamar a ambas y pasar al contexto.
- Template: fila de cards “Cobranza” (4 KPIs) y card “Comisiones” (proyectada + confirmada). Subsección o lista colapsable “Clientes en riesgo” con link a cada venta.

**Criterio de listo:** El vendedor ve cobranza y comisiones; la lista de clientes en riesgo muestra solo sus ventas con pago vencido.

**Preguntas:**
- **Clientes en riesgo:** ¿Solo “vencido” (fecha_vencimiento_pago &lt; hoy) o también “por vencer en X días” (ej. 7)? Si es así, ¿cuántos días?
- **Comisión confirmada:** ¿Es exactamente `sum(comision_pagada)` de `ComisionVenta` del mes o hay otro criterio de negocio (ej. “aprobada por contador”)?

---

### Fase 3 – Kilómetros Movums

**Objetivo:** KPIs de fidelidad: clientes activos en programa, kilómetros otorgados por el vendedor, recompras generadas.

**Entregables:**
- En `dashboard_vendedor.py`:
  - `kpis_kilometros(user, fecha_inicio, fecha_fin)` → `clientes_activos_fidelidad` (count), `kilometros_otorgados` (sum de `HistorialKilometros` con venta del vendedor, tipo COMPRA, no redención), `recompras_generadas` (count de ventas del vendedor donde el cliente ya tenía al menos una venta previa).
- Vista y template: fila de cards “Kilómetros Movums” con los 3 números.

**Criterio de listo:** Los tres KPIs se calculan bien y el vendedor solo ve datos de sus propias ventas/clientes.

**Pregunta:**
- **Recompras:** ¿Contamos cualquier 2ª venta del mismo cliente (atribuida al vendedor) o solo cuando esa venta usó kilómetros/descuento fidelidad?

---

### Fase 4 – Alertas automáticas

**Objetivo:** Cuatro alertas con lista y enlace: cotización sin seguimiento &gt;48 h, cliente con pago vencido, venta con margen &lt; mínimo, cancelación solicitada.

**Entregables:**
- En `dashboard_vendedor.py`:
  - `alertas_vendedor(user)` → dict con cuatro listas: `cotizaciones_sin_seguimiento`, `ventas_pago_vencido`, `ventas_margen_bajo`, `solicitudes_cancelacion`.
  - Cálculo de margen en una función auxiliar (NAC: (costo_venta_final - costo_neto)/costo_venta_final; INT: análogo en USD). Margen mínimo parametrizable (constante o setting, ej. 15%).
- Vista: llamar a `alertas_vendedor` y pasar al contexto.
- Template: sección “Alertas” con 4 bloques (o pestañas). Cada uno: título, contador, lista de ítems con link a cotización/venta/detalle cancelación.

**Criterio de listo:** Las cuatro alertas se muestran solo con datos del vendedor; los enlaces llevan a la pantalla correcta.

**Preguntas:**
- **Margen mínimo:** ¿Confirmamos 15% o otro valor? ¿Debe ser configurable por administrador en el futuro?
- **Cotización sin seguimiento:** ¿Criterio es “actualizada_en hace más de 48 h” o hay campo explícito “último seguimiento”?

---

### Fase 5 – Competencia interna

**Objetivo:** Top 3 del mes (ventas, conversión, margen, recompra) y posición del vendedor logueado (“Tú estás en posición X”).

**Entregables:**
- En `dashboard_vendedor.py`:
  - `competencia_interna(user, mes, anio)` → listas/rankings por vendedor (scope: todos los vendedores si no hay oficina; si hay `Ejecutivo.oficina`, filtrar por oficina del user). Incluir: top 3 por ventas cerradas MXN, por % conversión, por margen promedio, por recompras; y posición del `user` en cada ranking.
- Vista: llamar con mes/año actual (o del periodo seleccionado si se prefiere).
- Template: sección “Competencia interna” con “Tu posición” y Top 3 (nombres; montos o solo posición según política de privacidad).

**Criterio de listo:** El vendedor ve su posición y el top 3 sin errores; el scope (global vs oficina) es coherente con el modelo de datos actual.

**Preguntas:**
- **Privacidad:** ¿En el Top 3 mostramos nombre del vendedor y monto/porcentaje, o solo “Puesto 1, 2, 3” sin nombres?
- **Oficina:** Hoy ¿todos los vendedores compiten en el mismo ranking global o ya existe oficina y debe filtrarse por la oficina del vendedor?

---

### Fase 6 – Ajustes, configuración y pruebas

**Objetivo:** Dejar parametrizables margen mínimo y días de riesgo, opcionalmente propiedad de margen en el modelo, y tests básicos.

**Entregables:**
- Constantes o settings: `DASHBOARD_VENDEDOR_MARGEN_MINIMO` (ej. 0.15), `DASHBOARD_VENDEDOR_DIAS_RIESGO_COBRO` (ej. 7 si se usa “por vencer”).
- Opcional: propiedad `margen_porcentaje` en `VentaViaje` (o función en servicio) para no duplicar lógica.
- Tests unitarios para `dashboard_vendedor.py`: al menos `kpis_embudo`, `kpis_ventas`, `alertas_vendedor` con datos fixture.
- Revisión de textos y etiquetas en español en el template.

**Criterio de listo:** Cambiar el margen mínimo o los días de riesgo no requiere tocar código de negocio; los tests pasan.

---

### Fase 7 – Inteligencia (futuro; fuera de alcance por ahora)

**Objetivo:** Cuando existan otras oficinas/franquicias, añadir sección “Inteligencia”: ranking personal vs otros, margen vs promedio general, conversión por tipo de producto, días promedio entre primer contacto y cierre.

**Entregables:** Solo documentado en este plan; sin desarrollo en las fases anteriores. Implementar cuando el modelo multi-oficina/franquicia esté definido.

---

## 4. Preguntas para el negocio (resumen)

Para poder implementar sin suposiciones, conviene definir:

1. **Periodo por defecto:** ¿Dashboard vendedor abre en vista diaria o mensual?
2. **Cotizaciones activas:** ¿Solo creadas en el periodo o todas las no convertidas vigentes al corte?
3. **% Conversión:** ¿Denominador = cotizaciones generadas en el periodo o solo enviadas en el periodo?
4. **Ventas por tipo:** ¿Por ahora solo NAC, INT, INT_MXN (corporativo después)?
5. **Clientes en riesgo:** ¿Solo vencido o también “por vencer en X días”? ¿Cuántos días?
6. **Comisión confirmada:** ¿Exactamente suma de `comision_pagada` del mes o hay otra regla?
7. **Recompras:** ¿Cualquier 2ª venta del cliente con el vendedor o solo ventas con uso de fidelidad?
8. **Margen mínimo:** ¿15% fijo o configurable? ¿Configurable por admin en el futuro?
9. **Cotización sin seguimiento:** ¿Criterio = “actualizada_en hace &gt;48 h”?
10. **Competencia interna:** ¿Mostrar nombres y montos en el Top 3 o solo posiciones? ¿Ranking global o por oficina ya?

---

## 5. Consideraciones técnicas

- **Rendimiento:** Evitar N+1; usar `annotate`/`aggregate` y `prefetch_related`/`select_related` en los querysets del servicio.
- **Moneda:** Consistencia MXN para reportes (INT convertido con `tipo_cambio` de la venta).
- **Permisos:** Todo el dashboard vendedor debe usar ya el filtro `vendedor=request.user`; no exponer datos de otros vendedores salvo en “Competencia interna” (solo posición y top 3).
- **Tests:** Añadir tests unitarios para las funciones de `dashboard_vendedor.py` (embudo, ventas, cobranza, alertas) con datos de prueba.
- **i18n:** Etiquetas en español; mantener coherencia con el resto del sistema.

---

## 6. Resumen de archivos a tocar

| Archivo | Cambio |
|---------|--------|
| `ventas/services/dashboard_vendedor.py` | **Nuevo.** Funciones de KPIs y alertas para vendedor. |
| `ventas/views.py` | En `DashboardView.get_context_data`, bloque VENDEDOR: llamadas al servicio + contexto periodo y KPIs. |
| `templates/dashboard.html` | Nuevas secciones para VENDEDOR: selector periodo, cards Embudo/Ventas/Cobranza/Comisiones/Km, Alertas, Competencia. |
| `ventas/models.py` | Opcional: propiedad `margen_porcentaje` en `VentaViaje` para reutilizar en alertas y rankings. |
| Config/settings | Opcional: `DASHBOARD_VENDEDOR_MARGEN_MINIMO = 0.15`, `DASHBOARD_VENDEDOR_DIAS_RIESGO_COBRO = 7`. |

---

## 7. Referencia: orden de desarrollo por fase

Seguir el orden **Fase 0 → Fase 1 → … → Fase 6**. Cada fase tiene sus entregables y criterio de listo en la sección 3. La Fase 7 (Inteligencia) queda para cuando existan otras oficinas/franquicias.

Con este plan se cubren todos los puntos solicitados para el dashboard de vendedores (los 3 tipos), se mantiene un solo dashboard y se deja preparada la extensión para Inteligencia cuando existan otras oficinas y franquicias.
