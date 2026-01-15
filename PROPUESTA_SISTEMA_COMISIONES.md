# 💰 Propuesta de Implementación: Sistema de Comisiones Escalonadas

## 📋 Análisis de la Situación Actual

**Estado Actual:**
- ✅ Existe modelo `Ejecutivo` con campo `ubicacion_asignada` (CharField)
- ✅ Existe cálculo básico de comisiones (2.5% fijo)
- ✅ Vista `ComisionesVendedoresView` calcula comisiones
- ✅ Template muestra sueldo base, porcentaje de comisión y comisión ganada

**Requisitos Nuevos:**

### **Vendedores de OFICINA** (Comisión Escalonada):
- $0 - $99,999: **1%**
- $100,000 - $199,999: **2%**
- $200,000 - $299,999: **3%**
- $300,000 - $399,999: **4%**
- $400,000 - $500,000: **5%**

### **Vendedores de CALLE** (Comisión Fija):
- Siempre: **4%**

---

## 🔍 Pregunta Crítica: ¿Cómo Identificar Tipo de Vendedor?

Necesito saber **cómo distinguir** entre vendedor de oficina y vendedor de calle:

### **OPCIÓN A: Por Campo `ubicacion_asignada`** (Actual)
- **Ventaja**: Ya existe el campo
- **Método**: Verificar si contiene "oficina" o "calle" en el texto
- **Ejemplo**: 
  - `ubicacion_asignada = "Oficina Central"` → Vendedor de OFICINA
  - `ubicacion_asignada = "Ventas Calle"` → Vendedor de CALLE

### **OPCIÓN B: Agregar Campo Nuevo `tipo_vendedor`** (Recomendado)
- **Ventaja**: Más claro y específico
- **Método**: Agregar campo con opciones: `('OFICINA', 'Oficina')`, `('CALLE', 'Calle')`
- **Más profesional y mantenible**

---

## 🎯 Propuesta de Implementación

### **1. MODIFICACIÓN DEL MODELO (Recomendado - Opción B)**

Agregar campo `tipo_vendedor` al modelo `Ejecutivo`:

```python
# En ventas/models.py - Modelo Ejecutivo
TIPO_VENDEDOR_CHOICES = [
    ('OFICINA', 'Vendedor de Oficina'),
    ('CALLE', 'Vendedor de Calle'),
]

tipo_vendedor = models.CharField(
    max_length=10,
    choices=TIPO_VENDEDOR_CHOICES,
    default='OFICINA',
    verbose_name="Tipo de Vendedor"
)
```

**Ventajas:**
- ✅ Claro y explícito
- ✅ Fácil de filtrar y consultar
- ✅ No depende de texto libre en `ubicacion_asignada`
- ✅ Escalable para futuros tipos

**Desventajas:**
- ⚠️ Requiere migración de base de datos
- ⚠️ Datos existentes necesitan ser migrados

---

### **2. FUNCIÓN DE CÁLCULO DE COMISIÓN**

Crear función que calcule la comisión según el tipo y el monto:

```python
def calcular_comision(total_ventas, tipo_vendedor):
    """
    Calcula la comisión según el tipo de vendedor y el total de ventas.
    
    Args:
        total_ventas: Decimal - Total de ventas pagadas del vendedor
        tipo_vendedor: str - 'OFICINA' o 'CALLE'
    
    Returns:
        tuple: (porcentaje_comision, monto_comision)
            porcentaje_comision: Decimal (ej: 0.03 para 3%)
            monto_comision: Decimal (monto calculado)
    """
    if tipo_vendedor == 'CALLE':
        # Vendedores de calle: 4% fijo
        porcentaje = Decimal('0.04')
        return porcentaje, total_ventas * porcentaje
    
    elif tipo_vendedor == 'OFICINA':
        # Vendedores de oficina: Escalonado
        if total_ventas < Decimal('100000'):
            porcentaje = Decimal('0.01')  # 1%
        elif total_ventas < Decimal('200000'):
            porcentaje = Decimal('0.02')  # 2%
        elif total_ventas < Decimal('300000'):
            porcentaje = Decimal('0.03')  # 3%
        elif total_ventas < Decimal('400000'):
            porcentaje = Decimal('0.04')  # 4%
        else:  # >= 400,000
            porcentaje = Decimal('0.05')  # 5%
        
        return porcentaje, total_ventas * porcentaje
    
    # Fallback: Por defecto 4% si no se identifica
    porcentaje = Decimal('0.04')
    return porcentaje, total_ventas * porcentaje
```

---

### **3. MODIFICACIÓN DE LA VISTA**

Actualizar `ComisionesVendedoresView.get_context_data()`:

**Cambios necesarios:**
1. Obtener el `tipo_vendedor` del ejecutivo (o inferirlo de `ubicacion_asignada`)
2. Llamar a la función de cálculo de comisión
3. Pasar el porcentaje y monto calculados al contexto

**Código actual (línea ~1298):**
```python
# CÁLCULO DE COMISIÓN
comision_ganada = total_ventas_pagadas * self.COMISION_PORCENTAJE
```

**Código nuevo:**
```python
# Obtener tipo de vendedor
tipo_vendedor = 'OFICINA'  # Por defecto
if ejecutivo:
    # Si existe campo tipo_vendedor:
    tipo_vendedor = ejecutivo.tipo_vendedor
    # O si usamos ubicacion_asignada:
    # ubicacion_lower = ejecutivo.ubicacion_asignada.lower()
    # tipo_vendedor = 'CALLE' if 'calle' in ubicacion_lower else 'OFICINA'

# Calcular comisión según tipo
porcentaje_comision, comision_ganada = calcular_comision(
    total_ventas_pagadas, 
    tipo_vendedor
)
```

---

### **4. ACTUALIZACIÓN DEL TEMPLATE**

El template ya muestra `comision_porcentaje`, solo necesita que el valor sea dinámico.

**Opcional: Mejoras visuales:**
- Mostrar el rango alcanzado para vendedores de oficina
- Indicador visual del tipo de vendedor
- Badge con "Oficina" o "Calle"

---

### **5. ACTUALIZACIÓN DEL FORMULARIO**

Si agregamos campo `tipo_vendedor` al modelo:
- Agregar campo al `EjecutivoForm`
- Mostrar en el modal de crear/editar ejecutivo

---

## 📊 Resumen de Cambios Necesarios

### **Opción A: Usar `ubicacion_asignada` (Rápido, sin migración)**
1. ✅ Crear función `calcular_comision()`
2. ✅ Modificar vista para inferir tipo de vendedor
3. ✅ Actualizar cálculo en `get_context_data()`
4. ⚠️ Depende de que `ubicacion_asignada` contenga "oficina" o "calle"

### **Opción B: Agregar campo `tipo_vendedor` (Recomendado)**
1. ✅ Agregar campo al modelo `Ejecutivo`
2. ✅ Crear y ejecutar migración
3. ✅ Crear función `calcular_comision()`
4. ✅ Modificar vista para usar el campo
5. ✅ Actualizar `EjecutivoForm` para incluir el campo
6. ✅ Actualizar template del modal si es necesario

---

## 🎯 Mi Recomendación

**OPCIÓN B: Agregar campo `tipo_vendedor`**

**Razones:**
1. **Más profesional**: Campo específico y claro
2. **Más mantenible**: No depende de texto libre
3. **Más escalable**: Fácil agregar más tipos en el futuro
4. **Mejor UX**: El JEFE puede seleccionar directamente el tipo al crear ejecutivo

**Implementación:**
- Agregar campo con migración
- Datos existentes: Por defecto "OFICINA" (puedes cambiar manualmente después)
- Formulario: Dropdown para seleccionar tipo

---

## 🔄 Plan de Ejecución Propuesto

1. **Paso 1**: Agregar campo `tipo_vendedor` al modelo `Ejecutivo`
2. **Paso 2**: Crear migración
3. **Paso 3**: Crear función `calcular_comision()` en `views.py` o `utils.py`
4. **Paso 4**: Actualizar `ComisionesVendedoresView.get_context_data()`
5. **Paso 5**: Actualizar `EjecutivoForm` para incluir el campo
6. **Paso 6**: Actualizar template si es necesario (opcional)
7. **Paso 7**: Probar con datos reales

---

## ❓ Preguntas para Ti

1. **¿Prefieres Opción A o Opción B?**
   - A: Rápido, sin cambios al modelo (usa `ubicacion_asignada`)
   - B: Más profesional, requiere migración (nuevo campo)

2. **Si eliges Opción A:**
   - ¿Cómo están escritas las ubicaciones actuales?
   - Ejemplo: "Oficina Central", "Ventas Calle", etc.

3. **Si eliges Opción B:**
   - ¿Por defecto todos los ejecutivos existentes serán "OFICINA"?
   - ¿O prefieres que los identifique automáticamente?

4. **Límite máximo:**
   - Para vendedores de oficina, ¿después de $500,000 sigue siendo 5%?
   - ¿O hay otro porcentaje?

---

## 📝 Resumen Visual

```
Vendedor de OFICINA:
┌─────────────────────┬───────────┐
│ Total Ventas        │ Comisión  │
├─────────────────────┼───────────┤
│ $0 - $99,999        │    1%     │
│ $100k - $199,999    │    2%     │
│ $200k - $299,999    │    3%     │
│ $300k - $399,999    │    4%     │
│ $400k - $500k       │    5%     │
└─────────────────────┴───────────┘

Vendedor de CALLE:
┌─────────────────────┬───────────┐
│ Total Ventas        │ Comisión  │
├─────────────────────┼───────────┤
│ Cualquier monto     │    4%     │
└─────────────────────┴───────────┘
```

---

**¿Qué opción prefieres? ¿Tienes alguna pregunta o modificación antes de proceder?** 🤔

























