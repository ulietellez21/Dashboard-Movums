"""
Señales de Django para crear notificaciones automáticamente
cuando ocurren eventos importantes en el sistema.
"""
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
import os
import logging
from .models import AbonoPago, VentaViaje, Logistica, Notificacion

logger = logging.getLogger(__name__)


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
def aplicar_promociones_al_liquidar(sender, instance, **kwargs):
    """
    Aplica las promociones de Kilómetros Movums SOLO cuando la venta se liquida.
    Las promociones (kilómetros acumulados y bonos) solo se hacen efectivos cuando
    la venta está completamente pagada.
    
    IMPORTANTE: La verificación de liquidación se basa en el total_pagado >= costo_total_con_modificacion,
    NO solo en el estado_confirmacion, porque una venta puede estar marcada como COMPLETADO
    pero aún no estar completamente pagada (solo con apertura).
    """
    if kwargs.get('created'):
        # Si es creación nueva, no aplicar aún - se aplicará cuando se liquide
        return
    
    try:
        # IMPORTANTE: Verificar si la venta REALMENTE está liquidada
        # La liquidación se determina por: total_pagado >= costo_total_con_modificacion
        # NO solo por estado_confirmacion == 'COMPLETADO', porque una venta puede estar
        # marcada como COMPLETADO con solo la apertura pagada, pero aún no liquidada completamente.
        costo_total = instance.costo_total_con_modificacion
        total_pagado = instance.total_pagado
        
        venta_liquidada = (total_pagado >= costo_total and costo_total > 0)
        
        if not venta_liquidada:
            # Venta aún no liquidada completamente, no aplicar promociones
            logger.debug(
                f"⚠️ Venta {instance.pk} aún no liquidada: "
                f"Total pagado: ${total_pagado:,.2f}, Costo total: ${costo_total:,.2f}. "
                f"Omitiendo aplicación de promociones."
            )
            return
        
        # Verificar si ya se aplicaron los kilómetros para esta venta
        # Buscamos si ya existe un movimiento de tipo 'COMPRA' o 'BONO_PROMOCION' para esta venta
        from crm.models import HistorialKilometros
        kilometros_ya_aplicados = HistorialKilometros.objects.filter(
            venta=instance,
            tipo_evento__in=['COMPRA', 'BONO_PROMOCION']
        ).exists()
        
        if kilometros_ya_aplicados:
            # Ya se aplicaron los kilómetros, no duplicar
            logger.info(f"⚠️ Los kilómetros ya fueron aplicados para la venta {instance.pk}. Omitiendo.")
            return
        
        # Importar KilometrosService
        from crm.services import KilometrosService
        
        # Verificar que el cliente participe en kilómetros
        if not instance.cliente or not instance.cliente.participa_kilometros:
            logger.info(f"⚠️ Cliente {instance.cliente.pk if instance.cliente else 'N/A'} no participa en kilómetros. Omitiendo acumulación.")
            return
        
        logger.info(f"✅ Venta {instance.pk} liquidada. Aplicando promociones de kilómetros...")
        
        # 1. Acumular kilómetros por la compra (si aún no se acumularon)
        if instance.cliente and instance.cliente.participa_kilometros:
            # Calcular el monto sobre el cual acumular: costo_venta_final - descuento_kilometros_mxn
            monto_para_acumular = instance.costo_venta_final
            if instance.aplica_descuento_kilometros and instance.descuento_kilometros_mxn:
                monto_para_acumular = monto_para_acumular - instance.descuento_kilometros_mxn
            monto_para_acumular = max(Decimal('0.00'), monto_para_acumular)
            
            if monto_para_acumular > 0:
                registro_acumulacion = KilometrosService.acumular_por_compra(
                    instance.cliente,
                    monto_para_acumular,
                    venta=instance
                )
                if registro_acumulacion:
                    km_acumulados = monto_para_acumular * KilometrosService.KM_POR_PESO
                    logger.info(
                        f"✅ Kilómetros acumulados al liquidar venta {instance.pk}: "
                        f"{km_acumulados} km (por ${monto_para_acumular:,.2f} MXN)"
                    )
        
        # 2. Acumular bonos de promociones tipo 'KM' (si hay promociones aplicadas)
        promociones_con_km = instance.promociones_aplicadas.filter(km_bono__gt=0)
        bonos_acumulados = Decimal('0.00')
        
        for vpa in promociones_con_km:
            if vpa.km_bono and vpa.km_bono > 0:
                registro_bono = KilometrosService.acumular_bono_promocion(
                    cliente=instance.cliente,
                    kilometros=vpa.km_bono,
                    venta=instance,
                    promocion=vpa.promocion,
                    descripcion=f"Bono de promoción al liquidar: {vpa.nombre_promocion or vpa.promocion.nombre}"
                )
                if registro_bono:
                    bonos_acumulados += vpa.km_bono
                    logger.info(
                        f"✅ Bono de kilómetros acumulado al liquidar venta {instance.pk}: "
                        f"{vpa.km_bono} km (Promoción: {vpa.nombre_promocion or vpa.promocion.nombre})"
                    )
        
        if bonos_acumulados > 0:
            logger.info(
                f"📊 RESUMEN AL LIQUIDAR VENTA {instance.pk}: "
                f"Total bonos acumulados: {bonos_acumulados:,.2f} km"
            )
    
    except Exception as e:
        logger.exception(
            f"❌ Error aplicando promociones al liquidar venta {instance.pk}: {str(e)}"
        )


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
                # ✅ PERFORMANCE: Prefetch abonos una sola vez
                abonos_list = list(instance.abonos.all())
                
                # Eliminar comprobantes de abonos
                for abono in abonos_list:
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


@receiver(post_save, sender=VentaViaje)
def recalcular_comisiones_si_pagada(sender, instance, **kwargs):
    """
    Recalcula las comisiones de una venta si cambió su estado de pago.
    Se ejecuta cuando una venta se actualiza (especialmente cuando se marca como pagada).
    """
    # Solo procesar si la venta tiene un vendedor
    if not instance.vendedor:
        return
    
    # Verificar si el vendedor es de tipo MOSTRADOR
    try:
        perfil = instance.vendedor.perfil
        if perfil.tipo_vendedor != 'MOSTRADOR':
            return
    except:
        return
    
    # Importar aquí para evitar importaciones circulares
    try:
        from ventas.services.comisiones import recalcular_comision_venta_si_pagada
        recalcular_comision_venta_si_pagada(instance)
    except Exception as e:
        logger.error(f"Error al recalcular comisiones para venta {instance.pk}: {e}", exc_info=True)