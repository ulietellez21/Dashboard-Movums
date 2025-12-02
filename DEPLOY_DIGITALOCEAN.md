# 🚀 Guía Paso a Paso: Deploy en DigitalOcean

## 📋 Requisitos Previos

- [ ] Cuenta en DigitalOcean (puedes crearla en https://www.digitalocean.com)
- [ ] Proyecto en GitHub (o repositorio Git)
- [ ] Dominio opcional (puedes usar IP o subdominio de DigitalOcean)

---

## 📝 PASO 1: Preparar el Proyecto Localmente

### 1.1 Verificar Archivos Necesarios

Asegúrate de tener estos archivos en tu proyecto:

✅ `requirements.txt` - Ya lo tienes
✅ `Procfile` - Ya lo tienes  
✅ `runtime.txt` - Ya lo tienes
✅ `.gitignore` - Ya lo tienes

### 1.2 Verificar Configuración de Settings

Tu `settings.py` ya está configurado para usar variables de entorno, perfecto.

### 1.3 Subir Proyecto a GitHub (si aún no lo has hecho)

```bash
# Si no tienes repositorio Git
cd /Users/ulisestellez/Documents/agencia-web-project
git init
git add .
git commit -m "Preparado para deployment en DigitalOcean"

# Conectar con GitHub
# 1. Crea un repositorio nuevo en github.com
# 2. Luego ejecuta:
git remote add origin https://github.com/TU-USUARIO/TU-REPO.git
git branch -M main
git push -u origin main
```

---

## 📝 PASO 2: Crear Cuenta en DigitalOcean

### 2.1 Registrarse

1. Ve a https://www.digitalocean.com
2. Click en **"Sign Up"**
3. Registrate con email o GitHub (recomendado con GitHub)

### 2.2 Verificar Email

- Revisa tu email y verifica la cuenta
- Completa el perfil básico

### 2.3 Agregar Método de Pago

- Ve a **Billing** → **Payment Methods**
- Agrega tarjeta de crédito (necesario incluso para cuenta gratuita)
- DigitalOcean te da $200 de crédito por 60 días 🎉

---

## 📝 PASO 3: Crear Droplet (VPS)

### 3.1 Acceder al Panel

1. Entra a tu panel de DigitalOcean
2. Click en **"Create"** → **"Droplets"**

### 3.2 Configurar Droplet

#### **Ubicación (IMPORTANTE para México):**
- Selecciona: **San Francisco (USA)** o **New York (USA)**
- ⚠️ NO selecciones Amsterdam (Europa) - es más lento para México

#### **Imagen:**
- Selecciona: **Ubuntu 22.04 (LTS)**

#### **Plan:**
- **Basic Plan**
- **Regular Intel**: $6/mes (1 vCPU, 1 GB RAM, 25 GB SSD)
- O $12/mes (2 vCPU, 2 GB RAM, 50 GB SSD) para mejor rendimiento

#### **Autenticación:**
- Selecciona: **SSH Keys** (recomendado) o **Password** (más fácil para empezar)
- Si eliges Password, guarda la contraseña que te den

#### **Nombre del Droplet:**
- Ejemplo: `movums-agency-production`

#### **Crear:**
- Click en **"Create Droplet"**
- Espera 1-2 minutos mientras se crea

---

## 📝 PASO 4: Conectarte al Servidor por SSH

### 4.1 Obtener IP del Droplet

1. En el panel de DigitalOcean, ve a **Droplets**
2. Verás tu nuevo Droplet con su IP pública
3. Copia la IP (ejemplo: `157.230.123.45`)

### 4.2 Conectarte desde Terminal (Mac/Linux)

```bash
# Reemplaza 157.230.123.45 con tu IP real
ssh root@157.230.123.45

# Si usaste password, te pedirá la contraseña
# Si usaste SSH key, puede que no pida nada
```

### 4.3 Conectarte desde Windows

**Opción A: PowerShell**
```powershell
ssh root@157.230.123.45
```

**Opción B: PuTTY**
- Descargar PuTTY: https://www.putty.org/
- Host: tu IP
- Port: 22
- Click "Open"

---

## 📝 PASO 5: Configurar el Servidor

### 5.1 Actualizar Sistema

```bash
apt update && apt upgrade -y
```

### 5.2 Instalar Dependencias Necesarias

```bash
# Instalar Python y herramientas
apt install -y python3 python3-pip python3-venv git nginx supervisor postgresql postgresql-contrib

# Instalar dependencias del sistema para WeasyPrint
apt install -y python3-dev build-essential libffi-dev libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

### 5.3 Crear Usuario para la Aplicación

```bash
# Crear usuario (recomendado por seguridad)
adduser djangoapp
usermod -aG sudo djangoapp

# Cambiar al nuevo usuario
su - djangoapp
```

---

## 📝 PASO 6: Configurar Base de Datos PostgreSQL

### 6.1 Crear Base de Datos y Usuario

```bash
# Volver a root temporalmente
exit

# Acceder a PostgreSQL
sudo -u postgres psql

# Dentro de PostgreSQL, ejecutar:
CREATE DATABASE movums_db;
CREATE USER movums_user WITH PASSWORD 'TU_PASSWORD_SEGURO_AQUI';
ALTER ROLE movums_user SET client_encoding TO 'utf8';
ALTER ROLE movums_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE movums_user SET timezone TO 'America/Mexico_City';
GRANT ALL PRIVILEGES ON DATABASE movums_db TO movums_user;
\q

# Volver al usuario djangoapp
su - djangoapp
```

**⚠️ IMPORTANTE:** Guarda la contraseña que uses aquí, la necesitarás después.

---

## 📝 PASO 7: Clonar y Configurar el Proyecto

### 7.1 Crear Directorio y Clonar

```bash
# Crear directorio
mkdir -p ~/webapps
cd ~/webapps

# Clonar tu repositorio
git clone https://github.com/TU-USUARIO/TU-REPO.git movums
cd movums
```

### 7.2 Crear Entorno Virtual

```bash
python3 -m venv venv
source venv/bin/activate
```

### 7.3 Instalar Dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install psycopg2-binary  # Para PostgreSQL
```

---

## 📝 PASO 8: Configurar Variables de Entorno

### 8.1 Crear Archivo .env

```bash
nano .env
```

### 8.2 Agregar Contenido (Copia esto y ajusta):

```env
SECRET_KEY=GENERA_UNA_NUEVA_CLAVE_AQUI
DEBUG=False
ALLOWED_HOSTS=tu-ip-aqui,tu-dominio.com,www.tu-dominio.com
DATABASE_URL=postgresql://movums_user:TU_PASSWORD_AQUI@localhost/movums_db
```

**Generar nueva SECRET_KEY:**
```bash
# En otra terminal local o en el servidor:
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

**Guardar archivo:**
- Presiona `Ctrl + X`
- Luego `Y` para confirmar
- Luego `Enter` para guardar

---

## 📝 PASO 9: Actualizar Settings.py para PostgreSQL

### 9.1 Instalar dj-database-url

```bash
pip install dj-database-url
```

### 9.2 Actualizar settings.py

```bash
nano agencia_web/settings.py
```

**Busca la sección DATABASES y reemplázala con:**

```python
# Database
import dj_database_url

DATABASES = {
    'default': dj_database_url.parse(
        os.environ.get('DATABASE_URL', 'sqlite:///db.sqlite3'),
        conn_max_age=600
    )
}
```

**O mantén SQLite si prefieres (para pruebas):**
```python
# Mantener SQLite para pruebas
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

**Guardar:** `Ctrl + X`, `Y`, `Enter`

---

## 📝 PASO 10: Migrar Base de Datos y Configurar

### 10.1 Recopilar Archivos Estáticos

```bash
python manage.py collectstatic --noinput
```

### 10.2 Ejecutar Migraciones

```bash
python manage.py migrate
```

### 10.3 Crear Superusuario

```bash
python manage.py createsuperuser
```

Sigue las instrucciones para crear tu usuario admin.

---

## 📝 PASO 11: Configurar Gunicorn

### 11.1 Crear Archivo de Configuración

```bash
nano ~/webapps/movums/gunicorn_config.py
```

### 11.2 Agregar Contenido:

```python
bind = "127.0.0.1:8000"
workers = 3
timeout = 120
worker_class = "sync"
```

**Guardar:** `Ctrl + X`, `Y`, `Enter`

### 11.3 Probar Gunicorn

```bash
cd ~/webapps/movums
source venv/bin/activate
gunicorn agencia_web.wsgi:application --config gunicorn_config.py
```

**Si funciona:** Presiona `Ctrl + C` para detenerlo.

---

## 📝 PASO 12: Configurar Supervisor (Mantener Servicio Corriendo)

### 12.1 Crear Archivo de Configuración

```bash
sudo nano /etc/supervisor/conf.d/movums.conf
```

### 12.2 Agregar Contenido (Ajusta las rutas si son diferentes):

```ini
[program:movums]
command=/home/djangoapp/webapps/movums/venv/bin/gunicorn agencia_web.wsgi:application --config /home/djangoapp/webapps/movums/gunicorn_config.py
directory=/home/djangoapp/webapps/movums
user=djangoapp
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/movums.log
environment=PATH="/home/djangoapp/webapps/movums/venv/bin"
```

**Guardar:** `Ctrl + X`, `Y`, `Enter`

### 12.3 Activar Supervisor

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start movums
sudo supervisorctl status
```

**Deberías ver:** `movums RUNNING pid XXXXX`

---

## 📝 PASO 13: Configurar Nginx (Servidor Web)

### 13.1 Crear Configuración de Nginx

```bash
sudo nano /etc/nginx/sites-available/movums
```

### 13.2 Agregar Contenido (Reemplaza IP y dominio):

```nginx
server {
    listen 80;
    server_name TU_IP_AQUI tu-dominio.com www.tu-dominio.com;

    client_max_body_size 100M;

    location /static/ {
        alias /home/djangoapp/webapps/movums/staticfiles/;
    }

    location /media/ {
        alias /home/djangoapp/webapps/movums/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }
}
```

**Reemplaza:**
- `TU_IP_AQUI` con tu IP de DigitalOcean
- `tu-dominio.com` con tu dominio (si lo tienes)

**Guardar:** `Ctrl + X`, `Y`, `Enter`

### 13.3 Activar Sitio

```bash
# Crear enlace simbólico
sudo ln -s /etc/nginx/sites-available/movums /etc/nginx/sites-enabled/

# Eliminar configuración por defecto
sudo rm /etc/nginx/sites-enabled/default

# Probar configuración
sudo nginx -t

# Si todo está bien, reiniciar Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## 📝 PASO 14: Configurar Firewall

### 14.1 Permitir HTTP y HTTPS

```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow ssh
sudo ufw enable
sudo ufw status
```

---

## 📝 PASO 15: Configurar SSL (HTTPS) con Let's Encrypt

### 15.1 Instalar Certbot

```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 15.2 Obtener Certificado SSL

**Si tienes dominio:**
```bash
sudo certbot --nginx -d tu-dominio.com -d www.tu-dominio.com
```

**Solo con IP (sin SSL):**
- El sitio funcionará en HTTP (no HTTPS)
- Para producción real, necesitas un dominio

### 15.3 Renovación Automática

```bash
# Certbot ya configura renovación automática
sudo certbot renew --dry-run
```

---

## 📝 PASO 16: Verificar que Todo Funciona

### 16.1 Probar en Navegador

1. Abre tu navegador
2. Ve a: `http://TU_IP_DE_DIGITALOCEAN`
3. Deberías ver tu aplicación funcionando

### 16.2 Verificar Logs

```bash
# Logs de la aplicación
sudo tail -f /var/log/movums.log

# Logs de Nginx
sudo tail -f /var/log/nginx/error.log
```

### 16.3 Verificar Supervisor

```bash
sudo supervisorctl status movums
```

---

## 📝 PASO 17: Configurar Dominio (Opcional)

### 17.1 En el Proveedor de Dominio

Si tienes un dominio, configura los DNS:

**Registro A:**
- Tipo: `A`
- Nombre: `@` o `www`
- Valor: `TU_IP_DE_DIGITALOCEAN`
- TTL: `3600`

### 17.2 Esperar Propagación

- Espera 5-60 minutos para que los DNS se propaguen
- Verifica: https://www.whatsmydns.net/

### 17.3 Actualizar ALLOWED_HOSTS

```bash
nano ~/webapps/movums/.env
```

Agrega tu dominio:
```env
ALLOWED_HOSTS=tu-ip,tu-dominio.com,www.tu-dominio.com
```

Reiniciar:
```bash
sudo supervisorctl restart movums
```

---

## 📝 PASO 18: Comandos Útiles para Mantenimiento

### Ver Estado del Servicio
```bash
sudo supervisorctl status movums
```

### Reiniciar Aplicación
```bash
sudo supervisorctl restart movums
```

### Ver Logs en Tiempo Real
```bash
sudo tail -f /var/log/movums.log
```

### Actualizar Código (desde GitHub)
```bash
cd ~/webapps/movums
source venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo supervisorctl restart movums
```

### Crear Nuevo Superusuario
```bash
cd ~/webapps/movums
source venv/bin/activate
python manage.py createsuperuser
```

---

## 🐛 Troubleshooting

### Error: "502 Bad Gateway"
**Solución:**
```bash
# Verificar que Gunicorn está corriendo
sudo supervisorctl status movums

# Si no está corriendo:
sudo supervisorctl start movums
```

### Error: "DisallowedHost"
**Solución:**
```bash
# Agregar IP a ALLOWED_HOSTS
nano ~/webapps/movums/.env
# Agregar tu IP a ALLOWED_HOSTS
sudo supervisorctl restart movums
```

### Error: "Static files not found"
**Solución:**
```bash
cd ~/webapps/movums
source venv/bin/activate
python manage.py collectstatic --noinput
```

### Error: "Database connection failed"
**Solución:**
```bash
# Verificar PostgreSQL
sudo systemctl status postgresql

# Verificar credenciales en .env
nano ~/webapps/movums/.env
```

---

## ✅ Checklist Final

- [ ] Droplet creado en DigitalOcean
- [ ] Conectado por SSH
- [ ] Dependencias instaladas
- [ ] PostgreSQL configurado
- [ ] Proyecto clonado
- [ ] Entorno virtual creado
- [ ] Dependencias instaladas
- [ ] Variables de entorno configuradas
- [ ] Migraciones ejecutadas
- [ ] Superusuario creado
- [ ] Gunicorn configurado
- [ ] Supervisor configurado
- [ ] Nginx configurado
- [ ] Firewall configurado
- [ ] SSL configurado (opcional)
- [ ] Aplicación accesible en navegador

---

## 💰 Costos Finales

- **Droplet Básico**: $6/mes
- **Dominio**: $10-15/año (opcional)
- **SSL**: GRATIS (Let's Encrypt)
- **TOTAL**: ~$6/mes

---

## 🎉 ¡Listo!

Tu aplicación debería estar funcionando en:
- `http://TU_IP_DE_DIGITALOCEAN`
- O `https://tu-dominio.com` (si configuraste dominio)

**¿Tienes alguna duda en algún paso? ¡Avísame! 🚀**

