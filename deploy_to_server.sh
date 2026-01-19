#!/bin/bash
# Script de despliegue automático al servidor DigitalOcean
# Uso: ./deploy_to_server.sh

SERVER="root@206.189.223.176"
PASSWORD="Venado1998"

echo "🚀 Iniciando despliegue al servidor DigitalOcean..."
echo "📅 Fecha: $(date)"
echo ""

# Verificar si sshpass está instalado
if ! command -v sshpass &> /dev/null; then
    echo "⚠️  sshpass no está instalado. Instalando..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install hudochenkov/sshpass/sshpass
        else
            echo "❌ Por favor instala Homebrew primero: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo "   Luego ejecuta: brew install hudochenkov/sshpass/sshpass"
            exit 1
        fi
    else
        # Linux
        sudo apt-get update && sudo apt-get install -y sshpass
    fi
fi

echo "✅ sshpass disponible"
echo ""

# Función para ejecutar comandos en el servidor
run_remote() {
    sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$SERVER" "$1"
}

# Función para copiar archivos al servidor
copy_to_server() {
    sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$1" "$SERVER:$2"
}

echo "📋 Paso 1: Verificando conexión al servidor..."
if run_remote "echo 'Conexión exitosa'"; then
    echo "✅ Conexión establecida"
else
    echo "❌ Error al conectar al servidor"
    exit 1
fi

echo ""
echo "📋 Paso 2: Detectando ubicación del proyecto..."
PROJECT_DIR=$(run_remote "find /home -name 'manage.py' -type f 2>/dev/null | grep -i agencia | head -1 | xargs dirname 2>/dev/null")
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(run_remote "find ~ -name 'agencia-web-project' -type d 2>/dev/null | head -1")
fi
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(run_remote "find /var/www -name 'agencia-web-project' -type d 2>/dev/null | head -1")
fi

if [ -z "$PROJECT_DIR" ]; then
    echo "⚠️  No se encontró el proyecto. Usando directorio por defecto..."
    PROJECT_DIR="/home/tellez/sitios/agencia"
else
    echo "✅ Proyecto encontrado en: $PROJECT_DIR"
fi

echo ""
echo "📋 Paso 3: Haciendo backup del servidor..."
run_remote "cd $PROJECT_DIR && if [ -f db.sqlite3 ]; then cp db.sqlite3 db.sqlite3.backup_\$(date +%Y%m%d_%H%M%S) && echo '✅ Backup de BD creado'; else echo '⚠️  No se encontró db.sqlite3'; fi"

echo ""
echo "📋 Paso 4: Verificando rama actual..."
run_remote "cd $PROJECT_DIR && git branch"

echo ""
echo "📋 Paso 5: Haciendo pull de los cambios..."
run_remote "cd $PROJECT_DIR && git pull origin master"

if [ $? -eq 0 ]; then
    echo "✅ Pull completado"
else
    echo "❌ Error al hacer pull"
    exit 1
fi

echo ""
echo "📋 Paso 6: Activando entorno virtual (si existe)..."
run_remote "cd $PROJECT_DIR && if [ -d venv ]; then source venv/bin/activate && echo '✅ Entorno virtual activado'; elif [ -d env ]; then source env/bin/activate && echo '✅ Entorno virtual activado'; else echo '⚠️  No se encontró entorno virtual'; fi"

echo ""
echo "📋 Paso 7: Instalando dependencias (si hay cambios)..."
run_remote "cd $PROJECT_DIR && if [ -f requirements.txt ]; then pip install -q -r requirements.txt && echo '✅ Dependencias instaladas'; else echo '⚠️  No se encontró requirements.txt'; fi"

echo ""
echo "📋 Paso 8: Aplicando migraciones..."
run_remote "cd $PROJECT_DIR && python3 manage.py migrate --noinput"

if [ $? -eq 0 ]; then
    echo "✅ Migraciones aplicadas"
else
    echo "❌ Error al aplicar migraciones"
    exit 1
fi

echo ""
echo "📋 Paso 9: Recolectando archivos estáticos..."
run_remote "cd $PROJECT_DIR && python3 manage.py collectstatic --noinput"

echo ""
echo "📋 Paso 10: Reiniciando servicios..."

# Intentar diferentes métodos de reinicio
if run_remote "sudo systemctl is-active --quiet gunicorn 2>/dev/null"; then
    echo "   Detectado: systemd (gunicorn)"
    run_remote "sudo systemctl restart gunicorn && echo '✅ Gunicorn reiniciado'"
elif run_remote "sudo systemctl is-active --quiet agencia-web 2>/dev/null"; then
    echo "   Detectado: systemd (agencia-web)"
    run_remote "sudo systemctl restart agencia-web && echo '✅ Servicio reiniciado'"
elif run_remote "supervisorctl status 2>/dev/null | grep -q agencia"; then
    echo "   Detectado: supervisor"
    run_remote "sudo supervisorctl restart agencia-web && echo '✅ Servicio reiniciado'"
else
    echo "   ⚠️  No se detectó servicio automático. Reiniciando manualmente..."
    run_remote "pkill -HUP gunicorn && echo '✅ Gunicorn reiniciado (HUP)' || echo '⚠️  No se pudo reiniciar automáticamente'"
fi

echo ""
echo "📋 Paso 11: Verificando estado del servicio..."
sleep 3
if run_remote "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000 | grep -q '200\|301\|302'"; then
    echo "✅ Servicio respondiendo correctamente"
else
    echo "⚠️  El servicio puede no estar respondiendo. Verifica manualmente."
fi

echo ""
echo "✅ Despliegue completado!"
echo ""
echo "📝 Próximos pasos:"
echo "   1. Verificar que la aplicación funciona correctamente"
echo "   2. Probar las nuevas funcionalidades (contrato DOCX, promociones, etc.)"
echo "   3. Revisar logs si hay algún problema:"
echo "      sudo journalctl -u gunicorn -n 50"
echo ""
















