# Comandos de Despliegue Manual

Como el servidor tiene restricciones de acceso SSH, aquí están los comandos exactos para ejecutar **directamente en el servidor** (usando el panel de DigitalOcean o acceso directo).

## 🔐 Credenciales
- **Servidor**: tellez@206.189.223.176
- **Contraseña temporal**: 31eac78cfd175a773459799b41

## 📋 Comandos a Ejecutar (Copia y Pega)

### 1. Encontrar el proyecto
```bash
find ~ -name "agencia-web-project" -type d
# Si no lo encuentra, buscar en otras ubicaciones:
find /var/www -name "agencia-web-project" -type d
find /home -name "agencia-web-project" -type d
```

### 2. Ir al directorio del proyecto
```bash
cd /ruta/encontrada/agencia-web-project
# Reemplaza con la ruta que encontraste
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
```bash
# Opción 1: systemd
sudo systemctl restart gunicorn
# O
sudo systemctl restart agencia-web

# Opción 2: supervisor
sudo supervisorctl restart agencia-web

# Opción 3: Gunicorn directo
pkill -HUP gunicorn
# O encontrar el proceso:
ps aux | grep gunicorn
kill -HUP <PID>
```

### 11. Verificar que funciona
```bash
curl http://localhost:8000
# O ver logs:
sudo journalctl -u gunicorn -n 50
```

## 🎯 Script Todo-en-Uno (Copia Completa)

```bash
# Encontrar proyecto
PROJECT_DIR=$(find ~ -name "agencia-web-project" -type d 2>/dev/null | head -1)
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(find /var/www -name "agencia-web-project" -type d 2>/dev/null | head -1)
fi
if [ -z "$PROJECT_DIR" ]; then
    PROJECT_DIR=$(find /home -name "agencia-web-project" -type d 2>/dev/null | head -1)
fi

echo "📂 Proyecto encontrado en: $PROJECT_DIR"
cd "$PROJECT_DIR"

# Backup
echo "📦 Haciendo backup..."
cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || echo "⚠️  No se encontró db.sqlite3"

# Pull
echo "📥 Descargando cambios..."
git pull origin master

# Venv
echo "🐍 Activando entorno virtual..."
source venv/bin/activate 2>/dev/null || source env/bin/activate 2>/dev/null || echo "⚠️  No se encontró venv"

# Dependencias
echo "📦 Instalando dependencias..."
pip install -q -r requirements.txt

# Migraciones
echo "🔄 Aplicando migraciones..."
python manage.py migrate --noinput

# Static
echo "📁 Recolectando estáticos..."
python manage.py collectstatic --noinput

# Reiniciar
echo "🔄 Reiniciando servicio..."
sudo systemctl restart gunicorn 2>/dev/null || sudo systemctl restart agencia-web 2>/dev/null || sudo supervisorctl restart agencia-web 2>/dev/null || pkill -HUP gunicorn

echo "✅ Despliegue completado!"
```

## ⚠️ Si Algo Sale Mal

### Rollback
```bash
cd /ruta/a/proyecto
git reset --hard HEAD~1
sudo systemctl restart gunicorn
```

### Ver Logs
```bash
sudo journalctl -u gunicorn -n 100
# O
sudo tail -f /var/log/gunicorn/error.log
```

### Verificar Estado
```bash
sudo systemctl status gunicorn
# O
sudo supervisorctl status agencia-web
```
















