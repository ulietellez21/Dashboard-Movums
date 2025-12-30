"""
Servicio centralizado para registrar eventos en el historial de auditoría.
Proporciona métodos fáciles de usar para registrar diferentes tipos de eventos.
"""
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from decimal import Decimal
import json

from .models import HistorialMovimiento


class AuditoriaService:
    """Servicio para registrar eventos de auditoría en el sistema."""
    
    @classmethod
    def registrar_evento(
        cls,
        tipo_evento,
        descripcion,
        usuario=None,
        objeto=None,
        nivel='INFO',
        datos_adicionales=None,
        ip_address=None
    ):
        """
        Registra un evento en el historial de auditoría.
        
        Args:
            tipo_evento: Tipo de evento (de TIPO_EVENTO_CHOICES)
            descripcion: Descripción del evento en formato de texto
            usuario: Usuario que realizó la acción (opcional)
            objeto: Objeto relacionado (cualquier instancia de modelo, opcional)
            nivel: Nivel del evento ('INFO', 'WARNING', 'ERROR', 'CRITICAL')
            datos_adicionales: Diccionario con datos adicionales (opcional)
            ip_address: Dirección IP del cliente (opcional)
        
        Returns:
            HistorialMovimiento: Instancia creada
        """
        content_type = None
        object_id = None
        
        if objeto:
            content_type = ContentType.objects.get_for_model(objeto)
            object_id = objeto.pk
        
        movimiento = HistorialMovimiento.objects.create(
            tipo_evento=tipo_evento,
            descripcion=descripcion,
            usuario=usuario,
            content_type=content_type,
            object_id=object_id,
            nivel=nivel,
            datos_adicionales=datos_adicionales,
            ip_address=ip_address,
            fecha_hora=timezone.now()
        )
        
        return movimiento
    
    # Métodos de conveniencia para eventos comunes
    
    @classmethod
    def registrar_venta_creada(cls, venta, usuario, ip_address=None):
        """Registra la creación de una venta."""
        descripcion = (
            f"Venta #{venta.pk} creada para el cliente {venta.cliente.nombre_completo_display}. "
            f"Total: ${venta.costo_venta_final:,.2f} MXN. "
            f"Vendedor: {venta.vendedor.username if venta.vendedor else 'N/A'}"
        )
        return cls.registrar_evento(
            tipo_evento='VENTA_CREADA',
            descripcion=descripcion,
            usuario=usuario,
            objeto=venta,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_venta_editada(cls, venta, usuario, cambios=None, ip_address=None):
        """Registra la edición de una venta."""
        cambios_str = ""
        if cambios:
            cambios_str = f" Cambios: {', '.join([f'{k}: {v}' for k, v in cambios.items()])}"
        
        descripcion = (
            f"Venta #{venta.pk} editada para el cliente {venta.cliente.nombre_completo_display}.{cambios_str}"
        )
        return cls.registrar_evento(
            tipo_evento='VENTA_EDITADA',
            descripcion=descripcion,
            usuario=usuario,
            objeto=venta,
            datos_adicionales={'cambios': cambios} if cambios else None,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_cotizacion_creada(cls, cotizacion, usuario, ip_address=None):
        """Registra la creación de una cotización."""
        descripcion = (
            f"Cotización '{cotizacion.slug}' creada para el cliente {cotizacion.cliente.nombre_completo_display}. "
            f"Tipo: {cotizacion.get_tipo_display()}"
        )
        return cls.registrar_evento(
            tipo_evento='COTIZACION_CREADA',
            descripcion=descripcion,
            usuario=usuario,
            objeto=cotizacion,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_abono_registrado(cls, abono, usuario, ip_address=None):
        """Registra el registro de un abono."""
        descripcion = (
            f"Abono de ${abono.monto:,.2f} MXN registrado para la venta #{abono.venta.pk}. "
            f"Forma de pago: {abono.get_forma_pago_display()}. "
            f"Cliente: {abono.venta.cliente.nombre_completo_display}"
        )
        return cls.registrar_evento(
            tipo_evento='ABONO_REGISTRADO',
            descripcion=descripcion,
            usuario=usuario,
            objeto=abono,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_abono_confirmado(cls, abono, usuario_confirmador, ip_address=None):
        """Registra la confirmación de un abono."""
        descripcion = (
            f"Abono de ${abono.monto:,.2f} MXN confirmado para la venta #{abono.venta.pk} "
            f"por {usuario_confirmador.username}. "
            f"Cliente: {abono.venta.cliente.nombre_completo_display}"
        )
        return cls.registrar_evento(
            tipo_evento='ABONO_CONFIRMADO',
            descripcion=descripcion,
            usuario=usuario_confirmador,
            objeto=abono,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_cliente_creado(cls, cliente, usuario, ip_address=None):
        """Registra la creación de un cliente."""
        descripcion = f"Cliente '{cliente.nombre_completo_display}' creado."
        return cls.registrar_evento(
            tipo_evento='CLIENTE_CREADO',
            descripcion=descripcion,
            usuario=usuario,
            objeto=cliente,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_usuario_creado(cls, usuario_creado, usuario_creador, ip_address=None):
        """Registra la creación de un usuario."""
        descripcion = f"Usuario '{usuario_creado.username}' creado por {usuario_creador.username}."
        return cls.registrar_evento(
            tipo_evento='USUARIO_CREADO',
            descripcion=descripcion,
            usuario=usuario_creador,
            objeto=usuario_creado,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_kilometros_acumulados(cls, cliente, kilometros, venta=None, usuario=None, ip_address=None):
        """Registra la acumulación de kilómetros."""
        venta_str = f" en la venta #{venta.pk}" if venta else ""
        descripcion = (
            f"Kilómetros acumulados para el cliente {cliente.nombre_completo_display}: "
            f"{kilometros} km{venta_str}"
        )
        return cls.registrar_evento(
            tipo_evento='KILOMETROS_ACUMULADOS',
            descripcion=descripcion,
            usuario=usuario,
            objeto=cliente,
            datos_adicionales={
                'kilometros': float(kilometros),
                'venta_id': venta.pk if venta else None
            },
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_kilometros_redimidos(cls, cliente, kilometros, venta=None, usuario=None, ip_address=None):
        """Registra la redención de kilómetros."""
        venta_str = f" en la venta #{venta.pk}" if venta else ""
        descripcion = (
            f"Kilómetros redimidos para el cliente {cliente.nombre_completo_display}: "
            f"{kilometros} km{venta_str}"
        )
        return cls.registrar_evento(
            tipo_evento='KILOMETROS_REDIMIDOS',
            descripcion=descripcion,
            usuario=usuario,
            objeto=cliente,
            datos_adicionales={
                'kilometros': float(kilometros),
                'venta_id': venta.pk if venta else None
            },
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_login(cls, usuario, ip_address=None):
        """Registra el inicio de sesión de un usuario."""
        descripcion = f"Usuario '{usuario.username}' inició sesión."
        return cls.registrar_evento(
            tipo_evento='USUARIO_LOGIN',
            descripcion=descripcion,
            usuario=usuario,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_logout(cls, usuario, ip_address=None):
        """Registra el cierre de sesión de un usuario."""
        descripcion = f"Usuario '{usuario.username}' cerró sesión."
        return cls.registrar_evento(
            tipo_evento='USUARIO_LOGOUT',
            descripcion=descripcion,
            usuario=usuario,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_proveedor_creado(cls, proveedor, usuario, ip_address=None):
        """Registra la creación de un proveedor."""
        descripcion = f"Proveedor '{proveedor.nombre}' creado. Servicio: {proveedor.get_servicio_display()}"
        return cls.registrar_evento(
            tipo_evento='PROVEEDOR_CREADO',
            descripcion=descripcion,
            usuario=usuario,
            objeto=proveedor,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_proveedor_editado(cls, proveedor, usuario, ip_address=None):
        """Registra la edición de un proveedor."""
        descripcion = f"Proveedor '{proveedor.nombre}' editado."
        return cls.registrar_evento(
            tipo_evento='PROVEEDOR_EDITADO',
            descripcion=descripcion,
            usuario=usuario,
            objeto=proveedor,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_proveedor_eliminado(cls, proveedor, usuario, ip_address=None):
        """Registra la eliminación de un proveedor."""
        descripcion = f"Proveedor '{proveedor.nombre}' eliminado."
        return cls.registrar_evento(
            tipo_evento='PROVEEDOR_ELIMINADO',
            descripcion=descripcion,
            usuario=usuario,
            nivel='WARNING',
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_ejecutivo_creado(cls, ejecutivo, usuario, ip_address=None):
        """Registra la creación de un ejecutivo."""
        descripcion = f"Ejecutivo '{ejecutivo.nombre_completo}' creado. Oficina: {ejecutivo.oficina or 'N/A'}"
        return cls.registrar_evento(
            tipo_evento='EJECUTIVO_CREADO',
            descripcion=descripcion,
            usuario=usuario,
            objeto=ejecutivo,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_ejecutivo_editado(cls, ejecutivo, usuario, ip_address=None):
        """Registra la edición de un ejecutivo."""
        descripcion = f"Ejecutivo '{ejecutivo.nombre_completo}' editado."
        return cls.registrar_evento(
            tipo_evento='EJECUTIVO_EDITADO',
            descripcion=descripcion,
            usuario=usuario,
            objeto=ejecutivo,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_ejecutivo_eliminado(cls, ejecutivo, usuario, ip_address=None):
        """Registra la eliminación de un ejecutivo."""
        descripcion = f"Ejecutivo '{ejecutivo.nombre_completo}' eliminado."
        return cls.registrar_evento(
            tipo_evento='EJECUTIVO_ELIMINADO',
            descripcion=descripcion,
            usuario=usuario,
            nivel='WARNING',
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_logistica_actualizada(cls, logistica, usuario, cambios=None, ip_address=None):
        """Registra la actualización de logística."""
        cambios_str = ""
        if cambios:
            cambios_str = f" Cambios: {', '.join([f'{k}: {v}' for k, v in cambios.items()])}"
        descripcion = f"Logística actualizada para la venta #{logistica.venta.pk}.{cambios_str}"
        return cls.registrar_evento(
            tipo_evento='LOGISTICA_ACTUALIZADA',
            descripcion=descripcion,
            usuario=usuario,
            objeto=logistica,
            datos_adicionales={'cambios': cambios} if cambios else None,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_confirmacion_subida(cls, confirmacion, usuario, ip_address=None):
        """Registra la subida de una confirmación."""
        descripcion = (
            f"Confirmación subida para la venta #{confirmacion.venta.pk}. "
            f"Archivo: {confirmacion.archivo.name if confirmacion.archivo else 'N/A'}. "
            f"Nota: {confirmacion.nota or 'Sin nota'}"
        )
        return cls.registrar_evento(
            tipo_evento='CONFIRMACION_SUBIDA',
            descripcion=descripcion,
            usuario=usuario,
            objeto=confirmacion,
            ip_address=ip_address
        )
    
    @classmethod
    def registrar_confirmacion_eliminada(cls, confirmacion, usuario, ip_address=None):
        """Registra la eliminación de una confirmación."""
        descripcion = f"Confirmación eliminada de la venta #{confirmacion.venta.pk}."
        return cls.registrar_evento(
            tipo_evento='CONFIRMACION_ELIMINADA',
            descripcion=descripcion,
            usuario=usuario,
            nivel='WARNING',
            ip_address=ip_address
        )

