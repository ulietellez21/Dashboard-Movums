# usuarios/permissions.py
"""
Capa centralizada de permisos por rol.
Usar en vistas (test_func, get_queryset) y en templates (templatetags).
"""
from django.contrib.auth import get_user_model

User = get_user_model()

# Constantes de roles (evitar strings mágicos)
ROL_JEFE = 'JEFE'
ROL_DIRECTOR_GENERAL = 'DIRECTOR_GENERAL'
ROL_DIRECTOR_ADMINISTRATIVO = 'DIRECTOR_ADMINISTRATIVO'
ROL_DIRECTOR_VENTAS = 'DIRECTOR_VENTAS'
ROL_GERENTE = 'GERENTE'
ROL_CONTADOR = 'CONTADOR'
ROL_VENDEDOR = 'VENDEDOR'

# Constantes para secciones del contador
SECCION_DASHBOARD = 'dashboard'
SECCION_CLIENTES = 'clientes'
SECCION_VENTAS = 'ventas'
SECCION_LOGISTICA_PENDIENTE = 'logistica_pendiente'
SECCION_PAGOS_POR_CONFIRMAR = 'pagos_por_confirmar'

# Secciones permitidas para contador
CONTADOR_SECCIONES_PERMITIDAS = (
    SECCION_DASHBOARD,
    SECCION_CLIENTES,
    SECCION_VENTAS,
    SECCION_LOGISTICA_PENDIENTE,
    SECCION_PAGOS_POR_CONFIRMAR,
)


def get_user_role(user, request=None):
    """
    Devuelve el rol del usuario desde Perfil, o 'INVITADO' si no hay perfil.
    Cachea el rol en request._permissions_cached_role para evitar múltiples accesos a BD.
    """
    if not user or not user.is_authenticated:
        return 'INVITADO'
    
    # Cache por request si está disponible
    if request is not None:
        if hasattr(request, '_permissions_cached_role'):
            return request._permissions_cached_role
    
    try:
        rol = user.perfil.rol or 'INVITADO'
        # Guardar en cache si hay request
        if request is not None:
            request._permissions_cached_role = rol
        return rol
    except Exception:
        rol = 'INVITADO'
        if request is not None:
            request._permissions_cached_role = rol
        return rol


def _is_rol(user, rol, request=None):
    return get_user_role(user, request) == rol


def is_jefe(user, request=None):
    return _is_rol(user, ROL_JEFE, request)


def is_director_general(user, request=None):
    return _is_rol(user, ROL_DIRECTOR_GENERAL, request)


def is_director_administrativo(user, request=None):
    return _is_rol(user, ROL_DIRECTOR_ADMINISTRATIVO, request)


def is_director_ventas(user, request=None):
    return _is_rol(user, ROL_DIRECTOR_VENTAS, request)


def is_gerente(user, request=None):
    return _is_rol(user, ROL_GERENTE, request)


def is_contador(user, request=None):
    return _is_rol(user, ROL_CONTADOR, request)


def is_vendedor(user, request=None):
    return _is_rol(user, ROL_VENDEDOR, request)


def has_full_access(user, request=None):
    """JEFE (rol del desarrollador) y Director General tienen todos los permisos."""
    rol = get_user_role(user, request)
    return rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL)


# ---------- Permisos por módulo / template ----------

def can_manage_roles(user, request=None):
    """Quién puede ver/gestión el template Gestión de Roles."""
    if has_full_access(user, request):
        return True
    return is_director_administrativo(user, request)


def can_manage_suppliers(user, request=None):
    """Quién puede ver el template Proveedores."""
    if has_full_access(user, request):
        return True
    return is_director_administrativo(user, request)


def can_view_financial_report(user, request=None):
    """
    Quién puede ver el template Reporte Financiero.
    Director Administrativo NO lo ve. Contador NO lo ve (solo dashboard, clientes, ventas, logística, autorizaciones).
    Resto de directores, gerente y vendedor sí (vendedor solo verá sus ventas en la vista).
    """
    if has_full_access(user, request):
        return True
    if is_director_administrativo(user, request) or is_contador(user, request):
        return False
    return is_director_ventas(user, request) or is_gerente(user, request) or is_vendedor(user, request)


def can_view_financial_report_global(user, request=None):
    """Quién ve el reporte financiero global (todos los datos). Vendedor ve solo el suyo en la misma vista."""
    if has_full_access(user, request):
        return True
    if is_director_administrativo(user, request):
        return False
    return is_director_ventas(user, request) or is_gerente(user, request) or is_contador(user, request)


def can_edit_km_movums(user, request=None):
    """Quién puede editar en Kilómetros Movums. Vendedores solo consulta."""
    if has_full_access(user, request):
        return True
    if is_vendedor(user, request):
        return False
    return is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request) or is_contador(user, request)


def can_view_km_movums(user, request=None):
    """Quién puede ver el template Kilómetros Movums (consulta o más)."""
    if has_full_access(user, request):
        return True
    if is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request) or is_contador(user, request):
        return True
    return is_vendedor(user, request)


def can_view_logistica_pendiente(user, request=None):
    """Quién puede ver Logística Pendiente."""
    if has_full_access(user, request):
        return True
    return (
        is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request)
        or is_contador(user, request) or is_vendedor(user, request)
    )


def can_view_pagos_por_confirmar(user, request=None):
    """Template de autorizaciones (pagos por confirmar): Contador y roles con acceso total."""
    if has_full_access(user, request):
        return True
    return is_contador(user, request)


def can_view_reporte_comisiones(user, request=None):
    """Quién puede ver Reporte de Comisiones."""
    rol = get_user_role(user, request)
    return rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL, ROL_DIRECTOR_ADMINISTRATIVO,
                   ROL_DIRECTOR_VENTAS, ROL_GERENTE, ROL_CONTADOR, ROL_VENDEDOR)


def can_view_clientes(user, request=None):
    """Quién puede ver el menú/listado Clientes."""
    if has_full_access(user, request):
        return True
    return (
        is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request)
        or is_contador(user, request) or is_vendedor(user, request)
    )


def can_view_ventas(user, request=None):
    """Quién puede ver el menú Ventas (listado filtrado por rol)."""
    return user and user.is_authenticated


def can_view_cotizaciones(user, request=None):
    """Quién puede ver el menú Cotizaciones."""
    return user and user.is_authenticated


# ---------- Contador: solo dashboard, clientes, ventas, logística pendiente, pagos por confirmar ----------

def contador_menu_only(user, request=None):
    """Si es contador, solo debe ver: Dashboard, Clientes, Ventas, Logística pendiente, Pagos por confirmar."""
    return is_contador(user, request)


def contador_can_see_section(user, section, request=None):
    """
    section: usar constantes SECCION_* definidas arriba.
    """
    if not is_contador(user, request):
        return True  # No contador: otras reglas aplican
    return section in CONTADOR_SECCIONES_PERMITIDAS


# ---------- Scope de datos: ventas por rol ----------

def get_ventas_queryset_base(model, user, request=None):
    """
    Devuelve el queryset base de ventas según el rol.
    - JEFE / Director General: todas.
    - Director Admin / Director Ventas / Gerente: todas (gerente se filtra por oficina después).
    - Contador: todas.
    - Vendedor: solo ventas propias.
    """
    rol = get_user_role(user, request)
    if rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL, ROL_DIRECTOR_ADMINISTRATIVO, ROL_DIRECTOR_VENTAS, ROL_CONTADOR):
        return model.objects.all()
    if rol == ROL_GERENTE:
        oficina_id = _get_gerente_oficina_id(user)
        if not oficina_id:
            return model.objects.none()
        return model.objects.filter(vendedor__ejecutivo_asociado__oficina_id=oficina_id)
    if rol == ROL_VENDEDOR:
        return model.objects.filter(vendedor=user)
    return model.objects.none()


def _get_gerente_oficina_id(user):
    """Oficina asignada al gerente (Perfil.oficina)."""
    try:
        oficina = getattr(user.perfil, 'oficina_id', None) or getattr(user.perfil, 'oficina', None)
        if oficina is not None:
            return getattr(oficina, 'pk', oficina)
    except Exception:
        pass
    return None


def can_view_venta(user, venta, request=None):
    """Indica si el usuario puede ver esta venta concreta."""
    rol = get_user_role(user, request)
    if has_full_access(user) or rol in (ROL_DIRECTOR_ADMINISTRATIVO, ROL_DIRECTOR_VENTAS, ROL_CONTADOR):
        return True
    if rol == ROL_VENDEDOR:
        return venta.vendedor_id == user.id
    if rol == ROL_GERENTE:
        oficina_id = _get_gerente_oficina_id(user)
        if not oficina_id or not venta.vendedor_id:
            return False
        try:
            from ventas.models import Ejecutivo
            ej = Ejecutivo.objects.filter(usuario_id=venta.vendedor_id).values_list('oficina_id', flat=True).first()
            return ej == oficina_id
        except Exception:
            return False
    return False


# ---------- Permisos específicos para acciones en ventas ----------

def can_approve_abono_proveedor(user, request=None):
    """Quién puede aprobar abonos a proveedor (CONTADOR y roles con acceso total)."""
    if has_full_access(user, request):
        return True
    return is_contador(user, request)


def can_confirm_abono_proveedor(user, request=None):
    """Quién puede confirmar abonos a proveedor (CONTADOR y roles con acceso total)."""
    if has_full_access(user, request):
        return True
    return is_contador(user, request)


def can_cancel_abono_proveedor(user, request=None):
    """Quién puede cancelar abonos a proveedor (solo roles con acceso total)."""
    return has_full_access(user, request)


def can_solicitar_abono_proveedor(user, request=None):
    """Quién puede solicitar abonos a proveedor."""
    if has_full_access(user, request):
        return True
    return is_vendedor(user, request) or is_contador(user, request)


def can_edit_venta(user, venta=None, request=None):
    """
    Quién puede editar una venta.
    Si venta es None, verifica permisos generales de edición.
    """
    if has_full_access(user, request):
        return True
    if venta is None:
        # Permiso general: vendedores y contadores pueden crear/editar
        return is_vendedor(user, request) or is_contador(user, request)
    # Permiso específico: vendedor solo puede editar sus propias ventas
    if is_vendedor(user, request):
        return venta.vendedor_id == user.id
    return is_contador(user, request) or is_gerente(user, request)


def can_delete_venta(user, venta, request=None):
    """Quién puede eliminar una venta."""
    if has_full_access(user, request):
        return True
    # Vendedor solo puede eliminar sus propias ventas
    if is_vendedor(user, request):
        return venta.vendedor_id == user.id
    return False


def can_edit_campos_bloqueados(user, request=None):
    """Quién puede editar campos bloqueados en ventas (JEFE/Director General y Gerente)."""
    if has_full_access(user, request):
        return True
    return is_gerente(user, request)
