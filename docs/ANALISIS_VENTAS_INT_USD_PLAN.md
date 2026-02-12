# Análisis: Ventas internacionales en USD sin conversiones automáticas

## Objetivo

- Todas las cantidades de ventas internacionales se manejan en **dólares (USD)**.
- **Eliminar conversiones automáticas** a MXN; las conversiones serán manuales.
- Mostrar **todas** las cantidades en USD en pantalla y en documentos.
- Para **abonos** y **montos de apertura/anticipo**: seguir mostrando el **tipo de cambio** como referencia para cuando se hagan las conversiones manuales.

---

## 1. Flujo actual (resumen)

### 1.1 Modelo de datos (INT)

| Dónde | Qué se guarda hoy |
|-------|--------------------|
| **VentaViaje** | `cantidad_apertura`, `costo_venta_final`, `costo_neto` → en **MXN** (calculados desde USD × tipo_cambio al guardar). `tipo_cambio` (MXN por 1 USD). `tarifa_base_usd`, `impuestos_usd`, `suplementos_usd`, `tours_usd` → en USD. |
| **AbonoPago** | `monto` → en **MXN** (para INT se calcula desde USD × tipo_cambio). `monto_usd`, `tipo_cambio_aplicado` también se guardan. |
| **AbonoProveedor** | `monto` → MXN. `monto_usd`, `tipo_cambio_aplicado` para INT. |

Propiedades calculadas (modelo):

- `cantidad_apertura_usd` = cantidad_apertura / tipo_cambio  
- `total_pagado_usd` = cantidad_apertura_usd + suma abonos en USD  
- `total_usd` = tarifa_base_usd + impuestos_usd + suplementos_usd + tours_usd  
- `total_pagado` = siempre en **MXN** (apertura + abonos en MXN)  
- `saldo_restante` = en **MXN**  
- `costo_total_con_modificacion_usd` = costo_total_con_modificacion (MXN) / tipo_cambio  

Es decir: hoy **todo se persiste en MXN** (apertura, abonos, totales) y el sistema **convierte** con tipo_cambio al guardar y al mostrar USD.

### 1.2 Creación / edición de venta (formulario)

- **ventas/forms.py** (VentaViajeForm.clean, ~1726–1774):  
  Para INT el usuario ingresa USD (tarifa_base_usd, cantidad_apertura como USD, costo_neto como USD). El formulario **convierte a MXN** con `tipo_cambio` y asigna:
  - `costo_venta_final` = total_usd × tipo_cambio  
  - `costo_neto` = costo_neto_usd × tipo_cambio  
  - `cantidad_apertura` = cantidad_apertura_usd × tipo_cambio  

- Al **editar**, el initial convierte MXN → USD para mostrar (cantidad_apertura/tipo_cambio, costo_neto/tipo_cambio) en **ventas/forms.py** (~1515–1525).

### 1.3 Detalle de venta (vista + template)

- **ventas/views.py** (VentaViajeDetailView.get_context_data):  
  - Para abonos a proveedor INT: convierte a MXN para el contexto:  
    `total_abonado_proveedor * tipo_cambio`, `saldo_pendiente_proveedor * tipo_cambio` (~676–678).  
  - Pasa `resumen_financiero` con totales (en MXN para INT también).

- **ventas/templates/ventas/venta_detail.html**:  
  - Resumen arriba: **Total pagado** y **Saldo pendiente** = `venta.total_pagado` y `venta.saldo_restante` → hoy en **MXN** para INT.  
  - Pestaña Información general: bloque “Montos en USD” (tarifa_*_usd, total_usd, tipo_cambio) y bloque “Montos en MXN” (costo_neto, cantidad_apertura, total_final).  
  - Pestaña Abonos y pagos: para INT, campo “Monto (USD)” y “Tipo de cambio”; JS convierte USD → MXN y rellena `monto` (hidden); tabla muestra apertura y abonos en MXN y USD.  
  - Abonos a proveedor: monto en MXN y conversión con tipo_cambio.

### 1.4 Registro de abonos (AbonoPago)

- Usuario ve monto en **USD** y tipo de cambio; el **formulario** (SolicitarAbonoForm / registro de abono cliente) puede recibir MXN o USD según implementación.
- **ventas/views.py** (confirmación de abono, ~12849–12855): después de guardar AbonoProveedor, si hay tipo_cambio calcula `monto_usd = monto / tipo_cambio` (conversión MXN→USD).
- **ventas/forms.py** (SolicitarAbonoProveedorForm.clean): si venta INT y hay tipo_cambio, `monto_usd = monto / tipo_cambio` (monto en MXN → monto_usd).

Para **AbonoPago** (abono cliente): el template INT usa campo USD y JS rellena monto MXN; al guardar se persiste monto (MXN) y se calcula monto_usd.

### 1.5 Comprobante de abonos (PDF)

- **ventas/templates/ventas/comprobante_abonos_pdf.html**:  
  Para INT: totales en USD (total_final_usd, total_pagado_usd, saldo_restante_usd), “1 USD = X MXN”; fila de apertura: `cantidad_apertura/tipo_cambio` en USD; filas de abonos: monto_usd o monto/tipo_cambio.

- **ventas/views.py** (ComprobanteAbonosPdfView.get): pasa `total_pagado`, `saldo_restante` (hoy en MXN) y `total_final`; el template para INT usa propiedades _usd y conversiones.

### 1.6 Contratos (DOCX / plantillas)

- **ventas/utils.py** (generate_pdf_contrato / contexto para plantilla):  
  `monto_apertura_localizado` = `venta.cantidad_apertura` → **MXN** (no distingue INT).

- **ventas/views.py** (vistas de contrato DOCX, ~5622–5628, 5748–5749, 5973–5974):  
  Para INT usa `anticipo_usd`, `saldo_pendiente_usd`, `tipo_cambio` y en el doc escribe “Anticipo recibido: X USD (tc $Y)”.

- Contratos NAC (~4058, 4267, 4692, 5006): usan `venta.cantidad_apertura` y “MXN”.

### 1.7 Reporte financiero / Excel / comisiones

- **ventas/views.py**: agregaciones por `cantidad_apertura`, `total_pagado` (MXN). Para INT esas columnas siguen siendo MXN.
- **ventas/services/comisiones.py**: para INT convierte USD → MXN con tipo_cambio para calcular comisiones (tarifa_base_usd × tipo_cambio, etc.).

---

## 2. Dónde se hacen conversiones hoy

| Lugar | Conversión |
|-------|------------|
| Form venta (INT) | USD → MXN al guardar (costo_venta_final, costo_neto, cantidad_apertura). |
| Form venta (INT) initial | MXN → USD al cargar para edición. |
| total_pagado, saldo_restante | Siempre en MXN (apertura y abonos ya guardados en MXN). |
| cantidad_apertura_usd, total_pagado_usd | MXN → USD vía división por tipo_cambio (propiedades). |
| Abono cliente (INT) | Usuario ingresa USD → JS o backend convierte a MXN para monto; se guarda monto_usd también. |
| Abono proveedor (INT) | monto en MXN; vista/form calcula monto_usd = monto/tipo_cambio. |
| Detalle venta (abonos proveedor) | total_abonado_proveedor y saldo_pendiente_proveedor en USD en modelo; la vista los multiplica por tipo_cambio para mostrarlos en MXN en contexto. |
| Comprobante PDF INT | Usa total_pagado_usd, cantidad_apertura_usd, monto_usd; total_final_usd = total_final_mxn/tipo_cambio. |
| Contrato INT (DOCX) | anticipo_usd, saldo_pendiente_usd (ya calculados); muestra tipo_cambio. |
| Comisiones INT | USD × tipo_cambio → MXN para base de comisión. |

---

## 3. Cambios deseados (interpretación)

- **Todo en USD para INT**: totales, apertura, abonos, costo_venta_final, costo_neto, etc. se **muestran** siempre en USD.
- **Sin conversiones automáticas**: no calcular ni guardar MXN para INT (o guardar solo USD y no usar tipo_cambio para cálculos).
- **Tipo de cambio solo informativo**: se muestra junto a apertura y abonos para que, al hacer la conversión manual fuera del sistema, tengan el número correcto.

Implicaciones:

1. **Almacenamiento**: para INT, o bien se guarda todo en USD (nuevos campos o convención “para INT este campo es USD”) o se mantienen campos MXN en 0 y se usan solo campos USD. Esto afecta modelo, formularios y reportes.
2. **Formularios**: en venta INT el usuario ingresa solo USD; no se calcula ni guarda MXN. En abonos (cliente y proveedor) se ingresa USD; se guarda USD; monto MXN puede quedar en 0 o no usarse para INT.
3. **Pantallas**: detalle de venta, listados, resúmenes: para INT mostrar siempre USD (total pagado, saldo pendiente, apertura, abonos, costos). Tipo de cambio visible solo como “referencia” junto a apertura/abonos.
4. **PDFs y contratos**: comprobante de abonos y contratos INT en USD; tipo de cambio mostrado donde aplique para referencia.
5. **Comisiones / reportes**: definir si la base de comisión para INT sigue siendo “en MXN” (conversión manual o con tipo_cambio solo referencia) o pasa a ser en USD; hoy comisiones convierten a MXN.

---

## 4. Plan de cambios por área (para implementación futura)

### 4.1 Modelo (ventas/models.py)

- **Opción A (recomendada para no romper NAC):**  
  - Añadir (o reutilizar) campos en USD para INT: por ejemplo `cantidad_apertura_usd` (o convención “para INT, cantidad_apertura es USD”).  
  - Para INT: no rellenar `cantidad_apertura` en MXN (o dejarlo en 0); guardar apertura en USD.  
  - `costo_venta_final` y `costo_neto`: para INT guardar en USD (o añadir `costo_venta_final_usd`, `costo_neto_usd` y usar solo esos para INT).  
  - Mantener `tipo_cambio` solo como dato de referencia (no usarlo para conversiones automáticas en lógica nueva).
- Propiedades: para INT, `total_pagado` y `saldo_restante` deberían expresarse en USD (sumando solo montos USD de apertura y abonos), o exponer `total_pagado_usd` / `saldo_restante_usd` como valores principales para INT y usar esos en vistas/templates.
- AbonoPago: para INT guardar solo `monto_usd` (y opcionalmente tipo_cambio de referencia); `monto` en 0 o igual a monto_usd según criterio (evitar doble fuente de verdad).
- AbonoProveedor: análogo; para INT monto principal en USD.

### 4.2 Formularios (ventas/forms.py)

- **VentaViajeForm (INT):**  
  - Quitar conversión USD→MXN. Guardar directamente en USD (cantidad_apertura_usd o cantidad_apertura como USD, costo_venta_final_usd / costo_neto_usd o convención).  
  - Validar tipo_cambio > 0 si se sigue pidiendo, pero no usarlo para escribir MXN.
- **Initial al editar:** ya no convertir MXN→USD; mostrar los valores USD guardados.
- **AbonoPago (registro de abono cliente INT):** capturar monto en USD; guardar en `monto_usd`; no calcular `monto` en MXN (o dejarlo 0 para INT).
- **SolicitarAbonoProveedorForm (INT):** monto en USD; guardar monto_usd; tipo_cambio solo para mostrar o para un campo “tipo_cambio aplicado” de referencia; no derivar monto MXN.

### 4.3 Vistas (ventas/views.py)

- **VentaViajeDetailView:**  
  - Para INT, pasar al template totales en USD (total_pagado_usd, saldo_restante_usd, etc.) y usarlos en el resumen en lugar de total_pagado/saldo_restante en MXN.  
  - Abonos a proveedor: no multiplicar por tipo_cambio para contexto; pasar montos en USD y tipo_cambio solo como referencia.
- **ComprobanteAbonosPdfView:** contexto para INT solo en USD; total_pagado, saldo_restante en USD para la plantilla.
- **Vistas de contrato DOCX (INT):** ya usan anticipo_usd y saldo_pendiente_usd; asegurar que ningún paso convierta a MXN; mantener tipo_cambio solo como texto de referencia.
- **SolicitarAbonoProveedorView:** no calcular monto_usd desde monto MXN; guardar monto en USD directamente.
- **Confirmación de pago de apertura / abonos:** si se guarda apertura o abono en USD, no escribir MXN.

### 4.4 Templates

- **venta_detail.html:**  
  - Resumen: para INT mostrar “Total pagado (USD)”, “Saldo pendiente (USD)” con total_pagado_usd y saldo_restante_usd.  
  - Información general: para INT solo bloque “Montos en USD”; quitar bloque “Montos en MXN” o dejarlo opcional/oculto.  
  - Abonos y pagos: montos en USD; tipo de cambio mostrado como “Tipo de cambio (referencia): X MXN/USD”.  
  - Abonos a proveedor: montos en USD; tipo de cambio de referencia.
- **comprobante_abonos_pdf.html:** para INT todo en USD; tipo de cambio en un recuadro “Referencia: 1 USD = X MXN”.
- **pagos_por_confirmar, lista_abonos_proveedor, reporte_financiero, etc.:** para ventas INT mostrar columnas en USD; tipo de cambio solo referencia donde aplique.

### 4.5 Contratos (utils + vistas DOCX)

- **ventas/utils.py:** para INT, contexto de plantilla debe usar montos en USD (ej. monto_apertura_localizado = cantidad_apertura_usd y etiqueta “USD”) y tipo_cambio como “tipo_cambio_referencia”.
- **Vistas DOCX INT:** mantener anticipo y saldo en USD; texto tipo “Anticipo recibido: X USD. Tipo de cambio de referencia: Y MXN/USD (fecha …)”.

### 4.6 Comisiones y reportes

- **ventas/services/comisiones.py:** hoy convierte USD→MXN con tipo_cambio. Decidir: (1) base de comisión para INT en USD (y que el reporte muestre comisión en USD o en MXN con conversión manual), o (2) mantener una conversión “de referencia” solo para reporte de comisiones en MXN. Si “no conversiones” es estricto, la base podría quedar en USD y el reporte aclarar “venta en USD; conversión manual si aplica”.
- **Reporte financiero / Excel:** columnas para INT en USD; no rellenar totales en MXN desde conversión automática.

### 4.7 Migraciones y datos existentes

- Si hoy hay ventas INT con cantidad_apertura/costo_venta_final/costo_neto en MXN y abonos en MXN: definir migración de datos (recalcular USD desde MXN con tipo_cambio una última vez y guardar en los nuevos campos o en la nueva convención) o tratar solo ventas nuevas en USD.

---

## 5. Resumen de archivos a tocar (checklist)

| Área | Archivos |
|------|----------|
| Modelo | ventas/models.py (campos/propiedades INT en USD; tipo_cambio solo referencia). |
| Formularios | ventas/forms.py (VentaViajeForm, abonos cliente, SolicitarAbonoProveedorForm). |
| Vistas | ventas/views.py (detalle venta, comprobante PDF, contratos DOCX, abonos proveedor, confirmación pagos). |
| Templates detalle | ventas/templates/ventas/venta_detail.html (resumen, info general, abonos, abonos proveedor). |
| Templates PDF | ventas/templates/ventas/comprobante_abonos_pdf.html. |
| Otros templates | ventas/templates/ventas/pagos_por_confirmar.html, lista_abonos_proveedor.html, reporte_financiero.html, venta_list.html (totales INT), etc. |
| Contratos | ventas/utils.py (contexto plantilla); vistas que generan DOCX INT. |
| Comisiones | ventas/services/comisiones.py; templates de comisiones. |
| Migraciones | Nueva migración si se añaden campos o se cambia convención de almacenamiento. |

---

## 6. Preguntas para afinar el plan

1. **Ventas INT ya existentes:** ¿Se migran a “todo en USD” (recalcular USD desde MXN con tipo_cambio guardado y rellenar nuevos campos) o solo las ventas nuevas se manejan en USD y las viejas se dejan como están (mostrando USD calculado desde MXN)?  
2. **Comisiones:** ¿La comisión por venta internacional debe seguir calculándose “en MXN” usando un tipo de cambio (aunque sea solo para ese cálculo) o debe calcularse en USD y que el reporte muestre “comisión en USD” (o “equivalente MXN según conversión manual”)?  
3. **AbonoProveedor y AbonoPago:** ¿Para INT se guarda solo `monto_usd` (y `monto` en 0 o sin usar) o prefieren mantener `monto` con el valor en USD también (evitando confusión con “monto = MXN”)?  
4. **Tipo de cambio:** ¿Siguen capturando tipo_cambio en la venta y en cada abono solo para mostrarlo como referencia, o en algún flujo (por ejemplo facturación) sí necesitan un “tipo de cambio aplicado” guardado por operación para auditoría?  
5. **Reporte financiero / Excel:** ¿Las columnas de “total vendido / total pagado / saldo” para INT deben ser solo en USD o además una columna “equivalente MXN (referencia)” usando el tipo_cambio de la venta?

Con estas respuestas se puede bajar a detalle de campos, nombres y cambios línea por línea sin modificar nada hasta que lo decidas.
