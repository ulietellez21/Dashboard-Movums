"""
Señales de Django para crear notificaciones automáticamente
cuando ocurren eventos importantes en el sistema.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from .models import AbonoPago, VentaViaje, Logistica, Notificacion


def obtener_usuarios_jefe():
    """Obtiene todos los usuarios con rol JEFE."""
    try:
        return User.objects.filter(perfil__rol='JEFE')
    except Exception:
        return User.objects.none()


@receiver(post_save, sender=AbonoPago)
def notificar_abono_registrado(sender, instance, created, **kwargs):
    """
    Crea una notificación cuando se registra un nuevo abono.
    IMPORTANTE: Solo para abonos en efectivo. Para transferencia/tarjeta, 
    las notificaciones se crean manualmente en la vista como PAGO_PENDIENTE.
    """
    if created:
        # Solo crear notificación tipo ABONO para abonos en efectivo
        # Para transferencia/tarjeta, las notificaciones se manejan en la vista
        if instance.forma_pago == 'EFE':
            usuarios_jefe = obtener_usuarios_jefe()
            mensaje = f"Se registró un abono de ${instance.monto} (Efectivo) para la Venta #{instance.venta.pk} - Cliente: {instance.venta.cliente.nombre_completo_display}"
            
            for jefe in usuarios_jefe:
                # Solo crear si no existe ya una notificación PAGO_PENDIENTE para este abono
                existe_pendiente = Notificacion.objects.filter(
                    usuario=jefe,
                    venta=instance.venta,
                    abono=instance,
                    tipo='PAGO_PENDIENTE'
                ).exists()
                
                if not existe_pendiente:
                    Notificacion.objects.create(
                        usuario=jefe,
                        tipo='ABONO',
                        mensaje=mensaje,
                        venta=instance.venta,
                        abono=instance
                    )


@receiver(post_save, sender=VentaViaje)
def notificar_cambios_venta(sender, instance, created, **kwargs):
    """Crea notificaciones para cambios importantes en ventas."""
    usuarios_jefe = obtener_usuarios_jefe()
    
    if not usuarios_jefe.exists():
        return
    
    # Detectar si se registró una apertura (cantidad_apertura > 0)
    if created and instance.cantidad_apertura and instance.cantidad_apertura > 0:
        mensaje = f"Se registró una apertura de ${instance.cantidad_apertura} para la Venta #{instance.pk} - Cliente: {instance.cliente.nombre_completo_display}"
        for jefe in usuarios_jefe:
            Notificacion.objects.create(
                usuario=jefe,
                tipo='APERTURA',
                mensaje=mensaje,
                venta=instance
            )
    
    # Detectar liquidación (cuando total_pagado >= costo_venta_final)
    if not created:  # Solo para actualizaciones
        try:
            # Verificar si la venta está liquidada
            if instance.total_pagado >= instance.costo_venta_final:
                # Verificar si ya existe una notificación de liquidación para esta venta
                # IMPORTANTE: No filtrar por vista=False para evitar duplicados cuando se marca como vista
                existe_notificacion = Notificacion.objects.filter(
                    venta=instance,
                    tipo='LIQUIDACION'
                ).exists()
                
                if not existe_notificacion:
                    mensaje = f"¡Venta #{instance.pk} LIQUIDADA! - Cliente: {instance.cliente.nombre_completo_display} - Total pagado: ${instance.total_pagado}"
                    for jefe in usuarios_jefe:
                        Notificacion.objects.create(
                            usuario=jefe,
                            tipo='LIQUIDACION',
                            mensaje=mensaje,
                            venta=instance
                        )
        except Exception as e:
            # Si hay algún error al calcular total_pagado, no crear notificación
            pass


@receiver(post_save, sender=Logistica)
def notificar_cambio_logistica(sender, instance, created, **kwargs):
    """Crea una notificación cuando hay cambios en la logística."""
    if not created:  # Solo para actualizaciones
        # Verificar si algún campo de logística cambió a True (confirmado)
        # Solo verificar servicios que están contratados
        cambios = []
        
        if instance.servicio_contratado('VUE') and instance.vuelo_confirmado:
            cambios.append("Vuelo confirmado")
        if instance.servicio_contratado('HOS') and instance.hospedaje_reservado:
            cambios.append("Hospedaje reservado")
        if instance.servicio_contratado('TRA') and instance.traslado_confirmado:
            cambios.append("Traslado confirmado")
        if instance.servicio_contratado('TOU') and instance.tickets_confirmado:
            cambios.append("Tickets confirmados")
        
        if cambios:
            usuarios_jefe = obtener_usuarios_jefe()
            mensaje = f"Cambios en logística para Venta #{instance.venta.pk} - Cliente: {instance.venta.cliente.nombre_completo_display} - {', '.join(cambios)}"
            
            for jefe in usuarios_jefe:
                # Evitar notificaciones duplicadas recientes (últimos 5 minutos)
                # IMPORTANTE: Verificar también el mensaje exacto para evitar duplicados
                from datetime import timedelta
                tiempo_limite = timezone.now() - timedelta(minutes=5)
                existe_reciente = Notificacion.objects.filter(
                    usuario=jefe,
                    venta=instance.venta,
                    tipo='LOGISTICA',
                    mensaje=mensaje,  # Verificar el mensaje exacto
                    fecha_creacion__gte=tiempo_limite
                ).exists()
                
                if not existe_reciente:
                    Notificacion.objects.create(
                        usuario=jefe,
                        tipo='LOGISTICA',
                        mensaje=mensaje,
                        venta=instance.venta
                    )


