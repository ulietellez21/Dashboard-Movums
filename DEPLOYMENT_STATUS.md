# Estado del Despliegue

## ⚠️ Situación Actual

El servidor **206.189.223.176** está configurado para **solo aceptar autenticación por clave SSH**, no por contraseña. Esto es una configuración de seguridad común en servidores de producción.

## ✅ Completado

- ✅ Cambios commitados y subidos a GitHub
- ✅ Backups locales creados
- ✅ Scripts de despliegue preparados

## 🔧 Opciones para Completar el Despliegue

### Opción 1: Configurar Clave SSH (Recomendado)

1. **Generar clave SSH localmente** (si no tienes una):
```bash
ssh-keygen -t ed25519 -C "tu_email@ejemplo.com"
# Presiona Enter para usar la ubicación por defecto
# Opcional: agrega una frase de contraseña
```

2. **Copiar la clave pública al servidor**:
```bash
ssh-copy-id tellez@206.189.223.176
# Ingresa la contraseña cuando se solicite
```

3. **Probar la conexión**:
```bash
ssh tellez@206.189.223.176
# Ahora debería conectarse sin pedir contraseña
```

4. **Ejecutar el despliegue**:
```bash
./deploy_to_server.sh
```

### Opción 2: Despliegue Manual (Más Seguro)

Conéctate manualmente al servidor y ejecuta los comandos:

```bash
# 1. Conectar
ssh tellez@206.189.223.176
# Contraseña: EdgarTellez73!

# 2. Encontrar el proyecto
find ~ -name "agencia-web-project" -type d
# O buscar en otras ubicaciones:
find /var/www -name "agencia-web-project" -type d
find /home -name "agencia-web-project" -type d

# 3. Ir al directorio
cd /ruta/encontrada/agencia-web-project

# 4. Backup
cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)

# 5. Pull
git pull origin master

# 6. Activar venv (si aplica)
source venv/bin/activate

# 7. Dependencias
pip install -r requirements.txt

# 8. Migraciones
python manage.py migrate

# 9. Static files
python manage.py collectstatic --noinput

# 10. Reiniciar servicio
sudo systemctl restart gunicorn
# O el servicio que uses
```

### Opción 3: Habilitar Autenticación por Contraseña en el Servidor

**⚠️ No recomendado por seguridad**, pero si es necesario:

En el servidor, editar `/etc/ssh/sshd_config`:
```bash
PasswordAuthentication yes
PubkeyAuthentication yes
```

Luego reiniciar SSH:
```bash
sudo systemctl restart sshd
```

## 📋 Checklist de Despliegue

Una vez que puedas conectarte, verifica:

- [ ] Backup de base de datos creado
- [ ] `git pull origin master` ejecutado
- [ ] Migraciones aplicadas (`python manage.py migrate`)
- [ ] Archivos estáticos recolectados
- [ ] Servicio reiniciado
- [ ] Aplicación funcionando correctamente
- [ ] Contrato DOCX se genera correctamente
- [ ] Dashboard de Kilómetros Movums accesible
- [ ] Promociones funcionan

## 🆘 Si Algo Sale Mal

### Rollback Rápido
```bash
# En el servidor
cd /ruta/a/proyecto
git reset --hard HEAD~1
# O volver a un commit específico
git reset --hard <commit-hash>
sudo systemctl restart gunicorn
```

### Ver Logs
```bash
sudo journalctl -u gunicorn -n 100
# O
sudo tail -f /var/log/gunicorn/error.log
```

## 📝 Notas

- Los cambios ya están en GitHub, así que puedes hacer `git pull` cuando tengas acceso
- Las migraciones son importantes: asegúrate de aplicarlas
- El servicio debe reiniciarse para cargar los nuevos cambios
















