from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from decimal import Decimal


class HistorialMovimiento(models.Model):
    """
    Modelo para registrar todos los movimientos y eventos importantes del sistema.
    Almacena un historial completo de auditoría con fecha, hora, usuario y detalles.
    """
    
    TIPO_EVENTO_CHOICES = [
        ('VENTA_CREADA', 'Venta Creada'),
        ('VENTA_EDITADA', 'Venta Editada'),
        ('VENTA_ELIMINADA', 'Venta Eliminada'),
        ('COTIZACION_CREADA', 'Cotización Creada'),
        ('COTIZACION_EDITADA', 'Cotización Editada'),
        ('COTIZACION_ELIMINADA', 'Cotización Eliminada'),
        ('COTIZACION_CONVERTIDA', 'Cotización Convertida a Venta'),
        ('ABONO_REGISTRADO', 'Abono Registrado'),
        ('ABONO_CONFIRMADO', 'Abono Confirmado'),
        ('ABONO_ELIMINADO', 'Abono Eliminado'),
        ('CLIENTE_CREADO', 'Cliente Creado'),
        ('CLIENTE_EDITADO', 'Cliente Editado'),
        ('CLIENTE_ELIMINADO', 'Cliente Eliminado'),
        ('USUARIO_CREADO', 'Usuario Creado'),
        ('USUARIO_EDITADO', 'Usuario Editado'),
        ('USUARIO_ELIMINADO', 'Usuario Eliminado'),
        ('USUARIO_LOGIN', 'Usuario Inició Sesión'),
        ('USUARIO_LOGOUT', 'Usuario Cerró Sesión'),
        ('KILOMETROS_ACUMULADOS', 'Kilómetros Acumulados'),
        ('KILOMETROS_REDIMIDOS', 'Kilómetros Redimidos'),
        ('PROMOCION_APLICADA', 'Promoción Aplicada'),
        ('PROMOCION_CREADA', 'Promoción Creada'),
        ('PROMOCION_EDITADA', 'Promoción Editada'),
        ('PROMOCION_ELIMINADA', 'Promoción Eliminada'),
        ('PROVEEDOR_CREADO', 'Proveedor Creado'),
        ('PROVEEDOR_EDITADO', 'Proveedor Editado'),
        ('PROVEEDOR_ELIMINADO', 'Proveedor Eliminado'),
        ('EJECUTIVO_CREADO', 'Ejecutivo Creado'),
        ('EJECUTIVO_EDITADO', 'Ejecutivo Editado'),
        ('EJECUTIVO_ELIMINADO', 'Ejecutivo Eliminado'),
        ('CONFIRMACION_SUBIDA', 'Confirmación Subida'),
        ('CONFIRMACION_ELIMINADA', 'Confirmación Eliminada'),
        ('LOGISTICA_ACTUALIZADA', 'Logística Actualizada'),
        ('OTRO', 'Otro Evento'),
    ]
    
    NIVEL_CHOICES = [
        ('INFO', 'Informativo'),
        ('WARNING', 'Advertencia'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Crítico'),
    ]
    
    # Información básica del evento
    fecha_hora = models.DateTimeField(
        default=timezone.now,
        verbose_name="Fecha y Hora",
        db_index=True,
        help_text="Fecha y hora exacta del evento"
    )
    
    tipo_evento = models.CharField(
        max_length=50,
        choices=TIPO_EVENTO_CHOICES,
        verbose_name="Tipo de Evento",
        db_index=True
    )
    
    nivel = models.CharField(
        max_length=10,
        choices=NIVEL_CHOICES,
        default='INFO',
        verbose_name="Nivel",
        db_index=True
    )
    
    # Usuario que realizó la acción
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_realizados',
        verbose_name="Usuario",
        help_text="Usuario que realizó la acción"
    )
    
    # Referencia genérica al objeto relacionado (opcional)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Tipo de Objeto"
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="ID del Objeto"
    )
    objeto_relacionado = GenericForeignKey('content_type', 'object_id')
    
    # Descripción del evento
    descripcion = models.TextField(
        verbose_name="Descripción",
        help_text="Descripción detallada del evento en formato de texto"
    )
    
    # Información adicional (JSON opcional para datos estructurados)
    datos_adicionales = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Datos Adicionales",
        help_text="Información adicional en formato JSON (opcional)"
    )
    
    # IP del cliente (opcional)
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Dirección IP"
    )
    
    class Meta:
        verbose_name = "Historial de Movimiento"
        verbose_name_plural = "Historial de Movimientos"
        ordering = ['-fecha_hora']
        indexes = [
            models.Index(fields=['-fecha_hora']),
            models.Index(fields=['tipo_evento']),
            models.Index(fields=['usuario']),
            models.Index(fields=['nivel']),
        ]
    
    def __str__(self):
        usuario_str = self.usuario.username if self.usuario else "Sistema"
        return f"{self.get_tipo_evento_display()} - {usuario_str} - {self.fecha_hora.strftime('%Y-%m-%d %H:%M:%S')}"
    
    def descripcion_corta(self):
        """Retorna una descripción corta del evento"""
        if len(self.descripcion) > 100:
            return self.descripcion[:100] + "..."
        return self.descripcion

