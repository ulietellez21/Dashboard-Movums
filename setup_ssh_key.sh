#!/bin/bash
# Script para configurar clave SSH y desplegar

SERVER="tellez@206.189.223.176"
PASSPHRASE="E^M9gQsy(nf$d&H"

echo "🔑 Configurando clave SSH..."

# Verificar si existe clave SSH
if [ -f ~/.ssh/id_ed25519 ] || [ -f ~/.ssh/id_rsa ]; then
    echo "✅ Clave SSH encontrada"
    KEY_FILE=$(ls ~/.ssh/id_* | grep -v ".pub" | head -1)
    echo "   Usando: $KEY_FILE"
else
    echo "📝 Generando nueva clave SSH..."
    ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "$PASSPHRASE" -C "deployment_key"
    KEY_FILE=~/.ssh/id_ed25519
    echo "✅ Clave generada"
fi

# Intentar copiar la clave al servidor
echo ""
echo "📤 Copiando clave pública al servidor..."
PUBLIC_KEY=$(cat ${KEY_FILE}.pub)

# Usar sshpass para copiar la clave
if command -v sshpass &> /dev/null; then
    echo "$PASSPHRASE" | sshpass -p "$PASSPHRASE" ssh-copy-id -o StrictHostKeyChecking=no "$SERVER" 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Clave copiada exitosamente"
    else
        echo "⚠️  Error al copiar clave. Intentando método alternativo..."
        # Método alternativo: agregar manualmente
        echo "Ejecuta manualmente en el servidor:"
        echo "mkdir -p ~/.ssh && echo '$PUBLIC_KEY' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
    fi
else
    echo "⚠️  sshpass no disponible. Copia manualmente:"
    echo "$PUBLIC_KEY"
    echo ""
    echo "O ejecuta: ssh-copy-id $SERVER"
fi

echo ""
echo "🧪 Probando conexión..."
ssh -o BatchMode=yes -o ConnectTimeout=5 "$SERVER" "echo 'Conexión exitosa'" 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Conexión SSH funcionando sin contraseña"
    echo ""
    echo "🚀 Iniciando despliegue..."
    ./deploy_to_server.sh
else
    echo "⚠️  La conexión aún requiere contraseña"
    echo "   Verifica que la clave se haya copiado correctamente"
fi
