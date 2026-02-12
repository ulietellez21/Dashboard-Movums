# Configurar .env para base de datos (local vs servidor)

La app usa **solo** la variable `DB_ENGINE` para elegir la base de datos (nunca `DEBUG`):

- **Local (tu máquina):** en `.env` deja **comentada** la línea `DB_ENGINE` → se usa **SQLite** (`db.sqlite3`).
- **Servidor (movums.com.mx):** en `.env` del servidor **descomenta** `DB_ENGINE` y configura `DB_*` → se usa **PostgreSQL**.

Así evitas que el servidor use SQLite por error y pierda el login.

---

## En el servidor de producción

Crea o edita `.env` en la raíz del proyecto (donde está `manage.py`):

```bash
nano .env
```

Contenido (con credenciales reales); **DB_ENGINE debe estar descomentado**:

```
# Base de datos: en SERVIDOR descomentar DB_ENGINE para PostgreSQL
DB_ENGINE=django.db.backends.postgresql
DB_NAME=defaultdb
DB_USER=doadmin
DB_PASSWORD=tu_password_real
DB_HOST=db-postgresql-....ondigitalocean.com
DB_PORT=25060
```

Guarda (Ctrl+O, Enter) y cierra (Ctrl+X). Reinicia Gunicorn después de cambiar `.env`.

---

## En tu máquina (desarrollo local)

En tu `.env` local, **comenta** la línea `DB_ENGINE` para usar SQLite:

```
# Base de datos: LOCAL = dejar DB_ENGINE comentado para SQLite
# DB_ENGINE=django.db.backends.postgresql
DB_NAME=defaultdb
...
```

Si `DB_ENGINE` está comentado o no existe, Django usará `db.sqlite3` en local.
