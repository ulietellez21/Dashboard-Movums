# Prevención de errores en despliegue (módulo Ventas)

Las ventas son críticas: un error en producción puede mostrar pantallas rotas o estados incorrectos (abonos, apertura confirmada). Estas reglas ayudan a evitar fallos como los que ya ocurrieron.

## 1. Modelo y vistas siempre alineados

**Problema típico:** Se añade una propiedad en el modelo (ej. `puede_solicitar_abonos_proveedor`) y las vistas la usan, pero en un commit solo se sube `views.py`. En producción la vista accede al atributo y el modelo antiguo no lo tiene → **AttributeError**.

**Regla:**

- Cualquier **cambio que añada un atributo/propiedad/método en el modelo** usado por vistas o templates debe ir en **el mismo commit** que los archivos que lo usan (`views.py`, `templates/`, etc.).
- Al desplegar, **no** hacer push solo de vistas sin el modelo (ni solo del modelo sin vistas) cuando dependan entre sí.

**Checklist antes de commit:**

- [ ] Si toqué `ventas/models.py` añadiendo algo que usa `ventas/views.py` o templates, ¿incluí ambos en el commit?

## 2. Tests que protegen atributos críticos

Existen tests que comprueban que el modelo tiene propiedades usadas por las vistas (ej. `puede_solicitar_abonos_proveedor`). Si alguien despliega vistas que usan esa propiedad pero olvida el modelo, los tests deberían seguir pasando en local; si en CI se ejecutan antes del deploy, fallarían y evitarían el error en producción.

**Comando:** `pytest tests/test_models.py -k "puede_solicitar o VentaViaje"`

## 3. Apertura confirmada: no refrescar venta antes de guardar

En la vista que confirma el pago de apertura (contador), **no** llamar a `venta.refresh_from_db()` después de poner `venta.apertura_confirmada = True` y antes de `venta.save()`. El refresh recarga el modelo desde la BD (donde sigue `apertura_confirmada=False`) y borra el `True` en memoria; al guardar se persiste `False` y la venta vuelve a “pendiente”.

**Ubicación:** `ventas/views.py`, vista que procesa la confirmación de pago (notificación PAGO_PENDIENTE → PAGO_CONFIRMADO para apertura).

## 4. Recuperar ventas que quedaron en “pendiente” por el bug

Si por el bug anterior algunas ventas tenían la apertura confirmada por el contador pero en BD quedó `apertura_confirmada=False`, se puede corregir con:

```bash
python manage.py recuperar_apertura_confirmada [--dry-run]
```

Ese comando busca notificaciones **PAGO_CONFIRMADO** sin abono (confirmación de apertura) y pone `apertura_confirmada=True` en las ventas que aún tengan `apertura_confirmada=False`. Con `--dry-run` solo lista qué ventas se actualizarían.

## 5. Resumen

| Riesgo | Prevención |
|--------|------------|
| AttributeError por propiedad faltante en modelo | Mismo commit para modelo + vistas; tests de propiedades críticas |
| Apertura confirmada que vuelve a pendiente | No usar `refresh_from_db()` entre asignar `apertura_confirmada=True` y `save()` |
| Ventas ya confirmadas que quedaron pendientes en BD | Ejecutar `recuperar_apertura_confirmada` (con `--dry-run` si aplica) |
