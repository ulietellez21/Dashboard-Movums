# Plan: Dashboard DIRECTOR ADMINISTRATIVO

## Objetivo
**Control total del dinero y riesgo financiero.**

---

## Análisis de requisitos

### 1. Flujo de efectivo

| KPI | Fuente de datos | Disponibilidad |
|-----|-----------------|----------------|
| Ingresos cobrados reales | Suma de `total_pagado` de ventas activas (abonos confirmados + apertura confirmada) | ✅ Existe |
| Ingresos por cobrar | Suma de `saldo_restante` de ventas activas con saldo > 0 | ✅ Existe |
| Pagos a proveedores pendientes | Suma de `AbonoProveedor.monto` donde estado ∈ {PENDIENTE, APROBADO} (aún no pagados) | ✅ Existe |
| Anticipos retenidos | ❓ Requiere definición (ver preguntas) | ❓ |
| Flujo proyectado 30-60-90 | Proyección por run-rate o fechas de vencimiento | ⚠️ Parcial |

### 2. Riesgo financiero

| KPI | Fuente de datos | Disponibilidad |
|-----|-----------------|----------------|
| Cancelaciones en proceso | `SolicitudCancelacion` con estado='PENDIENTE' | ✅ Existe |
| Penalidades acumuladas | No existe modelo de penalidades | ❌ No existe |
| Ventas sin anticipo suficiente | Ventas donde `cantidad_apertura` < umbral % del costo | ⚠️ Requiere umbral |
| Margen comprometido | Ventas con margen < X% (ej. 15%) | ✅ Existe |

### 3. Control interno

| KPI | Fuente de datos | Disponibilidad |
|-----|-----------------|----------------|
| Comisiones devengadas vs pagadas | `ComisionVenta`: Sum(comision_calculada) vs Sum(comision_pagada) | ✅ Existe |
| Diferencias contables | ❓ Requiere definición exacta | ❓ |
| Ventas sin soporte documental | Ventas con `comprobante_apertura_subido=False` cuando aplica; AbonoPago con `comprobante_subido=False` | ✅ Existe |

---

## Alcance del Director Administrativo

- **Scope:** Red completa (todas las ventas, oficinas, vendedores).
- **Periodo:** Semana, mes, mes anterior (igual que otros dashboards) + datos acumulados/snapshots cuando aplique.
- **Rol:** `DIRECTOR_ADMINISTRATIVO` ya tiene acceso a todas las ventas vía `get_ventas_queryset_base`.

---

## Plan de implementación por fases

### Fase 0 — Definiciones y respuestas a preguntas
- Resolver preguntas abiertas (ver abajo).
- Confirmar fórmulas exactas para cada KPI.

### Fase 1 — Módulo base + Flujo de efectivo
- Crear `ventas/services/dashboard_director_admin.py`.
- Ingresos cobrados reales.
- Ingresos por cobrar.
- Pagos a proveedores pendientes.
- Anticipos retenidos (si se define).
- Flujo proyectado 30-60-90 (run-rate o vencimientos).

### Fase 2 — Riesgo financiero
- Cancelaciones en proceso (tabla o lista).
- Penalidades acumuladas (omitir si no hay modelo).
- Ventas sin anticipo suficiente (tabla con umbral configurable).
- Margen comprometido (ventas con margen < 15%).

### Fase 3 — Control interno
- Comisiones devengadas vs pagadas.
- Diferencias contables (si se define).
- Ventas sin soporte documental (tabla filtrable).

### Fase 4 — Integración en vista y template
- Bloque `elif user_rol == 'DIRECTOR_ADMINISTRATIVO'` en `DashboardView`.
- Template HTML con selector de periodo y secciones.
- Permisos de notificaciones en JS si aplica.

### Fase 5 — Pruebas y deploy
- Verificación con datos reales.
- Commit y deploy.

---

## Preguntas para el cliente

1. **Anticipos retenidos:** ¿Qué significa exactamente? Opciones:
   - (A) Monto total de aperturas de ventas en estado `EN_CONFIRMACION` (aún no confirmadas por contador).
   - (B) Anticipos de clientes que no se han liberado a operación (requeriría modelo o proceso nuevo).
   - (C) Otra definición: _______.

2. **Flujo proyectado 30-60-90:** ¿Cómo se debe calcular?
   - (A) Run-rate: ingresos cobrados del periodo ÷ días transcurridos × 30/60/90.
   - (B) Por fechas de vencimiento: suma de saldos vencibles en cada ventana (30, 60, 90 días).
   - (C) Híbrido: run-rate para ingresos + vencimientos para por cobrar.

3. **Penalidades acumuladas:** No existe modelo de penalidades. ¿Se omite este KPI o hay otro lugar donde se registran?

4. **Ventas sin anticipo suficiente:** ¿Qué umbral usar? Ejemplo: anticipo < 10% del costo total de la venta, o solo ventas con cantidad_apertura = 0.

5. **Margen comprometido:** ¿Qué umbral de margen? (Sugerido: 15%, igual que en otros dashboards.)

6. **Diferencias contables:** ¿Qué se considera “diferencia contable”? Opciones:
   - (A) Ventas donde `costo_venta_final` no cuadra con la suma de abonos + cantidad_apertura (por redondeos).
   - (B) Abonos confirmados sin comprobante subido (TRN/TAR/DEP).
   - (C) Otra definición: _______.

7. **Ventas sin soporte documental:** ¿Incluir solo:
   - ventas con apertura sin comprobante (modo TRN/TAR/DEP),
   - o también abonos sin comprobante?
   - ¿O solo uno de los dos?

8. **Periodo:** ¿Selector semana / mes / mes anterior como los otros dashboards, o necesitas vista adicional (ej. acumulado año)?
