# Reglas: Abonos a Proveedor

## Evitar inconsistencia "mostrar vs ejecutar"

La regla **"esta venta permite abonos a proveedor"** debe usarse en un solo lugar para:

1. **Mostrar** la sección y el botón de solicitud (contexto del detalle de venta).
2. **Validar** el POST al solicitar un abono (`SolicitarAbonoProveedorView`).

Si la lógica se duplica (por ejemplo, en la vista se comprueba solo `venta.proveedor` y en el modelo se considera también proveedores en logística), puede ocurrir que la sección se muestre pero el envío del formulario falle con "No se pueden solicitar abonos a proveedores para esta venta".

## Única fuente de verdad

- **Modelo:** `VentaViaje.puede_solicitar_abonos_proveedor` (propiedad).
- **Implementación interna:** `VentaViaje._debe_mostrar_abonos_proveedor()`.

Criterios (resumen):

- Viaje **internacional**: siempre permite abonos.
- Viaje **nacional**: permite si el proveedor principal tiene método de pago preferencial **o** si alguna fila de logística tiene un proveedor (por nombre) con método de pago preferencial.

## Uso en vistas

- En `VentaViajeDetailView.get_context_data`:  
  `context['debe_mostrar_abonos'] = venta.puede_solicitar_abonos_proveedor`
- En `SolicitarAbonoProveedorView.post`:  
  `puede_solicitar = venta.puede_solicitar_abonos_proveedor` antes de procesar el formulario.

**No** implementar en vistas una condición distinta (por ejemplo solo `venta.proveedor and venta.proveedor.metodo_pago_preferencial`). Cualquier cambio de regla debe hacerse solo en el modelo.

## Despliegue: evitar AttributeError

Si se añade una **nueva propiedad o método en el modelo** que las vistas usan (por ejemplo `puede_solicitar_abonos_proveedor`):

1. **Incluir en el mismo commit** tanto `ventas/models.py` como `ventas/views.py` (y cualquier template que use el atributo).
2. **Desplegar en un solo paso**: no subir solo las vistas sin el modelo, ni solo el modelo sin las vistas.
3. **Ejecutar tests** antes de desplegar: `pytest tests/test_models.py -k puede_solicitar` debe pasar.

Si se despliega solo la vista que usa `venta.puede_solicitar_abonos_proveedor` y el modelo en producción no tiene esa propiedad, se produce `AttributeError` en el detalle de venta (pestaña abonos).
