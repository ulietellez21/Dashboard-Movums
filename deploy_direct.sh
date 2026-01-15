#!/bin/bash
# Script de despliegue directo usando sshpass

SERVER="root@206.189.223.176"
PASSWORD="[REDACTED_SSH_PASSWORD]"

echo "🚀 Iniciando despliegue al servidor..."
echo ""

# Función para ejecutar comandos
run_cmd() {
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no "$SERVER" "$1"
}

# Encontrar proyecto
echo "📋 Buscando proyecto..."
PROJECT_DIR=$(run_cmd "find /home/tellez -name 'agencia-web-project' -type d 2>/dev/null | head -1")
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(run_cmd "find /var/www -name 'agencia-web-project' -type d 2>/dev/null | head -1")
fi
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(run_cmd "find /root -name 'agencia-web-project' -type d 2>/dev/null | head -1")
fi

if [ -z "$PROJECT_DIR" ]; then
    echo "❌ No se encontró el proyecto"
    echo "Buscando en todo el sistema..."
    run_cmd "find / -name 'agencia-web-project' -type d 2>/dev/null | head -3"
    exit 1
fi

echo "✅ Proyecto encontrado: $PROJECT_DIR"
echo ""

# Backup
echo "📦 Haciendo backup..."
run_cmd "cd $PROJECT_DIR && if [ -f db.sqlite3 ]; then cp db.sqlite3 db.sqlite3.backup_\$(date +%Y%m%d_%H%M%S) && echo '✅ Backup creado'; else echo '⚠️  No SQLite'; fi"

# Pull
echo ""
echo "📥 Descargando cambios..."
run_cmd "cd $PROJECT_DIR && git pull origin master"

# Venv y dependencias
echo ""
echo "🐍 Activando venv e instalando dependencias..."
run_cmd "cd $PROJECT_DIR && source venv/bin/activate 2>/dev/null || source env/bin/activate 2>/dev/null; pip install -q -r requirements.txt 2>/dev/null || echo '⚠️  Error en dependencias'"

# Migraciones
echo ""
echo "🔄 Aplicando migraciones..."
run_cmd "cd $PROJECT_DIR && source venv/bin/activate 2>/dev/null || source env/bin/activate 2>/dev/null; python manage.py migrate --noinput"

# Collectstatic
echo ""
echo "📁 Recolectando estáticos..."
run_cmd "cd $PROJECT_DIR && source venv/bin/activate 2>/dev/null || source env/bin/activate 2>/dev/null; python manage.py collectstatic --noinput"

# Reiniciar
echo ""
echo "🔄 Reiniciando servicio..."
run_cmd "systemctl restart gunicorn 2>/dev/null || systemctl restart agencia-web 2>/dev/null || supervisorctl restart agencia-web 2>/dev/null || pkill -HUP gunicorn 2>/dev/null || echo '⚠️  No se pudo reiniciar'"

# Verificar
echo ""
echo "📋 Verificando..."
sleep 3
HTTP_CODE=$(run_cmd "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000 2>/dev/null || echo '000'")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "✅ Servicio respondiendo (HTTP $HTTP_CODE)"
else
    echo "⚠️  Servicio puede no estar respondiendo (HTTP $HTTP_CODE)"
fi

echo ""
echo "✅ Despliegue completado!"
















