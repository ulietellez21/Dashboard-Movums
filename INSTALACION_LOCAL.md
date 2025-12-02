# 💻 Guía de Instalación Local - Movums Agency Web

## 📋 ¿Qué significa "Instalación Local"?

Ejecutar la aplicación directamente en cada computadora, sin necesidad de un servidor en internet.

---

## ✅ Ventajas de Instalación Local

1. **Sin costo de hosting** - $0/mes
2. **Funciona sin internet** - Una vez instalada
3. **Datos privados** - Todo queda en la computadora
4. **Velocidad máxima** - Sin latencia de red
5. **Control total** - El cliente tiene control completo

---

## ⚠️ Desventajas y Limitaciones

1. **Instalación manual** - En cada computadora
2. **Cada máquina es independiente** - No comparten datos (a menos que configures red)
3. **Actualizaciones manuales** - Debes actualizar cada máquina
4. **Requiere conocimientos técnicos** - Instalar Python, dependencias
5. **Solo accesible desde esa PC** - No desde otras ubicaciones

---

## 🎯 Escenarios de Uso

### ✅ Buena Idea para:
- **1-2 usuarios** en la misma oficina
- **Datos no necesitan compartirse** entre usuarios
- **Uso principalmente offline**
- **Presupuesto muy limitado**

### ❌ No Recomendado para:
- **Múltiples usuarios** que necesitan compartir datos
- **Acceso desde diferentes ubicaciones**
- **Equipo distribuido** (oficinas diferentes)
- **Mantenimiento centralizado**

---

## 🔧 Opción 1: Instalación Manual Local (Básica)

### Requisitos Previos:
- Python 3.12 instalado
- Terminal/Consola de comandos
- Conexión a internet (solo para descargar)

### Paso a Paso:

#### 1. Instalar Python

**Windows:**
- Descargar de: https://www.python.org/downloads/
- Instalar con "Add Python to PATH" marcado

**Mac:**
- Ya viene instalado, o instalar con Homebrew:
```bash
brew install python@3.12
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3.12 python3-pip python3-venv
```

#### 2. Clonar/Descargar el Proyecto

```bash
# En la carpeta donde quieres instalar
cd ~/Desktop  # o donde prefieras
git clone URL-DEL-REPOSITORIO movums-local
cd movums-local
```

**O descargar ZIP:**
- Descargar proyecto como ZIP
- Extraer en la carpeta deseada

#### 3. Crear Entorno Virtual

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

#### 4. Instalar Dependencias

```bash
pip install -r requirements.txt
```

#### 5. Configurar Base de Datos

```bash
# Migrar base de datos (SQLite se crea automáticamente)
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser
```

#### 6. Ejecutar la Aplicación

```bash
python manage.py runserver
```

#### 7. Acceder

Abrir navegador en: `http://127.0.0.1:8000`

---

## 🐳 Opción 2: Docker (Más Fácil)

### Ventajas:
- ✅ No requiere instalar Python manualmente
- ✅ Funciona igual en Windows, Mac, Linux
- ✅ Todo configurado automáticamente
- ✅ Fácil de actualizar

### Requisitos:
- Docker Desktop instalado
- Descargar: https://www.docker.com/products/docker-desktop

### Pasos:

#### 1. Instalar Docker Desktop

- Descargar e instalar Docker Desktop
- Reiniciar computadora

#### 2. Descargar Proyecto

```bash
git clone URL-DEL-REPOSITORIO movums-local
cd movums-local
```

#### 3. Ejecutar con Docker

```bash
# Primera vez (construye la imagen)
docker-compose up --build

# Siguientes veces
docker-compose up
```

#### 4. Acceder

Abrir navegador en: `http://localhost:8000`

#### 5. Crear Superusuario

En otra terminal:
```bash
docker-compose exec web python manage.py createsuperuser
```

---

## 📦 Opción 3: Script de Instalación Automática

Puedo crear un script que automatice todo el proceso:

### Para Windows:
- `install.bat` - Hace todo automáticamente

### Para Mac/Linux:
- `install.sh` - Script de instalación

Esto facilitaría mucho la instalación en múltiples máquinas.

---

## 🔄 Opción 4: Instalación Local con Base de Datos Compartida

Si quieres que **múltiples computadoras compartan los mismos datos**:

### Arquitectura:
```
Computadora 1 (Servidor)
├── Django corriendo
├── Base de datos PostgreSQL/SQLite
└── Accesible en red local (192.168.1.100:8000)

Computadora 2, 3, 4... (Clientes)
└── Acceden vía navegador a: http://192.168.1.100:8000
```

### Ventajas:
- ✅ Una sola instalación de Django
- ✅ Base de datos compartida
- ✅ Todos ven los mismos datos
- ✅ Actualizaciones en un solo lugar

### Configuración:

#### En la computadora servidor:

1. Obtener IP local:
```bash
# Windows
ipconfig

# Mac/Linux
ifconfig
```

2. Ejecutar servidor accesible en red:
```bash
python manage.py runserver 0.0.0.0:8000
```

3. Configurar `ALLOWED_HOSTS` en `settings.py`:
```python
ALLOWED_HOSTS = ['192.168.1.100', 'localhost', '127.0.0.1']
```

#### En las otras computadoras:
- Abrir navegador en: `http://IP-DEL-SERVIDOR:8000`
- Ejemplo: `http://192.168.1.100:8000`

---

## 📊 Comparativa de Opciones

| Opción | Facilidad | Compartir Datos | Mantenimiento | Costo |
|--------|-----------|-----------------|---------------|-------|
| **Local Individual** | Media | ❌ No | Alto | $0 |
| **Docker** | Alta | ❌ No | Medio | $0 |
| **Red Local** | Media | ✅ Sí | Bajo | $0 |
| **VPS Online** | Media | ✅ Sí | Bajo | $5-12/mes |

---

## 🎯 Mi Recomendación por Escenario

### Escenario 1: 1-2 Usuarios, Misma Oficina
✅ **Instalación Local Individual con Docker**
- Fácil de instalar
- Cada uno tiene su propia copia
- Sin costo

### Escenario 2: 3-10 Usuarios, Misma Oficina
✅ **Instalación Local con Red (1 servidor + clientes)**
- Una computadora como servidor
- Resto accede por navegador
- Todos comparten datos
- Sin costo

### Escenario 3: Múltiples Oficinas o Usuarios Remotos
✅ **VPS Online**
- Acceso desde cualquier lugar
- Base de datos centralizada
- Más fácil de mantener

---

## 🛠️ Scripts de Instalación Automática

Puedo crear scripts que faciliten la instalación:

### Windows (`install_windows.bat`):
```batch
@echo off
echo Instalando Movums Agency Web...
python -m venv venv
call venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
echo Instalacion completada!
echo Ejecutar: python manage.py runserver
pause
```

### Mac/Linux (`install.sh`):
```bash
#!/bin/bash
echo "Instalando Movums Agency Web..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
echo "Instalacion completada!"
echo "Ejecutar: python manage.py runserver"
```

---

## 📝 Checklist de Instalación Local

### Para Cada Computadora:

- [ ] Python 3.12 instalado
- [ ] Proyecto descargado/clonado
- [ ] Entorno virtual creado
- [ ] Dependencias instaladas
- [ ] Base de datos migrada
- [ ] Superusuario creado
- [ ] Servidor ejecutándose
- [ ] Accesible en navegador

---

## 🔒 Consideraciones de Seguridad

### Datos Locales:
- ⚠️ Base de datos en la computadora
- ⚠️ Sin respaldo automático (a menos que lo configures)
- ✅ Datos privados (no salen de la red local)

### Recomendaciones:
1. **Hacer backups regulares** de `db.sqlite3`
2. **Proteger con contraseña** la computadora
3. **No exponer a internet** (solo red local)

---

## 💡 Alternativa: Ejecutable (.exe en Windows)

Puedo ayudarte a crear un **ejecutable** usando:
- **PyInstaller** - Convierte Python en .exe
- **Auto-py-to-exe** - Interfaz gráfica

### Ventajas:
- ✅ No requiere instalar Python
- ✅ Doble clic y funciona
- ✅ Más fácil para usuarios no técnicos

### Desventajas:
- ⚠️ Archivo grande (~200-300 MB)
- ⚠️ Más lento al iniciar
- ⚠️ Requiere configuración adicional

---

## 🎯 Siguiente Paso

**Dime qué prefieres:**

1. **Instalación Manual** - Guía paso a paso
2. **Docker** - Más fácil, ya tengo `docker-compose.yml`
3. **Script Automático** - Creo scripts de instalación
4. **Ejecutable** - Creo un .exe para Windows
5. **Red Local** - Configuro servidor compartido

---

## 📞 Resumen

### ¿Puede correr localmente?
**✅ SÍ** - Definitivamente puede instalarse localmente

### ¿Es recomendable?
**Depende:**
- ✅ **Sí** para 1-2 usuarios
- ✅ **Sí** si no necesitan compartir datos
- ⚠️ **No** para múltiples usuarios que necesitan datos compartidos

### ¿Cuál opción elegir?
- **Fácil**: Docker
- **Tradicional**: Instalación manual
- **Compartir datos**: Red local (1 servidor)
- **No técnicos**: Ejecutable

**¿Qué opción prefieres? Te ayudo a configurarla. 🚀**








