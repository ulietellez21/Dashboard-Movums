# Registro de Mejoras y Observaciones del Sistema

Este documento centraliza los hallazgos, bugs, posibles mejoras y ajustes de UX/UI identificados durante el análisis y las pruebas del sistema.

## 1. Módulo de Ventas

### 1.1 Conversión de Cotización a Venta (Flujo Crítico)
*   **Estado:** Funcional pero perfectible.
*   **Observación:** Al convertir una Cotización en Venta (`Crear venta desde cotización`), los datos cuantitativos (fechas, montos, cliente) se transfieren correctamente. Sin embargo, los **datos cualitativos y descriptivos NO se transfieren**.
*   **Detalle:**
    *   Información perdida: Notas del vuelo (ej. horarios específicos), notas del hospedaje (ej. "Upgrade a Suite"), especificaciones de tours.
    *   Impacto: El vendedor debe re-capturar manualmente estos detalles en la pantalla de "Nueva Venta", lo que es propenso a errores u olvidos.
*   **Mejora Propuesta:** Implementar un mapeo más profundo en la vista de conversión para pre-llenar los campos de descripción/notas de `VentaViaje` con la información concatenada de los servicios de la `Cotizacion`.

### 1.2 Sección Logística (Detalle de Venta)
*   [x] **VERIFICADO (16 Ene):** Fix "Nuclear" Funciona Correctamente.
    *   **Prueba:** Se intentó modificar un "Monto Planificado" ya establecido (de $1,000 a $5,000) forzando el formulario. El servidor **rechazó el cambio** y mantuvo el valor original ($1,000).
    *   **Comportamiento:** El bloqueo es estricto y seguro. Si el campo está vacío (0.00), permite editarlo por primera vez. Una vez guardado, se vuelve inmutable.
*   **Mejora Futura (UX):** UI Feedback. El usuario no recibe una alerta visual inmediata de que el campo está bloqueado (solo inputs deshabilitados). Si usan herramientas de desarrollador o hay un glitch visual, podrían pensar que editaron el valor, pero al recargar volverá el original.

### 1.3 Pagos y Abonos
*   [x] **VERIFICADO (16 Ene):** Pagos tipo "Ikki".
    *   **Prueba:** Se registró un pago de $2,000.00 usando el método "Ikki" (código interno `EFE`).
    *   **Resultado:** El saldo pendiente se actualizó correctamente (de $40k a $38k) y el pago aparece en el historial.
*   **Observación:** El flujo de caja funciona correctamente para este método de pago.

## 2. Gestión de Usuarios y Roles

### 2.1 Creación de Ejecutivos
*   **Estado:** Corregido (Atomicidad).
*   **Observación:** Fallos en la creación del usuario de Django dejaban registros de "Ejecutivos" huérfanos (sin usuario asociado) en la base de datos.
*   **Fix Actual:** Se envolvió el proceso en `transaction.atomic()` para asegurar que o se crean ambos (Ejecutivo + Usuario) o ninguno.
*   **Mejora Futura:** Mejorar los mensajes de error en el frontend cuando el email ya existe o la contraseña es débil, para guiar mejor al administrador.

## 3. Interfaz General (UI/UX)

*   **Alertas y Feedback:** A veces los mensajes de éxito/error ("Toasts") desaparecen muy rápido o no son lo suficientemente descriptivos. Revisar tiempos de visualización.
*   **Validaciones de Formulario:** Homogeneizar el estilo de los errores de validación. En algunos formularios aparecen arriba del todo y en otros junto al campo.

---
*Última actualización: 16 de Enero 2026*
