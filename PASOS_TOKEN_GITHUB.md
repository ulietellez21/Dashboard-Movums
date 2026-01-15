# 🔐 Pasos para Configurar Token de GitHub

## 📋 Método 1: Personal Access Token (Recomendado)

### Paso 1: Crear el Token en GitHub

1. **Ir a GitHub.com** e iniciar sesión con tu cuenta
2. **Hacer clic en tu avatar** (esquina superior derecha) → **Settings**
3. En el menú lateral izquierdo, ir a:
   - **Developer settings** (al final del menú)
4. Dentro de Developer settings:
   - **Personal access tokens** → **Tokens (classic)**
5. **Generate new token** → **Generate new token (classic)**
6. **Configurar el token:**
   - **Note:** "Agencia Web Project - Acceso desde Mac"
   - **Expiration:** Selecciona la duración (90 días, 1 año, o "No expiration")
   - **Select scopes:** Marcar:
     - ✅ `repo` (todo) - Para push/pull completo
     - O más específico:
       - ✅ `repo:status`
       - ✅ `repo_deployment`
       - ✅ `public_repo` (si el repo es público)
       - ✅ `workflow` (si usas GitHub Actions)
7. **Scroll down** → **Generate token**
8. **⚠️ IMPORTANTE:** Copia el token inmediatamente (solo se muestra una vez)
   - Ejemplo: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

---

### Paso 2: Usar el Token para Push

#### Opción A: Usar el token como contraseña (temporal)

```bash
# Cuando pida contraseña, usa el token en lugar de tu contraseña
git push origin master
# Username: ulietellez21
# Password: [pegar aquí el token ghp_xxxxx]
```

#### Opción B: Guardar el token en la URL (más cómodo)

```bash
# Agregar el token a la URL del remoto
git remote set-url origin https://ulietellez21:TU_TOKEN_AQUI@github.com/ulietellez21/Dashboard-Movums.git

# O usando una variable de entorno
export GITHUB_TOKEN="tu_token_aqui"
git remote set-url origin https://ulietellez21:${GITHUB_TOKEN}@github.com/ulietellez21/Dashboard-Movums.git
```

#### Opción C: Usar Git Credential Helper (más seguro)

```bash
# Configurar el credential helper para macOS Keychain
git config --global credential.helper osxkeychain

# Hacer push (pedirá usuario y contraseña/token una vez)
git push origin master
# Username: ulietellez21
# Password: [pegar token]
# Se guardará en el Keychain de macOS
```

#### Opción D: Configurar en .git/config (local, menos recomendado)

```bash
# Editar el archivo de configuración del repositorio
nano .git/config

# Cambiar la línea:
# url = https://github.com/ulietellez21/Dashboard-Movums.git
# Por:
# url = https://ulietellez21:TU_TOKEN@github.com/ulietellez21/Dashboard-Movums.git
```

---

## 📋 Método 2: SSH Keys (Alternativa más segura)

Si prefieres no usar tokens, puedes configurar SSH:

### Paso 1: Generar clave SSH

```bash
# Generar nueva clave SSH (si no tienes una)
ssh-keygen -t ed25519 -C "tu_email@ejemplo.com"

# Presionar Enter para aceptar ubicación por defecto
# Ingresar una contraseña (opcional pero recomendado)
```

### Paso 2: Agregar clave al ssh-agent

```bash
# Iniciar el agente
eval "$(ssh-agent -s)"

# Agregar la clave
ssh-add ~/.ssh/id_ed25519
```

### Paso 3: Copiar clave pública

```bash
# Copiar la clave pública al portapapeles
pbcopy < ~/.ssh/id_ed25519.pub

# O mostrar en pantalla
cat ~/.ssh/id_ed25519.pub
```

### Paso 4: Agregar clave en GitHub

1. GitHub.com → **Settings** → **SSH and GPG keys**
2. **New SSH key**
3. **Title:** "MacBook Air - Agencia Web"
4. **Key:** Pegar la clave pública
5. **Add SSH key**

### Paso 5: Cambiar remoto a SSH

```bash
# Cambiar URL del remoto a SSH
git remote set-url origin git@github.com:ulietellez21/Dashboard-Movums.git

# Verificar
git remote -v

# Hacer push (ya no pedirá contraseña)
git push origin master
```

---

## 🎯 Recomendación

**Para uso rápido:** Método 1 - Opción C (credential helper + token)  
**Para mayor seguridad:** Método 2 (SSH keys)

---

## ⚠️ Seguridad

- **NUNCA** compartas tu token
- **NUNCA** subas el token a git
- Si el token se compromete, revócalo inmediatamente en GitHub
- Considera usar tokens con expiración

---

## 🔄 Revocar un Token

Si necesitas revocar un token:

1. GitHub.com → **Settings** → **Developer settings** → **Personal access tokens**
2. Buscar el token
3. Hacer clic en **Revoke**


