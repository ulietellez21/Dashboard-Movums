# Requisitos del Sistema para Producción

## Sistema Operativo

- **Ubuntu 22.04 LTS** (recomendado)
- También compatible con: Ubuntu 20.04, Debian 11+

## Dependencias del Sistema (apt)

Estas dependencias deben instalarse **antes** de `pip install -r requirements.txt`:

```bash
sudo apt update
sudo apt install -y \
    libmagic1 \
    libmagic-dev \
    python3-dev \
    libpq-dev \
    build-essential \
    nginx \
    supervisor
```

### Descripción de cada paquete:

| Paquete | Requerido por | Descripción |
|---------|---------------|-------------|
| `libmagic1` | `python-magic` | Librería para detectar tipos MIME de archivos |
| `libmagic-dev` | `python-magic` (compilación) | Headers para compilar extensiones |
| `python3-dev` | Varios paquetes Python | Headers de Python para compilar extensiones C |
| `libpq-dev` | `psycopg2-binary` | Cliente de PostgreSQL para Python |
| `build-essential` | Varios | Compiladores GCC, make, etc. |
| `nginx` | Servidor web | Proxy reverso para Gunicorn |
| `supervisor` | Opcional | Gestión de procesos (alternativa a systemd) |

## Verificación de Dependencias

### Verificar libmagic:

```bash
# Verificar instalación
dpkg -l | grep libmagic

# Verificar que el archivo de librería existe
ls -la /usr/lib/x86_64-linux-gnu/libmagic*

# Probar desde Python
python3 -c "import magic; print(magic.from_buffer(b'%PDF-1.4', mime=True))"
# Debe imprimir: application/pdf
```

### Verificar PostgreSQL client:

```bash
pg_config --version
```

## Script de Instalación Rápida

```bash
#!/bin/bash
# Ejecutar como root

apt update
apt install -y libmagic1 libmagic-dev python3-dev libpq-dev build-essential

# Verificar
python3 -c "import magic; print('OK')" && echo "✅ libmagic funciona"
```

## Despliegue

Usar el script de despliegue automatizado:

```bash
# Desde el servidor como root
cd /home/tellez/sitios/agencia
./scripts/deploy.sh
```

El script `deploy.sh` automáticamente:
1. Verifica e instala dependencias del sistema faltantes
2. Crea backup de la base de datos
3. Descarga cambios de Git
4. Instala dependencias de Python
5. Aplica migraciones
6. Recolecta archivos estáticos
7. Reinicia Gunicorn y Nginx

## Solución de Problemas

### Error: "failed to find libmagic"

```bash
# Instalar libmagic
sudo apt install libmagic1

# Si persiste, verificar la ruta
sudo find / -name "libmagic.so*" 2>/dev/null
```

### Error: "pg_config not found"

```bash
sudo apt install libpq-dev
```

### Error de permisos en archivos estáticos

```bash
sudo chown -R tellez:tellez /home/tellez/sitios/agencia/staticfiles
sudo chmod -R 755 /home/tellez/sitios/agencia/staticfiles
```
