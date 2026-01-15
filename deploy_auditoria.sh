#!/bin/bash
# Script de despliegue para sistema de auditoría
SERVER="tellez@206.189.223.176"
PASSWORD="[REDACTED_PASSWORD]"

echo "🚀 Iniciando despliegue al servidor DigitalOcean..."
echo "📅 Fecha: $(date)"
echo ""

# Verificar sshpass
if ! command -v sshpass &> /dev/null; then
    echo "⚠️  sshpass no está instalado. Instalando..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &> /dev/null; then
            brew install hudochenkov/sshpass/sshpass 2>/dev/null || echo "⚠️  Instalación de sshpass requerida manualmente"
        fi
    fi
fi

# Función para ejecutar comandos
run_remote() {
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$SERVER" "$1" 2>&1
}

echo "📋 Paso 1: Verificando conexión..."
if run_remote "echo 'Conexión exitosa'" | grep -q "Conexión exitosa"; then
    echo "✅ Conexión establecida"
else
    echo "❌ Error al conectar. Usa el método manual con DEPLOY_AUDITORIA.md"
    exit 1
fi

echo ""
echo "📋 Paso 2: Detectando proyecto..."
PROJECT_DIR=$(run_remote "find ~ -name 'agencia-web-project' -type d 2>/dev/null | head -1" | grep agencia-web-project | head -1)
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(run_remote "find /var/www -name 'agencia-web-project' -type d 2>/dev/null | head -1" | grep agencia-web-project | head -1)
fi
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR="~/agencia-web-project"
    echo "⚠️  Usando directorio por defecto"
else
    echo "✅ Proyecto encontrado: $PROJECT_DIR"
fi

echo ""
echo "📋 Paso 3: Backup..."
run_remote "cd $PROJECT_DIR && cp db.sqlite3 db.sqlite3.backup_\$(date +%Y%m%d_%H%M%S) 2>/dev/null && echo '✅ Backup creado' || echo '⚠️  No se encontró db.sqlite3'"

echo ""
echo "📋 Paso 4: Pull de cambios..."
run_remote "cd $PROJECT_DIR && git pull origin master"

echo ""
echo "📋 Paso 5: Activando venv..."
run_remote "cd $PROJECT_DIR && source venv/bin/activate 2>/dev/null || source env/bin/activate 2>/dev/null || echo '⚠️  Sin venv'"

echo ""
echo "📋 Paso 6: Instalando dependencias..."
run_remote "cd $PROJECT_DIR && pip install -q -r requirements.txt"

echo ""
echo "📋 Paso 7: Aplicando migraciones..."
run_remote "cd $PROJECT_DIR && python manage.py migrate --noinput"

echo ""
echo "📋 Paso 8: Collectstatic..."
run_remote "cd $PROJECT_DIR && python manage.py collectstatic --noinput"

echo ""
echo "📋 Paso 9: Reiniciando servicio..."
run_remote "sudo systemctl restart gunicorn 2>/dev/null || sudo systemctl restart agencia-web 2>/dev/null || sudo supervisorctl restart agencia-web 2>/dev/null || pkill -HUP gunicorn"

echo ""
echo "✅ Despliegue completado!"
