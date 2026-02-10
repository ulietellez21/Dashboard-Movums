# usuarios/templatetags/permisos_tags.py
"""
Template tags para mostrar/ocultar elementos según permisos por rol.
Uso: {% load permisos_tags %} ... {% if user|can_manage_roles %} ...
"""
from django import template
from django.contrib.auth import get_user_model
from usuarios import permissions as perm

User = get_user_model()
register = template.Library()


@register.filter
def can_manage_roles(user):
    return user and user.is_authenticated and perm.can_manage_roles(user)


@register.filter
def can_manage_suppliers(user):
    return user and user.is_authenticated and perm.can_manage_suppliers(user)


@register.filter
def can_view_financial_report(user):
    return user and user.is_authenticated and perm.can_view_financial_report(user)


@register.filter
def can_edit_km_movums(user):
    return user and user.is_authenticated and perm.can_edit_km_movums(user)


@register.filter
def can_view_km_movums(user):
    return user and user.is_authenticated and perm.can_view_km_movums(user)


@register.filter
def can_view_logistica_pendiente(user):
    return user and user.is_authenticated and perm.can_view_logistica_pendiente(user)


@register.filter
def can_view_pagos_por_confirmar(user):
    return user and user.is_authenticated and perm.can_view_pagos_por_confirmar(user)


@register.filter
def can_view_reporte_comisiones(user):
    return user and user.is_authenticated and perm.can_view_reporte_comisiones(user)


@register.filter
def can_view_clientes(user):
    return user and user.is_authenticated and perm.can_view_clientes(user)


@register.filter
def can_view_ventas(user):
    return user and user.is_authenticated and perm.can_view_ventas(user)


@register.filter
def can_view_cotizaciones(user):
    return user and user.is_authenticated and perm.can_view_cotizaciones(user)


@register.filter
def contador_can_see_dashboard(user):
    return not perm.contador_menu_only(user) or perm.contador_can_see_section(user, perm.SECCION_DASHBOARD)


@register.filter
def contador_can_see_clientes(user):
    return not perm.contador_menu_only(user) or perm.contador_can_see_section(user, perm.SECCION_CLIENTES)


@register.filter
def contador_can_see_ventas(user):
    return not perm.contador_menu_only(user) or perm.contador_can_see_section(user, perm.SECCION_VENTAS)


@register.filter
def contador_can_see_logistica(user):
    return not perm.contador_menu_only(user) or perm.contador_can_see_section(user, perm.SECCION_LOGISTICA_PENDIENTE)


@register.filter
def contador_can_see_pagos_por_confirmar(user):
    return not perm.contador_menu_only(user) or perm.contador_can_see_section(user, perm.SECCION_PAGOS_POR_CONFIRMAR)


@register.filter
def contador_can_see_reportefinanciero(user):
    """Contador NO ve Reporte Financiero (solo dashboard, clientes, ventas, logística, autorizaciones)."""
    return not perm.contador_menu_only(user)


@register.filter
def contador_can_see_km_movums(user):
    return not perm.contador_menu_only(user)


@register.filter
def contador_can_see_comisiones(user):
    return not perm.contador_menu_only(user)


@register.filter
def contador_can_see_cotizaciones(user):
    """Contador no ve Cotizaciones en el menú (solo dashboard, clientes, ventas, logística, autorizaciones)."""
    return not perm.contador_menu_only(user) or perm.contador_can_see_section(user, perm.SECCION_VENTAS)  # Cotizaciones no está en secciones permitidas
