# 🔥 Pasos para Revisar el Firewall en DigitalOcean

## Opción 1: Desde el Panel Web de DigitalOcean

### Paso 1: Acceder al Panel
1. Ve a https://cloud.digitalocean.com/
2. Inicia sesión con tus credenciales

### Paso 2: Localizar tu Droplet
1. En el menú lateral, haz clic en **"Droplets"**
2. Busca tu servidor (debería estar listado con la IP 143.198.48.195)
3. Haz clic en el nombre del droplet para ver sus detalles

### Paso 3: Verificar Firewall (si está configurado)
1. En la página del droplet, busca la sección **"Networking"**
2. Si hay un Firewall asignado, aparecerá listado
3. Haz clic en el nombre del firewall para ver sus reglas

### Paso 4: Verificar Reglas del Firewall
1. En la página del firewall, verifica las reglas **"Inbound"**
2. Debe haber una regla que permita:
   - **Type**: SSH
   - **Port Range**: 22
   - **Sources**: All IPv4, All IPv6 (o tu IP específica)

### Paso 5: Si NO hay firewall configurado
- El problema puede estar en el firewall del sistema operativo (iptables/ufw)
- O el servicio SSH puede estar detenido

---

## Opción 2: Desde la Consola Web de DigitalOcean

### Paso 1: Acceder a la Consola
1. En la página de tu Droplet, haz clic en **"Access"** en el menú superior
2. Luego haz clic en **"Launch Droplet Console"**
3. Esto abrirá una terminal en el navegador

### Paso 2: Verificar Estado del Servicio SSH
```bash
sudo systemctl status ssh
# o
sudo systemctl status sshd
```

### Paso 3: Verificar Firewall del Sistema (UFW)
```bash
sudo ufw status
```

Si está activo, verifica que permita SSH:
```bash
sudo ufw allow 22/tcp
sudo ufw reload
```

### Paso 4: Verificar Firewall del Sistema (iptables)
```bash
sudo iptables -L -n | grep 22
```

### Paso 5: Si el servicio SSH está detenido
```bash
sudo systemctl start ssh
sudo systemctl enable ssh
```

---

## Opción 3: Desde el Panel de Networking

1. En el menú lateral de DigitalOcean, haz clic en **"Networking"**
2. Luego haz clic en **"Firewalls"**
3. Si tienes firewalls configurados, revisa cada uno
4. Asegúrate de que permitan tráfico SSH (puerto 22)

---

## Solución Rápida: Permitir SSH desde el Panel

1. Ve a **Networking > Firewalls**
2. Si tienes un firewall, haz clic en él
3. En **"Inbound Rules"**, agrega:
   - **Type**: SSH
   - **Port**: 22
   - **Sources**: All IPv4, All IPv6
4. Guarda los cambios

---

## Alternativa: Sincronizar desde la Consola Web

Si SSH no está disponible, puedes usar la consola web para sincronizar:

1. Ve a tu Droplet en DigitalOcean
2. Haz clic en **"Access"** > **"Launch Droplet Console"**
3. Ejecuta estos comandos:

```bash
cd /home/tellez/Dashboard-Movums
git pull
chown -R tellez:tellez ventas/templates/ventas/pdf/ static/img/
systemctl restart gunicorn
```

Los cambios ya están en GitHub, solo necesitas hacer `git pull`.


