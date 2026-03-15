# Plan: Campana de leads calientes en el dashboard (Gerente / Director Administrativo)

## 1. Análisis del flujo de roles

### Dónde se definen los roles
- **Modelo:** `usuarios/models.py` — `Perfil.rol` con `ROL_CHOICES`: `JEFE`, `DIRECTOR_GENERAL`, `DIRECTOR_VENTAS`, `DIRECTOR_ADMINISTRATIVO`, `GERENTE`, `CONTADOR`, `VENDEDOR`.
- **Permisos:** `usuarios/permissions.py` — constantes `ROL_GERENTE = 'GERENTE'`, `ROL_DIRECTOR_ADMINISTRATIVO = 'DIRECTOR_ADMINISTRATIVO'`; `get_user_role(user, request)` devuelve el código del rol (ej. `'GERENTE'`).
- **Contexto global:** `usuarios/context_processors.py` — función `user_rol_safe` expone **`user_rol_display`** en todas las plantillas (valor = rol interno, ej. `'GERENTE'`, o `'Consulta ventas'` / `'INVITADO'` si aplica).

### Dónde se usa el rol en el dashboard
- **Vista:** `ventas/views.py` — `DashboardView.get_context_data()` hace `context['user_rol'] = perm.get_user_role(user, request)`.
- **Plantilla dashboard:** `templates/dashboard.html` — bloques condicionales `{% if user_rol == 'GERENTE' %}`, `{% if user_rol == 'DIRECTOR_VENTAS' %}`, etc.
- **Barra superior:** `templates/base.html` — navbar morada con “Bienvenido, {{ user.get_username }} ({{ user_rol_display }})”. No usa `user_rol`; en todas las páginas está disponible **`user_rol_display`** (mismo valor que el código de rol salvo consultor/invitado).

### Conclusión para la campana
- **Mostrar campana solo a:** Gerente y Director Administrativo.
- **En plantilla:** En `base.html` usar `user_rol_display` (disponible en todas las vistas):
  - `user_rol_display == 'GERENTE'` o `user_rol_display == 'DIRECTOR_ADMINISTRATIVO'`.
- **En API:** En el backend validar rol con `get_user_role(user, request)` y permitir solo `'GERENTE'` y `'DIRECTOR_ADMINISTRATIVO'`.

---

## 2. Cambios concretos

### 2.1 Base de datos
- **Tabla:** `leads_agencia` (ya existe en PostgreSQL).
- **Uso:** Leer leads con `estado_venta = 'caliente'` y `bot_activo = True` (solo los que siguen en “modo bot” y calientes). Al hacer “Tomar control” se actualiza `bot_activo = False`; ese lead deja de listarse en la campana (desaparece de la lista).

### 2.2 API REST (nueva)

| Método | Ruta (propuesta) | Descripción | Permisos |
|--------|-------------------|-------------|----------|
| GET | `/api/leads-calientes/` | Lista leads con `estado_venta='caliente'` y `bot_activo=True`. Campos: `id_usuario`, `nombre_cliente`, `plataforma`, `resumen_viaje`. | GERENTE, DIRECTOR_ADMINISTRATIVO |
| PATCH | `/api/leads-calientes/<id_usuario>/tomar-control/` | Pone `bot_activo=False` para ese lead. | GERENTE, DIRECTOR_ADMINISTRATIVO |

- **Implementación:** Nueva app `api` o rutas bajo `ventas`/`crm`. Recomendación: módulo `ventas` o `crm` con vistas API que lean/escriban la tabla vía SQL o un modelo Django “unmanaged” para `leads_agencia`.
- **Respuesta GET:** JSON con lista de objetos y un campo `count` (número de leads calientes para el badge).
- **Respuesta PATCH:** 200 + JSON `{ "ok": true }` o 404 si no existe el lead.

### 2.3 Frontend (barra superior)

**Archivo:** `templates/base.html`

- **Ubicación:** En la barra morada (`#main-navbar`), a la **izquierda** del ítem “Bienvenido, …” (por ejemplo dentro de `navbar-nav` con `ms-auto` para mantener el usuario a la derecha), solo si `user_rol_display in ('GERENTE', 'DIRECTOR_ADMINISTRATIVO')`:
  - **Icono:** Campana (Font Awesome `fa-bell`).
  - **Badge:** Número de leads calientes (oculto si es 0).
  - **Estado:** Si `count > 0`, campana con estilo “resaltado” (por ejemplo color/animación distinta).
- **Dropdown:** Al hacer clic en la campana, se abre un **dropdown/panel** que muestra:
  - Lista de tarjetas (una por lead).
  - Cada tarjeta: **nombre_cliente**, **icono de plataforma** (WA / IG / FB según `plataforma`), **resumen_viaje**, botón **“Tomar control”**.
  - Al hacer clic en “Tomar control”: llamada PATCH al API, quitar la tarjeta del DOM y actualizar el contador (y el estilo de la campana si llega a 0).

**Estilos:** Usar clases Bootstrap 5 + CSS en `static/css/main.css` (o en un bloque `extra_css` en `base.html`) para la barra morada y el dropdown.

### 2.4 Modelo Django para `leads_agencia` (opcional pero recomendable)
- Crear modelo **unmanaged** en `ventas/models.py` o en una app `leads` que refleje la tabla `leads_agencia` para usar ORM en las vistas API y no escribir SQL a mano. Si la tabla puede variar por migraciones externas, unmanaged evita que Django la gestione.

### 2.5 WebSockets (actualización en tiempo real)
- **Objetivo:** Que al marcar un lead como “caliente” (por n8n u otro proceso), la campana se actualice sin recargar.
- **Opción A:** **Django Channels** + canal “leads-calientes” + Redis como layer; el backend emite un evento cuando cambie un lead (o cuando n8n llame a un endpoint que además notifique por el canal). El frontend abre una conexión WebSocket y actualiza contador y lista.
- **Opción B (más simple):** **Polling** cada X segundos (ej. 15–30 s) al endpoint GET mientras el dropdown esté cerrado o la página visible. No requiere Channels ni Redis.
- **Recomendación:** Fase 1 con polling; Fase 2 añadir Channels si se requiere tiempo real estricto.

---

## 3. Plan de implementación por fases

### Fase 1 — API y campana con polling (sin WebSockets)
1. **Modelo unmanaged** (opcional): Añadir en `ventas` (o app `leads`) un modelo `LeadsAgencia` que refleje la tabla `leads_agencia` con `managed = False`.
2. **Vistas API:**
   - `GET /api/leads-calientes/`: lista leads con `estado_venta='caliente'` y `bot_activo=True`; retorna JSON con `count` y lista de objetos (id_usuario, nombre_cliente, plataforma, resumen_viaje).
   - `PATCH /api/leads-calientes/<id_usuario>/tomar-control/`: comprobar rol GERENTE/DIRECTOR_ADMINISTRATIVO, actualizar `bot_activo=False`, retornar 200/404.
3. **URLs:** Registrar en `agencia_web/urls.py` (o en `ventas/urls.py` y incluir) las rutas bajo `/api/leads-calientes/`.
4. **Navbar en `base.html`:**
   - Condicional por rol: `{% if user_rol_display == 'GERENTE' or user_rol_display == 'DIRECTOR_ADMINISTRATIVO' %}`.
   - Añadir ítem “Campana” con icono, badge de count y dropdown con tarjetas.
   - Cargar datos al abrir el dropdown (GET al API) y cada N segundos (polling) mientras la página esté activa.
   - Botón “Tomar control” por tarjeta: PATCH y luego eliminar tarjeta y actualizar count.
5. **CSRF:** Las peticiones AJAX (fetch/axios) deben enviar el token CSRF en cabecera o en el body según configuración Django.

### Fase 2 — WebSockets (opcional)
1. **Stack:** Instalar y configurar Django Channels, Daphne y Redis (o canal en memoria para desarrollo).
2. **Consumer:** Consumer que acepte conexiones en un grupo “leads_calientes” (o por usuario/rol) y envíe mensajes con `{ "count": N, "leads": [...] }` cuando haya cambios.
3. **Trigger:** Cuando n8n (o un endpoint interno) actualice un lead a caliente o alguien haga “Tomar control”, enviar mensaje al grupo desde la vista/signal para que el consumer notifique a los clientes.
4. **Frontend:** Abrir WebSocket al cargar la página (solo si rol GERENTE/DIRECTOR_ADMINISTRATIVO), escuchar mensajes y actualizar badge y lista; mantener fallback a polling si el WebSocket falla.

### Fase 3 — Ajustes y robustez
- Manejo de errores en el frontend (reintentos, mensaje si el API falla).
- Tests unitarios para las vistas API (permisos por rol y que “tomar control” ponga `bot_activo=False` y el lead deje de aparecer en GET).
- Documentación breve en el repo de cómo probar la campana y el API.

---

## 4. Resumen de archivos a tocar

| Archivo | Acción |
|---------|--------|
| `ventas/models.py` (o nueva app `leads`) | Añadir modelo unmanaged `LeadsAgencia` (opcional). |
| `ventas/views.py` o `ventas/api_leads.py` | Vistas API listado y tomar-control. |
| `ventas/urls.py` o `agencia_web/urls.py` | Rutas `/api/leads-calientes/` y `/api/leads-calientes/<id_usuario>/tomar-control/`. |
| `templates/base.html` | Campana + dropdown + condicional por rol. |
| `static/css/main.css` (o inline en base) | Estilos campana resaltada y tarjetas del dropdown. |
| `static/js/leads-calientes.js` (o bloque en base) | Lógica: GET, PATCH, polling, actualización del DOM. |
| `requirements.txt` (solo Fase 2) | Añadir `channels`, `daphne`, `channels-redis`. |

Con esto se puede implementar la campana de leads calientes solo para Gerente y Director Administrativo, con listado, “Tomar control” y desaparición de la tarjeta, y opción de pasar a WebSockets en una segunda fase.
