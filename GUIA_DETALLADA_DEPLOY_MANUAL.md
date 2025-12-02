# 📘 Guía Maestra de Despliegue Manual en DigitalOcean

¡Hola! Esta guía está diseñada para llevarte de **0 a 100** en el despliegue de tu aplicación Django. No solo te diré *qué* hacer, sino *por qué* lo estamos haciendo.

---

## 🧠 Conceptos Clave (Antes de empezar)

*   **VPS (Virtual Private Server)**: Es tu computadora en la nube. A diferencia de tu laptop, esta está prendida 24/7 y tiene una dirección IP pública fija. DigitalOcean llama a sus VPS "Droplets".
*   **SSH (Secure Shell)**: Es la forma en que controlamos el servidor remotamente. Es como abrir una terminal en tu compu, pero los comandos se ejecutan allá.
*   **Nginx**: Es el "portero" de tu edificio. Recibe las peticiones de internet (puerto 80/443) y decide a dónde mandarlas. Es muy rápido sirviendo archivos estáticos (imágenes, CSS).
*   **Gunicorn**: Es el "traductor". Nginx habla HTTP, pero Django habla Python. Gunicorn conecta a los dos.
*   **PostgreSQL**: Tu base de datos profesional. SQLite (lo que usas localmente) es un archivo simple, pero Postgres es un servidor de base de datos robusto para producción.
*   **Supervisor**: Es el "jefe de piso". Vigila que Gunicorn esté siempre trabajando. Si Gunicorn se cae, Supervisor lo levanta de nuevo.

---

## � PASO 0: Subir tus cambios a GitHub

Como ya tienes el proyecto en GitHub, necesitamos asegurarnos de que tu nube (GitHub) tenga la última versión de tu código (la que tienes en tu compu).

1.  **Abre tu terminal** en tu computadora (no en el servidor).
2.  Asegúrate de estar en la carpeta de tu proyecto.
3.  Ejecuta estos comandos **uno por uno**:

    Agrega todos los archivos nuevos o modificados:
    ```bash
    git add .
    ```

    Guarda los cambios con un mensaje (el "paquete" listo para enviar):
    ```bash
    git commit -m "Preparando proyecto para deploy en VPS"
    ```

    Envía el paquete a la nube (GitHub):
    ```bash
    git push origin master
    ```
    *(Nota: Si tu rama se llama `main`, usa `git push origin main`. Puedes ver el nombre en tu terminal, suele estar entre paréntesis).*

---

## �🛠️ PASO 1: Crear tu Servidor (Droplet)

Vamos a rentar el espacio en la nube.

1.  Entra a tu cuenta de **DigitalOcean**.
2.  Click en **Create** -> **Droplets**.
3.  **Region**: Elige **San Francisco** o **New York**.
    *   *¿Por qué?* Son los puntos más cercanos a México/Latam con mejor conectividad. Evita Europa (Amsterdam/London) por la latencia (lentitud).
4.  **OS (Sistema Operativo)**: Elige **Ubuntu 22.04 LTS**.
    *   *¿Por qué?* Ubuntu es el estándar en servidores. LTS significa "Long Term Support", o sea, estabilidad garantizada por años.
5.  **Droplet Type**: **Basic** -> **Regular** -> **$6/mo** (o $4/mo si está disponible).
    *   *¿Por qué?* Para empezar, 1GB de RAM y 1 CPU es suficiente. Siempre puedes aumentar el tamaño después con un click.
6.  **Authentication**:
    *   **SSH Key**: Es lo más seguro, pero requiere generar llaves en tu compu.
    *   **Password**: Más fácil para empezar. Elige una contraseña **muy difícil** y guárdala bien.
7.  **Hostname**: Ponle un nombre fácil, ej: `agencia-web-prod`.
8.  Click en **Create Droplet**.

⏳ **Espera unos segundos** hasta que veas una dirección IP (ej: `143.20.10.5`). Esa es la dirección de tu nueva casa en internet.

---

## 🔌 PASO 2: Conexión Inicial

Vamos a entrar a tu servidor.

1.  Abre tu terminal en Mac.
2.  Escribe el siguiente comando (reemplaza `TU_IP_AQUI` con la IP que te dio DigitalOcean):
    ```bash
    ssh root@TU_IP_AQUI
    ```
3.  Te preguntará si confías en el host (`Are you sure...?`). Escribe `yes` y da Enter.
4.  Pon tu contraseña (si elegiste password).
    *   **OJO**: Al escribir la contraseña **no verás asteriscos ni nada moverse**. Es normal por seguridad. Tú escribe la contraseña completa y da Enter.

🎉 **Si ves algo como `root@agencia-web-prod:~#`, ¡ya estás dentro del servidor!**

---

## 🛡️ PASO 3: Seguridad Básica y Usuarios

Ahora somos el usuario `root` (el dios del servidor). Es peligroso usar `root` para todo. Vamos a crear un usuario normal.

1.  Actualiza el sistema (copia y pega esta línea y da Enter):
    ```bash
    apt update && apt upgrade -y
    ```

2.  Crea tu usuario (reemplaza `ulises` si quieres otro nombre):
    ```bash
    adduser ulises
    ```
    *(Te pedirá una contraseña para este usuario. Ponle una segura. A las preguntas de "Full Name", etc., puedes dar Enter para dejarlas vacías. Al final escribe `Y` para confirmar).*

3.  Dale poderes de administrador al usuario:
    ```bash
    usermod -aG sudo ulises
    ```

4.  Cierra la sesión de root:
    ```bash
    exit
    ```

5.  **Vuelve a conectarte**, pero ahora con tu nuevo usuario:
    ```bash
    ssh ulises@TU_IP_AQUI
    ```

---

## 📦 PASO 4: Instalar Herramientas

Necesitamos instalar Python, la base de datos y el servidor web.

Copia y pega este comando largo (es una sola línea):
```bash
sudo apt install -y python3-pip python3-venv python3-dev libpq-dev postgresql postgresql-contrib nginx curl git
```
*(Te pedirá la contraseña de `ulises` que creaste en el paso anterior).*

---

## 🗄️ PASO 5: Configurar Base de Datos

Vamos a crear la "caja fuerte" para tus datos.

1.  Entra a la consola de Postgres:
    ```bash
    sudo -u postgres psql
    ```

2.  Ahora estás dentro de Postgres. Copia y pega estas líneas **una por una** y da Enter después de cada una:

    Crea la base de datos:
    ```sql
    CREATE DATABASE agencia_db;
    ```

    Crea el usuario de la base de datos (¡CAMBIA LA CONTRASEÑA AQUÍ!):
    ```sql
    CREATE USER agencia_user WITH PASSWORD 'TU_CONTRASEÑA_SEGURA_DB';
    ```

    Configura el usuario (copia estas 3 líneas juntas si quieres, o una por una):
    ```sql
    ALTER ROLE agencia_user SET client_encoding TO 'utf8';
    ALTER ROLE agencia_user SET default_transaction_isolation TO 'read committed';
    ALTER ROLE agencia_user SET timezone TO 'America/Mexico_City';
    ```

    Dale permisos:
    ```sql
    GRANT ALL PRIVILEGES ON DATABASE agencia_db TO agencia_user;
    ```

    Sal de Postgres:
    ```sql
    \q
    ```

---

## 📂 PASO 6: Descargar tu Código

1.  Crea la carpeta para el proyecto:
    ```bash
    mkdir -p ~/sitios/agencia
    ```

2.  Entra a la carpeta:
    ```bash
    cd ~/sitios/agencia
    ```

3.  Clona tu repositorio.
    *   Nota: Como es un repo privado (probablemente), te pedirá usuario y contraseña.
    *   **Importante**: En "Password", GitHub ya no acepta tu contraseña de login. Debes usar un **Personal Access Token**.
    *   Si no tienes token, es más fácil clonar usando HTTPS e ingresando tus credenciales.
    
    Reemplaza con tu usuario y repo:
    ```bash
    git clone https://github.com/TU_USUARIO/TU_REPO.git .
    ```
    *(El punto `.` al final es muy importante, para que clone en la carpeta actual).*

---

## 🐍 PASO 7: Entorno Virtual y Dependencias

1.  Crea el entorno virtual:
    ```bash
    python3 -m venv venv
    ```

2.  Activa el entorno:
    ```bash
    source venv/bin/activate
    ```
    *(Verás que tu terminal ahora dice `(venv)` al principio).*

3.  Instala las librerías de tu proyecto:
    ```bash
    pip install -r requirements.txt
    ```

4.  Instala Gunicorn y el conector de base de datos (necesarios para producción):
    ```bash
    pip install gunicorn psycopg2-binary
    ```

---

## 🔐 PASO 8: Variables de Entorno (.env)

1.  Abre el editor de texto `nano` para crear el archivo:
    ```bash
    nano .env
    ```

2.  Pega el siguiente contenido. **Asegúrate de cambiar los valores** por los reales:

    ```env
    DEBUG=False
    SECRET_KEY=inventa_una_clave_larga_y_rara_aqui
    ALLOWED_HOSTS=TU_IP_AQUI,tu-dominio.com
    DATABASE_URL=postgres://agencia_user:TU_CONTRASEÑA_SEGURA_DB@localhost/agencia_db
    ```
    *(Usa la contraseña que pusiste en el PASO 5).*

3.  **Para guardar y salir de nano:**
    *   Presiona `Ctrl + O` (letra O) y luego `Enter` (para guardar).
    *   Presiona `Ctrl + X` (para salir).

---

## 🏗️ PASO 9: Preparar Django

Ejecuta estos comandos uno por uno:

1.  Prepara la base de datos (crea las tablas):
    ```bash
    python manage.py migrate
    ```

2.  Junta los archivos estáticos (CSS, imágenes):
    ```bash
    python manage.py collectstatic
    ```
    *(Escribe `yes` si te pregunta).*

3.  Crea tu usuario administrador para entrar al dashboard:
    ```bash
    python manage.py createsuperuser
    ```

---

## 🤖 PASO 10: Configurar Gunicorn y Supervisor

1.  Crea el script de inicio:
    ```bash
    nano ~/sitios/agencia/gunicorn_start
    ```

2.  Pega este contenido (revisa que `USER` sea tu usuario, ej: `ulises`):

    ```bash
    #!/bin/bash
    NAME="agencia_app"
    DJANGODIR=/home/ulises/sitios/agencia
    SOCKFILE=/home/ulises/sitios/agencia/run/gunicorn.sock
    USER=ulises
    GROUP=ulises
    NUM_WORKERS=3
    DJANGO_SETTINGS_MODULE=agencia_web.settings
    DJANGO_WSGI_MODULE=agencia_web.wsgi
    
    echo "Starting $NAME as `whoami`"
    
    cd $DJANGODIR
    source venv/bin/activate
    export DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE
    export PYTHONPATH=$DJANGODIR:$PYTHONPATH
    
    RUNDIR=$(dirname $SOCKFILE)
    test -d $RUNDIR || mkdir -p $RUNDIR
    
    exec gunicorn ${DJANGO_WSGI_MODULE}:application \
      --name $NAME \
      --workers $NUM_WORKERS \
      --user=$USER --group=$GROUP \
      --bind=unix:$SOCKFILE \
      --log-level=debug \
      --log-file=-
    ```

3.  Guarda y sal (`Ctrl+O`, `Enter`, `Ctrl+X`).

4.  Haz el script ejecutable:
    ```bash
    chmod +x ~/sitios/agencia/gunicorn_start
    ```

5.  Configura Supervisor (el vigilante):
    ```bash
    sudo nano /etc/supervisor/conf.d/agencia.conf
    ```

6.  Pega esto:
    ```ini
    [program:agencia]
    command=/home/ulises/sitios/agencia/gunicorn_start
    user=ulises
    autostart=true
    autorestart=true
    redirect_stderr=true
    stdout_logfile=/home/ulises/sitios/agencia/logs/gunicorn-error.log
    ```

7.  Guarda y sal.

8.  Crea la carpeta de logs y arranca todo:
    ```bash
    mkdir -p ~/sitios/agencia/logs
    ```
    ```bash
    sudo supervisorctl reread
    ```
    ```bash
    sudo supervisorctl update
    ```
    ```bash
    sudo supervisorctl status
    ```
    *(Si dice `agencia RUNNING`, ¡vamos bien!).*

---

## 🌐 PASO 11: Configurar Nginx

1.  Crea la configuración del sitio:
    ```bash
    sudo nano /etc/nginx/sites-available/agencia
    ```

2.  Pega esto (**Cambia `TU_IP_AQUI` por tu IP real**):

    ```nginx
    server {
        listen 80;
        server_name TU_IP_AQUI;

        location = /favicon.ico { access_log off; log_not_found off; }
        
        location /static/ {
            root /home/ulises/sitios/agencia;
        }

        location /media/ {
            root /home/ulises/sitios/agencia;
        }

        location / {
            include proxy_params;
            proxy_pass http://unix:/home/ulises/sitios/agencia/run/gunicorn.sock;
        }
    }
    ```

3.  Guarda y sal.

4.  Activa el sitio:
    ```bash
    sudo ln -s /etc/nginx/sites-available/agencia /etc/nginx/sites-enabled
    ```

5.  Verifica que no haya errores:
    ```bash
    sudo nginx -t
    ```
    *(Debe decir "syntax is ok").*

6.  Reinicia Nginx:
    ```bash
    sudo systemctl restart nginx
    ```

---

## 🎉 ¡LISTO!

Abre tu navegador y pon tu IP. ¡Deberías ver tu sitio funcionando!
