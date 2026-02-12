#!/bin/bash
# =============================================================================
# SCRIPT DE DESPLIEGUE A PRODUCCIÓN
# Ejecutar desde la consola de DigitalOcean (Droplet Console)
# =============================================================================

set -e  # Salir si hay error

echo "=========================================="
echo "🚀 INICIANDO DESPLIEGUE A PRODUCCIÓN"
echo "=========================================="

# --- CONFIGURACIÓN ---
PROJECT_DIR="/home/tellez/agencia-web-project"
BACKUP_DIR="/home/tellez/backups"

# Crear directorio de backups si no existe
mkdir -p "$BACKUP_DIR"

# --- 1. IR AL DIRECTORIO DEL PROYECTO ---
echo ""
echo "📁 Accediendo al directorio del proyecto..."
cd "$PROJECT_DIR" || {
    echo "❌ ERROR: No se encontró el directorio $PROJECT_DIR"
    echo "Buscando el proyecto..."
    find /home -name "agencia-web-project" -type d 2>/dev/null
    exit 1
}

echo "✅ Directorio: $(pwd)"

# --- 2. BACKUP DE BASE DE DATOS ---
echo ""
echo "💾 Creando backup de la base de datos..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Detectar tipo de base de datos
if [ -f "db.sqlite3" ]; then
    cp db.sqlite3 "$BACKUP_DIR/db_backup_$TIMESTAMP.sqlite3"
    echo "✅ Backup SQLite creado: db_backup_$TIMESTAMP.sqlite3"
fi

# --- 3. VERIFICAR RAMA GIT ---
echo ""
echo "🔍 Verificando rama Git..."
git branch
git status

# --- 4. PULL DE CAMBIOS ---
echo ""
echo "⬇️  Descargando cambios de GitHub..."
git pull origin master

# --- 5. ACTIVAR ENTORNO VIRTUAL ---
echo ""
echo "🐍 Activando entorno virtual..."
source venv/bin/activate || source env/bin/activate || {
    echo "❌ ERROR: No se encontró entorno virtual"
    exit 1
}

# --- 6. INSTALAR DEPENDENCIAS ---
echo ""
echo "📦 Verificando dependencias..."
pip install -r requirements.txt --quiet

# --- 7. VERIFICAR/CREAR ARCHIVO .env DE PRODUCCIÓN ---
echo ""
echo "🔐 Verificando configuración de producción..."

if [ ! -f ".env" ]; then
    echo "❌ ERROR: No existe archivo .env"
    echo "Creando .env de producción..."
    cat > .env << 'ENVFILE'
# PRODUCCIÓN - Completar valores
DEBUG=False
SECRET_KEY=CAMBIAR_POR_CLAVE_SEGURA
ALLOWED_HOSTS=movums.com.mx,www.movums.com.mx,206.189.223.176
DB_ENGINE=django.db.backends.postgresql
DB_NAME=defaultdb
DB_USER=doadmin
DB_PASSWORD=CAMBIAR_POR_PASSWORD_DB
DB_HOST=CAMBIAR_POR_HOST_DB
DB_PORT=25060
ENVFILE
    echo "⚠️  IMPORTANTE: Edita .env con las credenciales correctas"
    echo "   nano .env"
    exit 1
fi

# Verificar variables críticas
echo "Verificando variables de entorno..."
source .env 2>/dev/null || true

if grep -q "CAMBIAR" .env 2>/dev/null; then
    echo "⚠️  ADVERTENCIA: El archivo .env tiene valores por completar"
    echo "   Ejecuta: nano .env"
fi

# --- 8. APLICAR MIGRACIONES ---
echo ""
echo "🗄️  Aplicando migraciones de base de datos..."
python manage.py migrate --noinput

# --- 9. RECOLECTAR ARCHIVOS ESTÁTICOS ---
echo ""
echo "📂 Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# --- 10. REINICIAR SERVICIOS ---
echo ""
echo "🔄 Reiniciando servicios..."

# Intentar diferentes formas de reiniciar
if systemctl is-active --quiet gunicorn 2>/dev/null; then
    sudo systemctl restart gunicorn
    echo "✅ Gunicorn reiniciado (systemd)"
elif systemctl is-active --quiet agencia-web 2>/dev/null; then
    sudo systemctl restart agencia-web
    echo "✅ agencia-web reiniciado (systemd)"
elif command -v supervisorctl &> /dev/null; then
    sudo supervisorctl restart all
    echo "✅ Supervisor reiniciado"
else
    # Reiniciar Gunicorn manualmente
    pkill -HUP gunicorn 2>/dev/null || true
    echo "✅ Señal HUP enviada a Gunicorn"
fi

# --- 11. VERIFICACIÓN ---
echo ""
echo "🔍 Verificando estado del servicio..."
sleep 2

# Verificar que responde
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000 | grep -q "200\|301\|302"; then
    echo "✅ Servidor respondiendo correctamente"
else
    echo "⚠️  Verificar manualmente: curl http://localhost:8000"
fi

# --- RESUMEN ---
echo ""
echo "=========================================="
echo "✅ DESPLIEGUE COMPLETADO"
echo "=========================================="
echo ""
echo "📋 Próximos pasos:"
echo "   1. Verificar en https://movums.com.mx"
echo "   2. Probar login y funcionalidades"
echo "   3. Revisar logs: sudo journalctl -u gunicorn -n 50"
echo ""
echo "🔐 IMPORTANTE - Rotar credenciales:"
echo "   - Cambiar DB_PASSWORD en DigitalOcean"
echo "   - Regenerar SECRET_KEY"
echo "   - Regenerar SENTRY_DSN"
echo ""
