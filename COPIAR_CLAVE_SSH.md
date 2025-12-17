# Instrucciones para Copiar Clave SSH al Servidor

## Clave Pública Generada

Tu clave pública SSH es:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAII6RwGr2Tg6x5UdqQqghqmSD6ecpfK76ebJc7munwoEy deployment_key
```

## Método 1: Copiar Manualmente (Recomendado)

1. **Conéctate al servidor** (puede que funcione desde otro lugar o necesites acceso directo):
```bash
ssh tellez@206.189.223.176
# Contraseña: [REDACTED_SSH_PASSWORD]
```

2. **Una vez conectado, ejecuta estos comandos**:
```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAII6RwGr2Tg6x5UdqQqghqmSD6ecpfK76ebJc7munwoEy deployment_key" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

3. **Prueba la conexión sin contraseña**:
```bash
ssh tellez@206.189.223.176
# Ahora debería conectarse sin pedir contraseña
```

## Método 2: Usar Panel de DigitalOcean

Si tienes acceso al panel de DigitalOcean:

1. Ve a tu droplet
2. Accede a "Access" o "Settings"
3. Busca "SSH Keys" o "Add SSH Key"
4. Pega la clave pública completa
5. Guarda los cambios

## Método 3: Verificar Configuración del Servidor

El servidor puede tener restricciones. Verifica en el servidor:

```bash
# Ver configuración SSH
sudo cat /etc/ssh/sshd_config | grep -E "PasswordAuthentication|PubkeyAuthentication"

# Si PasswordAuthentication está en "no", puedes cambiarlo temporalmente:
sudo sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

## Después de Configurar la Clave

Una vez que la clave SSH esté configurada, ejecuta:

```bash
./deploy_to_server.sh
```

O el despliegue manual siguiendo `deploy_manual_instructions.md`

