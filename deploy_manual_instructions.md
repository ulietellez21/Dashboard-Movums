# Instrucciones de Despliegue Manual

Como el servidor requiere autenticación interactiva, aquí están los pasos para hacer el despliegue manualmente:

## Conexión al Servidor

```bash
ssh tellez@206.189.223.176
# Contraseña: [REDACTED_SSH_PASSWORD]
```

## Pasos de Despliegue

Una vez conectado, ejecuta estos comandos en orden:

### 1. Encontrar el directorio del proyecto
```bash
find ~ -name "agencia-web-project" -type d 2>/dev/null
# O buscar en otras ubicaciones comunes:
find /var/www -name "agencia-web-project" -type d 2>/dev/null
find /home -name "agencia-web-project" -type d 2>/dev/null
```

### 2. Ir al directorio del proyecto
```bash
cd /ruta/encontrada/agencia-web-project
# O la ruta que encontraste
```

### 3. Hacer backup de la base de datos
```bash
# Si usas SQLite:
cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)

# Si usas PostgreSQL:
pg_dump nombre_db > backup_db_$(date +%Y%m%d_%H%M%S).sql

# Si usas MySQL:
mysqldump -u usuario -p nombre_db > backup_db_$(date +%Y%m%d_%H%M%S).sql
```

### 4. Verificar rama actual
```bash
git branch
# Debe estar en master
```

### 5. Hacer pull de los cambios
```bash
git pull origin master
```

### 6. Activar entorno virtual (si aplica)
```bash
source venv/bin/activate
# O
source env/bin/activate
```

### 7. Instalar dependencias nuevas
```bash
pip install -r requirements.txt
```

### 8. Aplicar migraciones
```bash
python manage.py migrate
```

### 9. Recolectar archivos estáticos
```bash
python manage.py collectstatic --noinput
```

### 10. Reiniciar el servicio

**Si usas systemd:**
```bash
sudo systemctl restart gunicorn
# O
sudo systemctl restart agencia-web
```

**Si usas supervisor:**
```bash
sudo supervisorctl restart agencia-web
```

**Si usas Gunicorn directamente:**
```bash
pkill -HUP gunicorn
# O encontrar el proceso y reiniciarlo
ps aux | grep gunicorn
kill -HUP <PID>
```

### 11. Verificar que funciona
```bash
curl http://localhost:8000
# O verificar los logs
sudo journalctl -u gunicorn -n 50
```

## Verificación Post-Despliegue

- [ ] Acceso al dashboard funciona
- [ ] Crear nueva venta funciona
- [ ] Generar contrato DOCX funciona
- [ ] Dashboard de Kilómetros Movums accesible
- [ ] Promociones se pueden crear y aplicar
- [ ] Ventas internacionales funcionan correctamente

