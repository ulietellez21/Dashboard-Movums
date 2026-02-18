import os
import json
import logging

from django.db import models
from django.db.models import Sum, Q
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.urls import reverse
# from crm.models import Cliente # NO se importa aquí, se usa la cadena de referencia
from decimal import Decimal
from datetime import date, datetime # Se asegura la importación de datetime
from django.utils import timezone
from django.utils.text import slugify 
from django.core.validators import FileExtensionValidator
from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys

logger = logging.getLogger(__name__)

# ------------------- MODELO CENTRAL: VentaViaje -------------------

class VentaViaje(models.Model):
    """
    Modelo central que almacena los detalles de la venta, servicios y el estado financiero.
    """
    
    # ------------------- CONSTANTES DE SERVICIOS -------------------
    SERVICIOS_CHOICES = [
        ('VUE', 'Vuelo'),
        ('HOS', 'Hospedaje'),
        ('ALO', 'Alojamiento Alterno'),
        ('TRA', 'Traslado'),
        ('TOU', 'Tour y Actividades'),
        ('CIR', 'Circuito Internacional'),
        ('REN', 'Renta de Auto'),
        ('PAQ', 'Paquete'),
        ('CRU', 'Crucero'),
        ('SEG', 'Seguro de Viaje'),
        ('DOC', 'Trámites de Documentación'),
        ('OTR', 'Otros Servicios'),
    ]
    
    # ------------------- Relaciones -------------------
    vendedor = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='ventas_realizadas',
        verbose_name="Vendedor"
    )
    
    # Referencia al modelo Cliente en la app 'crm'
    cliente = models.ForeignKey(
        'crm.Cliente', 
        on_delete=models.PROTECT, 
        related_name='ventas_asociadas', 
        verbose_name="Cliente Asociado"
    )
    
    # ------------------- INFORMACIÓN DEL VIAJE Y FINANCIERA -------------------
    
    TIPO_VIAJE_CONTRATO_CHOICES = [
        ('NAC', 'Nacional'),
        ('INT', 'Internacional'),
        ('INT_MXN', 'Internacional MXN'),
    ]
    tipo_viaje = models.CharField(
        max_length=7, 
        choices=TIPO_VIAJE_CONTRATO_CHOICES, 
        default='NAC',
        verbose_name="Tipo de Viaje (Plantilla de Contrato)",
        db_index=True
    )
    
    # ✅ CAMPO NUEVO: Pasajeros
    pasajeros = models.TextField(
        verbose_name='Pasajeros (Nombres Completos para Contrato)',
        blank=True,
        help_text='Ingresa el nombre completo de cada pasajero, separados por línea nueva o coma.'
    )
    edades_menores = models.TextField(
        verbose_name='Edades de los menores',
        blank=True,
        help_text='Lista de edades de los menores que viajan (ej. 5, 8, 12).'
    )
    cotizacion_origen = models.ForeignKey(
        'ventas.Cotizacion',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='ventas_generadas',
        verbose_name='Cotización origen'
    )

    fecha_inicio_viaje = models.DateField(verbose_name="Fecha de Ida (Inicio de Viaje)", db_index=True)
    fecha_fin_viaje = models.DateField(blank=True, null=True, verbose_name="Fecha de Regreso (Fin de Viaje)", db_index=True)
    
    # ✅ CAMPO CORREGIDO: Almacena los códigos de los servicios seleccionados (ej: "VUE,HOS,SEG")
    servicios_seleccionados = models.TextField(
        choices=SERVICIOS_CHOICES, # Se usa para referencia en el Admin, aunque no obliga la BD
        blank=True, 
        verbose_name="Servicios Incluidos (Selección Múltiple)",
        help_text="Códigos de servicios seleccionados separados por coma (ej. VUE,HOS).",
    )

    # ✅ CAMPO ÚNICO PARA DETALLE DE SERVICIOS (Texto libre para la descripción)
    servicios_detalle = models.TextField(
        verbose_name="Servicios del Viaje (Detalle y Descripción)",
        blank=True,
        help_text="Incluye los detalles específicos (fechas, aerolíneas, hoteles, etc.) de los servicios contratados."
    )

    proveedor = models.ForeignKey(
        'ventas.Proveedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ventas_asociadas',
        verbose_name="Proveedor Asignado"
    )

    cantidad_apertura = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        verbose_name="Cantidad de Apertura/Anticipo"
    )
    
    # Campo para indicar si se requiere factura por el monto de apertura
    requiere_factura_apertura = models.BooleanField(
        default=False,
        verbose_name="Requiere Factura por Apertura",
        help_text="Indica si el cliente requiere factura por el monto de apertura."
    )
    
    # Modo de pago para la apertura
    MODO_PAGO_CHOICES = [
        ('EFE', 'Ikki'),
        ('TRN', 'Transferencia'),
        ('TAR', 'Tarjeta'),
        ('DEP', 'Depósito'),
        ('LIG', 'Liga de Pago'),
        ('PRO', 'Directo a Proveedor'),
        ('CRE', 'Crédito'),
    ]
    modo_pago_apertura = models.CharField(
        max_length=3,
        choices=MODO_PAGO_CHOICES,
        default='EFE',
        verbose_name="Modo de Pago de Apertura",
        help_text="Modo de pago del anticipo/apertura"
    )
    
    # ✅ Campos para comprobante de pago de apertura (obligatorio para TRN/TAR/DEP)
    comprobante_apertura = models.ImageField(
        upload_to='comprobantes_apertura/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name="Comprobante de Apertura (Imagen)",
        help_text="Imagen del comprobante del pago de apertura. Obligatorio para Transferencia, Tarjeta y Depósito. No aplica para Crédito."
    )
    comprobante_apertura_subido = models.BooleanField(
        default=False,
        verbose_name="Comprobante Apertura Subido",
        help_text="Indica si el comprobante de apertura ya fue subido al servidor."
    )
    comprobante_apertura_subido_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Subida del Comprobante de Apertura"
    )
    comprobante_apertura_subido_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comprobantes_apertura_subidos',
        verbose_name="Comprobante Apertura Subido Por"
    )
    
    # Estado de confirmación del pago
    ESTADO_CONFIRMACION_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_CONFIRMACION', 'En Confirmación'),
        ('COMPLETADO', 'Completado'),
    ]
    estado_confirmacion = models.CharField(
        max_length=20,
        choices=ESTADO_CONFIRMACION_CHOICES,
        default='PENDIENTE',
        verbose_name="Estado de Confirmación",
        help_text="Estado de confirmación del pago por el contador",
        db_index=True
    )
    apertura_confirmada = models.BooleanField(
        default=False,
        verbose_name="Apertura confirmada por contador",
        help_text="True solo cuando el contador ha confirmado explícitamente el pago de apertura (y comprobante subido). Para TRN/TAR/DEP la apertura no cuenta en total_pagado hasta que sea True."
    )
    
    costo_neto = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="Costo real del viaje para la agencia."
    )
    costo_venta_final = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        help_text="Precio total que paga el cliente."
    )
    aplica_descuento_kilometros = models.BooleanField(
        default=False,
        verbose_name="Aplicar descuento Kilómetros Movums",
        help_text="Marca si se otorgó un descuento promocional del 10%."
    )
    descuento_kilometros_mxn = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Monto de descuento Kilómetros Movums",
        help_text="Se calcula automáticamente como el 10% del precio final."
    )

    # ------------------- PROMOCIONES CONFIGURABLES -------------------
    promociones = models.ManyToManyField(
        'crm.PromocionKilometros',
        through='VentaPromocionAplicada',
        blank=True,
        related_name='ventas_aplicadas'
    )
    descuento_promociones_mxn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Descuento total por promociones"
    )
    resumen_promociones = models.TextField(
        blank=True,
        null=True,
        verbose_name="Resumen de promociones aplicadas"
    )
    descuento_promociones_aplicado_como_pago = models.BooleanField(
        default=False,
        verbose_name="Descuento de promociones registrado en abonos"
    )
    
    # ------------------- CAMPOS PARA VENTAS INTERNACIONALES (USD) -------------------
    # Estos campos almacenan los valores en dólares americanos para ventas internacionales
    tarifa_base_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
        verbose_name="Tarifa Base (USD)",
        help_text="Tarifa base en dólares americanos para ventas internacionales."
    )
    impuestos_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
        verbose_name="Impuestos (USD)",
        help_text="Impuestos en dólares americanos para ventas internacionales."
    )
    suplementos_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
        verbose_name="Suplementos (USD)",
        help_text="Suplementos en dólares americanos para ventas internacionales."
    )
    tours_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        blank=True,
        null=True,
        verbose_name="Tours (USD)",
        help_text="Tours en dólares americanos para ventas internacionales."
    )
    tipo_cambio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal('0.0000'),
        blank=True,
        null=True,
        verbose_name="Tipo de Cambio (referencia)",
        help_text="Tipo de cambio del día (solo referencia; ventas internacionales se manejan en USD sin conversión automática)."
    )
    
    # Campos en USD para ventas internacionales (fuente de verdad; no se convierte a MXN)
    cantidad_apertura_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Cantidad de Apertura/Anticipo (USD)",
        help_text="Para ventas internacionales: monto de apertura en dólares."
    )
    costo_venta_final_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Precio total (USD)",
        help_text="Para ventas internacionales: precio total que paga el cliente en dólares."
    )
    costo_neto_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Costo neto (USD)",
        help_text="Para ventas internacionales: costo real del viaje en dólares."
    )
    costo_modificacion_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Costo de modificación (USD)",
        help_text="Para ventas internacionales: costo de modificación en dólares."
    )
    
    fecha_vencimiento_pago = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Fecha Límite de Pago Total",
        db_index=True
    )
    
    # Estado general de la venta
    ESTADO_VENTA_CHOICES = [
        ('ACTIVA', 'Activa'),
        ('CANCELADA', 'Cancelada'),
    ]
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_VENTA_CHOICES,
        default='ACTIVA',
        verbose_name="Estado de la Venta",
        help_text="Estado general de la venta",
        db_index=True
    )
    
    # Costo de modificación (solo se agrega cuando se edita una venta)
    costo_modificacion = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Costo de Modificación",
        help_text="Costo adicional por modificar la venta. Se suma al costo total."
    )

    # ------------------- DOCUMENTACIÓN Y METADATOS -------------------
    
    documentos_cliente = models.FileField(
        upload_to='documentos_cliente/%Y/%m/%d/', 
        blank=True, 
        null=True,
        verbose_name="Documentos del Cliente (Zip/PDF)"
    )
    
    slug = models.SlugField(
        max_length=255, 
        unique=True, 
        blank=True, 
        help_text="Slug único para la URL del viaje."
    )
    
    # ------------------- FOLIO DE VENTA -------------------
    folio = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Folio de Venta",
        help_text="Identificador único de la venta. Formato: SERVICIO-AAAAMMDD-XX"
    )

    fecha_creacion = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # ------------------- Propiedades y Métodos -------------------
    
    def save(self, *args, **kwargs):
        """
        Sobrescrive save(). Genera el slug único y folio ANTES de guardar.
        Se hace más robusta la lógica del slug.
        """
        is_new = self.pk is None
        
        # 1. LÓGICA DEL SLUG: Generar si no existe (tanto para nuevas como existentes sin slug)
        if not self.slug or self.slug.strip() == '':
            nombre_base = "viaje" # Fallback por defecto

            # Aumento de robustez: Chequea si el ID del cliente está seteado antes de acceder al objeto
            if self.cliente_id:
                try:
                    # Se asume la existencia de la propiedad nombre_completo_display en el modelo Cliente
                    temp_name = self.cliente.nombre_completo_display.split()[0]
                    if temp_name.strip():
                        nombre_base = temp_name
                except Exception:
                    # Si falla cualquier acceso a cliente o su propiedad (e.g., nombre_completo_display)
                    pass # nombre_base se queda como 'viaje'
            
            # Si es una venta existente, usar el PK en el slug para mayor unicidad
            if not is_new and self.pk:
                timestamp = f"{self.pk:06d}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            else:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:17]
            
            base_slug = slugify(f"{nombre_base}-{timestamp}")
            unique_slug = base_slug
            num = 1
            
            while VentaViaje.objects.filter(slug=unique_slug).exclude(pk=self.pk if self.pk else None).exists():
                unique_slug = f"{base_slug}-{num}"
                num += 1
                
            self.slug = unique_slug
        
        # 2. LÓGICA DEL FOLIO: Generar si no existe (solo para nuevas ventas)
        if not self.folio:
            self.folio = self._generar_folio()
            
        # 3. Primera y Única llamada a save() para asignar el self.pk.
        super().save(*args, **kwargs) 
        
        # ESCALABILIDAD: La generación del contrato PDF se movió a bajo demanda.
        # Los contratos ahora se generan cuando el usuario los solicita explícitamente
        # (ej. al descargar o visualizar) en lugar de bloquear cada save().
        # Esto mejora significativamente el tiempo de respuesta de las peticiones.
        # Ver: ContratoVentaPDFView, ContratoHospedajePDFView, etc.
    
    def _generar_folio(self):
        """
        Genera un folio único para la venta.
        Formato: SERVICIO-AAAAMMDD-XX
        Donde SERVICIO es el código del servicio (VUE, HOS, etc.) o VAR si hay múltiples.
        XX es el consecutivo global del día.
        """
        from django.utils import timezone
        
        # Determinar el prefijo basado en los servicios seleccionados
        if self.servicios_seleccionados:
            servicios = [s.strip() for s in self.servicios_seleccionados.split(',') if s.strip()]
            if len(servicios) == 1:
                prefijo = servicios[0]  # Un solo servicio: usar su código
            else:
                prefijo = 'VAR'  # Múltiples servicios: usar VAR
        else:
            prefijo = 'VAR'  # Sin servicios definidos: usar VAR
        
        # Obtener fecha actual
        hoy = timezone.localdate()
        fecha_str = hoy.strftime('%Y%m%d')
        
        # Contar ventas del día actual para obtener el consecutivo
        from django.db.models import Q
        ventas_hoy = VentaViaje.objects.filter(
            fecha_creacion__date=hoy
        ).exclude(folio__isnull=True).exclude(folio='')
        
        # El consecutivo es el número de ventas de hoy + 1
        consecutivo = ventas_hoy.count() + 1
        
        # Generar folio: SERVICIO-AAAAMMDD-XX
        folio = f"{prefijo}-{fecha_str}-{consecutivo:02d}"
        
        # Verificar unicidad y ajustar si es necesario
        while VentaViaje.objects.filter(folio=folio).exists():
            consecutivo += 1
            folio = f"{prefijo}-{fecha_str}-{consecutivo:02d}"
        
        return folio

    def get_slug_or_generate(self):
        """Retorna el slug si existe, o genera uno nuevo si está vacío."""
        if not self.slug or self.slug.strip() == '':
            # Forzar la generación del slug guardando el objeto
            self.save(update_fields=['slug'])
        return self.slug
    
    def get_absolute_url(self):
        # Se asume que 'detalle_venta' se define con 'slug' y 'pk'
        slug = self.get_slug_or_generate()
        return reverse('detalle_venta', kwargs={'slug': slug, 'pk': self.pk})
    
    def _apertura_confirmada_para_conteo(self):
        """Indica si la apertura debe contarse como pagada (MXN o USD según tipo_viaje)."""
        if self.tipo_viaje == 'INT':
            monto_apertura = self._cantidad_apertura_usd_resuelto()
            if not monto_apertura or monto_apertura <= 0:
                return False
        else:
            if not self.cantidad_apertura or self.cantidad_apertura <= 0:
                return False
        if self.modo_pago_apertura in ['EFE', 'LIG', 'PRO']:
            return True
        if self.modo_pago_apertura in ['TRN', 'TAR', 'DEP']:
            return bool(self.apertura_confirmada)
        if self.modo_pago_apertura == 'CRE':
            return self.estado_confirmacion != 'EN_CONFIRMACION'
        return False

    @property
    def total_pagado(self):
        """
        Calcula el total pagado incluyendo solo abonos confirmados.
        Para ventas INT devuelve el total en USD; para NAC en MXN.
        """
        if self.tipo_viaje == 'INT':
            return self.total_pagado_usd

        # NAC: Sumar solo abonos confirmados o abonos en efectivo
        total_abonos = self.abonos.filter(
            Q(confirmado=True) | Q(forma_pago='EFE')
        ).aggregate(Sum('monto'))['monto__sum']
        total_abonos = total_abonos if total_abonos is not None else Decimal('0.00')

        monto_apertura = Decimal('0.00')
        if self._apertura_confirmada_para_conteo():
            monto_apertura = self.cantidad_apertura

        total = total_abonos + monto_apertura
        if self.descuento_promociones_aplicado_como_pago and self.descuento_promociones_mxn:
            total = total - (self.descuento_promociones_mxn or Decimal('0.00'))
        return max(total, Decimal('0.00'))

    @property
    def costo_total_con_modificacion(self):
        """
        Calcula el costo total incluyendo el costo de modificación y descuentos.
        Para ventas INT devuelve el total en USD; para NAC en MXN.
        ✅ INTEGRIDAD FINANCIERA: Incluye TODOS los descuentos (kilómetros Y promociones)
        """
        if self.tipo_viaje == 'INT':
            return self.costo_total_con_modificacion_usd
        costo_mod = self.costo_modificacion if self.costo_modificacion else Decimal('0.00')
        descuento_km = self.descuento_kilometros_mxn if self.aplica_descuento_kilometros else Decimal('0.00')
        descuento_promo = self.descuento_promociones_mxn or Decimal('0.00')
        total = self.costo_venta_final + costo_mod - descuento_km - descuento_promo
        return max(Decimal('0.00'), total)

    @property
    def total_con_descuento(self):
        """
        Total de la venta considerando modificaciones y aplicando todos los descuentos.
        ✅ INTEGRIDAD FINANCIERA: Incluye descuentos de kilómetros Y promociones
        """
        total = self.costo_venta_final + (self.costo_modificacion or Decimal('0.00'))
        descuento_km = self.descuento_kilometros_mxn if self.aplica_descuento_kilometros else Decimal('0.00')
        descuento_promo = self.descuento_promociones_mxn or Decimal('0.00')
        total -= (descuento_km + descuento_promo)
        return max(Decimal('0.00'), total)

    @property
    def saldo_restante(self):
        """
        Calcula el saldo restante. Para ventas INT en USD; para NAC en MXN.
        """
        if self.tipo_viaje == 'INT':
            return self.saldo_restante_usd
        costo_base = (self.costo_venta_final or Decimal('0.00')) + (self.costo_modificacion or Decimal('0.00'))
        descuento_km = self.descuento_kilometros_mxn or Decimal('0.00')
        descuento_promo = self.descuento_promociones_mxn or Decimal('0.00')
        total_final = costo_base - descuento_km - descuento_promo
        saldo = total_final - self.total_pagado
        return max(Decimal('0.00'), saldo)
    
    # ------------------- PROPIEDADES PARA VENTAS INTERNACIONALES (USD) -------------------
    
    @property
    def total_usd(self):
        """Total de la venta en USD para ventas internacionales (campo o calculado)."""
        if self.tipo_viaje != 'INT':
            return Decimal('0.00')
        if self.costo_venta_final_usd is not None:
            return self.costo_venta_final_usd
        tarifa_base = self.tarifa_base_usd or Decimal('0.00')
        impuestos = self.impuestos_usd or Decimal('0.00')
        suplementos = self.suplementos_usd or Decimal('0.00')
        tours = self.tours_usd or Decimal('0.00')
        return tarifa_base + impuestos + suplementos + tours

    def _cantidad_apertura_usd_resuelto(self):
        """Cantidad de apertura en USD: campo si existe, si no conversión legacy para INT."""
        if self.tipo_viaje != 'INT':
            return Decimal('0.00')
        if self.cantidad_apertura_usd is not None:
            return self.cantidad_apertura_usd
        if self.tipo_cambio and self.cantidad_apertura:
            return (self.cantidad_apertura / self.tipo_cambio).quantize(Decimal('0.01'))
        return Decimal('0.00')

    @property
    def cantidad_apertura_usd_display(self):
        """Para plantillas: apertura en USD (campo o legacy) para INT."""
        return self._cantidad_apertura_usd_resuelto()

    @property
    def total_pagado_usd(self):
        """Total pagado en USD para ventas internacionales (apertura + abonos en USD)."""
        if self.tipo_viaje != 'INT':
            return Decimal('0.00')
        monto_apertura_usd = Decimal('0.00')
        if self._apertura_confirmada_para_conteo():
            monto_apertura_usd = self._cantidad_apertura_usd_resuelto()
        total_abonos_usd = Decimal('0.00')
        for abono in self.abonos.filter(Q(confirmado=True) | Q(forma_pago='EFE')):
            if abono.monto_usd is not None and abono.tipo_cambio_aplicado:
                total_abonos_usd += abono.monto_usd
            elif abono.tipo_cambio_aplicado and abono.tipo_cambio_aplicado > 0:
                total_abonos_usd += (abono.monto / abono.tipo_cambio_aplicado).quantize(Decimal('0.01'))
            elif self.tipo_cambio and self.tipo_cambio > 0:
                total_abonos_usd += (abono.monto / self.tipo_cambio).quantize(Decimal('0.01'))
        return (monto_apertura_usd + total_abonos_usd).quantize(Decimal('0.01'))

    @property
    def costo_total_con_modificacion_usd(self):
        """Costo total con modificación en USD para ventas internacionales."""
        if self.tipo_viaje != 'INT':
            return Decimal('0.00')
        total_venta = self.costo_venta_final_usd if self.costo_venta_final_usd is not None else self.total_usd
        mod_usd = self.costo_modificacion_usd or Decimal('0.00')
        return (total_venta + mod_usd).quantize(Decimal('0.01'))

    @property
    def saldo_restante_usd(self):
        """Saldo restante en USD para ventas internacionales."""
        if self.tipo_viaje != 'INT':
            return Decimal('0.00')
        saldo = self.costo_total_con_modificacion_usd - self.total_pagado_usd
        return max(Decimal('0.00'), saldo.quantize(Decimal('0.01')))
    
    @property
    def esta_pagada(self):
        return self.saldo_restante <= Decimal('0.00')
    
    def _debe_mostrar_abonos_proveedor(self):
        """Determina si se deben mostrar abonos al proveedor (lógica interna).
        No duplicar en vistas: usar la propiedad puede_solicitar_abonos_proveedor."""
        # Ventas internacionales: siempre mostrar
        if self.tipo_viaje == 'INT':
            return True
        # Ventas nacionales: proveedor principal con método de pago preferencial
        if self.tipo_viaje in ('NAC', 'INT_MXN') and self.proveedor and self.proveedor.metodo_pago_preferencial:
            return True
        if self.tipo_viaje in ('NAC', 'INT_MXN'):
            def _normalizar(n):
                return (n or '').strip().lower().replace(' ', '').replace('\t', '')
            nombres_logistica = list({
                _normalizar(s.opcion_proveedor) for s in self.servicios_logisticos.all()
                if s.opcion_proveedor and s.opcion_proveedor.strip()
            })
            if not nombres_logistica:
                return False
            # Comparar normalizado: "YameviTravel" y "Yamevi Travel" deben coincidir
            for p in Proveedor.objects.filter(metodo_pago_preferencial=True).only('nombre'):
                if _normalizar(p.nombre) in nombres_logistica:
                    return True
        return False

    @property
    def puede_solicitar_abonos_proveedor(self):
        """Única fuente de verdad para "esta venta permite abonos a proveedor".
        Usar SIEMPRE en vistas: tanto para mostrar la sección (debe_mostrar_abonos)
        como para validar el POST de solicitud de abono. No duplicar la lógica en vistas."""
        return self._debe_mostrar_abonos_proveedor()
    
    @property
    def total_abonado_proveedor(self):
        """Calcula el total abonado al proveedor (abonos APROBADOS y COMPLETADOS).
        Para ventas internacionales: en USD.
        Para ventas nacionales: en MXN.
        """
        if not self._debe_mostrar_abonos_proveedor():
            return Decimal('0.00')
        
        total = Decimal('0.00')
        for abono in self.abonos_proveedor.filter(estado__in=['APROBADO', 'COMPLETADO']):
            if self.tipo_viaje == 'INT':
                # Ventas internacionales: calcular en USD
                if abono.monto_usd:
                    total += abono.monto_usd
                elif abono.tipo_cambio_aplicado and abono.tipo_cambio_aplicado > 0:
                    total += (abono.monto / abono.tipo_cambio_aplicado).quantize(Decimal('0.01'))
                elif self.tipo_cambio and self.tipo_cambio > 0:
                    total += (abono.monto / self.tipo_cambio).quantize(Decimal('0.01'))
            else:
                # Ventas nacionales: usar monto directamente en MXN
                total += abono.monto
        return total
    
    @property
    def saldo_pendiente_proveedor(self):
        """Calcula el saldo pendiente por abonar al proveedor.
        Base: Servicios planificados (costo_neto), no total del viaje.
        Para ventas internacionales: base en USD (costo_neto/tipo_cambio).
        Para ventas nacionales: base en MXN (costo_neto).
        """
        if not self._debe_mostrar_abonos_proveedor():
            return Decimal('0.00')
        
        abonado = self.total_abonado_proveedor

        if self.tipo_viaje == 'INT':
            # Ventas internacionales: base en USD (campo o conversión legacy)
            base_usd = self.costo_neto_usd if self.costo_neto_usd is not None else Decimal('0.00')
            if base_usd == 0 and self.costo_neto and self.tipo_cambio and self.tipo_cambio > 0:
                base_usd = (self.costo_neto / self.tipo_cambio).quantize(Decimal('0.01'))
            pendiente = base_usd - abonado
        else:
            base_servicios = self.costo_neto or Decimal('0.00')
            pendiente = base_servicios - abonado
        return max(Decimal('0.00'), pendiente.quantize(Decimal('0.01')))
    
    @property
    def servicios_seleccionados_display(self):
        """Devuelve una lista legible de los servicios seleccionados."""
        if not self.servicios_seleccionados:
            return ""
        
        selected_codes = self.servicios_seleccionados.split(',')
        # Crea un mapeo de código a nombre ('VUE' -> 'Vuelo')
        code_to_name = dict(self.SERVICIOS_CHOICES)
        
        # Mapea los códigos seleccionados a sus nombres
        names = [code_to_name.get(code.strip(), code.strip()) for code in selected_codes]
        
        return ", ".join(names)
    
    @property
    def servicios_detalle_desde_logistica(self):
        """
        Construye servicios_detalle desde servicios_logisticos, incluyendo TODOS los proveedores
        de Tours y Vuelos (múltiples filas). Si hay servicios en logística, los usa;
        si no, usa servicios_detalle original.
        """
        servicios_logisticos = self.servicios_logisticos.all().order_by('orden', 'pk')
        if not servicios_logisticos.exists():
            # Si no hay servicios en logística, usar servicios_detalle original
            return self.servicios_detalle or ''
        
        # Construir lista de servicios desde logística
        servicios_list = []
        choices = dict(self.SERVICIOS_CHOICES)
        
        # Agrupar por código de servicio para manejar múltiples proveedores
        servicios_por_codigo = {}
        for serv in servicios_logisticos:
            code = serv.codigo_servicio
            if code not in servicios_por_codigo:
                servicios_por_codigo[code] = []
            servicios_por_codigo[code].append(serv)
        
        # Construir líneas de servicios
        for code, servicios in servicios_por_codigo.items():
            nombre_servicio = choices.get(code, servicios[0].nombre_servicio)
            
            # Para TOU, VUE y HOS: mostrar cada fila con su proveedor
            if code in ['TOU', 'VUE', 'HOS']:
                for serv in servicios:
                    if serv.opcion_proveedor and serv.opcion_proveedor.strip():
                        servicios_list.append(f"{nombre_servicio} - Proveedor: {serv.opcion_proveedor}")
                    else:
                        servicios_list.append(nombre_servicio)
            else:
                # Para otros servicios: mostrar solo una vez con el proveedor (si existe)
                serv = servicios[0]  # Tomar el primero
                if serv.opcion_proveedor and serv.opcion_proveedor.strip():
                    servicios_list.append(f"{nombre_servicio} - Proveedor: {serv.opcion_proveedor}")
                else:
                    servicios_list.append(nombre_servicio)
        
        return '\n'.join(servicios_list)
    
    @property
    def is_logistica_completa(self):
        """Verifica si la logística está completamente confirmada."""
        try:
            return self.logistica.is_fully_confirmed
        except Logistica.DoesNotExist:
            return False
    
    @property
    def slug_safe(self):
        """Retorna el slug si existe, o genera uno nuevo si está vacío."""
        if not self.slug or self.slug.strip() == '':
            # Forzar la generación del slug guardando el objeto
            self.save(update_fields=['slug'])
        return self.slug

    def actualizar_estado_financiero(self, guardar=True):
        """
        Actualiza el estado de confirmación según lo pagado vs. el costo total.
        IMPORTANTE: No cambia el estado si hay pagos confirmados (apertura o abonos),
        para evitar que pagos ya confirmados regresen a pendientes.
        """
        nuevo_total = self.total_pagado
        estado_actual = self.estado_confirmacion
        nuevo_estado = estado_actual

        # Verificar si hay pagos confirmados (abonos o apertura)
        # Abonos confirmados: tienen confirmado=True y confirmado_en no es None
        tiene_abonos_confirmados = self.abonos.filter(confirmado=True, confirmado_en__isnull=False).exists()
        
        # Apertura confirmada (para no degradar a PENDIENTE y forzar COMPLETADO solo cuando corresponde):
        # - CRE: confirmada si el contador ya la validó (estado != EN_CONFIRMACION).
        # - EFE/LIG/PRO: no se usa aquí para forzar COMPLETADO.
        # - TRN/TAR/DEP: solo confirmada cuando el contador la aprobó explícitamente (apertura_confirmada=True).
        #   Para INT puede haber solo cantidad_apertura_usd (cantidad_apertura en 0).
        if self.modo_pago_apertura == 'CRE':
            apertura_confirmada = (self.estado_confirmacion != 'EN_CONFIRMACION')
        elif self.modo_pago_apertura in ['TRN', 'TAR', 'DEP']:
            tiene_monto_apertura = False
            if self.tipo_viaje == 'INT':
                monto_apertura = self._cantidad_apertura_usd_resuelto()
                tiene_monto_apertura = bool(monto_apertura and monto_apertura > 0)
            else:
                tiene_monto_apertura = bool(self.cantidad_apertura and self.cantidad_apertura > 0)
            apertura_confirmada = tiene_monto_apertura and bool(self.apertura_confirmada)
        else:
            apertura_confirmada = False
        
        # No marcar como COMPLETADO/liquidada si el total pagado no alcanza y la apertura (TRN/TAR/DEP) no está confirmada
        if (nuevo_estado == estado_actual and estado_actual == 'COMPLETADO' and
            nuevo_total < self.costo_total_con_modificacion and
            self.modo_pago_apertura in ['TRN', 'TAR', 'DEP'] and not self.apertura_confirmada):
            nuevo_estado = 'EN_CONFIRMACION'
        
        # Si hay una apertura confirmada (por contador en TRN/TAR/DEP o CRE), mantener COMPLETADO
        # y NO debe cambiar, independientemente del total pagado
        if apertura_confirmada:
            # La apertura fue confirmada por el contador, mantener COMPLETADO
            nuevo_estado = 'COMPLETADO'
        elif nuevo_total >= self.costo_total_con_modificacion:
            # Si el total pagado alcanza el costo total, marcar como completado
            nuevo_estado = 'COMPLETADO'
        elif estado_actual == 'EN_CONFIRMACION':
            # Si está en confirmación, mantener EN_CONFIRMACION hasta que se confirme o complete
            nuevo_estado = 'EN_CONFIRMACION'
        # CRÍTICO: Si hay comprobante subido pero no confirmado (TRN/TAR/DEP), debe estar en EN_CONFIRMACION
        elif (self.modo_pago_apertura in ['TRN', 'TAR', 'DEP'] and 
              self.comprobante_apertura_subido and 
              not apertura_confirmada):
            # Tiene comprobante subido esperando confirmación del contador → EN_CONFIRMACION
            nuevo_estado = 'EN_CONFIRMACION'
        elif estado_actual == 'COMPLETADO' and tiene_abonos_confirmados:
            # Si está completado y hay abonos confirmados, mantener COMPLETADO
            nuevo_estado = 'COMPLETADO'
        elif estado_actual == 'COMPLETADO' and not tiene_abonos_confirmados and not apertura_confirmada:
            # Solo cambiar a PENDIENTE si estaba completado pero NO hay pagos confirmados
            nuevo_estado = 'PENDIENTE'
        else:
            # Para otros casos, mantener el estado actual o poner PENDIENTE
            if estado_actual not in ['EN_CONFIRMACION', 'COMPLETADO']:
                nuevo_estado = 'PENDIENTE'

        if nuevo_estado != estado_actual:
            self.estado_confirmacion = nuevo_estado
            if guardar:
                # IMPORTANTE: Guardar sin update_fields para disparar todos los signals
                # y asegurar que total_pagado esté actualizado cuando se ejecute el signal
                self.save()
        elif guardar:
            # IMPORTANTE: Si el estado no cambia pero la venta está liquidada,
            # debemos guardar igual para disparar el signal de promociones.
            # Esto asegura que los kilómetros se apliquen aunque el estado ya sea COMPLETADO.
            if (nuevo_estado == 'COMPLETADO' and 
                nuevo_total >= self.costo_total_con_modificacion and 
                self.costo_total_con_modificacion > 0):
                # La venta está liquidada, guardar para disparar signal de promociones
                self.save()


    def __str__(self):
        # Se mantiene la asunción de nombre_completo_display en el Cliente
        return f"Venta {self.pk} - Cliente {self.cliente} ({self.slug})"

    class Meta:
        verbose_name = "Venta de Viaje"
        verbose_name_plural = "Ventas de Viajes"


# ------------------- MODELO: VentaPromocionAplicada -------------------

class VentaPromocionAplicada(models.Model):
    """Relación de promociones aplicadas a una venta, con montos y snapshot."""
    venta = models.ForeignKey(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='promociones_aplicadas'
    )
    promocion = models.ForeignKey(
        'crm.PromocionKilometros',
        on_delete=models.CASCADE,
        related_name='aplicaciones_venta'
    )
    nombre_promocion = models.CharField(max_length=150)
    porcentaje_aplicado = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    monto_descuento = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    combinable_snapshot = models.BooleanField(default=True)
    requiere_confirmacion_snapshot = models.BooleanField(default=False)
    km_bono = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Promoción aplicada a venta"
        verbose_name_plural = "Promociones aplicadas a ventas"

    def __str__(self):
        return f"{self.nombre_promocion} en venta {self.venta_id}"


# ------------------- MODELO: AbonoPago (Corregido el default de fecha_pago) -------------------

class AbonoPago(models.Model):
    """Registra cada pago o abono realizado por el cliente."""
    FORMA_PAGO_CHOICES = [
        ('TRN', 'Transferencia'),
        ('EFE', 'Ikki'),
        ('TAR', 'Tarjeta'),
        ('DEP', 'Depósito'),
        ('PPL', 'PayPal/Digital'),
        ('LIG', 'Liga de Pago'),
        ('PRO', 'Directo a Proveedor'),
    ]
    
    venta = models.ForeignKey(VentaViaje, on_delete=models.CASCADE, related_name='abonos', verbose_name="Venta Asociada")
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto del Abono")
    forma_pago = models.CharField(max_length=3, choices=FORMA_PAGO_CHOICES, default='TRN', verbose_name="Forma de Pago", db_index=True) 
    
    # ✅ CORRECCIÓN: Se usa datetime.now() como default para que coincida con el tipo DateTimeField.
    fecha_pago = models.DateTimeField(default=datetime.now, verbose_name="Fecha del Pago", db_index=True)
    
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Registrado Por")
    recibo_pdf = models.FileField(upload_to='recibos/', blank=True, null=True, verbose_name="Recibo/Comprobante")
    # Campos para ventas internacionales
    monto_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Monto en USD")
    tipo_cambio_aplicado = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="Tipo de Cambio aplicado")
    
    # Campos para confirmación de pagos por transferencia/tarjeta
    confirmado = models.BooleanField(default=False, verbose_name="Confirmado por Contador", db_index=True)
    confirmado_por = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='abonos_confirmados',
        verbose_name="Confirmado Por",
        limit_choices_to={'perfil__rol': 'CONTADOR'}
    )
    confirmado_en = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Confirmación", db_index=True)
    
    # ✅ Campos para comprobante de pago (obligatorio para TRN/TAR/DEP)
    comprobante_imagen = models.ImageField(
        upload_to='comprobantes_pagos/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name="Comprobante de Pago (Imagen)",
        help_text="Imagen del comprobante (recibo, screenshot, ticket). Obligatorio para Transferencia, Tarjeta y Depósito."
    )
    comprobante_subido = models.BooleanField(
        default=False,
        verbose_name="Comprobante Subido",
        help_text="Indica si el comprobante ya fue subido al servidor."
    )
    comprobante_subido_en = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Subida del Comprobante"
    )
    comprobante_subido_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comprobantes_subidos',
        verbose_name="Comprobante Subido Por"
    )
    
    # Campo para indicar si se requiere factura por el abono
    requiere_factura = models.BooleanField(
        default=False,
        verbose_name="Requiere Factura",
        help_text="Indica si el cliente requiere factura por este abono."
    )

    @property
    def monto_usd_para_display(self):
        """Para ventas INT: monto en USD a mostrar (monto_usd si existe, si no monto/tipo_cambio)."""
        if self.monto_usd is not None and self.monto_usd > 0:
            return self.monto_usd
        tc = self.tipo_cambio_aplicado or (getattr(self.venta, 'tipo_cambio', None) if self.venta_id else None)
        if tc and tc > 0 and self.monto:
            return (self.monto / tc).quantize(Decimal('0.01'))
        return None

    @property
    def tipo_cambio_para_display(self):
        """Tipo de cambio usado al registrar (para mostrar en plantillas INT)."""
        return self.tipo_cambio_aplicado or (getattr(self.venta, 'tipo_cambio', None) if self.venta_id else None)
    
    def comprimir_comprobante(self):
        """Comprime la imagen del comprobante para optimizar espacio."""
        if self.comprobante_imagen and self.comprobante_imagen.name:
            try:
                # Abrir la imagen
                img = Image.open(self.comprobante_imagen)
                
                # Convertir a RGB si es necesario (para PNG con transparencia)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                
                # Redimensionar si es muy grande (máximo 1920px de ancho)
                if img.width > 1920:
                    ratio = 1920 / img.width
                    new_size = (1920, int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Comprimir con calidad 85%
                output = BytesIO()
                img.save(output, format='JPEG', quality=85, optimize=True)
                output.seek(0)
                
                # Crear nuevo archivo en memoria
                filename = os.path.basename(self.comprobante_imagen.name)
                if not filename.endswith('.jpg') and not filename.endswith('.jpeg'):
                    filename = os.path.splitext(filename)[0] + '.jpg'
                
                self.comprobante_imagen = InMemoryUploadedFile(
                    output, 'ImageField', filename, 'image/jpeg', sys.getsizeof(output), None
                )
            except Exception as e:
                # Si falla la compresión, mantener la imagen original
                pass

    def __str__(self):
        return f"Abono de ${self.monto} ({self.get_forma_pago_display()}) para Venta {self.venta.pk}"

    class Meta:
        verbose_name = "Abono o Pago"
        verbose_name_plural = "Abonos y Pagos"


# ------------------- MODELO: Logistica (Sin cambios) -------------------

class Logistica(models.Model):
    """Rastrea el estado de confirmación de los servicios para una VentaViaje."""
    venta = models.OneToOneField(VentaViaje, on_delete=models.CASCADE, related_name='logistica', verbose_name="Venta Asociada")
    vuelo_confirmado = models.BooleanField(default=False, verbose_name="Vuelo Confirmado")
    hospedaje_reservado = models.BooleanField(default=False, verbose_name="Hospedaje Reservado")
    traslado_confirmado = models.BooleanField(default=False, verbose_name="Traslado Confirmado")
    tickets_confirmado = models.BooleanField(default=False, verbose_name="Tickets Confirmados")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Registro de Logística"
        verbose_name_plural = "Registros de Logística"
        
    def __str__(self):
        return f"Logística para Venta {self.venta.pk}"
    
    def servicio_contratado(self, codigo_servicio):
        """
        Verifica si un servicio está contratado en la venta asociada.
        codigo_servicio: 'VUE', 'HOS', 'TRA', 'TOU', etc.
        """
        if not self.venta.servicios_seleccionados:
            return False
        servicios_codes = [s.strip() for s in self.venta.servicios_seleccionados.split(',')]
        return codigo_servicio in servicios_codes
    
    @property
    def is_fully_confirmed(self):
        """Verifica si todos los servicios contratados están confirmados."""
        servicios_contratados = self.get_servicios_contratados()
        if not servicios_contratados:
            return True  # Si no hay servicios contratados, se considera completado
        
        for servicio in servicios_contratados:
            if servicio['codigo'] == 'VUE' and not self.vuelo_confirmado:
                return False
            elif servicio['codigo'] == 'HOS' and not self.hospedaje_reservado:
                return False
            elif servicio['codigo'] == 'TRA' and not self.traslado_confirmado:
                return False
            elif servicio['codigo'] == 'TOU' and not self.tickets_confirmado:
                return False
        
        return True
    
    def get_servicios_contratados(self):
        """Retorna una lista de los servicios contratados en la venta."""
        if not self.venta.servicios_seleccionados:
            return []
        
        servicios_codes = [s.strip() for s in self.venta.servicios_seleccionados.split(',')]
        servicios_info = []
        
        # Mapeo de códigos a información de logística
        servicios_logistica = {
            'VUE': {'codigo': 'VUE', 'nombre': 'Vuelo', 'campo': 'vuelo_confirmado'},
            'HOS': {'codigo': 'HOS', 'nombre': 'Hospedaje', 'campo': 'hospedaje_reservado'},
            'TRA': {'codigo': 'TRA', 'nombre': 'Traslado', 'campo': 'traslado_confirmado'},
            'TOU': {'codigo': 'TOU', 'nombre': 'Tickets', 'campo': 'tickets_confirmado'},
        }
        
        # Solo retornar servicios que están en la lista de logística
        for code in servicios_codes:
            if code in servicios_logistica:
                servicio_info = servicios_logistica[code].copy()
                servicio_info['confirmado'] = getattr(self, servicio_info['campo'], False)
                servicios_info.append(servicio_info)
        
        return servicios_info

    def get_fields(self):
        """Retorna solo los campos de logística para servicios contratados."""
        fields_data = []
        servicios_contratados = self.get_servicios_contratados()
        
        for servicio in servicios_contratados:
            campo = servicio['campo']
            value = getattr(self, campo, False)
            fields_data.append({
                'label': servicio['nombre'],
                'value': value,
                'name': campo,
                'codigo': servicio['codigo']
            })
        
        return fields_data


class LogisticaServicio(models.Model):
    """Detalle financiero por servicio contratado en una venta."""
    ESTADO_CHOICES = VentaViaje.SERVICIOS_CHOICES

    venta = models.ForeignKey(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='servicios_logisticos',
        verbose_name="Venta Asociada"
    )
    codigo_servicio = models.CharField(
        max_length=5,
        choices=ESTADO_CHOICES,
        verbose_name="Código de Servicio"
    )
    nombre_servicio = models.CharField(
        max_length=120,
        verbose_name="Nombre mostrado"
    )
    monto_planeado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Monto planificado"
    )
    pagado = models.BooleanField(default=False, verbose_name="Servicio pagado")
    fecha_pagado = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de pago")
    notas = models.CharField(max_length=255, blank=True, verbose_name="Notas internas")
    orden = models.PositiveIntegerField(default=0, verbose_name="Orden de visualización")
    opcion_proveedor = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Opción elegida del proveedor",
        help_text="Ej: Aerolínea, Hotel, etc."
    )

    class Meta:
        verbose_name = "Servicio logístico"
        verbose_name_plural = "Servicios logísticos"
        ordering = ['orden', 'pk']
        # Sin unique_together: se permiten múltiples filas TOU (Tour) por venta desde Logística.

    def __str__(self):
        return f"{self.nombre_servicio} - Venta {self.venta.pk}"

# ------------------- MODELOS PARA CONTRATOS (Sin cambios) -------------------

class ContratoPlantilla(models.Model):
    """
    Define las plantillas de contrato base (e.g., Nacional, Internacional).
    """
    TIPO_CHOICES = [
        ('NAC', 'Nacional'),
        ('INT', 'Internacional'),
        ('OTROS', 'Otros'),
    ]
    
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre de la Plantilla")
    tipo = models.CharField(max_length=5, choices=TIPO_CHOICES, verbose_name="Tipo de Contrato") 
    
    contenido_base = models.TextField(
        help_text="Usar variables de sustitución en formato Python como {cliente_nombre_completo}, {costo_total}, etc."
    )
    
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Plantilla: {self.nombre} ({self.get_tipo_display()})"
    
    class Meta:
        verbose_name = "Plantilla de Contrato"
        verbose_name_plural = "Plantillas de Contrato"


class ContratoGenerado(models.Model):
    """
    Almacena la versión final y única del contrato generado para cada venta.
    """
    venta = models.OneToOneField(
        VentaViaje, 
        on_delete=models.CASCADE, 
        related_name='contrato',
        verbose_name="Venta Asociada"
    )
    plantilla = models.ForeignKey(
        ContratoPlantilla, 
        on_delete=models.SET_NULL, 
        null=True, 
        verbose_name="Plantilla Base Utilizada"
    ) 
    
    contenido_final = models.TextField(verbose_name="Contrato Final")
    
    archivo_pdf = models.FileField(
        upload_to='contratos/', 
        null=True, 
        blank=True, 
        verbose_name="Archivo PDF del Contrato"
    ) 
    
    fecha_generacion = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        plantilla_nombre = self.plantilla.nombre if self.plantilla else 'Plantilla eliminada'
        return f"Contrato Venta {self.venta.pk} ({plantilla_nombre})"

    class Meta:
        verbose_name = "Contrato Generado"
        verbose_name_plural = "Contratos Generados"


class Proveedor(models.Model):
    """
    Catálogo de proveedores externos que brindan servicios para las ventas.
    """
    SERVICIO_CHOICES = [
        ('VUELOS', 'Vuelos'),
        ('HOTELES', 'Hoteles'),
        ('ALOJAMIENTO_ALTERNO', 'Alojamiento Alterno'),
        ('TOURS', 'Tours y Actividades'),
        ('CRUCERO', 'Crucero'),
        ('TRASLADOS', 'Traslados'),
        ('CIRCUITOS', 'Circuitos Internacionales'),
        ('PAQUETES', 'Paquetes'),
        ('TRAMITE_DOCS', 'Trámites de Documentación'),
        ('SEGUROS_VIAJE', 'Seguros de Viaje'),
        ('RENTA_AUTOS', 'Renta de Autos'),
        ('TODO', 'Todo'),
    ]

    nombre = models.CharField(max_length=255, verbose_name="Nombre del Proveedor")
    razon_social = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Razón Social"
    )
    rfc = models.CharField(
        max_length=13,
        blank=True,
        null=True,
        verbose_name="RFC"
    )
    condiciones_comerciales = models.TextField(
        blank=True,
        null=True,
        verbose_name="Condiciones Comerciales",
        help_text="Términos, condiciones y acuerdos comerciales con el proveedor"
    )
    telefono = models.CharField(max_length=30, blank=True, verbose_name="Teléfono")
    ejecutivo = models.CharField(max_length=255, blank=True, verbose_name="Ejecutivo a Cargo")
    # ✅ Campos de contacto del ejecutivo
    telefono_ejecutivo = models.CharField(max_length=30, blank=True, verbose_name="Contacto del Ejecutivo")
    email_ejecutivo = models.EmailField(blank=True, verbose_name="Email del Ejecutivo")
    # ✅ Cambiado a TextField para almacenar múltiples servicios separados por comas
    servicios = models.TextField(
        blank=True,
        verbose_name="Servicios que Ofrece (Selección Múltiple)",
        help_text="Códigos de servicios seleccionados separados por coma (ej. VUELOS,HOTELES,TOURS)."
    )
    link = models.URLField(blank=True, verbose_name="Link del Proveedor")
    genera_factura = models.BooleanField(default=False, verbose_name="Genera Factura Automática")
    metodo_pago_preferencial = models.BooleanField(
        default=False,
        verbose_name="Método de Pago Preferencial",
        help_text="Si está activo, las ventas nacionales con este proveedor mostrarán la tabla de abonos al proveedor."
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ["nombre"]

    def __str__(self):
        if self.servicios:
            servicios_display = ', '.join([
                dict(self.SERVICIO_CHOICES).get(s.strip(), s.strip())
                for s in self.servicios.split(',') if s.strip()
            ])
            return f"{self.nombre} ({servicios_display})"
        return f"{self.nombre}"

    def get_servicios_display(self):
        """Retorna una lista de los nombres de servicios seleccionados."""
        if not self.servicios:
            return []
        servicios_dict = dict(self.SERVICIO_CHOICES)
        return [
            servicios_dict.get(s.strip(), s.strip())
            for s in self.servicios.split(',') if s.strip()
        ]

    def tiene_servicio(self, codigo_servicio):
        """Verifica si el proveedor ofrece un servicio específico."""
        if not self.servicios:
            return False
        return codigo_servicio.strip() in [s.strip() for s in self.servicios.split(',')]


class AbonoProveedor(models.Model):
    """
    Modelo para gestionar abonos solicitados a proveedores en ventas internacionales.
    Flujo: Vendedor solicita → Contador aprueba → Contador confirma con comprobante → Completo
    """
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('COMPLETADO', 'Completado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    venta = models.ForeignKey(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='abonos_proveedor',
        verbose_name="Venta Asociada"
    )
    proveedor = models.CharField(
        max_length=255,
        verbose_name="Proveedor",
        help_text="Nombre del proveedor al que se abonará"
    )
    
    # Montos (puede ser MXN con conversión a USD)
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto a Abonar"
    )
    monto_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Monto en USD"
    )
    tipo_cambio_aplicado = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="Tipo de Cambio Aplicado",
        help_text="Tipo de cambio usado para convertir MXN a USD"
    )
    
    # Flujo de estados
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE',
        verbose_name="Estado"
    )
    
    # Solicitud inicial (vendedor)
    solicitud_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='abonos_proveedor_solicitados',
        verbose_name="Solicitado Por"
    )
    fecha_solicitud = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Solicitud"
    )
    nota_solicitud = models.TextField(
        blank=True,
        verbose_name="Nota de Solicitud",
        help_text="Notas o comentarios sobre el abono solicitado"
    )
    
    # Aprobación (contador)
    aprobado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='abonos_proveedor_aprobados',
        verbose_name="Aprobado Por"
    )
    fecha_aprobacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Aprobación"
    )
    
    # Confirmación/Completado (contador con comprobante)
    confirmado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='abonos_proveedor_confirmados',
        verbose_name="Confirmado Por"
    )
    fecha_confirmacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Confirmación"
    )
    comprobante = models.FileField(
        upload_to='comprobantes_proveedor/%Y/%m/%d/',
        null=True,
        blank=True,
        verbose_name="Comprobante de Abono",
        help_text="Comprobante de pago al proveedor (imagen JPG, PNG o PDF)",
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
    )
    nota_confirmacion = models.TextField(
        blank=True,
        verbose_name="Nota de Confirmación",
        help_text="Notas adicionales al confirmar el abono"
    )
    
    # Cancelación
    cancelado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='abonos_proveedor_cancelados',
        verbose_name="Cancelado Por"
    )
    fecha_cancelacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Cancelación"
    )
    motivo_cancelacion = models.TextField(
        blank=True,
        verbose_name="Motivo de Cancelación"
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Abono a Proveedor"
        verbose_name_plural = "Abonos a Proveedores"
        ordering = ['-fecha_solicitud']
        indexes = [
            models.Index(fields=['venta', 'estado']),
            models.Index(fields=['estado', 'fecha_solicitud']),
        ]
    
    def __str__(self):
        return f"Abono #{self.pk} - {self.proveedor} - ${self.monto:,.2f} - {self.get_estado_display()}"
    
    def puede_modificar(self, user):
        """Verifica si un usuario puede modificar este abono."""
        # Solo JEFE puede modificar
        from usuarios.models import Perfil
        if hasattr(user, 'perfil'):
            return user.perfil.rol == 'JEFE'
        return False
    
    def puede_aprobar(self, user):
        """Verifica si un usuario puede aprobar este abono."""
        from usuarios.models import Perfil
        if hasattr(user, 'perfil'):
            return user.perfil.rol in ['CONTADOR', 'JEFE']
        return False
    
    def puede_confirmar(self, user):
        """Verifica si un usuario puede confirmar este abono."""
        from usuarios.models import Perfil
        if hasattr(user, 'perfil'):
            return user.perfil.rol in ['CONTADOR', 'JEFE']
        return False
    
    def puede_cancelar(self, user):
        """Verifica si un usuario puede cancelar este abono."""
        from usuarios.models import Perfil
        if hasattr(user, 'perfil'):
            return user.perfil.rol in ['CONTADOR', 'JEFE']
        return False

    @property
    def monto_usd_para_display(self):
        """Para ventas INT: monto en USD a mostrar (monto_usd si existe, si no monto/tipo_cambio)."""
        if self.monto_usd is not None and self.monto_usd > 0:
            return self.monto_usd
        tc = self.tipo_cambio_aplicado or (getattr(self.venta, 'tipo_cambio', None) if self.venta_id else None)
        if tc and tc > 0 and self.monto:
            return (self.monto / tc).quantize(Decimal('0.01'))
        return None

    @property
    def tipo_cambio_para_display(self):
        """Tipo de cambio usado al registrar (para mostrar en plantillas INT)."""
        return self.tipo_cambio_aplicado or (getattr(self.venta, 'tipo_cambio', None) if self.venta_id else None)


class ConfirmacionVenta(models.Model):
    """
    Archivos de confirmación asociados a una venta (boletos, vouchers, etc.).
    """
    venta = models.ForeignKey(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='confirmaciones',
        verbose_name="Venta Asociada"
    )
    archivo = models.FileField(
        upload_to='confirmaciones/%Y/%m/%d/',
        verbose_name="Archivo de Confirmación"
    )
    nota = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Descripción / Nota"
    )
    subido_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='confirmaciones_subidas',
        verbose_name="Subido Por"
    )
    fecha_subida = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Subida")

    class Meta:
        verbose_name = "Confirmación de Venta"
        verbose_name_plural = "Confirmaciones de Venta"
        ordering = ('-fecha_subida',)

    def __str__(self):
        return f"Confirmación {self.nombre_archivo} - Venta {self.venta_id}"

    @property
    def nombre_archivo(self):
        if self.archivo:
            return os.path.basename(self.archivo.name)
        return ""

    @property
    def es_pdf(self):
        return self.nombre_archivo.lower().endswith('.pdf')

    @property
    def es_imagen(self):
        return self.nombre_archivo.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'))

    @property
    def extension(self):
        name = self.nombre_archivo
        if '.' in name:
            return name.split('.')[-1].upper()
        return ""


# ------------------- MODELO: Ejecutivo -------------------

class Oficina(models.Model):
    """
    Representa una oficina física de la agencia.
    Puede ser propia o franquicia.
    """
    TIPO_CHOICES = [
        ('PROPIA', 'Propia'),
        ('FRANQUICIA', 'Franquicia'),
    ]
    
    nombre = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nombre de la Oficina",
        help_text="Nombre único que identifica la oficina"
    )
    direccion = models.TextField(
        verbose_name="Dirección",
        help_text="Dirección completa (punto en el mapa)"
    )
    ubicacion = models.CharField(
        max_length=255,
        verbose_name="Ubicación",
        help_text="Descripción de ubicación dentro de plaza/edificio (ej: Local 15, Piso 2, Oficina 201)"
    )
    responsable = models.CharField(
        max_length=255,
        verbose_name="Responsable",
        help_text="Nombre del responsable de la oficina"
    )
    encargado = models.CharField(
        max_length=255,
        verbose_name="Encargado",
        help_text="Nombre del encargado de la oficina"
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de Oficina",
        help_text="Indica si la oficina es propia o franquicia"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_actualizacion = models.DateTimeField(auto_now=True, verbose_name="Fecha de Actualización")
    activa = models.BooleanField(
        default=True,
        verbose_name="Activa",
        help_text="Indica si la oficina está activa"
    )
    
    class Meta:
        verbose_name = "Oficina"
        verbose_name_plural = "Oficinas"
        ordering = ['nombre']
    
    def __str__(self):
        return f"{self.nombre} ({self.get_tipo_display()})"


class Ejecutivo(models.Model):
    """
    Representa a los ejecutivos/vendedores gestionados por el usuario Jefe.
    """
    TIPO_VENDEDOR_CHOICES = [
        ('MOSTRADOR', 'Asesor de Mostrador'),
        ('CAMPO', 'Asesor de Campo'),
        ('ISLA', 'Asesor de Isla'),
    ]
    
    nombre_completo = models.CharField(max_length=255, verbose_name="Nombre Completo")
    direccion = models.TextField(verbose_name="Dirección")
    telefono = models.CharField(max_length=25, verbose_name="Teléfono de Contacto")
    email = models.EmailField(
        verbose_name="Correo Electrónico",
        unique=True,
        blank=True,
        null=True,
        help_text="Será usado para crear sus credenciales."
    )
    oficina = models.ForeignKey(
        'Oficina',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ejecutivos',
        verbose_name="Oficina",
        help_text="Oficina a la que pertenece el ejecutivo"
    )
    tipo_vendedor = models.CharField(
        max_length=10,
        choices=TIPO_VENDEDOR_CHOICES,
        default='MOSTRADOR',
        verbose_name="Tipo de Asesor",
        help_text="Determina el sistema de comisiones: Asesor de Mostrador, Campo o Isla"
    )
    sueldo_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('10000.00'),
        verbose_name="Sueldo Base"
    )
    fecha_ingreso = models.DateField(
        verbose_name="Fecha de Ingreso",
        help_text="Fecha en que el ejecutivo ingresó a la empresa",
        blank=True,
        null=True
    )
    fecha_nacimiento = models.DateField(
        verbose_name="Fecha de Nacimiento",
        help_text="Fecha de nacimiento del ejecutivo",
        blank=True,
        null=True
    )
    acta_nacimiento = models.FileField(
        upload_to='ejecutivos/documentos/%Y/%m/%d/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        verbose_name="Acta de Nacimiento",
        help_text="Sube el acta de nacimiento en formato PDF o imagen (JPG, PNG)"
    )
    ine_imagen = models.FileField(
        upload_to='ejecutivos/documentos/%Y/%m/%d/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        verbose_name="INE",
        help_text="Sube la identificación oficial (INE) en formato PDF o imagen (JPG, PNG)"
    )
    comprobante_domicilio = models.FileField(
        upload_to='ejecutivos/documentos/%Y/%m/%d/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        verbose_name="Comprobante de Domicilio",
        help_text="Sube el comprobante de domicilio en formato PDF o imagen (JPG, PNG)"
    )
    usuario = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ejecutivo_asociado',
        verbose_name="Usuario del Sistema"
    )
    # SEGURIDAD: Campo 'ultima_contrasena' eliminado - nunca almacenar contraseñas en texto plano
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ejecutivo"
        verbose_name_plural = "Ejecutivos"
        ordering = ['nombre_completo']

    def __str__(self):
        return self.nombre_completo


# ------------------- MODELO: Notificacion -------------------

class Notificacion(models.Model):
    """Modelo para almacenar notificaciones para JEFE, CONTADOR y VENDEDOR."""
    TIPO_CHOICES = [
        ('ABONO', 'Abono Registrado'),
        ('LIQUIDACION', 'Venta Liquidada'),
        ('APERTURA', 'Apertura Registrada'),
        ('LOGISTICA', 'Cambio en Logística'),
        ('PAGO_PENDIENTE', 'Pago Pendiente de Confirmación'),
        ('PAGO_CONFIRMADO', 'Pago Confirmado por Contador'),
        ('CANCELACION', 'Venta Cancelada'),
        ('SOLICITUD_ABONO_PROVEEDOR', 'Solicitud de Abono a Proveedor'),
        ('ABONO_PROVEEDOR_APROBADO', 'Abono a Proveedor Aprobado'),
        ('ABONO_PROVEEDOR_COMPLETADO', 'Abono a Proveedor Completado'),
        ('ABONO_PROVEEDOR_CANCELADO', 'Abono a Proveedor Cancelado'),
        ('SOLICITUD_CANCELACION', 'Solicitud de Cancelación'),
        ('CANCELACION_APROBADA', 'Cancelación Aprobada'),
        ('CANCELACION_RECHAZADA', 'Cancelación Rechazada'),
        ('CANCELACION_DEFINITIVA', 'Cancelación Definitiva'),
    ]
    
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notificaciones',
        verbose_name="Usuario"
        # Ahora puede ser JEFE, CONTADOR o VENDEDOR
    )
    tipo = models.CharField(
        max_length=35,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de Notificación"
    )
    mensaje = models.TextField(verbose_name="Mensaje")
    venta = models.ForeignKey(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='notificaciones',
        null=True,
        blank=True,
        verbose_name="Venta Relacionada"
    )
    abono = models.ForeignKey(
        'ventas.AbonoPago',
        on_delete=models.CASCADE,
        related_name='notificaciones',
        null=True,
        blank=True,
        verbose_name="Abono Relacionado"
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    vista = models.BooleanField(default=False, verbose_name="Vista")
    fecha_vista = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Vista")
    
    # Campos para confirmación de pagos
    confirmado = models.BooleanField(default=False, verbose_name="Confirmado")
    confirmado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notificaciones_confirmadas',
        verbose_name="Confirmado Por",
        limit_choices_to={'perfil__rol': 'CONTADOR'}
    )
    confirmado_en = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Confirmación")
    # Relación con AbonoProveedor
    abono_proveedor = models.ForeignKey(
        'ventas.AbonoProveedor',
        on_delete=models.CASCADE,
        related_name='notificaciones',
        null=True,
        blank=True,
        verbose_name="Abono a Proveedor Relacionado"
    )
    # Relación con SolicitudCancelacion
    solicitud_cancelacion = models.ForeignKey(
        'ventas.SolicitudCancelacion',
        on_delete=models.CASCADE,
        related_name='notificaciones',
        null=True,
        blank=True,
        verbose_name="Solicitud de Cancelación Relacionada"
    )
    
    class Meta:
        verbose_name = "Notificación"
        verbose_name_plural = "Notificaciones"
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['usuario', 'vista']),
            models.Index(fields=['-fecha_creacion']),
        ]
    
    def __str__(self):
        return f"{self.get_tipo_display()} - {self.usuario.username} ({'Vista' if self.vista else 'No vista'})"
    
    def marcar_como_vista(self):
        """Marca la notificación como vista."""
        from django.utils import timezone
        self.vista = True
        self.fecha_vista = timezone.now()
        self.save(update_fields=['vista', 'fecha_vista'])


# ------------------- MODELO: PlantillaConfirmacion -------------------

class PlantillaConfirmacion(models.Model):
    """
    Almacena las plantillas de confirmación llenadas por el vendedor.
    Cada plantilla puede ser de tipo: vuelo único, vuelo redondo, hospedaje, traslado, o genérica.
    """
    
    TIPO_CHOICES = [
        ('VUELO_UNICO', 'Vuelo Sencillo'),
        ('VUELO_REDONDO', 'Vuelo Redondo'),
        ('HOSPEDAJE', 'Hospedaje'),
        ('TRASLADO', 'Traslado'),
        ('GENERICA', 'Genérica (Cualquier captura)'),
    ]
    
    venta = models.ForeignKey(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='plantillas_confirmacion',
        verbose_name="Venta Asociada"
    )
    
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        verbose_name="Tipo de Plantilla"
    )
    
    # Almacenamos los datos en formato JSON para flexibilidad
    datos = models.JSONField(
        default=dict,
        verbose_name="Datos de la Plantilla",
        help_text="Almacena todos los campos llenados de la plantilla en formato JSON"
    )
    
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plantillas_creadas',
        verbose_name="Creado Por"
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    fecha_actualizacion = models.DateTimeField(auto_now=True, verbose_name="Fecha de Actualización")
    
    class Meta:
        verbose_name = "Plantilla de Confirmación"
        verbose_name_plural = "Plantillas de Confirmación"
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['venta', 'tipo']),
            models.Index(fields=['-fecha_creacion']),
        ]
    
    def __str__(self):
        return f"{self.get_tipo_display()} - Venta #{self.venta.pk} - {self.fecha_creacion.strftime('%d/%m/%Y')}"


# ------------------- MODELO: Cotización -------------------
class Cotizacion(models.Model):
    folio = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Folio de Cotización",
        help_text="Identificador único de la cotización. Formato: COT-AAAAMMDD-XX"
    )
    ESTADO_CHOICES = [
        ('BORRADOR', 'Borrador'),
        ('ENVIADA', 'Enviada'),
        ('CONVERTIDA', 'Convertida a venta'),
    ]

    cliente = models.ForeignKey('crm.Cliente', on_delete=models.PROTECT, related_name='cotizaciones')
    vendedor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cotizaciones_creadas')
    titulo = models.CharField(max_length=200, default='Cotización')
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    origen = models.CharField(max_length=150, blank=True)
    destino = models.CharField(max_length=150, blank=True)
    dias = models.PositiveIntegerField(default=0)
    noches = models.PositiveIntegerField(default=0)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)

    pasajeros = models.PositiveIntegerField(default=1)
    adultos = models.PositiveIntegerField(default=1)
    menores = models.PositiveIntegerField(default=0)
    edades_menores = models.TextField(blank=True, help_text='Nombre y edad de los menores (ej. Juan - 5; Ana - 8)')

    propuestas = models.JSONField(default=dict, blank=True)
    notas = models.TextField(blank=True)
    total_estimado = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='BORRADOR')

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creada_en']

    def save(self, *args, **kwargs):
        if not self.folio:
            hoy = timezone.localdate()
            fecha_str = hoy.strftime('%Y%m%d')
            consecutivo = Cotizacion.objects.filter(creada_en__date=hoy).exclude(folio__isnull=True).exclude(folio='').count() + 1
            folio = f"COT-{fecha_str}-{consecutivo:02d}"
            while Cotizacion.objects.filter(folio=folio).exclude(pk=self.pk).exists():
                consecutivo += 1
                folio = f"COT-{fecha_str}-{consecutivo:02d}"
            self.folio = folio
        if not self.slug:
            base = slugify(f"{self.cliente.nombre_completo_display}-{timezone.now().strftime('%Y%m%d%H%M%S')}")
            slug_unique = base
            num = 1
            while Cotizacion.objects.filter(slug=slug_unique).exclude(pk=self.pk).exists():
                slug_unique = f"{base}-{num}"
                num += 1
            self.slug = slug_unique
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Cotización {self.pk} - {self.cliente.nombre_completo_display}"


# ------------------- MODELOS DE COMISIONES -------------------

class ComisionVenta(models.Model):
    """
    Almacena el cálculo de comisión para cada venta individual.
    Permite desglosar las comisiones por venta y rastrear el estado de pago.
    """
    venta = models.ForeignKey(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='comisiones',
        verbose_name="Venta"
    )
    vendedor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comisiones_ventas',
        verbose_name="Vendedor"
    )
    mes = models.IntegerField(verbose_name="Mes")
    anio = models.IntegerField(verbose_name="Año")
    
    TIPO_VENTA_CHOICES = [
        ('NACIONAL', 'Nacional'),
        ('INTERNACIONAL', 'Internacional'),
        ('INTERNACIONAL MXN', 'Internacional MXN'),
        ('VUELO', 'Vuelo Solitario'),
    ]
    tipo_venta = models.CharField(
        max_length=20,
        choices=TIPO_VENTA_CHOICES,
        verbose_name="Tipo de Venta"
    )
    
    # Monto base sobre el que se calcula la comisión
    monto_base_comision = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Monto Base para Comisión"
    )
    
    # Porcentaje aplicado según el total mensual
    porcentaje_aplicado = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Porcentaje Aplicado (%)"
    )
    
    # Comisión calculada (100% del monto)
    comision_calculada = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Comisión Calculada (100%)"
    )
    
    # Comisión pagada (100% si está pagada, 30% si está pendiente)
    comision_pagada = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Comisión Pagada"
    )
    
    # Comisión pendiente (70% restante si está pendiente)
    comision_pendiente = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Comisión Pendiente"
    )
    
    ESTADO_PAGO_CHOICES = [
        ('PAGADA', 'Pagada al 100%'),
        ('PENDIENTE', 'Pendiente de Pago'),
    ]
    estado_pago_venta = models.CharField(
        max_length=20,
        choices=ESTADO_PAGO_CHOICES,
        default='PENDIENTE',
        verbose_name="Estado de Pago de la Venta"
    )
    
    # Detalles en JSON para desglose (tarifa_base, suplementos, tours, impuestos excluidos, etc.)
    detalles = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Detalles de la Comisión",
        help_text="Desglose detallado de la comisión (tarifa_base, suplementos, tours, impuestos excluidos, etc.)"
    )
    
    fecha_calculo = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Cálculo"
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name="Fecha de Actualización"
    )
    
    # Campo para marcar comisiones canceladas por cancelación de venta
    cancelada = models.BooleanField(
        default=False,
        verbose_name="Cancelada",
        help_text="Indica si la comisión fue cancelada debido a la cancelación de la venta"
    )
    fecha_cancelacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Cancelación"
    )
    
    class Meta:
        verbose_name = "Comisión de Venta"
        verbose_name_plural = "Comisiones de Ventas"
        unique_together = ['venta', 'mes', 'anio']
        indexes = [
            models.Index(fields=['vendedor', 'mes', 'anio']),
            models.Index(fields=['venta']),
            models.Index(fields=['cancelada']),
        ]
    
    def __str__(self):
        return f"Comisión Venta #{self.venta.pk} - {self.vendedor.username} - {self.mes}/{self.anio}"


class ComisionMensual(models.Model):
    """
    Almacena el resumen mensual de comisiones por vendedor.
    Incluye totales, porcentajes aplicados y bonos.
    """
    vendedor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comisiones_mensuales',
        verbose_name="Vendedor"
    )
    mes = models.IntegerField(verbose_name="Mes")
    anio = models.IntegerField(verbose_name="Año")
    
    TIPO_VENDEDOR_CHOICES = [
        ('MOSTRADOR', 'Asesor de Mostrador'),
        ('CAMPO', 'Asesor de Campo'),
        ('ISLA', 'Asesor de Isla'),
    ]
    tipo_vendedor = models.CharField(
        max_length=20,
        choices=TIPO_VENDEDOR_CHOICES,
        default='MOSTRADOR',
        verbose_name="Tipo de Vendedor"
    )
    
    # Total de ventas del mes (para determinar el porcentaje)
    total_ventas_mes = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Total de Ventas del Mes"
    )
    
    # Porcentaje de comisión según la escala alcanzada
    porcentaje_comision = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Porcentaje de Comisión (%)"
    )
    
    # Bono extra del 1% si supera $500,000
    bono_extra = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Bono Extra (1% sobre $500,000+)"
    )
    
    # Suma de comisiones de ventas pagadas al 100%
    comision_total_pagada = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Comisión Total Pagada"
    )
    
    # Suma de comisiones pendientes (30% de ventas no pagadas)
    comision_total_pendiente = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Comisión Total Pendiente"
    )
    
    # Total de comisión (pagada + pendiente + bono)
    comision_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Comisión Total"
    )
    
    # Campos para ajuste manual de comisión (especialmente para ISLA)
    porcentaje_ajustado_manual = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Porcentaje Ajustado Manualmente (%)",
        help_text="Porcentaje de comisión ajustado manualmente. Si está presente, sobrescribe el cálculo automático."
    )
    ajustado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comisiones_ajustadas',
        verbose_name="Ajustado Por",
        help_text="Usuario que realizó el ajuste manual"
    )
    fecha_ajuste = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Ajuste",
        help_text="Fecha en que se realizó el ajuste manual"
    )
    nota_ajuste = models.TextField(
        blank=True,
        verbose_name="Nota del Ajuste",
        help_text="Justificación o nota sobre el ajuste manual realizado"
    )
    
    fecha_calculo = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Cálculo"
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name="Fecha de Actualización"
    )
    
    # Archivo Excel generado (opcional)
    archivo_excel = models.FileField(
        upload_to='comisiones_excel/%Y/%m/',
        blank=True,
        null=True,
        verbose_name="Archivo Excel Generado"
    )
    
    class Meta:
        verbose_name = "Comisión Mensual"
        verbose_name_plural = "Comisiones Mensuales"
        unique_together = ['vendedor', 'mes', 'anio', 'tipo_vendedor']
        indexes = [
            models.Index(fields=['vendedor', 'mes', 'anio']),
            models.Index(fields=['tipo_vendedor', 'mes', 'anio']),
        ]
        ordering = ['-anio', '-mes', 'vendedor']
    
    def __str__(self):
        return f"Comisión Mensual - {self.vendedor.username} - {self.mes}/{self.anio}"


# ------------------- MODELO: SolicitudCancelacion -------------------

class SolicitudCancelacion(models.Model):
    """
    Modelo para gestionar las solicitudes de cancelación de ventas.
    Flujo: Vendedor solicita → Director aprueba → Vendedor cancela definitivamente
    """
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente de Aprobación'),
        ('APROBADA', 'Aprobada'),
        ('RECHAZADA', 'Rechazada'),
        ('CANCELADA', 'Cancelada Definitivamente'),
    ]
    
    venta = models.OneToOneField(
        VentaViaje,
        on_delete=models.CASCADE,
        related_name='solicitud_cancelacion',
        verbose_name="Venta"
    )
    solicitado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='solicitudes_cancelacion',
        verbose_name="Solicitado Por"
    )
    motivo = models.TextField(
        verbose_name="Motivo de la Cancelación",
        help_text="Razón por la cual se solicita la cancelación de la venta"
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE',
        verbose_name="Estado"
    )
    aprobado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelaciones_aprobadas',
        verbose_name="Aprobado Por"
    )
    fecha_solicitud = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Solicitud"
    )
    fecha_aprobacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Aprobación"
    )
    fecha_cancelacion_definitiva = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Fecha de Cancelación Definitiva"
    )
    motivo_rechazo = models.TextField(
        blank=True,
        verbose_name="Motivo de Rechazo",
        help_text="Razón por la cual se rechazó la solicitud de cancelación"
    )
    
    class Meta:
        verbose_name = "Solicitud de Cancelación"
        verbose_name_plural = "Solicitudes de Cancelación"
        ordering = ['-fecha_solicitud']
        indexes = [
            models.Index(fields=['venta', 'estado']),
            models.Index(fields=['estado', 'fecha_solicitud']),
            models.Index(fields=['solicitado_por']),
        ]
    
    def __str__(self):
        return f"Solicitud Cancelación Venta #{self.venta.pk} - {self.get_estado_display()}"


# ------------------- SIGNALS -------------------

@receiver(post_save, sender=VentaViaje)
def crear_registros_iniciales(sender, instance, created, **kwargs):
    """
    Asegura la creación del registro de Logística al crear una VentaViaje.
    """
    if created:
        Logistica.objects.get_or_create(venta=instance)

