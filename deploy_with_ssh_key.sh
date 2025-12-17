#!/bin/bash
# Despliegue usando clave SSH específica

SERVER="tellez@206.189.223.176"
SSH_KEY="$HOME/.ssh/id_ed25519"

echo "🚀 Iniciando despliegue con clave SSH..."
echo ""

# Función para ejecutar comandos remotos
run_remote() {
    ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -o PreferredAuthentications=publickey -o StrictHostKeyChecking=no "$SERVER" "$1"
}

# Probar conexión
echo "📋 Probando conexión..."
if run_remote "echo 'Conexión exitosa'"; then
    echo "✅ Conexión establecida"
else
    echo "❌ Error de conexión. Verificando..."
    # Intentar con contraseña como fallback
    echo "Intentando con autenticación por contraseña..."
    sshpass -p "EdgarTellez73!" ssh -o StrictHostKeyChecking=no "$SERVER" "echo 'Conexión con contraseña exitosa'"
    if [ $? -eq 0 ]; then
        echo "✅ Usando autenticación por contraseña"
        # Reconfigurar función para usar contraseña
        run_remote() {
            sshpass -p "EdgarTellez73!" ssh -o StrictHostKeyChecking=no "$SERVER" "$1"
        }
    else
        echo "❌ No se pudo conectar. Verifica las credenciales."
        exit 1
    fi
fi

# Continuar con despliegue...
echo ""
echo "📋 Buscando proyecto..."
PROJECT_DIR=$(run_remote "find ~ -name 'agencia-web-project' -type d 2>/dev/null | head -1")
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(run_remote "find /var/www -name 'agencia-web-project' -type d 2>/dev/null | head -1")
fi
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR="~/agencia-web-project"
fi

echo "📂 Proyecto: $PROJECT_DIR"

echo ""
echo "📋 Haciendo pull..."
run_remote "cd $PROJECT_DIR && git pull origin master"

echo ""
echo "📋 Aplicando migraciones..."
run_remote "cd $PROJECT_DIR && source venv/bin/activate 2>/dev/null || source env/bin/activate 2>/dev/null; python manage.py migrate --noinput"

echo ""
echo "📋 Recolectando estáticos..."
run_remote "cd $PROJECT_DIR && source venv/bin/activate 2>/dev/null || source env/bin/activate 2>/dev/null; python manage.py collectstatic --noinput"

echo ""
echo "📋 Reiniciando servicio..."
run_remote "sudo systemctl restart gunicorn 2>/dev/null || sudo systemctl restart agencia-web 2>/dev/null || sudo supervisorctl restart agencia-web 2>/dev/null || pkill -HUP gunicorn"

echo ""
echo "✅ Despliegue completado!"
