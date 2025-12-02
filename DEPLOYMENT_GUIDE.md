# Guía de Deployment - Movums Agency Web

Esta guía te ayudará a subir tu proyecto Django a un host en internet.

## 📋 Índice
1. [Preparación del Proyecto](#preparación-del-proyecto)
2. [Opciones de Hosting](#opciones-de-hosting)
3. [Guía por Plataforma](#guía-por-plataforma)

---

## 🔧 Preparación del Proyecto

### 1. Actualizar `settings.py` para Producción

Necesitas hacer cambios importantes en `agencia_web/settings.py`:

#### A. Separar settings de desarrollo y producción

Crea variables de entorno seguras:
- `SECRET_KEY`: Clave secreta (NO subirla al repositorio)
- `DEBUG`: `False` en producción
- `ALLOWED_HOSTS`: Dominios permitidos

#### B. Configurar archivos estáticos

Para producción necesitas:
- `STATIC_ROOT`: Ruta donde se recopilarán los archivos estáticos
- `WHITENOISE`: Para servir archivos estáticos (recomendado)

#### C. Base de datos

SQLite funciona para pruebas, pero para producción real considera:
- PostgreSQL (recomendado)
- MySQL
- O mantener SQLite para pruebas rápidas

---

## 🚀 Opciones de Hosting Recomendadas

### Opción 1: Render.com (Recomendado - Gratis para empezar)
✅ **Ventajas:**
- Plan gratuito disponible
- Fácil de configurar
- PostgreSQL gratis
- SSL automático
- Deploy automático desde Git

❌ **Desventajas:**
- El servidor se "duerme" después de inactividad (plan gratuito)
- Límites de recursos en plan gratuito

### Opción 2: Railway.app
✅ **Ventajas:**
- Muy fácil de usar
- $5 de crédito gratis mensual
- Deploy desde Git muy simple
- PostgreSQL incluido

### Opción 3: PythonAnywhere
✅ **Ventajas:**
- Gratis para aplicaciones básicas
- Interfaz web completa
- Bueno para principiantes

❌ **Desventajas:**
- Más limitado que otras opciones
- Solo permite un dominio personalizado en planes de pago

### Opción 4: Fly.io
✅ **Ventajas:**
- Generoso plan gratuito
- Muy rápido
- Global CDN incluido

### Opción 5: DigitalOcean App Platform
✅ **Ventajas:**
- Muy confiable
- Escalable
- Buena documentación

❌ **Desventajas:**
- Plan más costoso ($5/mes mínimo)

---

## 📝 Pasos Específicos por Plataforma

### 🎯 OPCIÓN RECOMENDADA: Render.com

#### Paso 1: Preparar el proyecto

1. **Crear `.env` para variables de entorno** (NO subir a Git):
```env
SECRET_KEY=tu-clave-secreta-aqui-generar-una-nueva
DEBUG=False
ALLOWED_HOSTS=tu-app.onrender.com
```

2. **Actualizar `settings.py`** para usar variables de entorno:
```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Variables de entorno
SECRET_KEY = os.environ.get('SECRET_KEY', 'fallback-key-only-for-dev')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# Static files
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

3. **Crear `.gitignore`** si no existe:
```
*.pyc
__pycache__/
*.db
*.sqlite3
.env
venv/
env/
*.log
media/
staticfiles/
```

#### Paso 2: Crear archivos necesarios

1. **`Procfile`** (en la raíz del proyecto):
```
web: gunicorn agencia_web.wsgi --log-file -
```

2. **`runtime.txt`** (opcional, si quieres especificar la versión de Python):
```
python-3.12.12
```

3. **Actualizar `requirements.txt`** (incluir gunicorn y whitenoise):
```
Django>=5.0.6
gunicorn
whitenoise
python-docx
WeasyPrint
crispy-forms
crispy-bootstrap5
# ... otras dependencias
```

#### Paso 3: Deploy en Render

1. **Crear cuenta en Render.com**
   - Ve a https://render.com
   - Regístrate con GitHub/GitLab/Bitbucket

2. **Conectar repositorio Git**
   - Conecta tu repositorio de GitHub/GitLab
   - Si no tienes repositorio, créalo primero:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin tu-repositorio-url
   git push -u origin main
   ```

3. **Crear Web Service en Render**
   - Click en "New +" → "Web Service"
   - Conecta tu repositorio
   - Configuración:
     - **Name**: `movums-agency` (o el nombre que quieras)
     - **Environment**: `Python 3`
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `gunicorn agencia_web.wsgi:application`
     - **Instance Type**: Free (para pruebas)

4. **Configurar Variables de Entorno**
   En Render, ve a Environment Variables:
   ```
   SECRET_KEY=tu-clave-secreta-generada
   DEBUG=False
   ALLOWED_HOSTS=movums-agency.onrender.com
   PYTHON_VERSION=3.12.12
   ```

5. **Crear PostgreSQL Database (Opcional)**
   - Click en "New +" → "PostgreSQL"
   - Conecta la base de datos a tu Web Service
   - Agrega variable de entorno: `DATABASE_URL`

6. **Deploy**
   - Click en "Create Web Service"
   - Render hará el deploy automáticamente
   - Espera 5-10 minutos
   - Tu app estará disponible en: `https://movums-agency.onrender.com`

#### Paso 4: Comandos post-deploy

Después del primer deploy, necesitas ejecutar:

1. **Migraciones**:
   - En Render, ve a tu servicio
   - Click en "Shell"
   - Ejecuta: `python manage.py migrate`

2. **Crear superusuario**:
   - En el Shell: `python manage.py createsuperuser`

3. **Recopilar archivos estáticos**:
   - En el Shell: `python manage.py collectstatic --noinput`

---

### 🚂 Railway.app

#### Pasos:

1. **Crear cuenta en Railway.app**
   - Ve a https://railway.app
   - Regístrate con GitHub

2. **Instalar Railway CLI** (opcional):
   ```bash
   npm i -g @railway/cli
   railway login
   ```

3. **Deploy desde GitHub**:
   - Click en "New Project"
   - "Deploy from GitHub repo"
   - Selecciona tu repositorio
   - Railway detecta automáticamente que es Django

4. **Configurar Variables de Entorno**:
   ```
   SECRET_KEY=tu-clave-secreta
   DEBUG=False
   ALLOWED_HOSTS=tu-app.railway.app
   ```

5. **Agregar PostgreSQL** (recomendado):
   - Click en "+ New" → "Database" → "PostgreSQL"
   - Railway crea automáticamente la variable `DATABASE_URL`

6. **Actualizar settings.py para Railway**:
```python
import dj_database_url

# Database
if 'DATABASE_URL' in os.environ:
    DATABASES = {
        'default': dj_database_url.parse(os.environ.get('DATABASE_URL'))
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
```

7. **Agregar a requirements.txt**:
```
dj-database-url
psycopg2-binary
```

8. **Railway ejecuta automáticamente**:
   - `python manage.py migrate`
   - `python manage.py collectstatic`

---

## 🔒 Seguridad Importante

### ⚠️ ANTES DE SUBIR:

1. **NUNCA subas tu SECRET_KEY real al repositorio**
2. **Usa variables de entorno** para datos sensibles
3. **Cambia DEBUG a False** en producción
4. **Configura ALLOWED_HOSTS** correctamente
5. **Revisa el checklist de Django**: https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

### Generar nueva SECRET_KEY:
```python
# En Python shell:
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

---

## 📂 Estructura de Archivos Necesarios

Tu proyecto debe tener:
```
agencia-web-project/
├── manage.py
├── requirements.txt
├── Procfile (para Render/Railway)
├── runtime.txt (opcional)
├── .gitignore
├── .env (NO subir a Git)
├── agencia_web/
│   ├── settings.py
│   ├── wsgi.py
│   └── ...
├── static/
├── media/
└── ...
```

---

## 🐛 Troubleshooting Común

### Error: "DisallowedHost"
- **Solución**: Agregar tu dominio a `ALLOWED_HOSTS`

### Error: "Static files not found"
- **Solución**: Ejecutar `python manage.py collectstatic`

### Error: "No module named 'gunicorn'"
- **Solución**: Agregar `gunicorn` a `requirements.txt`

### Error: "Database locked"
- **Solución**: Cambiar a PostgreSQL en producción

---

## ✅ Checklist Pre-Deploy

- [ ] `requirements.txt` actualizado
- [ ] `DEBUG = False` en producción
- [ ] `ALLOWED_HOSTS` configurado
- [ ] `SECRET_KEY` en variables de entorno
- [ ] `STATIC_ROOT` configurado
- [ ] `.gitignore` incluye `.env` y archivos sensibles
- [ ] Migraciones listas
- [ ] `Procfile` creado
- [ ] Archivos estáticos recopilados
- [ ] Base de datos migrada
- [ ] Superusuario creado

---

## 🎉 Después del Deploy

1. Accede a tu URL: `https://tu-app.onrender.com`
2. Verifica que todo funciona
3. Crea un superusuario: `python manage.py createsuperuser`
4. Prueba todas las funcionalidades
5. Comparte la URL con tu cliente

---

## 📞 Soporte

Si tienes problemas durante el deploy, revisa:
- Logs del servicio en tu plataforma de hosting
- Console de Django (errores 500)
- Configuración de variables de entorno
- Documentación oficial de Django: https://docs.djangoproject.com/en/5.0/howto/deployment/

---

**¡Buena suerte con tu deployment! 🚀**








