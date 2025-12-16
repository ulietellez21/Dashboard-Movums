# Backups del Proyecto

Este directorio contiene las copias de seguridad del proyecto.

## Estructura de Backups

### Base de Datos
- `db.sqlite3.backup_YYYYMMDD_HHMMSS` - Copias de seguridad de la base de datos SQLite

### Git
- **Tags**: `backup_pre_deployment_YYYYMMDD_HHMMSS` - Puntos de restauración en Git
- **Branches**: `backup_pre_deployment_YYYYMMDD_HHMMSS` - Ramas de backup

## Cómo Restaurar

### Restaurar Base de Datos
```bash
# Ver backups disponibles
ls -lh backups/db.sqlite3.backup_*

# Restaurar un backup específico
cp backups/db.sqlite3.backup_YYYYMMDD_HHMMSS db.sqlite3
```

### Restaurar Código desde Git Tag
```bash
# Ver tags de backup
git tag | grep backup_pre_deployment

# Restaurar a un tag específico
git checkout backup_pre_deployment_YYYYMMDD_HHMMSS

# O crear una nueva rama desde el tag
git checkout -b restore_backup backup_pre_deployment_YYYYMMDD_HHMMSS
```

### Restaurar Código desde Branch de Backup
```bash
# Ver branches de backup
git branch | grep backup_pre_deployment

# Cambiar a la rama de backup
git checkout backup_pre_deployment_YYYYMMDD_HHMMSS

# O fusionar cambios de la rama de backup
git merge backup_pre_deployment_YYYYMMDD_HHMMSS
```

## Backup del Servidor (DigitalOcean)

Para hacer backup del servidor, ejecuta en el servidor:

```bash
# Backup de base de datos (PostgreSQL/MySQL)
# PostgreSQL:
pg_dump nombre_db > backup_db_$(date +%Y%m%d_%H%M%S).sql

# MySQL:
mysqldump -u usuario -p nombre_db > backup_db_$(date +%Y%m%d_%H%M%S).sql

# Backup del código
cd /ruta/a/proyecto
tar -czf backup_codigo_$(date +%Y%m%d_%H%M%S).tar.gz .
```

## Frecuencia Recomendada

- **Antes de cada deployment importante**: ✅
- **Semanalmente**: Recomendado
- **Antes de cambios en modelos**: Obligatorio

