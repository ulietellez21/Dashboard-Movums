#!/usr/bin/env bash
# backup.sh - Copia de seguridad de la base de datos SQLite
# Uso: ./backup.sh
# Mantiene backups en backups/ y elimina los de más de 7 días.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DB_FILE="db.sqlite3"
BACKUP_DIR="backups"
RETENTION_DAYS=7

# Nombre del archivo con fecha y hora: db_backup_2023-10-27_1400.sqlite3
TIMESTAMP=$(date +%Y-%m-%d_%H%M)
BACKUP_NAME="db_backup_${TIMESTAMP}.sqlite3"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

if [ ! -f "$DB_FILE" ]; then
    echo "❌ No se encontró $DB_FILE. Nada que respaldar."
    exit 1
fi

mkdir -p "$BACKUP_DIR"

cp "$DB_FILE" "$BACKUP_PATH"
echo "✅ Backup creado: $BACKUP_PATH"

# Borrar backups más viejos de RETENTION_DAYS días
find "$BACKUP_DIR" -name "db_backup_*.sqlite3" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
echo "📁 Backups en $BACKUP_DIR (se conservan últimos $RETENTION_DAYS días)."
echo "🟢 Tus datos están respaldados."
