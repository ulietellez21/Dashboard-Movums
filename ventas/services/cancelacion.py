"""
Servicio para gestionar la cancelación definitiva de ventas.
Incluye la reversión de KM Movums, promociones y comisiones.
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from crm.services import KilometrosService
from ventas.models import VentaViaje, SolicitudCancelacion, ComisionVenta, VentaPromocionAplicada

logger = logging.getLogger(__name__)


class CancelacionService:
    """
    Servicio para manejar la cancelación definitiva de ventas.
    """
    
    @staticmethod
    @transaction.atomic
    def cancelar_venta_definitivamente(venta, solicitud):
        """
        Cancela una venta definitivamente y revierte todos los efectos:
        - KM Movums
        - Promociones
        - Comisiones
        
        Args:
            venta: Instancia de VentaViaje a cancelar
            solicitud: Instancia de SolicitudCancelacion aprobada
            
        Returns:
            dict: Resumen de la cancelación con detalles de lo revertido
        """
        resultado = {
            'km_revertidos': Decimal('0.00'),
            'km_devueltos': Decimal('0.00'),
            'promociones_revertidas': 0,
            'comisiones_canceladas': 0,
            'exito': True,
            'errores': []
        }
        
        try:
            # 1. Revertir KM Movums
            try:
                km_resultado = KilometrosService.revertir_por_cancelacion(venta)
                resultado['km_revertidos'] = Decimal(str(km_resultado.get('km_totales', 0)))
                resultado['km_devueltos'] = Decimal(str(km_resultado.get('km_devueltos', 0)))
                logger.info(
                    f"✅ KM Movums revertidos para venta {venta.pk}: "
                    f"{resultado['km_revertidos']} km revertidos, "
                    f"{resultado['km_devueltos']} km devueltos"
                )
            except Exception as e:
                error_msg = f"Error al revertir KM Movums: {str(e)}"
                resultado['errores'].append(error_msg)
                logger.exception(f"❌ {error_msg} para venta {venta.pk}")
            
            # 2. Revertir promociones aplicadas
            try:
                promociones_aplicadas = VentaPromocionAplicada.objects.filter(venta=venta)
                for promocion_aplicada in promociones_aplicadas:
                    # Revertir bonos de promoción si existen
                    if promocion_aplicada.km_bono and promocion_aplicada.km_bono > 0:
                        try:
                            KilometrosService.revertir_bono_promocion(
                                venta.cliente,
                                promocion_aplicada.km_bono,
                                venta,
                                promocion_aplicada.promocion,
                                descripcion=f"Reversión por cancelación de venta {venta.pk}"
                            )
                            resultado['promociones_revertidas'] += 1
                            logger.info(
                                f"✅ Bono de promoción revertido: {promocion_aplicada.km_bono} km "
                                f"para venta {venta.pk}"
                            )
                        except Exception as e:
                            error_msg = f"Error al revertir bono de promoción {promocion_aplicada.pk}: {str(e)}"
                            resultado['errores'].append(error_msg)
                            logger.exception(f"❌ {error_msg}")
            except Exception as e:
                error_msg = f"Error al procesar promociones: {str(e)}"
                resultado['errores'].append(error_msg)
                logger.exception(f"❌ {error_msg} para venta {venta.pk}")
            
            # 3. Cancelar comisiones del vendedor
            try:
                comisiones = ComisionVenta.objects.filter(venta=venta, cancelada=False)
                for comision in comisiones:
                    comision.cancelada = True
                    comision.fecha_cancelacion = timezone.now()
                    comision.save(update_fields=['cancelada', 'fecha_cancelacion'])
                    resultado['comisiones_canceladas'] += 1
                    logger.info(
                        f"✅ Comisión cancelada: {comision.pk} para venta {venta.pk}"
                    )
                
                # Recalcular comisiones mensuales del vendedor
                if venta.vendedor and comisiones.exists():
                    # Obtener el mes y año de la primera comisión
                    primera_comision = comisiones.first()
                    if primera_comision:
                        from ventas.services.comisiones import actualizar_comision_mensual
                        try:
                            actualizar_comision_mensual(
                                venta.vendedor,
                                primera_comision.mes,
                                primera_comision.anio
                            )
                            logger.info(
                                f"✅ Comisiones mensuales actualizadas para vendedor {venta.vendedor.username} "
                                f"mes {primera_comision.mes}/{primera_comision.anio}"
                            )
                        except Exception as e:
                            error_msg = f"Error al actualizar comisiones mensuales: {str(e)}"
                            resultado['errores'].append(error_msg)
                            logger.exception(f"❌ {error_msg}")
            except Exception as e:
                error_msg = f"Error al cancelar comisiones: {str(e)}"
                resultado['errores'].append(error_msg)
                logger.exception(f"❌ {error_msg} para venta {venta.pk}")
            
            # 4. Cambiar estado de venta
            venta.estado = 'CANCELADA'
            venta.save(update_fields=['estado'])
            
            # 5. Actualizar solicitud
            solicitud.estado = 'CANCELADA'
            solicitud.fecha_cancelacion_definitiva = timezone.now()
            solicitud.save(update_fields=['estado', 'fecha_cancelacion_definitiva'])
            
            logger.info(f"✅ Venta {venta.pk} cancelada definitivamente")
            
        except Exception as e:
            resultado['exito'] = False
            resultado['errores'].append(f"Error general en cancelación: {str(e)}")
            logger.exception(f"❌ Error general al cancelar venta {venta.pk}: {e}")
            raise
        
        return resultado
