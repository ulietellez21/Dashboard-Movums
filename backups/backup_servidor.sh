#!/bin/bash
# Script para hacer backup del servidor en DigitalOcean
# Uso: ./backup_servidor.sh

# Configuración (ajusta según tu servidor)
BACKUP_DIR="/home/usuario/backups"
PROJECT_DIR="/ruta/a/tu/proyecto"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Crear directorio de backups si no existe
mkdir -p $BACKUP_DIR

echo "🔄 Iniciando backup del servidor..."
echo "📅 Fecha: $(date)"

# Backup de base de datos
echo "📦 Haciendo backup de la base de datos..."

# Si usas PostgreSQL
if command -v pg_dump &> /dev/null; then
    echo "   Detectado PostgreSQL"
    # Ajusta estos valores según tu configuración
    # pg_dump -U usuario -d nombre_db > $BACKUP_DIR/db_backup_$TIMESTAMP.sql
    echo "   Comando: pg_dump -U usuario -d nombre_db > $BACKUP_DIR/db_backup_$TIMESTAMP.sql"
fi

# Si usas MySQL
if command -v mysqldump &> /dev/null; then
    echo "   Detectado MySQL"
    # Ajusta estos valores según tu configuración
    # mysqldump -u usuario -p nombre_db > $BACKUP_DIR/db_backup_$TIMESTAMP.sql
    echo "   Comando: mysqldump -u usuario -p nombre_db > $BACKUP_DIR/db_backup_$TIMESTAMP.sql"
fi

# Si usas SQLite
if [ -f "$PROJECT_DIR/db.sqlite3" ]; then
    echo "   Detectado SQLite"
    cp $PROJECT_DIR/db.sqlite3 $BACKUP_DIR/db.sqlite3.backup_$TIMESTAMP
    echo "   ✅ Backup de SQLite creado: db.sqlite3.backup_$TIMESTAMP"
fi

# Backup del código (solo archivos importantes, no cache)
echo "💾 Haciendo backup del código..."
cd $PROJECT_DIR
tar -czf $BACKUP_DIR/codigo_backup_$TIMESTAMP.tar.gz \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='venv' \
    --exclude='env' \
    --exclude='db.sqlite3' \
    --exclude='media' \
    --exclude='staticfiles' \
    .

echo "   ✅ Backup del código creado: codigo_backup_$TIMESTAMP.tar.gz"

# Backup de archivos estáticos y media (si existen)
if [ -d "$PROJECT_DIR/staticfiles" ]; then
    echo "📁 Haciendo backup de archivos estáticos..."
    tar -czf $BACKUP_DIR/staticfiles_backup_$TIMESTAMP.tar.gz -C $PROJECT_DIR staticfiles
    echo "   ✅ Backup de staticfiles creado"
fi

if [ -d "$PROJECT_DIR/media" ]; then
    echo "📁 Haciendo backup de archivos media..."
    tar -czf $BACKUP_DIR/media_backup_$TIMESTAMP.tar.gz -C $PROJECT_DIR media
    echo "   ✅ Backup de media creado"
fi

# Resumen
echo ""
echo "✅ Backup completado!"
echo "📂 Ubicación: $BACKUP_DIR"
echo "📊 Archivos creados:"
ls -lh $BACKUP_DIR/*$TIMESTAMP* 2>/dev/null | awk '{print "   " $9 " (" $5 ")"}'

# Limpiar backups antiguos (mantener solo los últimos 7 días)
echo ""
echo "🧹 Limpiando backups antiguos (más de 7 días)..."
find $BACKUP_DIR -name "*.backup_*" -mtime +7 -delete 2>/dev/null
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete 2>/dev/null
echo "   ✅ Limpieza completada"






