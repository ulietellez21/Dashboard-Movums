# 🖥️ Guía de Deployment en Host Existente del Cliente

Si tu cliente ya tiene un hosting disponible, aquí tienes las opciones según el tipo de hosting.

---

## 🔍 Primero: Identificar el Tipo de Hosting

### Opción 1: Hosting Compartido (cPanel/Plesk)
**Características:**
- Interfaz web (cPanel, Plesk, etc.)
- PHP y MySQL comunes
- Limitado para aplicaciones Python/Django
- Ejemplos: Hostinger, SiteGround, HostGator, GoDaddy

**Ventajas:**
- ✅ Ya pagado por el cliente
- ✅ Panel de control visual
- ⚠️ **PERO**: La mayoría NO soportan Django bien

**Recomendación:** ⚠️ **NO recomendado** - Hosting compartido tradicional generalmente solo soporta PHP. Necesitarías un hosting que soporte Python.

---

### Opción 2: VPS (Virtual Private Server)
**Características:**
- Acceso SSH (línea de comandos)
- Control completo del servidor
- Puedes instalar lo que necesites
- Ejemplos: DigitalOcean Droplet, Vultr, Linode, AWS EC2

**Ventajas:**
- ✅ Control total
- ✅ Ideal para Django
- ✅ Más profesional

**Recomendación:** ✅ **Excelente opción** - Es lo ideal para Django

---

### Opción 3: Servidor Dedicado
**Características:**
- Servidor físico completo
- Máximo control
- Mayor costo

**Recomendación:** ✅ **Excelente opción** - Funciona perfectamente

---

## 📋 ¿Qué Información Necesitas del Cliente?

Antes de proceder, pregunta a tu cliente:

1. **¿Qué tipo de hosting es?**
   - [ ] Hosting compartido (cPanel/Plesk)
   - [ ] VPS (servidor virtual)
   - [ ] Servidor dedicado
   - [ ] Otro: ___________

2. **¿Tiene acceso SSH?**
   - [ ] Sí (puede acceder por terminal)
   - [ ] No (solo panel web)

3. **¿Soporta Python?**
   - [ ] Sí
   - [ ] No
   - [ ] No sé

4. **¿Tiene base de datos PostgreSQL o MySQL disponible?**
   - [ ] Sí
   - [ ] No
   - [ ] No sé

5. **¿Cuál es el dominio/hosting?**
   - Dominio: _______________
   - Proveedor: _______________

---

## 🎯 Guías por Tipo de Hosting

---

## 🟢 OPCIÓN RECOMENDADA: VPS o Servidor Dedicado

### Si el cliente tiene VPS/Dedicado con acceso SSH:

#### Paso 1: Preparar el código localmente

```bash
# Asegúrate de tener todo en Git
git add .
git commit -m "Listo para deployment"
git push origin main
```

#### Paso 2: Conectar al servidor por SSH

```bash
# Desde tu terminal local
ssh usuario@ip-del-servidor
# o
ssh usuario@dominio-del-cliente.com
```

#### Paso 3: Instalar dependencias en el servidor

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y  # Ubuntu/Debian
# o
sudo yum update -y  # CentOS/RHEL

# Instalar Python y herramientas
sudo apt install python3 python3-pip python3-venv nginx supervisor -y

# Instalar PostgreSQL (recomendado) o MySQL
sudo apt install postgresql postgresql-contrib -y
# o
sudo apt install mysql-server -y

# Instalar Git
sudo apt install git -y
```

#### Paso 4: Configurar usuario y directorio

```bash
# Crear usuario para la aplicación (recomendado)
sudo adduser djangoapp
sudo usermod -aG sudo djangoapp

# Cambiar al usuario
su - djangoapp

# Crear directorio para la aplicación
mkdir -p ~/webapps/movums
cd ~/webapps/movums
```

#### Paso 5: Clonar el repositorio

```bash
# Clonar tu repositorio (o subir archivos)
git clone https://github.com/TU-USUARIO/TU-REPO.git .
# o usar scp para subir archivos manualmente
```

#### Paso 6: Configurar entorno virtual

```bash
# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

#### Paso 7: Configurar base de datos

```bash
# PostgreSQL
sudo -u postgres psql
CREATE DATABASE movums_db;
CREATE USER movums_user WITH PASSWORD 'tu_password_seguro';
GRANT ALL PRIVILEGES ON DATABASE movums_db TO movums_user;
\q

# Actualizar settings.py para usar PostgreSQL
```

#### Paso 8: Configurar Django

```bash
# Crear archivo .env en el servidor
nano .env
```

Contenido del `.env`:
```
SECRET_KEY=tu-clave-secreta-generada
DEBUG=False
ALLOWED_HOSTS=dominio-del-cliente.com,www.dominio-del-cliente.com
DATABASE_URL=postgresql://movums_user:tu_password_seguro@localhost/movums_db
```

#### Paso 9: Migrar y recopilar estáticos

```bash
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

#### Paso 10: Configurar Gunicorn

```bash
# Crear archivo de configuración para Gunicorn
nano ~/webapps/movums/gunicorn_config.py
```

Contenido:
```python
bind = "127.0.0.1:8000"
workers = 3
timeout = 120
```

#### Paso 11: Configurar Supervisor (para mantener el servicio corriendo)

```bash
sudo nano /etc/supervisor/conf.d/movums.conf
```

Contenido:
```ini
[program:movums]
command=/home/djangoapp/webapps/movums/venv/bin/gunicorn agencia_web.wsgi:application --config /home/djangoapp/webapps/movums/gunicorn_config.py
directory=/home/djangoapp/webapps/movums
user=djangoapp
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/movums.log
```

```bash
# Recargar supervisor
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start movums
```

#### Paso 12: Configurar Nginx (servidor web)

```bash
sudo nano /etc/nginx/sites-available/movums
```

Contenido:
```nginx
server {
    listen 80;
    server_name dominio-del-cliente.com www.dominio-del-cliente.com;

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
    }
}
```

```bash
# Activar sitio
sudo ln -s /etc/nginx/sites-available/movums /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### Paso 13: Configurar SSL (Let's Encrypt - Gratis)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d dominio-del-cliente.com -d www.dominio-del-cliente.com
```

#### Paso 14: ¡Listo!

Tu aplicación debería estar disponible en:
`https://dominio-del-cliente.com`

---

## 🟡 OPCIÓN ALTERNATIVA: Hosting Compartido con Soporte Python

### Si el hosting compartido SÍ soporta Python (poco común):

#### Opción A: Usar cPanel con Python App

1. Entra a cPanel
2. Busca "Setup Python App" o "Python Selector"
3. Crea una nueva aplicación Python
4. Sube tu código vía FTP o Git
5. Instala dependencias desde cPanel
6. Configura el dominio

**⚠️ Limitaciones:**
- Puede ser más complicado
- Menos control
- Algunas dependencias pueden no estar disponibles

---

## 🔵 OPCIÓN RÁPIDA: Si el Hosting NO Soporta Django

Si el hosting del cliente NO soporta Django (solo PHP), tienes estas opciones:

### Opción 1: Usar el VPS del cliente con Docker (Recomendado)

Si el cliente tiene un VPS, puedes usar Docker para facilitar el deployment:

```bash
# En el servidor
git clone https://github.com/TU-USUARIO/TU-REPO.git
cd TU-REPO

# Crear Dockerfile
# Crear docker-compose.yml
# Deploy con docker-compose
```

### Opción 2: Subdominio con Servicio Gratuito

Usar un subdominio apuntando a Render/Railway:
- Cliente mantiene su dominio principal
- Subdominio (ej: `demo.cliente.com`) apunta a Render
- Gratis para pruebas

### Opción 3: Recomendar VPS Temporal

Recomendar al cliente un VPS temporal ($5/mes):
- DigitalOcean
- Vultr
- Linode

---

## 📊 Tabla Comparativa

| Tipo de Hosting | Facilidad | Costo Cliente | Soporte Django | Recomendación |
|----------------|-----------|---------------|----------------|---------------|
| **VPS/Dedicado** | Media | Ya pagado | ✅ Excelente | ⭐⭐⭐⭐⭐ |
| **Hosting Python** | Media-Alta | Ya pagado | ✅ Bueno | ⭐⭐⭐⭐ |
| **Hosting Compartido PHP** | - | Ya pagado | ❌ No | ⭐ |
| **Render/Railway** | Alta | Gratis/$5 | ✅ Excelente | ⭐⭐⭐⭐⭐ |

---

## 🎯 Mi Recomendación para Pruebas

Para que el cliente pueda **probarlo rápidamente**:

### Si tiene VPS/Dedicado:
✅ **Usa el servidor existente** - Sigue la guía de VPS arriba

### Si tiene Hosting Compartido:
✅ **Usa un subdominio con Render.com** (gratis):
1. Cliente configura subdominio `demo.cliente.com` → apunta a Render
2. Tú despliegas en Render
3. Cliente prueba en su propio dominio
4. Gratis y funciona perfectamente

### Si no sabe qué tiene:
✅ **Pregúntale por acceso SSH:**
- Si tiene SSH → VPS/Dedicado ✅ (sigue guía VPS)
- Si NO tiene SSH → Hosting compartido ❌ (usa Render con subdominio)

---

## 📝 Checklist para Deployment en Host Existente

- [ ] Identificar tipo de hosting
- [ ] Verificar acceso SSH
- [ ] Verificar soporte Python
- [ ] Configurar base de datos
- [ ] Subir código al servidor
- [ ] Configurar entorno virtual
- [ ] Instalar dependencias
- [ ] Configurar variables de entorno
- [ ] Migrar base de datos
- [ ] Configurar Gunicorn
- [ ] Configurar Nginx
- [ ] Configurar SSL
- [ ] Probar aplicación

---

## 🆘 ¿Necesitas Ayuda?

Si me dices:
1. Qué tipo de hosting tiene el cliente
2. Si tiene acceso SSH
3. El proveedor de hosting

Puedo darte instrucciones **más específicas** para su caso.

---

**¡Buena suerte con el deployment! 🚀**










