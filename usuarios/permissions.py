# usuarios/permissions.py
"""
Capa centralizada de permisos por rol.
Usar en vistas (test_func, get_queryset) y en templates (templatetags).
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

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


def is_solo_lectura_ventas(user, request=None):
    """
    Usuario consultor: solo ve ventas (listado/detalle) y calendario en dashboard, sin modificar nada.
    No es un rol; es un flag en Perfil (solo_lectura_ventas).
    """
    if not user or not user.is_authenticated:
        return False
    try:
        return getattr(user.perfil, 'solo_lectura_ventas', False)
    except Exception:
        return False


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
    """Quién puede ver/gestión el template Gestión de Roles. Consultor solo lectura no."""
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    return is_director_administrativo(user, request)


def can_manage_suppliers(user, request=None):
    """Quién puede ver el template Proveedores. Consultor solo lectura no."""
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    return is_director_administrativo(user, request)


def can_view_financial_report(user, request=None):
    """Consultor solo lectura no ve reporte financiero."""
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    if is_director_administrativo(user, request) or is_contador(user, request):
        return False
    return is_director_ventas(user, request) or is_gerente(user, request) or is_vendedor(user, request)


def can_view_financial_report_global(user, request=None):
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    if is_director_administrativo(user, request):
        return False
    return is_director_ventas(user, request) or is_gerente(user, request) or is_contador(user, request)


def can_edit_km_movums(user, request=None):
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    if is_vendedor(user, request):
        return False
    return is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request) or is_contador(user, request)


def can_view_km_movums(user, request=None):
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    if is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request) or is_contador(user, request):
        return True
    return is_vendedor(user, request)


def can_view_logistica_pendiente(user, request=None):
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    return (
        is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request)
        or is_contador(user, request) or is_vendedor(user, request)
    )


def can_view_pagos_por_confirmar(user, request=None):
    if is_solo_lectura_ventas(user, request):
        return False
    return is_contador(user, request)


def can_view_reporte_comisiones(user, request=None):
    if is_solo_lectura_ventas(user, request):
        return False
    rol = get_user_role(user, request)
    return rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL, ROL_DIRECTOR_ADMINISTRATIVO,
                   ROL_DIRECTOR_VENTAS, ROL_GERENTE, ROL_CONTADOR, ROL_VENDEDOR)


def can_view_clientes(user, request=None):
    """Quién puede ver el menú/listado Clientes. Consultor solo lectura no ve clientes."""
    if not user or not user.is_authenticated:
        return False
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    return (
        is_director_administrativo(user, request) or is_director_ventas(user, request) or is_gerente(user, request)
        or is_contador(user, request) or is_vendedor(user, request)
    )


def can_view_ventas(user, request=None):
    """Quién puede ver el menú Ventas (listado filtrado por rol). Incluye consultor solo lectura."""
    if not user or not user.is_authenticated:
        return False
    if is_solo_lectura_ventas(user, request):
        return True
    return True


def can_view_cotizaciones(user, request=None):
    """Quién puede ver el menú Cotizaciones. Consultor solo lectura no ve cotizaciones."""
    if not user or not user.is_authenticated:
        return False
    if is_solo_lectura_ventas(user, request):
        return False
    return True


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

def get_ventas_queryset_base(model, user, request=None, optimize=False):
    """
    Devuelve el queryset base de ventas según el rol.
    - Consultor solo lectura: todas (solo lectura).
    - JEFE / Director General: todas.
    - Director Admin / Director Ventas / Gerente: todas (gerente se filtra por oficina después).
    - Contador: todas.
    - Vendedor: solo ventas propias.
    """
    if is_solo_lectura_ventas(user, request):
        qs = model.objects.all()
    else:
        rol = get_user_role(user, request)
        if rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL, ROL_DIRECTOR_ADMINISTRATIVO, ROL_DIRECTOR_VENTAS, ROL_CONTADOR):
            qs = model.objects.all()
        elif rol == ROL_GERENTE:
            oficina_id = _get_gerente_oficina_id(user)
            if not oficina_id:
                return model.objects.none()
            qs = model.objects.filter(vendedor__ejecutivo_asociado__oficina_id=oficina_id)
        elif rol == ROL_VENDEDOR:
            qs = model.objects.filter(vendedor=user)
        else:
            return model.objects.none()
    
    # OPTIMIZACIÓN N+1: Aplicar select_related y prefetch básico si se solicita
    if optimize:
        qs = qs.select_related('cliente', 'vendedor', 'proveedor')
    
    return qs


def _get_gerente_oficina_id(user):
    """Oficina asignada al gerente (Perfil.oficina)."""
    try:
        oficina = getattr(user.perfil, 'oficina_id', None) or getattr(user.perfil, 'oficina', None)
        if oficina is not None:
            return getattr(oficina, 'pk', oficina)
    except Exception:
        pass
    return None


def get_cotizaciones_queryset_base(model, user, request=None):
    """
    Devuelve el queryset base de cotizaciones según el rol.
    - Vendedor: solo sus propias cotizaciones.
    - Resto de roles: todas las cotizaciones.
    """
    if not user or not user.is_authenticated:
        return model.objects.none()
    if is_vendedor(user, request):
        return model.objects.filter(vendedor=user)
    return model.objects.all()


def can_view_cotizacion(user, cotizacion, request=None):
    """Indica si el usuario puede ver esta cotización (vendedor solo las propias)."""
    if not user or not user.is_authenticated:
        return False
    if is_vendedor(user, request):
        return cotizacion.vendedor_id == user.pk
    return True


def is_director_o_superior(user, request=None):
    """
    Director (Ventas, Administrativo, General), Jefe o Director General.
    Pueden adjudicar cotizaciones sin restricción de tiempo ni de "una sola vez".
    """
    rol = get_user_role(user, request)
    return rol in (ROL_JEFE, ROL_DIRECTOR_GENERAL, ROL_DIRECTOR_VENTAS, ROL_DIRECTOR_ADMINISTRATIVO)


def can_adjudicate_cotizacion(user, cotizacion, request=None):
    """
    True si el usuario puede adjudicar o cambiar el vendedor de la cotización.
    - Director o superior: siempre.
    - Resto: solo si la cotización no ha sido adjudicada antes y tiene menos de 1 día de creada.
    """
    if not user or not user.is_authenticated:
        return False
    if is_director_o_superior(user, request):
        return True
    if getattr(cotizacion, 'vendedor_adjudicado_en', None) is not None:
        return False
    creada = getattr(cotizacion, 'creada_en', None)
    if not creada:
        return True
    return timezone.now() - creada <= timedelta(days=1)


def get_queryset_vendedores_adjudicables(user, request=None):
    """
    Queryset de usuarios a los que se puede adjudicar una cotización.
    Incluye asesores de campo definidos en Perfil.tipo_vendedor O en Ejecutivo.tipo_vendedor
    (Gestión de Roles usa Ejecutivo; así aparece quien sea "Asesor de Campo" en cualquiera de los dos).
    """
    return User.objects.filter(
        perfil__rol=ROL_VENDEDOR,
        is_active=True
    ).filter(
        Q(perfil__tipo_vendedor='CAMPO') | Q(ejecutivo_asociado__tipo_vendedor='CAMPO')
    ).order_by('first_name', 'last_name', 'username').distinct()


def can_view_venta(user, venta, request=None):
    """Indica si el usuario puede ver esta venta concreta. Consultor solo lectura puede ver todas."""
    if is_solo_lectura_ventas(user, request):
        return True
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
    Consultor solo lectura no puede editar.
    """
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    if venta is None:
        return is_vendedor(user, request) or is_contador(user, request)
    if is_vendedor(user, request):
        return venta.vendedor_id == user.id
    return is_contador(user, request) or is_gerente(user, request)


def can_delete_venta(user, venta, request=None):
    """Quién puede eliminar una venta. Consultor solo lectura no puede."""
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):
        return True
    if is_vendedor(user, request):
        return venta.vendedor_id == user.id
    return False


def can_edit_campos_bloqueados(user, request=None):
    """Quién puede editar campos bloqueados en ventas (JEFE/Director General y Gerente)."""
    if has_full_access(user, request):
        return True
    return is_gerente(user, request)


def can_edit_datos_viaje(user, request=None):
    """
    Quién puede ver/usar el botón "Editar datos del viaje" en el detalle de venta.
    Consultor solo lectura no puede.
    """
    if is_solo_lectura_ventas(user, request):
        return False
    if has_full_access(user, request):  # JEFE, Director General
        return True
    rol = get_user_role(user, request)
    return rol in (
        ROL_GERENTE,
        ROL_DIRECTOR_ADMINISTRATIVO,
        ROL_DIRECTOR_VENTAS,
    )


def can_approve_reject_cancelacion(user, request=None):
    """Consultor solo lectura no puede aprobar/rechazar cancelaciones."""
    if is_solo_lectura_ventas(user, request):
        return False
    rol = get_user_role(user, request)
    return rol in (
        ROL_JEFE,
        ROL_DIRECTOR_GENERAL,
        ROL_DIRECTOR_ADMINISTRATIVO,
    )


def can_edit_logistica_campos_restringidos(user, request=None):
    """Consultor solo lectura no puede editar logística."""
    if is_solo_lectura_ventas(user, request):
        return False
    rol = get_user_role(user, request)
    return rol in (
        ROL_JEFE,
        ROL_DIRECTOR_GENERAL,
        ROL_DIRECTOR_ADMINISTRATIVO,
    )
