#!/usr/bin/env bash
# Ejecutar EN EL SERVIDOR (por SSH) en la raíz del proyecto.
# Aplica migraciones a PostgreSQL, crea superusuario admin y reinicia gunicorn.

set -e

# Ajusta la ruta del venv si en tu servidor es distinta
VENV_PATH="${VENV_PATH:-/home/tellez/agencia-env/bin/activate}"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
else
    echo "No se encontró $VENV_PATH. Usando python del PATH."
fi

echo "=== 1. Migrar a PostgreSQL ==="
python manage.py migrate --noinput
echo ""

echo "=== 2. Crear superusuario admin (si no existe) ==="
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if User.objects.filter(username='admin').exists():
    print('El usuario admin ya existe.')
else:
    User.objects.create_superuser('admin', 'admin@movums.com.mx', 'Movums2026!')
    print('Superusuario admin creado.')
"
echo ""

echo "=== 3. Reiniciar Gunicorn ==="
sudo service gunicorn restart
echo ""

echo "Listo. Prueba el sitio y el login con admin / Movums2026!"
