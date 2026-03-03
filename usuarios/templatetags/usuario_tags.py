# usuarios/templatetags/usuario_tags.py
"""
Template tags para acceso seguro a Perfil.
Evita error 500 cuando un usuario no tiene Perfil asociado.
"""
from django import template

register = template.Library()


@register.filter
def rol_safe(user):
    """
    Devuelve el rol del usuario de forma segura.
    Si no tiene Perfil, devuelve cadena vacía (evita RelatedObjectDoesNotExist).
    """
    if not user:
        return ''
    try:
        return (user.perfil.rol or '').upper()
    except Exception:
        return ''


@register.filter
def tiene_perfil(user):
    """
    Devuelve True si el usuario tiene Perfil asociado, False en caso contrario.
    Útil para {% if user|tiene_perfil %} sin causar excepción.
    """
    if not user:
        return False
    try:
        return bool(user.perfil)
    except Exception:
        return False
