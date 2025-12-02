# 🚀 Guía Rápida de Deployment - Pasos Esenciales

## 📌 Resumen de lo que ya está listo:

✅ `requirements.txt` - Actualizado con gunicorn y whitenoise
✅ `Procfile` - Configurado para Render/Railway
✅ `runtime.txt` - Versión de Python especificada
✅ `.gitignore` - Configurado para no subir archivos sensibles
✅ `settings.py` - Actualizado para usar variables de entorno
✅ `DEPLOYMENT_GUIDE.md` - Guía completa con todas las opciones

---

## 🎯 Opción RÁPIDA: Render.com (Gratis)

### Paso 1: Preparar repositorio Git

```bash
# Si no tienes Git inicializado
git init
git add .
git commit -m "Preparado para deployment"

# Si no tienes cuenta en GitHub, créala en github.com
# Luego crea un repositorio nuevo y ejecuta:
git remote add origin https://github.com/TU-USUARIO/TU-REPO.git
git branch -M main
git push -u origin main
```

### Paso 2: Crear cuenta en Render

1. Ve a https://render.com
2. Regístrate con GitHub (es más fácil)
3. Conecta tu cuenta de GitHub

### Paso 3: Crear Web Service

1. Click en **"New +"** → **"Web Service"**
2. Selecciona tu repositorio de GitHub
3. Configuración:
   - **Name**: `movums-agency` (o el que prefieras)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
   - **Start Command**: `gunicorn agencia_web.wsgi:application`
   - **Instance Type**: `Free`

### Paso 4: Configurar Variables de Entorno

En la sección **"Environment"**, agrega:

```
SECRET_KEY=genera-una-nueva-clave-secreta
DEBUG=False
ALLOWED_HOSTS=movums-agency.onrender.com
```

**⚠️ IMPORTANTE:** Para generar una nueva SECRET_KEY, ejecuta en tu terminal local:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Paso 5: Deploy

1. Click en **"Create Web Service"**
2. Espera 5-10 minutos mientras Render construye y despliega
3. Verás los logs en tiempo real

### Paso 6: Post-Deploy (Primera vez)

Después del primer deploy exitoso:

1. Ve a tu servicio en Render
2. Click en **"Shell"** (consola)
3. Ejecuta estos comandos:

```bash
# Migrar base de datos
python manage.py migrate

# Crear superusuario (sigue las instrucciones)
python manage.py createsuperuser
```

### Paso 7: ¡Listo!

Tu aplicación estará disponible en:
`https://movums-agency.onrender.com`

---

## 🔧 Troubleshooting Rápido

### Error: "DisallowedHost"
**Solución**: Verifica que `ALLOWED_HOSTS` en Render incluya tu dominio

### Error: "Static files not found"
**Solución**: El build command ya incluye `collectstatic`, pero si persiste, ejecuta en Shell:
```bash
python manage.py collectstatic --noinput
```

### Error: "No module named 'whitenoise'"
**Solución**: Verifica que `requirements.txt` incluya `whitenoise==6.6.0`

### Error: "Secret key not found"
**Solución**: Asegúrate de haber agregado `SECRET_KEY` en las variables de entorno de Render

---

## 📝 Checklist Final

Antes de compartir con tu cliente:

- [ ] Aplicación desplegada y funcionando
- [ ] Puedes acceder a la URL
- [ ] Migraciones ejecutadas
- [ ] Superusuario creado
- [ ] Puedes hacer login
- [ ] Pruebas las funcionalidades principales
- [ ] Archivos estáticos (CSS, imágenes) cargan correctamente

---

## 💡 Tips

1. **Primera carga lenta**: En plan gratuito, Render "duerme" el servidor después de 15 minutos de inactividad. La primera petición después de dormir puede tardar 30-60 segundos.

2. **Logs**: Siempre revisa los logs en Render si algo no funciona.

3. **Dominio personalizado**: Puedes agregar tu propio dominio en Render (Settings → Custom Domains).

4. **Actualizaciones**: Cada vez que hagas `git push`, Render desplegará automáticamente.

---

## 🆘 ¿Problemas?

- Revisa `DEPLOYMENT_GUIDE.md` para más detalles
- Consulta los logs en Render
- Verifica que todas las variables de entorno estén configuradas

---

**¡Mucha suerte con tu deployment! 🎉**








