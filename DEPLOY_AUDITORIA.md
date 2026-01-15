# 🚀 Comandos de Despliegue - Sistema de Auditoría

## ✅ Cambios Subidos a Git

Los cambios han sido subidos exitosamente a Git:
- **Commit**: `3405898f` - "feat: Implementar sistema de auditoría e historial de movimientos"
- **Branch**: `master`
- **Repositorio**: https://github.com/ulietellez21/Dashboard-Movums.git

## 📋 Comandos para Ejecutar en el Servidor

Debes ejecutar estos comandos **directamente en el servidor** usando el panel de DigitalOcean o acceso SSH manual.

### 1. Conectarse al Servidor
```bash
ssh tellez@206.189.223.176
# O usar el panel de DigitalOcean: Access > Launch Droplet Console
```

### 2. Encontrar el Proyecto
```bash
find ~ -name "agencia-web-project" -type d
# Si no lo encuentra:
find /var/www -name "agencia-web-project" -type d
find /home -name "agencia-web-project" -type d
```

### 3. Ir al Directorio del Proyecto
```bash
cd /ruta/encontrada/agencia-web-project
# Reemplaza con la ruta que encontraste
```

### 4. Hacer Backup de la Base de Datos
```bash
cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)
```

### 5. Verificar Rama Actual
```bash
git branch
# Debe estar en master
```

### 6. Descargar Cambios de Git
```bash
git pull origin master
```

### 7. Activar Entorno Virtual
```bash
source venv/bin/activate
# O si no existe:
source env/bin/activate
```

### 8. Instalar Dependencias (si hay nuevas)
```bash
pip install -r requirements.txt
```

### 9. Aplicar Migraciones
```bash
python manage.py migrate
```

**IMPORTANTE**: Se agregó una nueva app `auditoria`, por lo que se crearán nuevas tablas en la base de datos.

### 10. Recolectar Archivos Estáticos
```bash
python manage.py collectstatic --noinput
```

### 11. Reiniciar el Servicio
```bash
# Opción 1: systemd
sudo systemctl restart gunicorn
# O
sudo systemctl restart agencia-web

# Opción 2: supervisor
sudo supervisorctl restart agencia-web

# Opción 3: Gunicorn directo
pkill -HUP gunicorn
```

### 12. Verificar que Funciona
```bash
curl http://localhost:8000
# O ver logs:
sudo journalctl -u gunicorn -n 50
```

## 📝 Script Todo-en-Uno (Copia y Pega Completo)

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

# Collectstatic
echo "📁 Recolectando archivos estáticos..."
python manage.py collectstatic --noinput

# Reiniciar
echo "🔄 Reiniciando servicio..."
sudo systemctl restart gunicorn 2>/dev/null || sudo systemctl restart agencia-web 2>/dev/null || sudo supervisorctl restart agencia-web 2>/dev/null || (pkill -HUP gunicorn && echo "✅ Gunicorn reiniciado") || echo "⚠️  No se pudo reiniciar automáticamente"

echo "✅ Despliegue completado!"
```

## 🎯 Cambios Principales Desplegados

1. **Nueva app `auditoria`** con sistema completo de historial de movimientos
2. **Modal de historial** en reporte financiero con filtros avanzados
3. **Vista previa de movimientos** en carrusel con cambio automático
4. **Corrección de formato de moneda** en campos de abonos
5. **Enlaces inteligentes** que dirigen a la pestaña correcta según el tipo de movimiento
6. **Documentación** sobre problema de pantalla opaca en modales

## ⚠️ Notas Importantes

- Las migraciones crearán nuevas tablas en la base de datos
- El servicio se reiniciará automáticamente
- Verifica que la aplicación funcione correctamente después del despliegue
- Revisa los logs si hay algún problema









