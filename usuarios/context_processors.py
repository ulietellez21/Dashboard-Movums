# usuarios/context_processors.py
"""
Context processors para acceso seguro a Perfil.
Evita error 500 cuando un usuario no tiene Perfil asociado.
"""
from . import permissions


def user_rol_safe(request):
    """Añade user_rol_display al contexto: rol del usuario actual o 'INV' si no hay perfil."""
    if request and request.user.is_authenticated:
        if permissions.is_solo_lectura_ventas(request.user, request):
            return {'user_rol_display': 'Consulta ventas'}
        return {'user_rol_display': permissions.get_user_role(request.user, request)}
    return {'user_rol_display': 'INVITADO'}
