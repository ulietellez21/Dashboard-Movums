# Estado de los permisos y análisis de mejoras

**Fecha:** 10 feb 2026

---

## 1. Estructura actual

### 1.1 Capas

| Capa | Ubicación | Uso |
|------|------------|-----|
| **Lógica central** | `usuarios/permissions.py` | Constantes de roles, `get_user_role()`, `can_*()`, `get_ventas_queryset_base()`, `can_view_venta()` |
| **Mixins para vistas** | `usuarios/mixins.py` | `ManageRolesRequiredMixin`, `ManageSuppliersRequiredMixin`, `FinancialReportRequiredMixin`, `KmMovumsEditRequiredMixin`, `VentaPermissionMixin` |
| **Templates** | `usuarios/templatetags/permisos_tags.py` | Filtros `user\|can_manage_roles`, `user\|contador_can_see_*`, etc. |
| **Vistas** | `ventas/views.py`, `crm/views.py` | Uso de `perm.*` en `test_func`, `get_queryset` y en lógica de contexto |

### 1.2 Reglas por rol (resumen)

- **Director General / JEFE:** acceso total (`has_full_access`).
- **Director Administrativo:** todo excepto Reporte Financiero.
- **Director de Ventas:** todo excepto Proveedores y Gestión de Roles.
- **Gerente:** todo excepto Proveedores y Gestión de Roles; datos filtrados por oficina (`Perfil.oficina`).
- **Vendedor (M/C/I):** sin Proveedores ni Gestión de Roles; reporte financiero solo sus ventas; Kilómetros solo consulta; ventas solo propias.
- **Contador:** solo Dashboard, Clientes, Ventas, Logística pendiente, Pagos por confirmar (menú); en backend aún puede entrar al Reporte Financiero por URL.

---

## 2. Problemas e inconsistencias

### 2.1 Crítico: Contador y Reporte Financiero

- **Qué pasa:** `can_view_financial_report(user)` devuelve `True` para contador (línea 95 en `permissions.py`).
- **Efecto:** El menú oculta “Reporte Financiero” al contador, pero si escribe la URL `/ventas/reporte-financiero/` puede ver la vista.
- **Recomendación:** Excluir al contador en `can_view_financial_report()` para que la vista también le deniegue el acceso (alineado con “contador solo dashboard, clientes, ventas, logística, autorizaciones”).

### 2.2 Crítico: Director General no equiparado a JEFE en muchas vistas

- En `ventas/views.py` hay muchas comprobaciones del tipo `user_rol == 'JEFE'` sin incluir Director General (p. ej. líneas 227, 239, 599, 697–699, 746, 755, 762, 770, 1111, 1285, 1291, 1571, 2094, 2098, 2338, 2345, 2409, 2457, 2511, 2522, 2606, 2710).
- **Efecto:** Un usuario con rol Director General puede quedar sin permiso en esas acciones que solo miran `JEFE`.
- **Recomendación:** Sustituir `user_rol == 'JEFE'` por `perm.has_full_access(user)` (o por un helper tipo `can_approve_abono_proveedor(user)` que use `has_full_access` + contador donde aplique) en todas esas ramas.

### 2.3 Username hardcodeado

- Siguen apareciendo `user.username == 'daviddiaz'` (y en un caso `antonio_balderas`) para desbloqueo de campos o permisos especiales (p. ej. líneas 239, 770, 972, 1370, 2409, 2457).
- **Riesgo:** Frágil ante cambios de usuario o entornos.
- **Recomendación:** Eliminar estos checks y usar solo roles/permisos (p. ej. `perm.has_full_access(user)` o un permiso explícito “puede_editar_campos_bloqueados”) o un grupo/flag en Perfil si se necesita un “supervisor” distinto de JEFE/Director General.

### 2.4 Obtención del rol duplicada e inconsistente

- En `ventas/views.py` se usa en muchos sitios `request.user.perfil.rol if hasattr(request.user, 'perfil') else 'INVITADO'` en lugar de `get_user_role(user)` o `perm.get_user_role(user)`.
- `DashboardView` tiene su propio `get_user_role(self, user)` que lee `user.perfil.rol` en lugar de delegar en `perm.get_user_role`.
- **Recomendación:** Unificar todo en `perm.get_user_role(user)` (y quitar el `get_user_role` local de `ventas/views.py` si solo delega en `perm`) para una sola fuente de verdad y mismo manejo cuando no hay perfil.

### 2.5 Mixins no usados en ventas

- En `usuarios/mixins.py` están definidos `ManageRolesRequiredMixin`, `ManageSuppliersRequiredMixin`, `FinancialReportRequiredMixin`, etc., pero en `ventas/views.py` las vistas usan `UserPassesTestMixin` + `perm.can_manage_roles(...)` (y similares) con `handle_no_permission` repetido.
- **Recomendación:** Usar los mixins de `usuarios.mixins` en las vistas correspondientes (Gestión de Roles, Proveedores, Reporte Financiero, etc.) para menos duplicación y mensajes de error unificados.

---

## 3. Mejoras de optimización

### 3.1 Cache del rol por request

- `get_user_role(user)` y los `is_*` tocan `user.perfil` varias veces por request; en listados o vistas pesadas puede haber muchas llamadas.
- **Recomendación:** Cachear el rol en el request la primera vez, por ejemplo `request._permissions_cached_role = get_user_role(request.user)` y usar ese valor en el mismo request (o un helper `get_user_role_cached(request)` que rellene y use ese atributo).

### 3.2 Queries en `can_view_venta` (Gerente)

- Para cada venta que se comprueba, si el usuario es Gerente se hace `Ejecutivo.objects.filter(usuario_id=venta.vendedor_id).values_list('oficina_id', flat=True).first()`.
- En listados o comprobaciones masivas esto puede ser N consultas.
- **Recomendación:** En listados, no llamar `can_view_venta` por fila; el queryset ya está filtrado con `get_ventas_queryset_base`. En detalle/una sola venta está bien. Si en el futuro se usa `can_view_venta` en bucles, considerar prefetch de `vendedor__ejecutivo_asociado__oficina_id` o anotar oficina en el queryset y comparar en Python.

### 3.3 Constantes para secciones del contador

- `contador_can_see_section(user, section)` usa strings (`'dashboard'`, `'clientes'`, `'ventas'`, etc.).
- **Recomendación:** Definir constantes en `permissions.py` (p. ej. `SECCION_DASHBOARD = 'dashboard'`, …) y usar esas constantes en `contador_can_see_section` y en los templatetags para evitar typos y tener un solo lugar de definición.

### 3.4 Código muerto en `permissions.py`

- En `get_ventas_queryset_base` se hace `from django.db.models import Q` y no se usa.
- **Recomendación:** Quitar el import de `Q`.

---

## 4. Resumen de acciones sugeridas

| Prioridad | Acción |
|-----------|--------|
| Alta | Excluir contador de `can_view_financial_report()` para que no pueda abrir la URL del reporte. |
| Alta | Sustituir todas las comprobaciones `user_rol == 'JEFE'` (y equivalentes) por `perm.has_full_access(user)` donde corresponda (abonos proveedor, edición venta, etc.). |
| Media | Eliminar checks por `username == 'daviddiaz'` (y similares) y reemplazar por permisos por rol. |
| Media | Unificar obtención del rol: usar solo `perm.get_user_role(user)` en vistas y quitar duplicados. |
| Media | Usar mixins de `usuarios.mixins` en las vistas de Gestión de Roles, Proveedores, Reporte Financiero, etc. |
| Baja | Cachear rol por request para reducir accesos a `user.perfil`. |
| Baja | Constantes para secciones del contador y quitar import no usado de `Q`. |

---

## 5. Estado por archivo (resumen)

- **usuarios/permissions.py:** Lógica clara y centralizada; solo ajustar contador en reporte financiero, quitar `Q` y (opcional) constantes de sección.
- **usuarios/mixins.py:** Bien definidos; falta usarlos en ventas en lugar de repetir `UserPassesTestMixin` + `perm.*`.
- **usuarios/templatetags/permisos_tags.py:** Coherente con `permissions.py`; si se cambia `can_view_financial_report` para contador, el menú y la vista quedarán alineados.
- **ventas/views.py:** Muchos puntos donde unificar con `perm.has_full_access` / `perm.get_user_role` y eliminar username hardcodeado; buena candidata para usar mixins.
- **crm/views.py:** Ya usa `perm` de forma consistente para Kilómetros.
- **templates/base.html:** Menú condicionado por permisos; correcto una vez `can_view_financial_report` excluya al contador.

Si quieres, el siguiente paso puede ser implementar solo los cambios de prioridad alta (contador + `has_full_access` en ventas) y dejar el resto para una segunda pasada.
