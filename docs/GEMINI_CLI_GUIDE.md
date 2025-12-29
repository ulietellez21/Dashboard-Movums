# Guía de Implementación: Gemini CLI para Desarrolladores

Esta guía detalla cómo integrar Gemini en tu flujo de trabajo diario como programador.

## 1. Instalación (Opción Node.js Oficial)

Recomendamos usar el paquete oficial `@google/gemini-cli` que ofrece integración con Google Cloud y un modo de chat robusto.

**Requisitos:** Node.js v20+

**Comando de Instalación:**
```bash
npm install -g @google/gemini-cli
```
*(Si prefieres no instalar, puedes usar `npx @google/gemini-cli`)*

**Configuración:**
1.  **Ejecutar:** Escribe `gemini` en tu terminal.
2.  **Login:** Elige "Login with Google". Esto abrirá tu navegador para autenticarte.
    *   *Nota:* Si tienes Google Cloud SDK instalado, detectará tu sesión. Si no, usará OAuth estándar.

---

## 2. Ventajas en tu Flujo de Trabajo

### A. Debugging "Tubería" (Piping)
Envía errores directamente a la IA:
```bash
python manage.py runserver 2>&1 | gemini chat "Analiza este error"
```

### B. Comandos Shell
```bash
gemini chat "Dame el comando para comprimir logs antiguos en zip"
```

### C. Explicación de Código
```bash
cat ventas/views.py | gemini chat "Explica esta vista"
```
