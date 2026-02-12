# Reporte de diagnóstico QA – Pre-Beta Testing
**Fecha:** 29/01/2026  
**Lead QA:** Diagnóstico automatizado  
**Objetivo:** Verificar salud del backend antes de pruebas con datos reales.

---

## 1. Estado de la base de datos

| Verificación | Resultado |
|--------------|-----------|
| `python manage.py showmigrations` | Todas las migraciones con **[X]** aplicadas. |
| Migraciones sin aplicar `[ ]` | Ninguna. |
| `python manage.py makemigrations --dry-run` | **No changes detected** – no hay cambios en modelos sin migración. |

**Conclusión:** Base de datos al día y consistente con los modelos.

---

## 2. Suite de pruebas (regression testing)

| Métrica | Valor |
|---------|--------|
| Comando | `pytest -v --tb=short` |
| Tests recolectados | 58 |
| Tests pasados | **58** |
| Tests fallidos | 0 |
| Warnings | 21 (no bloquean) |
| Tiempo | ~6.7 s |

**Conclusión:** Los 58 tests existentes pasan al 100 %. Regresión en verde.

---

## 3. Configuración de entorno (sanity check)

### DEBUG
- **Configuración:** `DEBUG = os.environ.get('DEBUG', 'True') == 'True'`
- **Lectura:** Correcta desde variable de entorno; fallback para desarrollo.
- **Producción:** Debe definirse `DEBUG=False` en el entorno.

### LOGGING
- **Activo:** Sí, bloque `LOGGING` definido en `settings.py`.
- **Niveles capturados:**
  - `file`: nivel **INFO** → `logs/django.log`
  - `error_file`: nivel **ERROR** → `logs/django-errors.log`
  - `console`: **INFO** (o DEBUG si `DEBUG=True`)
- **Loggers:** `django`, `django.request`, `django.server`, `ventas`, `crm`, `usuarios`, `auditoria` con niveles INFO/ERROR según corresponda.

**Conclusión:** Configuración de entorno y logging correctas para beta.

---

## 4. Integridad de modelos críticos

### VentaViaje (Venta)
| Campo | Obligatorio | Observación |
|-------|-------------|-------------|
| `cliente` | Sí | FK sin `null=True`. |
| `costo_venta_final` | Sí | Sin null/blank. |
| `costo_neto` | Sí | Sin null/blank. |
| `fecha_inicio_viaje` | Sí | Fecha de ida obligatoria. |
| `fecha_vencimiento_pago` | No | `null=True`, `blank=True`. |
| `fecha_fin_viaje` | No | Opcional (viaje solo ida). |

### Cliente (crm)
| Campo | Obligatorio | Observación |
|-------|-------------|-------------|
| `telefono` | Sí | Requerido (sin blank). |
| `nombre` / `apellido` | No | Opcionales (diseño Particular/Empresa). |
| `nombre_empresa` | No | Opcional. |

### Cotizacion
| Campo | Obligatorio | Observación |
|-------|-------------|-------------|
| `cliente` | Sí | FK PROTECT, obligatorio. |
| `fecha_inicio` / `fecha_fin` | No | `null=True`, `blank=True`. |
| `total_estimado` | Default | Default `0.00`. |

### Atención – campos críticos opcionales
- **VentaViaje.fecha_vencimiento_pago:** opcional. Usado en reporte financiero y liquidez; ventas sin esta fecha pueden afectar proyecciones por mes. Vigilar en beta que no se generen muchas ventas sin fecha límite de pago.
- **Cotizacion.fecha_inicio / fecha_fin:** opcionales. Aceptable para borradores; vigilar que cotizaciones “enviadas” tengan fechas cuando sea necesario.

**Conclusión:** No hay campos de precio o cliente críticos opcionales en ventas. Las únicas observaciones son fechas opcionales (fecha_vencimiento_pago y fechas de cotización), ya contempladas en el diseño; conviene vigilarlas en beta.

---

## 5. Veredicto final

### LISTO PARA BETA (todo en orden)

- Migraciones: todas aplicadas, sin cambios pendientes.
- Tests: 58/58 pasando.
- DEBUG y LOGGING: configurados y leyendo de entorno.
- Modelos críticos: cliente y precios obligatorios en ventas; solo fechas opcionales ya conocidas.

**Recomendaciones para beta:**
1. En pruebas con datos reales, evitar dejar ventas activas sin `fecha_vencimiento_pago` si se usarán reportes de liquidez por mes.
2. Revisar los 21 warnings de pytest cuando haya tiempo (no bloquean).
3. Confirmar en el servidor de beta que `DEBUG=False` y que las variables de entorno (incl. `DEBUG`) estén definidas.

---

*Reporte generado por diagnóstico automatizado (Lead QA).*
