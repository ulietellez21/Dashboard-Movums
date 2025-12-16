# Guía de Despliegue - Cambios del Contrato DOCX y Mejoras

## 📋 Resumen de Cambios Principales

1. **Contrato de Servicios Turísticos**: Cambio de PDF a DOCX con formato completo
2. **Cotizaciones**: Mejoras en formato DOCX (vuelos, hospedaje, tours, paquetes)
3. **Confirmaciones**: Ajustes de formato y espaciado
4. **Kilómetros Movums**: Sistema de promociones y dashboard
5. **Ventas Internacionales**: Manejo completo de USD y tipo de cambio
6. **Promociones**: Sistema de descuentos y bonificaciones

---

## 🔄 PASO 1: Preparación Local (Git)

### 1.1 Verificar estado actual
```bash
cd /Users/ulisestellez/Documents/agencia-web-project
git status
```

### 1.2 Agregar archivos relevantes (excluyendo cache y DB)
```bash
# Agregar archivos modificados importantes
git add ventas/views.py
git add ventas/models.py
git add ventas/forms.py
git add ventas/templates/ventas/*.html
git add ventas/templates/ventas/partials/
git add ventas/migrations/
git add ventas/services/

git add crm/models.py
git add crm/forms.py
git add crm/views.py
git add crm/templates/crm/
git add crm/migrations/

git add templates/base.html
git add templates/dashboard.html

# Agregar archivos nuevos importantes
git add crm/migrations/0008_promocionkilometros.py
git add crm/migrations/0009_remove_promocionkilometros_factor_multiplicador_and_more.py
git add crm/migrations/0010_remove_promocionkilometros_combinable_and_more.py
git add crm/templates/crm/kilometros_dashboard.html
git add crm/templates/crm/promocion_form.html

git add ventas/migrations/0030_*.py
git add ventas/migrations/0031_*.py
git add ventas/migrations/0032_*.py
git add ventas/migrations/0033_*.py
git add ventas/migrations/0034_*.py
git add ventas/migrations/0035_*.py
git add ventas/migrations/0036_*.py
git add ventas/services/promociones.py
git add ventas/templates/ventas/partials/
git add ventas/templates/ventas/detalle_comisiones.html
git add ventas/templates/ventas/proveedor_confirm_delete.html

# Si hay cambios en requirements.txt
git add requirements.txt
```

### 1.3 Verificar qué se va a commitear
```bash
git status
```

### 1.4 Crear commit descriptivo
```bash
git commit -m "feat: Implementación completa de contrato DOCX y mejoras del sistema

- Cambio de contrato de PDF a DOCX con formato completo y editable
- Implementación de texto legal completo en sección 10
- Mejoras en formato de cotizaciones DOCX (vuelos, hospedaje, tours, paquetes)
- Ajustes de formato en confirmaciones (espaciado, tamaños de fuente)
- Sistema completo de Kilómetros Movums con promociones
- Dashboard de Kilómetros Movums con KPIs y gestión de promociones
- Manejo completo de ventas internacionales (USD) con tipo de cambio
- Sistema de promociones aplicables a ventas con descuentos y bonificaciones
- Mejoras en formularios de ventas con preview de promociones en tiempo real
- Correcciones en reportes de comisiones y visualización de datos
- Mejoras en UI/UX del dashboard (sidebar fijo, mejor scroll en dropdowns)"
```

### 1.5 Push a GitHub
```bash
git push origin master
```

---

## 🚀 PASO 2: Despliegue en DigitalOcean

### 2.1 Conectarse al servidor
```bash
# Ajusta la IP y usuario según tu configuración
ssh usuario@tu_ip_digitalocean
# O si usas clave SSH específica:
ssh -i ~/.ssh/tu_clave usuario@tu_ip_digitalocean
```

### 2.2 Navegar al directorio del proyecto
```bash
cd /ruta/a/tu/proyecto
# Ejemplo común:
cd /home/usuario/agencia-web-project
# O si está en otro lugar:
cd /var/www/agencia-web-project
```

### 2.3 Verificar rama actual
```bash
git branch
# Debe estar en master
```

### 2.4 Hacer pull de los cambios
```bash
git pull origin master
```

### 2.5 Activar entorno virtual (si aplica)
```bash
# Si usas venv:
source venv/bin/activate
# O si usas otro nombre:
source env/bin/activate
# O si está en otra ubicación:
source /ruta/a/venv/bin/activate
```

### 2.6 Instalar nuevas dependencias (si hay cambios en requirements.txt)
```bash
pip install -r requirements.txt
```

### 2.7 Aplicar migraciones de base de datos
```bash
python manage.py migrate
```

### 2.8 Recolectar archivos estáticos (si es necesario)
```bash
python manage.py collectstatic --noinput
```

### 2.9 Reiniciar servicios

#### Si usas Gunicorn directamente:
```bash
# Encontrar el proceso
ps aux | grep gunicorn

# Matar el proceso (reemplaza PID con el número del proceso)
kill -HUP PID

# O reiniciar completamente
pkill gunicorn
# Luego iniciar de nuevo según tu configuración
```

#### Si usas systemd:
```bash
sudo systemctl restart gunicorn
# O el nombre de tu servicio:
sudo systemctl restart agencia-web
```

#### Si usas supervisor:
```bash
sudo supervisorctl restart agencia-web
# O el nombre de tu proceso en supervisor
```

#### Si usas Nginx + Gunicorn:
```bash
# Reiniciar Gunicorn
sudo systemctl restart gunicorn
# O
sudo supervisorctl restart gunicorn

# Reiniciar Nginx (generalmente no es necesario)
sudo systemctl restart nginx
```

### 2.10 Verificar que el servicio está corriendo
```bash
# Ver logs de Gunicorn
sudo journalctl -u gunicorn -f
# O si usas supervisor:
sudo supervisorctl tail -f agencia-web

# Verificar que responde
curl http://localhost:8000
# O la URL de tu aplicación
```

---

## ✅ PASO 3: Verificación Post-Despliegue

### 3.1 Verificar funcionalidades principales
- [ ] Acceso al dashboard
- [ ] Crear nueva venta
- [ ] Generar contrato DOCX
- [ ] Generar cotizaciones DOCX
- [ ] Dashboard de Kilómetros Movums
- [ ] Aplicar promociones en ventas
- [ ] Ventas internacionales (USD)

### 3.2 Verificar migraciones aplicadas
```bash
python manage.py showmigrations
# Todas las migraciones deben estar marcadas con [X]
```

### 3.3 Revisar logs por errores
```bash
# Logs de Django
tail -f /ruta/a/logs/django.log
# O donde tengas configurados los logs

# Logs de Gunicorn
sudo journalctl -u gunicorn -n 50
```

---

## ⚠️ IMPORTANTE: Archivos que NO se deben subir

Los siguientes archivos NO deben incluirse en el commit:
- `__pycache__/` (carpetas de cache de Python)
- `*.pyc` (archivos compilados de Python)
- `db.sqlite3` (base de datos local)
- `db.sqlite3.backup-*` (backups de base de datos)
- Archivos temporales

Estos deberían estar en `.gitignore`. Si no lo están, agrégalos antes del commit.

---

## 🔧 Comandos Rápidos (Todo en uno)

### Local (preparación):
```bash
cd /Users/ulisestellez/Documents/agencia-web-project
git add ventas/ crm/ templates/ ventas/migrations/ crm/migrations/ ventas/services/ ventas/templates/ventas/partials/
git commit -m "feat: Implementación completa de contrato DOCX y mejoras del sistema"
git push origin master
```

### Servidor (despliegue):
```bash
cd /ruta/a/proyecto
git pull origin master
source venv/bin/activate  # Si aplica
pip install -r requirements.txt  # Si hay cambios
python manage.py migrate
python manage.py collectstatic --noinput  # Si aplica
sudo systemctl restart gunicorn  # O el servicio que uses
```

---

## 📝 Notas Adicionales

1. **Backup antes de desplegar**: Es recomendable hacer backup de la base de datos antes de aplicar migraciones en producción
2. **Horario de despliegue**: Considera hacer el despliegue en horario de bajo tráfico
3. **Pruebas**: Prueba primero en un entorno de staging si lo tienes disponible
4. **Rollback**: Si algo sale mal, puedes hacer rollback con `git reset --hard HEAD~1` en el servidor (después de hacer backup)

---

## 🆘 Solución de Problemas

### Si hay conflictos en el pull:
```bash
git stash
git pull origin master
git stash pop
# Resolver conflictos manualmente
```

### Si las migraciones fallan:
```bash
# Ver qué migración está fallando
python manage.py migrate --verbosity 2

# Si es necesario, hacer rollback de una migración específica
python manage.py migrate app_name migration_number
```

### Si el servicio no inicia:
```bash
# Ver logs detallados
sudo journalctl -u gunicorn -n 100 --no-pager

# Verificar configuración
python manage.py check
```
