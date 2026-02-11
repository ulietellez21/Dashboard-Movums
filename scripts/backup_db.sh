#!/bin/bash
# =============================================================================
# Script de Respaldo de Base de Datos PostgreSQL
# Proyecto: Agencia Web (Dashboard Movums)
# =============================================================================
#
# Uso: ./backup_db.sh
# 
# Variables de entorno requeridas:
#   - DB_NAME: Nombre de la base de datos
#   - DB_USER: Usuario de PostgreSQL
#   - DB_HOST: Host del servidor PostgreSQL
#   - DB_PORT: Puerto (default: 25060 para DigitalOcean managed DB)
#   - DB_PASSWORD: Contraseña (usada via PGPASSWORD)
#
# El script crea respaldos comprimidos y elimina los mayores a 7 días.
# =============================================================================

set -e  # Salir si cualquier comando falla

# --- Cargar variables de entorno desde .env ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${PROJECT_DIR}/.env"

if [ -f "$ENV_FILE" ]; then
    # Exportar variables del .env (ignorando comentarios y líneas vacías)
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)
    echo "[INFO] Variables cargadas desde: $ENV_FILE"
fi

# --- Configuración ---
BACKUP_DIR="${PROJECT_DIR}/backups"
RETENTION_DAYS=7
TIMESTAMP=$(date +"%Y-%m-%d_%H%M%S")
BACKUP_FILE="db_backup_${TIMESTAMP}.sql.gz"

# --- Validar variables de entorno ---
if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ] || [ -z "$DB_HOST" ] || [ -z "$DB_PASSWORD" ]; then
    echo "[ERROR] Variables de entorno faltantes. Requeridas: DB_NAME, DB_USER, DB_HOST, DB_PASSWORD"
    exit 1
fi

# Puerto por defecto para DigitalOcean Managed PostgreSQL
DB_PORT="${DB_PORT:-25060}"

# --- Crear directorio de backups si no existe ---
mkdir -p "$BACKUP_DIR"

echo "=============================================="
echo "Iniciando respaldo de base de datos"
echo "Fecha: $(date)"
echo "Base de datos: $DB_NAME"
echo "Host: $DB_HOST:$DB_PORT"
echo "=============================================="

# --- Ejecutar pg_dump con compresión ---
export PGPASSWORD="$DB_PASSWORD"

pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
    | gzip > "${BACKUP_DIR}/${BACKUP_FILE}"

unset PGPASSWORD

# --- Verificar que el archivo se creó correctamente ---
if [ -f "${BACKUP_DIR}/${BACKUP_FILE}" ]; then
    FILE_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
    echo "[OK] Respaldo creado: ${BACKUP_FILE} (${FILE_SIZE})"
else
    echo "[ERROR] Falló la creación del respaldo"
    exit 1
fi

# --- Eliminar respaldos antiguos (mayores a 7 días) ---
echo ""
echo "Limpiando respaldos antiguos (> ${RETENTION_DAYS} días)..."

DELETED_COUNT=$(find "$BACKUP_DIR" -name "db_backup_*.sql.gz" -type f -mtime +${RETENTION_DAYS} | wc -l)

find "$BACKUP_DIR" -name "db_backup_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete

echo "[OK] Respaldos eliminados: ${DELETED_COUNT}"

# --- Mostrar respaldos actuales ---
echo ""
echo "Respaldos disponibles:"
ls -lh "$BACKUP_DIR"/db_backup_*.sql.gz 2>/dev/null || echo "  (ninguno)"

echo ""
echo "=============================================="
echo "Respaldo completado exitosamente"
echo "=============================================="
