# Implementación Fase 1 - Sistema de Kilómetros Movums

**Fecha de Implementación**: Enero 2026  
**Estado**: ✅ Completada

---

## Resumen de Cambios

### 1. Modelos Actualizados

#### **HistorialKilometros** (`crm/models.py`)
- ✅ Agregados nuevos tipos de evento:
  - `'BONO_PROMOCION'`: Bonos de promociones tipo KM
  - `'REVERSION_CANCELACION'`: Reversión de acumulaciones por cancelación
  - `'REVERSION_REDENCION'`: Reversión de redenciones por cancelación
- ✅ Campo `tipo_evento` actualizado a `max_length=25` (antes 12)

**Migración**: `crm/migrations/0014_agregar_tipos_evento_kilometros.py`

---

### 2. Servicios Actualizados

#### **KilometrosService** (`crm/services.py`)

**Nuevos Métodos**:

1. **`acumular_bono_promocion()`**:
   ```python
   @classmethod
   def acumular_bono_promocion(cls, cliente, kilometros, venta=None, promocion=None, descripcion=''):
       """Acumula kilómetros bonificados por una promoción tipo 'KM'."""
   ```
   - Crea registro en `HistorialKilometros` con tipo `'BONO_PROMOCION'`
   - Actualiza `cliente.kilometros_acumulados` y `cliente.kilometros_disponibles`
   - Transaccional (atomic)

2. **`revertir_bono_promocion()`**:
   ```python
   @classmethod
   def revertir_bono_promocion(cls, cliente, kilometros, venta=None, promocion=None, descripcion=''):
       """Revierte kilómetros bonificados por una promoción."""
   ```
   - Crea registro de reversión (tipo `'AJUSTE'` con kilómetros negativos)
   - Resta kilómetros del cliente
   - Transaccional (atomic)

**Método Mejorado**:

3. **`revertir_por_cancelacion()`**:
   - ✅ Ahora también busca y revierte redenciones (`es_redencion=True`)
   - ✅ Crea registros de tipo `'REVERSION_CANCELACION'` para acumulaciones
   - ✅ Crea registros de tipo `'REVERSION_REDENCION'` para devolver redenciones
   - ✅ Retorna dict con `km_totales` (revertidos) y `km_devueltos` (redenciones)

---

### 3. Vistas Actualizadas

#### **VentaViajeCreateView** (`ventas/views.py`)

**Cambios en `form_valid()`**:
- ✅ Después de acumular kilómetros por compra, itera sobre `form.promos_km`
- ✅ Para cada promoción con `km_bono > 0`, llama a `KilometrosService.acumular_bono_promocion()`
- ✅ Crea registros en `HistorialKilometros` con tipo `'BONO_PROMOCION'`
- ✅ Logging detallado de bonos acumulados

**Código Agregado** (líneas ~1340-1350):
```python
# ACUMULAR BONOS DE PROMOCIONES (tipo 'KM')
promociones_aplicadas = getattr(form, 'promos_km', [])
for promo_data in promociones_aplicadas:
    km_bono = promo_data.get('km_bono', Decimal('0.00'))
    promocion = promo_data.get('promo')
    if km_bono and km_bono > 0 and promocion:
        registro_bono = KilometrosService.acumular_bono_promocion(...)
```

#### **VentaViajeUpdateView** (`ventas/views.py`)

**Cambios en `form_valid()`**:
- ✅ Compara promociones anteriores vs nuevas
- ✅ Identifica promociones agregadas, eliminadas y modificadas
- ✅ **Acumula bonos** de promociones nuevas
- ✅ **Revierte bonos** de promociones eliminadas
- ✅ **Ajusta bonos** si cambió el `km_bono` (acumula diferencia positiva, revierte diferencia negativa)
- ✅ Logging detallado de todos los cambios

**Código Agregado** (líneas ~1539-1635):
```python
# Manejar cambios en promociones con bonos de kilómetros
promociones_anteriores = {...}
promociones_nuevas = {...}
# Identificar cambios
# Acumular/revertir/ajustar según corresponda
```

#### **CancelarVentaView** (`ventas/views.py`)

**Cambios en `post()`**:
- ✅ Mensajes mejorados que incluyen información de redenciones devueltas
- ✅ Logging detallado con desglose de kilómetros revertidos y devueltos

**Código Mejorado** (líneas ~1558-1575):
```python
resultado = KilometrosService.revertir_por_cancelacion(venta)
# Mensaje incluye km_totales y km_devueltos
```

---

## Flujos Actualizados

### Flujo 1: Creación de Venta con Promoción tipo KM

**Antes**:
1. Se guardaba `km_bono` en `VentaPromocionAplicada`
2. ❌ NO se acumulaban kilómetros al cliente

**Ahora**:
1. Se guarda `km_bono` en `VentaPromocionAplicada`
2. ✅ Se llama a `KilometrosService.acumular_bono_promocion()`
3. ✅ Se crea registro en `HistorialKilometros` (tipo `'BONO_PROMOCION'`)
4. ✅ Se actualizan `cliente.kilometros_acumulados` y `cliente.kilometros_disponibles`

### Flujo 2: Actualización de Venta - Cambio en Promociones

**Antes**:
1. Se actualizaban las promociones en `VentaPromocionAplicada`
2. ❌ NO se ajustaban los kilómetros del cliente

**Ahora**:
1. Se comparan promociones anteriores vs nuevas
2. ✅ Se acumulan bonos de promociones nuevas
3. ✅ Se revierten bonos de promociones eliminadas
4. ✅ Se ajustan bonos si cambió el `km_bono`

### Flujo 3: Cancelación de Venta

**Antes**:
1. Se revertían solo acumulaciones por compra
2. ❌ NO se devolvían kilómetros redimidos

**Ahora**:
1. ✅ Se revierten todas las acumulaciones (compra + bonos de promociones)
2. ✅ Se devuelven kilómetros redimidos
3. ✅ Se crean registros de reversión apropiados

---

## Archivos Modificados

1. ✅ `crm/models.py`: Agregados tipos de evento, actualizado `max_length`
2. ✅ `crm/services.py`: Agregados métodos `acumular_bono_promocion()` y `revertir_bono_promocion()`, mejorado `revertir_por_cancelacion()`
3. ✅ `ventas/views.py`: Modificadas `VentaViajeCreateView`, `VentaViajeUpdateView` y `CancelarVentaView`
4. ✅ `crm/migrations/0014_agregar_tipos_evento_kilometros.py`: Migración creada y aplicada

---

## Pruebas Recomendadas

### Test 1: Crear Venta con Promoción tipo KM
1. Crear una venta con una promoción tipo 'KM' que otorgue 1000 km
2. Verificar que se cree registro en `HistorialKilometros` con tipo `'BONO_PROMOCION'`
3. Verificar que `cliente.kilometros_disponibles` aumente en 1000 km

### Test 2: Actualizar Venta - Agregar Promoción
1. Editar una venta existente
2. Agregar una promoción tipo 'KM' con 500 km
3. Verificar que se acumulen 500 km adicionales

### Test 3: Actualizar Venta - Eliminar Promoción
1. Editar una venta con promoción tipo 'KM' (1000 km)
2. Eliminar la promoción
3. Verificar que se reviertan 1000 km

### Test 4: Cancelar Venta con Redención
1. Crear una venta con descuento de kilómetros (redime 500 km)
2. Cancelar la venta
3. Verificar que se devuelvan los 500 km redimidos

---

## Próximos Pasos (Fase 2)

1. Implementar validación de consistencia
2. Crear comando de gestión para validar/corregir kilómetros
3. Agregar tests unitarios e integración
4. Mejorar documentación de flujos

---

## Notas Técnicas

- Todos los métodos usan transacciones atómicas para garantizar consistencia
- Se mantiene logging detallado para auditoría
- Los mensajes al usuario son informativos y específicos
- Se previenen reversiones duplicadas verificando el estado anterior de la venta









