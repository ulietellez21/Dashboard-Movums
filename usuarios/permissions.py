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


def get_user_role(user):
    """Devuelve el rol del usuario desde Perfil, o 'INVITADO' si no hay perfil."""
    if not user or not user.is_authenticated:
        return 'INVITADO'
    try:
        return user.perfil.rol or 'INVITADO'
    except Exception:
        return 'INVITADO'


def _is_rol(user, rol):
    return get_user_role(user) == rol


def is_jefe(user):
    return _is_rol(user, ROL_JEFE)


def is_director_general(user):
    return _is_rol(user, ROL_DIRECTOR_GENERAL)


def is_director_administrativo(user):
    return _is_rol(user, ROL_DIRECTOR_ADMINISTRATIVO)


def is_director_ventas(user):
    return _is_rol(user, ROL_DIRECTOR_VENTAS)


def is_gerente(user):
    return _is_rol(user, ROL_GERENTE)


def is_contador(user):
    return _is_rol(user, ROL_CONTADOR)


def is_vendedor(user):
    return _is_rol(user, ROL_VENDEDOR)


def has_full_access(user):
    """Director General y JEFE tienen todos los permisos."""
    rol = get_user_role(user)
    return rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL)


# ---------- Permisos por módulo / template ----------

def can_manage_roles(user):
    """Quién puede ver/gestión el template Gestión de Roles."""
    if has_full_access(user):
        return True
    return is_director_administrativo(user)


def can_manage_suppliers(user):
    """Quién puede ver el template Proveedores."""
    if has_full_access(user):
        return True
    return is_director_administrativo(user)


def can_view_financial_report(user):
    """
    Quién puede ver el template Reporte Financiero.
    Director Administrativo NO lo ve. Resto de directores, gerente, contador y vendedor sí
    (vendedor solo verá sus ventas en la vista).
    """
    if has_full_access(user):
        return True
    if is_director_administrativo(user):
        return False
    return is_director_ventas(user) or is_gerente(user) or is_contador(user) or is_vendedor(user)


def can_view_financial_report_global(user):
    """Quién ve el reporte financiero global (todos los datos). Vendedor ve solo el suyo en la misma vista."""
    if has_full_access(user):
        return True
    if is_director_administrativo(user):
        return False
    return is_director_ventas(user) or is_gerente(user) or is_contador(user)


def can_edit_km_movums(user):
    """Quién puede editar en Kilómetros Movums. Vendedores solo consulta."""
    if has_full_access(user):
        return True
    if is_vendedor(user):
        return False
    return is_director_administrativo(user) or is_director_ventas(user) or is_gerente(user) or is_contador(user)


def can_view_km_movums(user):
    """Quién puede ver el template Kilómetros Movums (consulta o más)."""
    if has_full_access(user):
        return True
    if is_director_administrativo(user) or is_director_ventas(user) or is_gerente(user) or is_contador(user):
        return True
    return is_vendedor(user)


def can_view_logistica_pendiente(user):
    """Quién puede ver Logística Pendiente."""
    if has_full_access(user):
        return True
    return (
        is_director_administrativo(user) or is_director_ventas(user) or is_gerente(user)
        or is_contador(user) or is_vendedor(user)
    )


def can_view_pagos_por_confirmar(user):
    """Template de autorizaciones (pagos por confirmar): Contador y roles con acceso total."""
    if has_full_access(user):
        return True
    return is_contador(user)


def can_view_reporte_comisiones(user):
    """Quién puede ver Reporte de Comisiones."""
    rol = get_user_role(user)
    return rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL, ROL_DIRECTOR_ADMINISTRATIVO,
                   ROL_DIRECTOR_VENTAS, ROL_GERENTE, ROL_CONTADOR, ROL_VENDEDOR)


def can_view_clientes(user):
    """Quién puede ver el menú/listado Clientes."""
    if has_full_access(user):
        return True
    return (
        is_director_administrativo(user) or is_director_ventas(user) or is_gerente(user)
        or is_contador(user) or is_vendedor(user)
    )


def can_view_ventas(user):
    """Quién puede ver el menú Ventas (listado filtrado por rol)."""
    return user and user.is_authenticated


def can_view_cotizaciones(user):
    """Quién puede ver el menú Cotizaciones."""
    return user and user.is_authenticated


# ---------- Contador: solo dashboard, clientes, ventas, logística pendiente, pagos por confirmar ----------

def contador_menu_only(user):
    """Si es contador, solo debe ver: Dashboard, Clientes, Ventas, Logística pendiente, Pagos por confirmar."""
    return is_contador(user)


def contador_can_see_section(user, section):
    """
    section: 'dashboard' | 'clientes' | 'ventas' | 'logistica_pendiente' | 'pagos_por_confirmar'
    """
    if not is_contador(user):
        return True  # No contador: otras reglas aplican
    return section in ('dashboard', 'clientes', 'ventas', 'logistica_pendiente', 'pagos_por_confirmar')


# ---------- Scope de datos: ventas por rol ----------

def get_ventas_queryset_base(model, user):
    """
    Devuelve el queryset base de ventas según el rol.
    - JEFE / Director General: todas.
    - Director Admin / Director Ventas / Gerente: todas (gerente se filtra por oficina después).
    - Contador: todas.
    - Vendedor: solo ventas propias.
    """
    from django.db.models import Q
    rol = get_user_role(user)
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


def can_view_venta(user, venta):
    """Indica si el usuario puede ver esta venta concreta."""
    rol = get_user_role(user)
    if rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL, ROL_DIRECTOR_ADMINISTRATIVO, ROL_DIRECTOR_VENTAS, ROL_CONTADOR):
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
