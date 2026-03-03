# Plan: Dashboard DIRECTOR GENERAL

## Objetivo
**Decidir expansión y dominar mercado.** Minimalista pero brutalmente claro.

---

## Análisis de requisitos

### 12 KPIs maestros

| KPI | Fuente de datos | Disponibilidad |
|-----|-----------------|----------------|
| Ventas totales | Sum(costo_venta_final) ventas activas | ✅ Existe |
| Utilidad neta | Sum(costo_venta_final - costo_neto) | ✅ Existe |
| Margen consolidado | Promedio ponderado de márgenes | ✅ Existe |
| Crecimiento mensual | MoM (mes actual vs anterior) | ✅ Existe |
| Crecimiento anual | YoY (mismo mes año anterior) | ✅ Existe |
| Ventas por oficina | Agregar por vendedor→ejecutivo→oficina | ✅ Existe |
| Ventas por canal | NAC, INT, INT_MXN, Corporativo | ✅ Existe |
| ROI marketing | Ingresos / gasto marketing | ❌ No hay modelo de gastos marketing |
| Recompra clientes | Clientes con 2+ ventas (count o %) | ✅ Existe |
| Ticket promedio | Ventas totales / count ventas | ✅ Existe |
| Cancelaciones % | (canceladas / total) × 100 en periodo | ✅ Existe |
| Flujo disponible | Ingresos cobrados - pagos pendientes (proveedores) | ✅ Existe |

### Expansión

| KPI | Fuente de datos | Disponibilidad |
|-----|-----------------|----------------|
| Rentabilidad por oficina | Utilidad y margen por oficina | ✅ Existe |
| Potencial franquicia por ciudad | Necesita dimensión "ciudad" | ❓ No hay campo ciudad estructurado |
| Ranking ciudades | Mismo | ❓ |
| Penetración por segmento | % NAC, INT, Corporativo del total | ✅ Existe |

### Inteligencia estratégica

| KPI | Fuente de datos | Disponibilidad |
|-----|-----------------|----------------|
| Dependencia de proveedores | % ventas por proveedor (Top 3 = X%) | ✅ Existe (VentaViaje.proveedor) |
| Concentración de ingresos | % por vendedor/oficina/canal (ej. Top 5) | ✅ Existe |
| Temporadas pico vs valle | Ventas por mes (últimos 12–24 meses) | ✅ Existe (fecha_creacion) |
| Elasticidad de precios | Histórico avg precio vs actual | ⚠️ Requiere definición precisa |

---

## Alcance del Director General

- **Scope:** Red completa.
- **Periodo:** Semana, mes, mes anterior (consistente con otros dashboards).
- **Rol:** `DIRECTOR_GENERAL` ya tiene acceso a todas las ventas.
- **Estilo:** Minimalista, KPIs grandes y claros.

---

## Plan de implementación por fases

### Fase 0 — Definiciones y preguntas
- Resolver preguntas (ver abajo).
- Confirmar fórmulas y omitir lo que no tenga datos.

### Fase 1 — 12 KPIs maestros
- Cards principales: ventas, utilidad, margen, crecimiento MoM/YoY.
- Desglose: ventas por oficina, ventas por canal.
- Recompra, ticket promedio, cancelaciones %, flujo disponible.
- Omitir ROI marketing si no hay datos.

### Fase 2 — Expansión
- Rentabilidad por oficina (tabla o cards).
- Potencial franquicia / Ranking ciudades: según respuesta a preguntas.
- Penetración por segmento (barras o %).

### Fase 3 — Inteligencia estratégica
- Dependencia de proveedores (Top N + %).
- Concentración de ingresos (por vendedor, oficina, canal).
- Temporadas pico vs valle (gráfica o tabla mensual).
- Elasticidad de precios (según definición).

### Fase 4 — Integración
- Bloque en `DashboardView` para `DIRECTOR_GENERAL`.
- Template HTML minimalista.
- Permisos notificaciones JS.

### Fase 5 — Commit y deploy

---

## Implementado (respuestas del cliente)

- ROI marketing: omitido
- Potencial franquicia / Ranking ciudades: omitido por ahora
- Penetración: NAC, INT, INT_MXN, Corporativo
- Temporadas: últimos 12 meses
- Elasticidad: ticket histórico 12 meses vs mes actual
- Periodo: semana/mes/mes anterior

---

## Preguntas para el cliente (archivadas)

1. **ROI marketing:** No existe modelo de gastos de marketing. ¿Se omite este KPI o hay otro lugar donde se registren (ej. Excel, otro sistema)?

2. **Potencial franquicia por ciudad / Ranking ciudades:** Oficina no tiene campo "ciudad" estructurado. Opciones:
   - (A) Inferir ciudad desde `Oficina.direccion` (parsear o etiquetar manual).
   - (B) Usar ciudad del **cliente** (si existe o se agrega).
   - (C) Usar **nombre de oficina** como proxy (ej. "Movums CDMX", "Movums Guadalajara") y agrupar ventas por oficina.
   - (D) Omitir estos dos KPIs hasta tener un campo ciudad.

3. **Penetración por segmento:** ¿Quieres solo NAC / INT / INT_MXN / Corporativo (como en Director Ventas) o segmentos distintos?

4. **Temporadas pico vs valle:** ¿Rango temporal? (últimos 12 meses, últimos 24 meses).

5. **Elasticidad de precios — "En cuanto se ha vendido vs Cuanto se vende actualmente":** ¿Qué métrica prefieres?
   - (A) Ticket promedio histórico (últimos N meses) vs ticket promedio del mes actual.
   - (B) Precio promedio por producto/destino comparando periodos.
   - (C) Otra definición: _______.

6. **Periodo:** ¿Selector semana / mes / mes anterior como los demás dashboards?

7. **Estilo minimalista:** ¿Prefieres muchas cards pequeñas o pocas cards grandes con los 12 KPIs principales? ¿Algún orden de prioridad para los 12?
