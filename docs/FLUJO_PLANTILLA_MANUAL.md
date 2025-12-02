# 📋 Flujo de Plantilla Manual para Captura de Datos

## 🎯 Objetivo

Crear una plantilla estructurada y fácil de usar donde el vendedor puede copiar y pegar manualmente la información de las capturas de vuelos/hoteles, y al final generar un documento imprimible con toda la información.

---

## 🔄 Flujo Propuesto

### **Paso 1: Acceso a la Plantilla**
- El vendedor accede a "Nueva Venta" desde el menú
- Se muestra una opción: **"Plantilla de Captura Rápida"** o usar el formulario estándar

### **Paso 2: Plantilla de Captura**
La plantilla mostrará secciones claramente delimitadas con campos grandes (textarea) para copiar/pegar:

```
┌─────────────────────────────────────────────────────────┐
│  PLANTILLA DE CAPTURA RÁPIDA - NUEVA VENTA              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. CLIENTE                                             │
│     [Dropdown: Seleccionar Cliente]                     │
│                                                          │
│  2. INFORMACIÓN DE VUELO                                │
│     ┌───────────────────────────────────────────────┐  │
│     │ [Pega aquí la información del vuelo]          │  │
│     │ - Número de vuelo                              │  │
│     │ - Aerolínea                                    │  │
│     │ - Fechas y horarios                            │  │
│     │ - Ruta (origen → destino)                      │  │
│     └───────────────────────────────────────────────┘  │
│                                                          │
│  3. INFORMACIÓN DE HOTEL                                │
│     ┌───────────────────────────────────────────────┐  │
│     │ [Pega aquí la información del hotel]          │  │
│     │ - Nombre del hotel                             │  │
│     │ - Fechas de check-in/check-out                 │  │
│     │ - Tipo de habitación                           │  │
│     └───────────────────────────────────────────────┘  │
│                                                          │
│  4. PASAJEROS                                           │
│     ┌───────────────────────────────────────────────┐  │
│     │ [Pega aquí los nombres completos]             │  │
│     │ Nombre 1                                       │  │
│     │ Nombre 2                                       │  │
│     └───────────────────────────────────────────────┘  │
│                                                          │
│  5. INFORMACIÓN FINANCIERA                              │
│     Costo Total: [Campo numérico]                       │
│     Monto de Apertura: [Campo numérico]                 │
│     Forma de Pago: [Dropdown]                           │
│                                                          │
│  6. DETALLES ADICIONALES                                │
│     ┌───────────────────────────────────────────────┐  │
│     │ [Cualquier información adicional]             │  │
│     └───────────────────────────────────────────────┘  │
│                                                          │
│  [Botón: GUARDAR Y CONTINUAR]                           │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### **Paso 3: Guardar Información**
- Al hacer clic en "Guardar", se crea la venta en el sistema
- Los datos se guardan en el modelo `VentaViaje` existente
- Se redirige a la página de detalle de la venta

### **Paso 4: Revisar y Editar (Opcional)**
- En la página de detalle, el vendedor puede:
  - Ver toda la información capturada
  - Editar cualquier campo si es necesario
  - Agregar información adicional

### **Paso 5: Imprimir Documento**
- Ya existe el sistema de generación de PDF (`ContratoVentaPDFView`)
- El vendedor puede hacer clic en "Imprimir Contrato" o "Generar PDF"
- Se genera un PDF con toda la información formateada según la plantilla de contrato existente

---

## 📝 Ventajas de este Enfoque

1. ✅ **Fácil de usar**: Campos grandes para copiar/pegar sin restricciones
2. ✅ **Organizado**: Secciones claras que guían al vendedor
3. ✅ **Flexible**: Permite pegar texto libre sin estructura específica
4. ✅ **Integrado**: Usa el sistema existente de guardado e impresión
5. ✅ **Revisable**: El vendedor puede editar después de guardar

---

## 🛠️ Implementación Técnica

### **Componentes Necesarios:**

1. **Nueva Vista Django**: `PlantillaCapturaRapidaView`
   - Formulario simplificado con campos grandes
   - Usa el mismo modelo `VentaViaje` y `VentaViajeForm` (pero con widgets personalizados)

2. **Nuevo Template**: `ventas/plantilla_captura_rapida.html`
   - Diseño limpio y organizado por secciones
   - Campos tipo textarea grandes
   - Validación básica

3. **Mejoras al Formulario Existente** (Opcional):
   - Agregar un modo "vista ampliada" o "vista plantilla"
   - Toggle para cambiar entre vista normal y vista plantilla

4. **Sistema de Impresión** (Ya existe):
   - `ContratoVentaPDFView` ya genera PDFs
   - Solo necesitamos asegurarnos de que esté accesible desde la vista de detalle

---

## 📄 Estructura de Campos en la Plantilla

### **Sección 1: Cliente**
- Campo: `cliente` (ModelChoiceField - dropdown)

### **Sección 2: Información de Vuelo**
- Campo: `servicios_detalle` (TextField grande - textarea)
- Label: "Información Completa del Vuelo"
- Placeholder: "Pega aquí toda la información del vuelo: número de vuelo, aerolínea, fechas, horarios, ruta, etc."

### **Sección 3: Información de Hotel**
- Campo: `servicios_detalle` (se puede combinar con vuelo o separar)
- O crear un campo adicional temporal

### **Sección 4: Pasajeros**
- Campo: `pasajeros` (TextField - textarea)
- Label: "Nombres Completos de Pasajeros"
- Placeholder: "Un pasajero por línea"

### **Sección 5: Fechas**
- Campo: `fecha_inicio_viaje` (DateField)
- Campo: `fecha_fin_viaje` (DateField)
- Campo: `fecha_vencimiento_pago` (DateField)

### **Sección 6: Información Financiera**
- Campo: `costo_venta_final` (DecimalField)
- Campo: `cantidad_apertura` (DecimalField)
- Campo: `modo_pago_apertura` (ChoiceField)

### **Sección 7: Servicios Seleccionados**
- Campo: `servicios_seleccionados` (MultipleChoiceField - checkboxes)
- Opciones: Vuelo, Hospedaje, Tour, etc.

---

## 🎨 Diseño Visual

La plantilla tendrá:
- **Secciones con bordes** para separar visualmente
- **Campos grandes** (textarea de al menos 6-8 líneas)
- **Labels claros y descriptivos**
- **Colores distintivos** para cada sección
- **Botones de acción claros**

---

## 🔄 Alternativa: Modo "Plantilla" en Formulario Existente

En lugar de crear una vista completamente nueva, podríamos:

1. Agregar un toggle en `venta_form.html`: "Vista Normal" / "Vista Plantilla"
2. Con JavaScript, cambiar el tamaño de los campos y reorganizarlos
3. Mantener un solo formulario, dos presentaciones

**Ventajas:**
- No duplica código
- Más fácil de mantener
- El usuario puede cambiar entre modos

---

## 📊 Comparación: Formulario Actual vs. Plantilla

| Aspecto | Formulario Actual | Plantilla Manual |
|---------|-------------------|------------------|
| Campos pequeños | ✅ | ❌ |
| Campos grandes (textarea) | ❌ | ✅ |
| Secciones organizadas | ✅ | ✅✅ |
| Ideal para copiar/pegar | ⚠️ | ✅✅ |
| Validación estricta | ✅✅ | ✅ |
| Vista rápida | ⚠️ | ✅✅ |

---

## 🚀 Próximos Pasos

1. **Crear la vista y template de Plantilla de Captura Rápida**
2. **Agregar URL y enlace en el menú**
3. **Probar con datos reales**
4. **Ajustar diseño según feedback**
5. **Asegurar que la impresión funcione correctamente**

¿Te parece bien este enfoque? ¿Quieres que proceda con la implementación?




