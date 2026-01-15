"""
Señales de Django para capturar automáticamente eventos importantes
y registrarlos en el historial de auditoría.
"""
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth.models import User

from .services import AuditoriaService
from ventas.models import VentaViaje, AbonoPago, Cotizacion, Proveedor, Ejecutivo, Logistica, ConfirmacionVenta
from crm.models import Cliente


# ==================== VENTAS ====================

@receiver(post_save, sender=VentaViaje)
def registrar_venta_guardada(sender, instance, created, **kwargs):
    """Registra cuando se crea o edita una venta."""
    # Obtener el usuario del request si está disponible
    # Nota: En señales, necesitamos obtener el usuario de otra forma
    # Por ahora, usamos el vendedor de la venta
    usuario = instance.vendedor
    
    if created:
        # Nueva venta creada
        AuditoriaService.registrar_venta_creada(
            venta=instance,
            usuario=usuario
        )
    else:
        # Venta editada - detectar cambios importantes
        # Nota: Para detectar cambios específicos, necesitaríamos usar pre_save
        # Por ahora, solo registramos que se editó
        AuditoriaService.registrar_venta_editada(
            venta=instance,
            usuario=usuario
        )


@receiver(post_save, sender=AbonoPago)
def registrar_abono_guardado(sender, instance, created, **kwargs):
    """Registra cuando se crea o confirma un abono."""
    usuario = instance.registrado_por
    
    if created:
        AuditoriaService.registrar_abono_registrado(
            abono=instance,
            usuario=usuario
        )
    elif instance.confirmado and instance.confirmado_por:
        # Abono confirmado
        AuditoriaService.registrar_abono_confirmado(
            abono=instance,
            usuario_confirmador=instance.confirmado_por
        )


@receiver(post_save, sender=Cotizacion)
def registrar_cotizacion_guardada(sender, instance, created, **kwargs):
    """Registra cuando se crea o edita una cotización."""
    # Intentar obtener el usuario del request
    # Por ahora, usamos None si no está disponible
    usuario = None
    
    if created:
        AuditoriaService.registrar_cotizacion_creada(
            cotizacion=instance,
            usuario=usuario
        )


# ==================== CLIENTES ====================

@receiver(post_save, sender=Cliente)
def registrar_cliente_guardado(sender, instance, created, **kwargs):
    """Registra cuando se crea o edita un cliente."""
    usuario = None  # En señales, es difícil obtener el usuario del request
    
    if created:
        AuditoriaService.registrar_cliente_creado(
            cliente=instance,
            usuario=usuario
        )


# ==================== USUARIOS ====================

@receiver(post_save, sender=User)
def registrar_usuario_guardado(sender, instance, created, **kwargs):
    """Registra cuando se crea un usuario."""
    if created:
        # Intentar obtener quién creó el usuario
        # Por ahora, usamos None
        usuario_creador = None
        AuditoriaService.registrar_usuario_creado(
            usuario_creado=instance,
            usuario_creador=usuario_creador
        )


# ==================== FUNCIONES AUXILIARES ====================

def get_client_ip(request):
    """Obtiene la dirección IP del cliente desde el request."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ==================== LOGIN/LOGOUT ====================

@receiver(user_logged_in)
def registrar_login(sender, request, user, **kwargs):
    """Registra cuando un usuario inicia sesión."""
    ip_address = get_client_ip(request)
    AuditoriaService.registrar_login(
        usuario=user,
        ip_address=ip_address
    )


@receiver(user_logged_out)
def registrar_logout(sender, request, user, **kwargs):
    """Registra cuando un usuario cierra sesión."""
    ip_address = get_client_ip(request)
    AuditoriaService.registrar_logout(
        usuario=user,
        ip_address=ip_address
    )


# ==================== PROVEEDORES ====================

@receiver(post_save, sender=Proveedor)
def registrar_proveedor_guardado(sender, instance, created, **kwargs):
    """Registra cuando se crea o edita un proveedor."""
    usuario = None  # En señales, es difícil obtener el usuario del request
    
    if created:
        AuditoriaService.registrar_proveedor_creado(
            proveedor=instance,
            usuario=usuario
        )
    else:
        AuditoriaService.registrar_proveedor_editado(
            proveedor=instance,
            usuario=usuario
        )


@receiver(post_delete, sender=Proveedor)
def registrar_proveedor_eliminado(sender, instance, **kwargs):
    """Registra cuando se elimina un proveedor."""
    usuario = None
    AuditoriaService.registrar_proveedor_eliminado(
        proveedor=instance,
        usuario=usuario
    )


# ==================== EJECUTIVOS ====================

@receiver(post_save, sender=Ejecutivo)
def registrar_ejecutivo_guardado(sender, instance, created, **kwargs):
    """Registra cuando se crea o edita un ejecutivo."""
    usuario = None
    
    if created:
        AuditoriaService.registrar_ejecutivo_creado(
            ejecutivo=instance,
            usuario=usuario
        )
    else:
        AuditoriaService.registrar_ejecutivo_editado(
            ejecutivo=instance,
            usuario=usuario
        )


@receiver(post_delete, sender=Ejecutivo)
def registrar_ejecutivo_eliminado(sender, instance, **kwargs):
    """Registra cuando se elimina un ejecutivo."""
    usuario = None
    AuditoriaService.registrar_ejecutivo_eliminado(
        ejecutivo=instance,
        usuario=usuario
    )


# ==================== LOGÍSTICA ====================

@receiver(post_save, sender=Logistica)
def registrar_logistica_guardada(sender, instance, created, **kwargs):
    """Registra cuando se actualiza la logística."""
    if not created:  # Solo registrar actualizaciones, no la creación inicial
        usuario = None
        AuditoriaService.registrar_logistica_actualizada(
            logistica=instance,
            usuario=usuario
        )


# ==================== CONFIRMACIONES ====================

@receiver(post_save, sender=ConfirmacionVenta)
def registrar_confirmacion_guardada(sender, instance, created, **kwargs):
    """Registra cuando se sube una confirmación."""
    if created:
        usuario = instance.subido_por
        ip_address = None  # No disponible en signals
        AuditoriaService.registrar_confirmacion_subida(
            confirmacion=instance,
            usuario=usuario,
            ip_address=ip_address
        )


@receiver(post_delete, sender=ConfirmacionVenta)
def registrar_confirmacion_eliminada(sender, instance, **kwargs):
    """Registra cuando se elimina una confirmación."""
    usuario = instance.subido_por if hasattr(instance, 'subido_por') else None
    AuditoriaService.registrar_confirmacion_eliminada(
        confirmacion=instance,
        usuario=usuario
    )










