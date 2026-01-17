"""
Señales de Django para crear notificaciones automáticamente
cuando ocurren eventos importantes en el sistema.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
import os
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


@receiver(pre_save, sender=AbonoPago)
def comprimir_comprobante_abono(sender, instance, **kwargs):
    """Comprime automáticamente el comprobante cuando se sube."""
    if instance.comprobante_imagen and instance.comprobante_imagen.name:
        # Solo comprimir si es una nueva imagen o si cambió
        if instance.pk:
            try:
                abono_anterior = AbonoPago.objects.get(pk=instance.pk)
                if abono_anterior.comprobante_imagen != instance.comprobante_imagen:
                    instance.comprimir_comprobante()
            except AbonoPago.DoesNotExist:
                instance.comprimir_comprobante()
        else:
            instance.comprimir_comprobante()


@receiver(post_save, sender=VentaViaje)
def eliminar_comprobantes_venta_liquidada(sender, instance, **kwargs):
    """
    Elimina los comprobantes de pagos cuando la venta se liquida completamente
    para ahorrar espacio en el servidor.
    """
    if not kwargs.get('created'):  # Solo para actualizaciones
        try:
            # Verificar si la venta está completamente liquidada
            if instance.esta_pagada:
                # Eliminar comprobantes de abonos
                for abono in instance.abonos.all():
                    if abono.comprobante_imagen and abono.comprobante_imagen.name:
                        try:
                            if os.path.isfile(abono.comprobante_imagen.path):
                                os.remove(abono.comprobante_imagen.path)
                            abono.comprobante_imagen = None
                            abono.save(update_fields=['comprobante_imagen'])
                        except Exception:
                            pass
                
                # Eliminar comprobante de apertura
                if instance.comprobante_apertura and instance.comprobante_apertura.name:
                    try:
                        if os.path.isfile(instance.comprobante_apertura.path):
                            os.remove(instance.comprobante_apertura.path)
                        instance.comprobante_apertura = None
                        instance.save(update_fields=['comprobante_apertura'])
                    except Exception:
                        pass
        except Exception:
            # Si hay algún error, no hacer nada
            pass
