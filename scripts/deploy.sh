#!/bin/bash
# =============================================================================
# SCRIPT DE DESPLIEGUE A PRODUCCIÓN
# =============================================================================
# Uso: ./scripts/deploy.sh
# 
# Este script realiza un despliegue completo incluyendo:
# - Instalación de dependencias del sistema (libmagic, etc.)
# - Pull de cambios de Git
# - Instalación de dependencias de Python
# - Migraciones de base de datos
# - Recolección de archivos estáticos
# - Reinicio de servicios
# =============================================================================

set -e  # Salir si hay error

# --- Configuración ---
PROJECT_DIR="/home/tellez/sitios/agencia"
BACKUP_DIR="/home/tellez/backups"
VENV_DIR="$PROJECT_DIR/venv"
LOG_FILE="/var/log/deploy_$(date +%Y%m%d_%H%M%S).log"

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

# =============================================================================
# PASO 0: Verificar que somos root
# =============================================================================
if [ "$EUID" -ne 0 ]; then
    error "Este script debe ejecutarse como root"
fi

log "=========================================="
log "🚀 INICIANDO DESPLIEGUE A PRODUCCIÓN"
log "=========================================="

# =============================================================================
# PASO 1: Instalar dependencias del sistema operativo
# =============================================================================
log ""
log "📦 Verificando dependencias del sistema..."

# Lista de paquetes requeridos
SYSTEM_PACKAGES=(
    "libmagic1"        # Requerido por python-magic
    "libmagic-dev"     # Headers para compilar (opcional pero recomendado)
    "python3-dev"      # Headers de Python
    "libpq-dev"        # Requerido por psycopg2
    "build-essential"  # Herramientas de compilación
)

# Actualizar lista de paquetes (solo si no se actualizó en las últimas 24h)
LAST_UPDATE=$(stat -c %Y /var/lib/apt/lists/ 2>/dev/null || echo 0)
CURRENT_TIME=$(date +%s)
if [ $((CURRENT_TIME - LAST_UPDATE)) -gt 86400 ]; then
    log "Actualizando lista de paquetes..."
    apt-get update -qq
fi

# Instalar paquetes faltantes
for pkg in "${SYSTEM_PACKAGES[@]}"; do
    if ! dpkg -l | grep -q "^ii  $pkg "; then
        log "Instalando $pkg..."
        apt-get install -y -qq "$pkg"
    else
        log "✅ $pkg ya instalado"
    fi
done

# =============================================================================
# PASO 2: Crear backup
# =============================================================================
log ""
log "💾 Creando backup de la base de datos..."

mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

cd "$PROJECT_DIR"

# Backup de SQLite si existe
if [ -f "db.sqlite3" ]; then
    cp db.sqlite3 "$BACKUP_DIR/db_backup_$TIMESTAMP.sqlite3"
    log "✅ Backup SQLite creado: db_backup_$TIMESTAMP.sqlite3"
fi

# Backup de PostgreSQL si está configurado
if grep -q "DB_ENGINE=django.db.backends.postgresql" .env 2>/dev/null; then
    source .env
    PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -U "$DB_USER" -p "$DB_PORT" "$DB_NAME" > "$BACKUP_DIR/pg_backup_$TIMESTAMP.sql" 2>/dev/null && \
        log "✅ Backup PostgreSQL creado" || \
        warn "No se pudo crear backup de PostgreSQL (puede que no haya cambios)"
fi

# Limpiar backups antiguos (más de 7 días)
find "$BACKUP_DIR" -name "db_backup_*.sqlite3" -mtime +7 -delete 2>/dev/null || true
find "$BACKUP_DIR" -name "pg_backup_*.sql" -mtime +7 -delete 2>/dev/null || true

# =============================================================================
# PASO 3: Pull de cambios
# =============================================================================
log ""
log "⬇️ Descargando cambios de Git..."

cd "$PROJECT_DIR"

# Guardar estado actual para posible rollback
CURRENT_COMMIT=$(git rev-parse HEAD)
log "Commit actual: $CURRENT_COMMIT"

# Pull cambios
git fetch origin master
git pull origin master

NEW_COMMIT=$(git rev-parse HEAD)
if [ "$CURRENT_COMMIT" != "$NEW_COMMIT" ]; then
    log "✅ Actualizado a commit: $NEW_COMMIT"
    log "Cambios:"
    git log --oneline "$CURRENT_COMMIT..$NEW_COMMIT" | head -10
else
    log "ℹ️ No hay cambios nuevos"
fi

# =============================================================================
# PASO 4: Activar entorno virtual e instalar dependencias Python
# =============================================================================
log ""
log "🐍 Configurando entorno Python..."

# Crear venv si no existe
if [ ! -d "$VENV_DIR" ]; then
    log "Creando entorno virtual..."
    python3 -m venv "$VENV_DIR"
fi

# Activar venv
source "$VENV_DIR/bin/activate"

# Actualizar pip
pip install --upgrade pip -q

# Instalar dependencias
log "📦 Instalando dependencias de Python..."
pip install -r requirements.txt -q

# Verificar que python-magic funciona
python3 -c "import magic; magic.from_buffer(b'test', mime=True)" && \
    log "✅ python-magic funcionando correctamente" || \
    error "python-magic no funciona - verificar libmagic"

# =============================================================================
# PASO 5: Verificar archivo .env
# =============================================================================
log ""
log "🔐 Verificando configuración..."

if [ ! -f ".env" ]; then
    error "Archivo .env no encontrado. Crear desde .env.production.example"
fi

# Verificar variables críticas
source .env
if [ -z "$SECRET_KEY" ]; then
    error "SECRET_KEY no configurada en .env"
fi

if [ "$DEBUG" = "True" ] || [ "$DEBUG" = "true" ]; then
    warn "⚠️ DEBUG está habilitado - NO recomendado para producción"
fi

# =============================================================================
# PASO 6: Migraciones de base de datos
# =============================================================================
log ""
log "🗄️ Aplicando migraciones..."

python3 manage.py migrate --noinput

# =============================================================================
# PASO 7: Recolectar archivos estáticos
# =============================================================================
log ""
log "📂 Recolectando archivos estáticos..."

python3 manage.py collectstatic --noinput -v 0

# =============================================================================
# PASO 8: Reiniciar servicios
# =============================================================================
log ""
log "🔄 Reiniciando servicios..."

# Reiniciar Gunicorn
if systemctl is-active --quiet gunicorn; then
    systemctl restart gunicorn
    log "✅ Gunicorn reiniciado"
else
    warn "Gunicorn no está activo como servicio"
fi

# Recargar Nginx
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
    log "✅ Nginx recargado"
fi

# =============================================================================
# PASO 9: Verificación final
# =============================================================================
log ""
log "🔍 Verificación final..."

sleep 2

# Verificar que Gunicorn responde
if systemctl is-active --quiet gunicorn; then
    log "✅ Gunicorn: activo"
else
    error "Gunicorn no está respondiendo"
fi

# Verificar respuesta HTTP
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://movums.com.mx/ --max-time 10 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    log "✅ HTTPS respondiendo: $HTTP_CODE"
else
    warn "⚠️ HTTPS código: $HTTP_CODE - verificar manualmente"
fi

# =============================================================================
# RESUMEN
# =============================================================================
log ""
log "=========================================="
log "✅ DESPLIEGUE COMPLETADO EXITOSAMENTE"
log "=========================================="
log ""
log "📋 Resumen:"
log "   - Commit desplegado: $(git rev-parse --short HEAD)"
log "   - Backup creado: $TIMESTAMP"
log "   - Log guardado en: $LOG_FILE"
log ""
log "🔗 Verificar en: https://movums.com.mx"
log ""
