# Análisis Detallado del Sistema de Kilómetros Movums

**Fecha de Análisis**: Enero 2026  
**Última Actualización**: Enero 2026  
**Estado de Implementación**: Fase 1 Completada ✅  
**Objetivo**: Analizar la estructura actual, identificar puntos débiles y proponer mejoras para un sistema robusto y bien estructurado.

---

## 1. Estructura Actual del Sistema

### 1.1 Modelos de Datos

#### **Cliente** (`crm/models.py`)
- **Campos de Kilómetros**:
  - `participa_kilometros` (Boolean): Indica si el cliente participa en el programa
  - `kilometros_acumulados` (Decimal): Total histórico de kilómetros acumulados
  - `kilometros_disponibles` (Decimal): Kilómetros disponibles para redimir
  - `ultima_fecha_km` (DateTime): Última fecha de acumulación
  - `fecha_ultimo_bono_cumple` (Date): Control para bonos de cumpleaños anuales
  - `referido_por` (ForeignKey): Cliente que refirió a este cliente

#### **HistorialKilometros** (`crm/models.py`)
- **Campos Clave**:
  - `cliente` (ForeignKey): Cliente asociado
  - `tipo_evento` (CharField): Tipo de movimiento (COMPRA, REFERIDO, CUMPLE, CAMPANIA, AJUSTE, REDENCION, EXPIRACION)
  - `kilometros` (Decimal): Cantidad de kilómetros (positivo para acumulación, negativo para redención/expiracion)
  - `venta` (ForeignKey, nullable): Venta asociada (si aplica)
  - `es_redencion` (Boolean): Indica si es una redención
  - `expirado` (Boolean): Indica si ya fue procesado para expiración
  - `fecha_expiracion` (DateTime): Fecha de expiración del movimiento
  - `valor_equivalente` (Decimal): Valor en pesos MXN equivalente
  - `multiplicador` (Decimal): Multiplicador aplicado (para promociones especiales)

#### **PromocionKilometros** (`crm/models.py`)
- **Tipos de Promoción**:
  - `DESCUENTO`: Descuento porcentual sobre el total
  - `KM`: Bonificación de kilómetros
- **Campos Clave**:
  - `kilometros_bono` (Decimal): Kilómetros a bonificar (solo para tipo KM)
  - `porcentaje_descuento` (Decimal): Porcentaje de descuento (solo para tipo DESCUENTO)
  - `monto_tope_mxn` (Decimal): Tope máximo del descuento
  - `condicion` (CharField): Condición de aplicación (SIEMPRE, CUMPLE, MES, RANGO)
  - `alcance` (CharField): Alcance (TODAS, NAC, INT)
  - `activa` (Boolean): Estado de la promoción

#### **VentaPromocionAplicada** (`ventas/models.py`)
- **Campos Clave**:
  - `venta` (ForeignKey): Venta donde se aplicó la promoción
  - `promocion` (ForeignKey): Promoción aplicada
  - `km_bono` (Decimal): **Kilómetros bonificados (NO se acumulan automáticamente)**
  - `monto_descuento` (Decimal): Monto de descuento aplicado
  - `porcentaje_aplicado` (Decimal): Porcentaje aplicado

### 1.2 Servicios

#### **KilometrosService** (`crm/services.py`)
- **Constantes**:
  - `KM_POR_PESO = 0.5`: Cada $1 MXN = 0.5 km
  - `VALOR_PESO_POR_KM = 0.05`: Cada km = $0.05 MXN
  - `MAX_PORCENTAJE_REDENCION = 0.10`: Máximo 10% del total de la venta
  - `VIGENCIA_DIAS = 730`: 24 meses de vigencia
  - `BONO_REFERIDO = 2000`: Bono por referido
  - `BONO_CUMPLE = 1000`: Bono por cumpleaños

- **Métodos Principales**:
  - `acumular_por_compra()`: Acumula kilómetros por compra
  - `redimir()`: Redime kilómetros aplicados a una venta
  - `otorgar_referido()`: Otorga bono por referido
  - `otorgar_cumple()`: Otorga bono de cumpleaños
  - `expirar_kilometros()`: Procesa expiraciones automáticas
  - `revertir_por_cancelacion()`: **NUEVO** - Revierte kilómetros de ventas canceladas

#### **PromocionesService** (`ventas/services/promociones.py`)
- **Método Principal**:
  - `obtener_promos_aplicables()`: Evalúa y retorna promociones aplicables a una venta

---

## 2. Flujo Actual Completo

### 2.1 Creación de Venta (`VentaViajeCreateView`)

**Secuencia de eventos**:

1. **Validación del formulario** (`VentaViajeForm`)
   - Se evalúan promociones aplicables
   - Se calculan descuentos y bonos de kilómetros
   - Se guardan en `VentaPromocionAplicada` con `km_bono`

2. **Guardado de la venta**
   - Se guarda la instancia de `VentaViaje`
   - Se guardan las promociones aplicadas (ManyToMany through `VentaPromocionAplicada`)

3. **Procesamiento de Kilómetros Movums** (en `form_valid`):
   - **PRIMERO**: Redención de kilómetros (si aplica descuento)
     - Si `aplica_descuento_kilometros = True` y `descuento_kilometros_mxn > 0`
     - Calcula: `km_a_redimir = descuento_kilometros_mxn / 0.05`
     - Llama a `KilometrosService.redimir()`
     - Crea registro en `HistorialKilometros` con `tipo_evento='REDENCION'`
   
   - **DESPUÉS**: Acumulación por compra
     - Calcula: `monto_para_acumular = costo_venta_final - descuento_kilometros_mxn`
     - Llama a `KilometrosService.acumular_por_compra()`
     - Crea registro en `HistorialKilometros` con `tipo_evento='COMPRA'`
     - Actualiza `cliente.kilometros_acumulados` y `cliente.kilometros_disponibles`

4. **⚠️ PROBLEMA CRÍTICO**: Los bonos de kilómetros de promociones (`km_bono`) **NO se acumulan**
   - Se guardan en `VentaPromocionAplicada.km_bono`
   - Se muestran en el resumen de promociones
   - **PERO NO se crean registros en `HistorialKilometros`**
   - **NO se suman a `cliente.kilometros_disponibles`**

### 2.2 Actualización de Venta (`VentaViajeUpdateView`)

**Secuencia de eventos**:

1. Se obtienen valores anteriores de la venta
2. Se guarda la nueva instancia
3. Se comparan valores de descuento de kilómetros:
   - Si se aplica descuento por primera vez → redime kilómetros
   - Si el descuento aumenta → redime kilómetros adicionales
   - Si el descuento disminuye → **NO se revierten kilómetros ya redimidos** ⚠️

4. **⚠️ PROBLEMA**: No se manejan cambios en promociones aplicadas
   - Si se agregan/eliminan promociones con `km_bono`, no se acumulan/revierten kilómetros
   - Si cambia el `km_bono` de una promoción, no se ajustan los kilómetros

### 2.3 Cancelación de Venta (`CancelarVentaView`)

**Secuencia de eventos** (después de la mejora implementada):

1. Se cambia el estado a `'CANCELADA'`
2. Se llama a `KilometrosService.revertir_por_cancelacion()`
3. Se buscan todos los movimientos positivos asociados a la venta
4. Se crean registros de reversión (tipo `'AJUSTE'` con kilómetros negativos)
5. Se restan los kilómetros del cliente

**✅ MEJORA IMPLEMENTADA**: Ahora se revierten automáticamente los kilómetros acumulados por compra.

**⚠️ PROBLEMA PENDIENTE**: Si hubiera bonos de promociones acumulados, no se revertirían porque no existen registros en `HistorialKilometros`.

### 2.4 Expiración de Kilómetros (`KilometrosService.expirar_kilometros()`)

**Secuencia de eventos**:

1. Busca movimientos con `fecha_expiracion < hoy` y `expirado=False`
2. Crea registros de expiración (tipo `'EXPIRACION'` con kilómetros negativos)
3. Resta kilómetros disponibles del cliente
4. Marca el movimiento original como `expirado=True`

**✅ FUNCIONA CORRECTAMENTE**

---

## 3. Puntos Débiles Identificados

### 3.1 🔴 CRÍTICO: Bonos de Kilómetros de Promociones No Se Acumulan

**Problema**:
- Los bonos de kilómetros (`km_bono`) de promociones tipo `'KM'` se guardan en `VentaPromocionAplicada.km_bono`
- Se muestran en el resumen de promociones
- **PERO NO se acumulan al cliente**
- **NO se crean registros en `HistorialKilometros`**
- **NO se suman a `cliente.kilometros_disponibles`**

**Impacto**:
- Los clientes no reciben los kilómetros prometidos por las promociones
- Pérdida de confianza en el programa de lealtad
- Inconsistencia entre lo mostrado y lo acumulado

**Evidencia**:
- En `VentaViajeCreateView.form_valid()` (líneas 1302-1341) solo se procesa:
  - Redención de kilómetros (si aplica descuento)
  - Acumulación por compra
  - **NO hay lógica para acumular `km_bono` de promociones**

### 3.2 🟡 MEDIO: No Se Manejan Cambios en Promociones al Actualizar Venta

**Problema**:
- Si se agregan promociones con `km_bono` al actualizar una venta, no se acumulan
- Si se eliminan promociones con `km_bono`, no se revierten
- Si cambia el `km_bono` de una promoción, no se ajustan los kilómetros

**Impacto**:
- Inconsistencias en el historial de kilómetros
- Diferencias entre lo mostrado y lo acumulado

### 3.3 🟡 MEDIO: No Se Revierte Redención al Cancelar Venta

**Problema**:
- Si una venta tiene kilómetros redimidos y se cancela, los kilómetros redimidos **NO se devuelven**
- Solo se revierten los kilómetros acumulados por compra

**Impacto**:
- Pérdida de kilómetros del cliente si se cancela una venta después de redimir
- Inconsistencia en el balance de kilómetros

**Evidencia**:
- En `KilometrosService.revertir_por_cancelacion()` (líneas 240-245) solo se buscan movimientos con `kilometros__gt=0` y `es_redencion=False`
- Las redenciones (`es_redencion=True`) no se revierten

### 3.4 🟡 MEDIO: Falta Validación de Consistencia

**Problema**:
- No hay validación que asegure que `cliente.kilometros_disponibles` coincida con la suma de movimientos no expirados
- No hay validación que asegure que `cliente.kilometros_acumulados` coincida con la suma de todos los movimientos positivos

**Impacto**:
- Posibles inconsistencias en los datos
- Difícil detectar errores en el sistema

### 3.5 🟢 BAJO: Falta Tipo de Evento Específico para Bonos de Promociones

**Problema**:
- Los bonos de promociones deberían tener un tipo de evento específico (ej: `'PROMOCION'` o `'BONO_PROMOCION'`)
- Actualmente solo existe `'CAMPANIA'` que no se usa

**Impacto**:
- Dificulta el seguimiento y reportes de bonos de promociones
- No se puede distinguir entre diferentes tipos de bonos

### 3.6 🟢 BAJO: Falta Manejo de Reversión de Bonos al Actualizar Promociones

**Problema**:
- Si se actualiza una venta y se elimina una promoción con `km_bono`, no se revierten los kilómetros
- Si se cambia el `km_bono` de una promoción, no se ajustan los kilómetros

**Impacto**:
- Inconsistencias si se modifican promociones después de aplicarlas

### 3.7 🟢 BAJO: Falta Documentación de Flujos

**Problema**:
- No hay documentación clara del flujo completo de kilómetros
- No hay documentación de cómo se manejan los diferentes tipos de eventos

**Impacto**:
- Dificulta el mantenimiento y la comprensión del sistema
- Mayor probabilidad de introducir errores

---

## 4. Plan de Mejoras Estructurado

### ✅ Fase 1: Corrección de Funcionalidad Crítica - COMPLETADA

**Fecha de Implementación**: Enero 2026  
**Estado**: ✅ Completada

#### Implementaciones Realizadas:

1. ✅ **Nuevos Tipos de Evento en HistorialKilometros**:
   - `'BONO_PROMOCION'`: Para bonos de promociones tipo KM
   - `'REVERSION_CANCELACION'`: Para reversiones de acumulaciones por cancelación
   - `'REVERSION_REDENCION'`: Para reversiones de redenciones por cancelación
   - Migración aplicada: `crm/migrations/0014_agregar_tipos_evento_kilometros.py`
   - Campo `tipo_evento` actualizado a `max_length=25`

2. ✅ **Métodos en KilometrosService**:
   - `acumular_bono_promocion()`: Acumula kilómetros bonificados por promociones
   - `revertir_bono_promocion()`: Revierte bonos de promociones
   - `revertir_por_cancelacion()` mejorado: Ahora también revierte redenciones

3. ✅ **VentaViajeCreateView**:
   - Acumula automáticamente bonos de promociones tipo 'KM' al crear venta
   - Crea registros en `HistorialKilometros` con tipo `'BONO_PROMOCION'`

4. ✅ **VentaViajeUpdateView**:
   - Detecta cambios en promociones aplicadas
   - Acumula bonos de promociones nuevas
   - Revierte bonos de promociones eliminadas
   - Ajusta bonos si cambió el `km_bono`

5. ✅ **CancelarVentaView**:
   - Revierte acumulaciones (compra y bonos de promociones)
   - Devuelve kilómetros redimidos
   - Mensajes informativos mejorados

### Fase 1: Corrección de Funcionalidad Crítica ⚠️ PRIORIDAD ALTA (COMPLETADA)

#### 1.1 Implementar Acumulación de Bonos de Promociones

**Objetivo**: Acumular automáticamente los kilómetros bonificados por promociones tipo `'KM'`.

**Tareas**:
1. Agregar nuevo tipo de evento `'PROMOCION'` o `'BONO_PROMOCION'` en `HistorialKilometros.TIPO_EVENTO`
2. Crear método `KilometrosService.acumular_bono_promocion()`:
   ```python
   @classmethod
   def acumular_bono_promocion(cls, cliente, kilometros, venta, promocion, descripcion=''):
       """Acumula kilómetros bonificados por una promoción."""
   ```
3. Modificar `VentaViajeCreateView.form_valid()`:
   - Después de acumular por compra, iterar sobre `form.promos_km`
   - Para cada promoción con `km_bono > 0`, llamar a `acumular_bono_promocion()`
   - Crear registro en `HistorialKilometros` con `tipo_evento='PROMOCION'`
4. Modificar `VentaViajeUpdateView.form_valid()`:
   - Comparar promociones anteriores vs nuevas
   - Acumular bonos de promociones nuevas
   - Revertir bonos de promociones eliminadas
   - Ajustar bonos si cambió el `km_bono`

**Archivos a Modificar**:
- `crm/models.py`: Agregar tipo de evento
- `crm/services.py`: Agregar método `acumular_bono_promocion()`
- `ventas/views.py`: Modificar `VentaViajeCreateView` y `VentaViajeUpdateView`

**Estimación**: 4-6 horas

#### 1.2 Implementar Reversión de Redenciones al Cancelar

**Objetivo**: Devolver kilómetros redimidos cuando se cancela una venta.

**Tareas**:
1. Modificar `KilometrosService.revertir_por_cancelacion()`:
   - Buscar también movimientos con `es_redencion=True` y `kilometros < 0`
   - Crear registros de reversión que devuelvan los kilómetros redimidos
   - Sumar kilómetros de vuelta a `cliente.kilometros_disponibles`

**Archivos a Modificar**:
- `crm/services.py`: Modificar `revertir_por_cancelacion()`

**Estimación**: 2-3 horas

---

### Fase 2: Mejoras de Consistencia y Validación ⚠️ PRIORIDAD MEDIA

#### 2.1 Implementar Validación de Consistencia

**Objetivo**: Asegurar que los totales del cliente coincidan con el historial.

**Tareas**:
1. Crear método `KilometrosService.validar_consistencia_cliente(cliente)`:
   ```python
   @classmethod
   def validar_consistencia_cliente(cls, cliente):
       """Valida que los totales del cliente coincidan con el historial."""
       # Calcular totales desde HistorialKilometros
       # Comparar con cliente.kilometros_acumulados y cliente.kilometros_disponibles
       # Retornar dict con diferencias si las hay
   ```
2. Crear comando de gestión `python manage.py validar_kilometros`:
   - Valida todos los clientes
   - Reporta inconsistencias
   - Opción para corregir automáticamente

**Archivos a Crear/Modificar**:
- `crm/services.py`: Agregar método de validación
- `crm/management/commands/validar_kilometros.py`: Crear comando

**Estimación**: 3-4 horas

#### 2.2 Implementar Manejo de Cambios en Promociones

**Objetivo**: Manejar correctamente cambios en promociones al actualizar ventas.

**Tareas**:
1. Crear método `KilometrosService.revertir_bono_promocion()`:
   ```python
   @classmethod
   def revertir_bono_promocion(cls, cliente, kilometros, venta, promocion, descripcion=''):
       """Revierte kilómetros bonificados por una promoción."""
   ```
2. Modificar `VentaViajeUpdateView.form_valid()`:
   - Comparar `VentaPromocionAplicada` anteriores vs nuevas
   - Identificar promociones agregadas, eliminadas y modificadas
   - Acumular/revertir/ajustar kilómetros según corresponda

**Archivos a Modificar**:
- `crm/services.py`: Agregar método de reversión
- `ventas/views.py`: Modificar `VentaViajeUpdateView`

**Estimación**: 4-5 horas

---

### ✅ Fase 3: Mejoras de Estructura y Documentación - COMPLETADA

**Fecha de Implementación**: Enero 2026  
**Estado**: ✅ Completada

#### Implementaciones Realizadas:

1. ✅ **Logging Mejorado**:
   - Logging detallado con IDs de cliente y venta
   - Resúmenes de operaciones
   - Mejor trazabilidad

2. ✅ **Métricas del Sistema**:
   - Método `obtener_metricas_sistema()` en `KilometrosService`
   - Comando `python manage.py metricas_kilometros`
   - Formatos: simple, detallado, json

3. ✅ **Validaciones de Negocio**:
   - Validaciones existentes mejoradas y documentadas
   - Mejor manejo de errores

### Fase 3: Mejoras de Estructura y Documentación ⚠️ PRIORIDAD BAJA (COMPLETADA)

#### 3.1 Refactorizar Lógica de Kilómetros en Vistas

**Objetivo**: Centralizar la lógica de kilómetros en el servicio.

**Tareas**:
1. Crear método `KilometrosService.procesar_venta_completa()`:
   ```python
   @classmethod
   def procesar_venta_completa(cls, venta, promociones_aplicadas=None):
       """
       Procesa todos los aspectos de kilómetros para una venta:
       - Redención (si aplica)
       - Acumulación por compra
       - Bonos de promociones
       """
   ```
2. Mover lógica de `VentaViajeCreateView` y `VentaViajeUpdateView` al servicio
3. Simplificar las vistas para que solo llamen al servicio

**Archivos a Modificar**:
- `crm/services.py`: Agregar método principal
- `ventas/views.py`: Simplificar vistas

**Estimación**: 5-6 horas

#### 3.2 Agregar Señales Django para Automatización

**Objetivo**: Automatizar acumulación de kilómetros usando señales.

**Tareas**:
1. Crear señal `post_save` para `VentaViaje`:
   - Detecta cuando se crea/actualiza una venta
   - Llama a `KilometrosService.procesar_venta_completa()`
2. Crear señal `post_save` para `VentaPromocionAplicada`:
   - Detecta cuando se agrega una promoción con `km_bono`
   - Acumula los kilómetros automáticamente
3. Crear señal `pre_delete` para `VentaPromocionAplicada`:
   - Detecta cuando se elimina una promoción con `km_bono`
   - Revierte los kilómetros automáticamente

**Archivos a Crear/Modificar**:
- `ventas/signals.py`: Crear señales (o agregar a existente)
- `ventas/apps.py`: Registrar señales

**Estimación**: 4-5 horas

#### 3.3 Mejorar Tipos de Evento en HistorialKilometros

**Objetivo**: Tener tipos de evento más específicos y claros.

**Tareas**:
1. Agregar nuevos tipos de evento:
   - `'BONO_PROMOCION'`: Bonos de promociones tipo KM
   - `'REVERSION_CANCELACION'`: Reversión por cancelación de venta
   - `'REVERSION_REDENCION'`: Reversión de redención (al cancelar)
2. Migrar registros existentes si es necesario
3. Actualizar documentación

**Archivos a Modificar**:
- `crm/models.py`: Agregar tipos de evento
- Crear migración para actualizar registros existentes

**Estimación**: 2-3 horas

#### 3.4 Crear Documentación Completa

**Objetivo**: Documentar todos los flujos y casos de uso.

**Tareas**:
1. Crear documento de flujos principales:
   - Creación de venta
   - Actualización de venta
   - Cancelación de venta
   - Expiración de kilómetros
   - Aplicación de promociones
2. Crear diagramas de flujo (opcional)
3. Documentar casos edge:
   - Venta cancelada y luego reactivada
   - Promociones modificadas después de aplicar
   - Cliente que deja de participar en el programa

**Archivos a Crear**:
- `docs/FLUJO_KILOMETROS_MOVUMS.md`: Documentación completa

**Estimación**: 3-4 horas

---

## 5. Resumen de Prioridades

### 🔴 CRÍTICO (Implementar Inmediatamente)
1. **Acumular bonos de promociones** - Los clientes no reciben kilómetros prometidos
2. **Revertir redenciones al cancelar** - Pérdida de kilómetros del cliente

### 🟡 IMPORTANTE (Implementar en Próxima Iteración)
3. **Validación de consistencia** - Detectar y corregir errores
4. **Manejo de cambios en promociones** - Evitar inconsistencias

### 🟢 MEJORAS (Implementar cuando sea posible)
5. **Refactorizar lógica** - Mejor mantenibilidad
6. **Señales Django** - Automatización
7. **Mejorar tipos de evento** - Mejor trazabilidad
8. **Documentación** - Facilitar mantenimiento

---

## 6. Recomendaciones Adicionales

### 6.1 Testing
- Crear tests unitarios para `KilometrosService`
- Crear tests de integración para flujos completos
- Tests para casos edge (cancelaciones, reversiones, etc.)

### 6.2 Monitoreo
- Agregar logging detallado en todas las operaciones de kilómetros
- Crear dashboard de métricas de kilómetros
- Alertas para inconsistencias detectadas

### 6.3 Performance
- Optimizar consultas de `HistorialKilometros` con índices
- Considerar agregación de totales en lugar de calcular siempre desde historial
- Cachear resúmenes de kilómetros cuando sea posible

---

## 7. Conclusión

El sistema de Kilómetros Movums tiene una base sólida pero presenta **problemas críticos** en la acumulación de bonos de promociones y en la reversión de redenciones. El plan propuesto aborda estos problemas de manera estructurada, priorizando las correcciones críticas y luego mejorando la consistencia y mantenibilidad del sistema.

**Próximo Paso Recomendado**: Implementar la Fase 1 (Corrección de Funcionalidad Crítica) para resolver los problemas más urgentes antes de continuar con mejoras adicionales.









