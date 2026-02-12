# Backup y restauración del apartado de cotizaciones (antes del 7 feb)

## Resumen

- **Los formatos de los PDF de cotizaciones** (márgenes, tablas, términos) dependen del **código** (plantillas HTML/CSS), **no de la base de datos**.
- Restaurar un backup de **base de datos** no corrige errores de formato; solo recuperaría *datos* (cotizaciones, clientes, montos) si se hubieran perdido.
- Para recuperar el **formato** hay que restaurar la **versión del código** (plantillas de ventas/PDF) de antes del 7 de febrero.

---

## 1. Backup de base de datos

### 1.1 En tu máquina local (este repo)

| Ubicación | Archivo | Fecha | Nota |
|-----------|---------|--------|------|
| `backups/` | `db_backup_2026-01-30_1337.sqlite3` | 30 ene 2026 | Único backup en carpeta; retención 7 días, no hay backup del 5–6 feb |
| Raíz del proyecto | `db.sqlite3.backup-20251205-182415` | 5 dic 2025 | Muy antiguo; anterior a los cambios de cotizaciones |

- **Conclusión:** No hay backup de base de datos **del servidor** ni local con fecha “antes del sábado 7 de febrero” en este repositorio. El `backup.sh` solo guarda los últimos 7 días en `backups/`.

### 1.2 En el servidor

No tenemos acceso al servidor desde aquí. Si tienes SSH o consola:

1. **Buscar backups de base de datos** (SQLite o PostgreSQL/MySQL según cómo esté desplegado):

   ```bash
   # Si usan SQLite en el servidor
   find /home -name "db.sqlite3*" -o -name "db_backup*" 2>/dev/null
   ls -la /ruta/del/proyecto/backups/
   ls -la /ruta/del/proyecto/*.sqlite3*

   # Si usan PostgreSQL
   ls -la /var/backups/  # o donde se guarden dumps
   ```

2. **Ver fechas de modificación** para ver si hay algo anterior al 7 feb:

   ```bash
   find /ruta/del/proyecto -name "*.sqlite3*" -o -name "*.sql" -mtime +20 2>/dev/null | xargs ls -la
   ```

Si en el servidor no se ejecuta ningún script de backup automático (o solo se guardan pocos días), es posible que **no exista** un backup de BD de “antes del 7 de febrero” en el servidor.

---

## 2. Restaurar el **formato** de cotizaciones (código, no BD)

Los cambios que afectaron el formato de los PDF se hicieron el **7 feb 2026** en la plantilla base de cotizaciones. Esa historia está en **Git**.

### 2.1 Commits relevantes (template `base_cotizacion_pdf.html`)

| Commit     | Fecha     | Descripción |
|-----------|-----------|-------------|
| `0ac45c80` | 5 feb 2026 | **Último estado antes de los cambios del 7 feb** (fix tabla genérica, página en blanco) |
| `ae0ebe77` | 7 feb 2026 | Cambios erróneos: body con `cotizacion-{{ tipo }}`, incluye traslados |
| `ef0e0eb3` | 7 feb 2026 | Margen 4.77cm traslados/paquete; refuerzo margin-top tablas |
| `462fcc83` | 7 feb 2026 | page cotizacion-servicios globalmente |
| `91c36a3f` | 7 feb 2026 | **Revert** de los cambios erróneos (body por tipo, solo vuelos/hospedaje) |
| `f12d1629` | 9 feb 2026 | Visibilidad tablas, términos en 1ª página con spacer |

### 2.2 Restaurar solo la plantilla a “antes del 7 de febrero”

Para dejar la plantilla base como estaba **justo antes** del 7 feb (commit del 5 feb):

```bash
cd /ruta/al/proyecto
git show 0ac45c80:ventas/templates/ventas/pdf/base_cotizacion_pdf.html > ventas/templates/ventas/pdf/base_cotizacion_pdf_5feb.html
# Revisar base_cotizacion_pdf_5feb.html y, si es la versión deseada, reemplazar la actual:
# mv ventas/templates/ventas/pdf/base_cotizacion_pdf.html ventas/templates/ventas/pdf/base_cotizacion_pdf_backup_actual.html
# mv ventas/templates/ventas/pdf/base_cotizacion_pdf_5feb.html ventas/templates/ventas/pdf/base_cotizacion_pdf.html
```

**Nota:** La versión del 5 feb **no** incluye la clase `cotizacion-tours` en el `<body>` (tours se añadió después). Si necesitas mantener tours y solo deshacer lo del 7 feb, la situación actual (después del revert `91c36a3f`) ya coincide en reglas de `page: cotizacion-servicios` y body por tipo con la lógica “solo vuelos/hospedaje”; la diferencia con el 5 feb es que ahora también está `tours` en el body.

### 2.3 Restaurar todo el proyecto a un punto anterior (tag de backup)

Si en el servidor o en este repo se creó un tag antes del 7 feb:

```bash
git tag | grep backup
# Ejemplo existente: backup_pre_deployment_20251215_225815 (15 dic 2025)
```

Para **ver** el código de ese momento (sin cambiar tu rama actual):

```bash
git checkout backup_pre_deployment_20251215_225815 -- ventas/templates/ventas/pdf/
```

Eso trae la carpeta de PDF de cotizaciones como estaba en diciembre; luego puedes commitear si quieres dejar ese estado en tu rama.

---

## 3. Recomendaciones

1. **Formatos rotos:** Corregir restaurando **código** (plantillas) desde Git (por ejemplo `0ac45c80` para “antes del 7 feb”), no desde un backup de base de datos.
2. **Backups de BD en el servidor:** Revisar en el servidor si existe algún directorio de backups (p. ej. `backups/`, `/var/backups/`) y qué fechas tienen; si no hay nada anterior al 7 feb, no habrá backup de BD de esa fecha.
3. **Backups futuros:** Ejecutar `backup.sh` (o el script del servidor) antes de despliegues importantes; opcionalmente aumentar la retención o copiar un backup “pre-7feb” a otro nombre para no borrarlo a los 7 días.

Si indicas si quieres “formato como el 5 feb” o “mantener tours y solo quitar lo del 7 feb”, se puede concretar exactamente qué archivo restaurar y desde qué commit.
