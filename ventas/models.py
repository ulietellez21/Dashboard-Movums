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
    ]
    tipo_viaje = models.CharField(
        max_length=3, 
        choices=TIPO_VIAJE_CONTRATO_CHOICES, 
        default='NAC',
        verbose_name="Tipo de Viaje (Plantilla de Contrato)"
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

    fecha_inicio_viaje = models.DateField(verbose_name="Fecha de Ida (Inicio de Viaje)")
    fecha_fin_viaje = models.DateField(blank=True, null=True, verbose_name="Fecha de Regreso (Fin de Viaje)")
    
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
    
    # Modo de pago para la apertura
    MODO_PAGO_CHOICES = [
        ('EFE', 'Efectivo'),
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
        help_text="Estado de confirmación del pago por el contador"
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
        verbose_name="Tipo de Cambio (USD a MXN)",
        help_text="Tipo de cambio del día para convertir dólares a pesos mexicanos."
    )
    
    fecha_vencimiento_pago = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Fecha Límite de Pago Total"
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
        help_text="Estado general de la venta"
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

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
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
        
        # 4. Generar o actualizar el Contrato solo después de que el objeto tiene PK
        if self.pk:
            try:
                # Importación local para evitar bucles de importación
                from .utils import generar_contrato_para_venta 

                generar_contrato_para_venta(self.pk)
            except Exception as e:
                logger.warning(f"Falló la generación del contrato para Venta {self.pk}: {e}", exc_info=True)
    
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
    
    @property
    def total_pagado(self):
        """
        Calcula el total pagado incluyendo solo abonos confirmados.
        Para abonos con Transferencia/Tarjeta, solo cuenta los confirmados por el contador.
        Para abonos con Efectivo, se cuentan todos (ya que se confirman automáticamente).
        """
        # Sumar solo abonos confirmados o abonos en efectivo (que se confirman automáticamente)
        # Un abono está confirmado si:
        # 1. confirmado=True (confirmado por contador), O
        # 2. forma_pago='EFE' (efectivo, se confirma automáticamente)
        total_abonos = self.abonos.filter(
            Q(confirmado=True) | Q(forma_pago='EFE')
        ).aggregate(Sum('monto'))['monto__sum']
        total_abonos = total_abonos if total_abonos is not None else Decimal('0.00')
        
        # Sumar el monto de apertura solo si está confirmado o es efectivo
        monto_apertura = Decimal('0.00')
        if self.cantidad_apertura and self.cantidad_apertura > 0:
            # Si la apertura es efectivo, liga de pago o directo a proveedor, se cuenta automáticamente
            if self.modo_pago_apertura in ['EFE', 'LIG', 'PRO']:
                monto_apertura = self.cantidad_apertura
            # Si la apertura es transferencia/tarjeta/depósito/crédito:
            # - Si está en 'EN_CONFIRMACION', NO se cuenta (pendiente de confirmación del contador)
            # - Si el estado NO es 'EN_CONFIRMACION', se cuenta (significa que ya fue confirmada)
            # IMPORTANTE: Una vez que el contador confirma la apertura, el estado cambia temporalmente 
            # a 'COMPLETADO' y luego puede cambiar a 'PENDIENTE' si aún falta pagar. En ambos casos,
            # la apertura debe contarse porque ya fue confirmada.
            elif self.modo_pago_apertura in ['TRN', 'TAR', 'DEP', 'CRE']:
                # IMPORTANTE: La lógica es simple:
                # - Si está en 'EN_CONFIRMACION', NO se cuenta (pendiente de confirmación del contador)
                # - Si NO está en 'EN_CONFIRMACION', se cuenta porque:
                #   1. Ya fue confirmada por el contador (estado cambió de EN_CONFIRMACION a COMPLETADO/PENDIENTE)
                #   2. O nunca necesitó confirmación (estado siempre fue PENDIENTE desde el inicio)
                # Una vez que el contador confirma, el estado cambia de 'EN_CONFIRMACION' a 'COMPLETADO'
                # y luego puede cambiar a 'PENDIENTE' si aún falta pagar. En ambos casos, la apertura
                # debe contarse porque ya fue confirmada.
                if self.estado_confirmacion != 'EN_CONFIRMACION':
                    monto_apertura = self.cantidad_apertura
        
        total = total_abonos + monto_apertura

        # Restar el abono virtual de promociones si ya se aplicó, para no marcar como pagada
        if self.descuento_promociones_aplicado_como_pago and self.descuento_promociones_mxn:
            total = total - (self.descuento_promociones_mxn or Decimal('0.00'))

        return max(total, Decimal('0.00'))

    @property
    def costo_total_con_modificacion(self):
        """
        Calcula el costo total incluyendo el costo de modificación.
        Este es el costo final que debe pagar el cliente.
        """
        costo_mod = self.costo_modificacion if self.costo_modificacion else Decimal('0.00')
        total = self.costo_venta_final + costo_mod
        if self.aplica_descuento_kilometros:
            total -= self.descuento_kilometros_mxn
        return max(Decimal('0.00'), total)

    @property
    def total_con_descuento(self):
        """
        Total de la venta considerando modificaciones y aplicando el descuento Movums.
        """
        total = self.costo_venta_final + (self.costo_modificacion or Decimal('0.00'))
        if self.aplica_descuento_kilometros:
            total -= self.descuento_kilometros_mxn
        return max(Decimal('0.00'), total)

    @property
    def saldo_restante(self):
        """
        Calcula el saldo restante usando el total final con descuentos (kilómetros y promociones).
        """
        # Calcular el total final con descuentos
        costo_base = (self.costo_venta_final or Decimal('0.00')) + (self.costo_modificacion or Decimal('0.00'))
        descuento_km = self.descuento_kilometros_mxn or Decimal('0.00')
        descuento_promo = self.descuento_promociones_mxn or Decimal('0.00')
        total_descuentos = descuento_km + descuento_promo
        total_final = costo_base - total_descuentos
        
        saldo = total_final - self.total_pagado
        # Crucial para la estabilidad del dashboard: el saldo nunca es negativo
        return max(Decimal('0.00'), saldo)
    
    # ------------------- PROPIEDADES PARA VENTAS INTERNACIONALES (USD) -------------------
    
    @property
    def total_usd(self):
        """Calcula el total en USD para ventas internacionales."""
        if self.tipo_viaje != 'INT' or not self.tipo_cambio or self.tipo_cambio <= 0:
            return Decimal('0.00')
        tarifa_base = self.tarifa_base_usd or Decimal('0.00')
        impuestos = self.impuestos_usd or Decimal('0.00')
        suplementos = self.suplementos_usd or Decimal('0.00')
        tours = self.tours_usd or Decimal('0.00')
        return tarifa_base + impuestos + suplementos + tours
    
    @property
    def cantidad_apertura_usd(self):
        """Convierte la cantidad de apertura de MXN a USD para ventas internacionales."""
        if self.tipo_viaje != 'INT' or not self.tipo_cambio or self.tipo_cambio <= 0 or not self.cantidad_apertura:
            return Decimal('0.00')
        return (self.cantidad_apertura / self.tipo_cambio).quantize(Decimal('0.01'))
    
    @property
    def total_pagado_usd(self):
        """Convierte el total pagado de MXN a USD para ventas internacionales."""
        if self.tipo_viaje != 'INT' or not self.tipo_cambio or self.tipo_cambio <= 0:
            return Decimal('0.00')
        total_usd_abonos = Decimal('0.00')
        for abono in self.abonos.filter(confirmado=True):
            if abono.monto_usd is not None and abono.tipo_cambio_aplicado:
                total_usd_abonos += abono.monto_usd
            else:
                total_usd_abonos += (abono.monto / self.tipo_cambio)
        return (self.cantidad_apertura_usd + total_usd_abonos).quantize(Decimal('0.01'))
    
    @property
    def saldo_restante_usd(self):
        """Convierte el saldo restante de MXN a USD para ventas internacionales."""
        if self.tipo_viaje != 'INT' or not self.tipo_cambio or self.tipo_cambio <= 0:
            return Decimal('0.00')
        saldo_usd = self.total_usd - self.total_pagado_usd
        return saldo_usd.quantize(Decimal('0.01')) if saldo_usd > 0 else Decimal('0.00')
    
    @property
    def costo_total_con_modificacion_usd(self):
        """Convierte el costo total con modificación de MXN a USD para ventas internacionales."""
        if self.tipo_viaje != 'INT' or not self.tipo_cambio or self.tipo_cambio <= 0:
            return Decimal('0.00')
        costo_mxn = self.costo_total_con_modificacion
        return (costo_mxn / self.tipo_cambio).quantize(Decimal('0.01'))
    
    @property
    def esta_pagada(self):
        return self.saldo_restante <= Decimal('0.00')
    
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
        
        # Apertura confirmada: tiene comprobante subido y modo de pago que requiere confirmación
        # Para crédito: no requiere comprobante, solo que el estado no sea EN_CONFIRMACION
        # IMPORTANTE: No depender del estado actual, solo verificar si la apertura fue confirmada
        if self.modo_pago_apertura == 'CRE':
            # Para crédito: se considera confirmada si el estado no es EN_CONFIRMACION
            apertura_confirmada = (self.estado_confirmacion != 'EN_CONFIRMACION')
        else:
            apertura_confirmada = (self.cantidad_apertura > 0 and 
                                  self.modo_pago_apertura in ['TRN', 'TAR', 'DEP'] and
                                  self.comprobante_apertura_subido)
        
        # Si hay una apertura confirmada, el estado debe ser COMPLETADO (fue confirmada por el contador)
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
                self.save(update_fields=['estado_confirmacion'])


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
        ('EFE', 'Efectivo'),
        ('TAR', 'Tarjeta'),
        ('DEP', 'Depósito'),
        ('PPL', 'PayPal/Digital'),
        ('LIG', 'Liga de Pago'),
        ('PRO', 'Directo a Proveedor'),
    ]
    
    venta = models.ForeignKey(VentaViaje, on_delete=models.CASCADE, related_name='abonos', verbose_name="Venta Asociada")
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto del Abono")
    forma_pago = models.CharField(max_length=3, choices=FORMA_PAGO_CHOICES, default='TRN', verbose_name="Forma de Pago") 
    
    # ✅ CORRECCIÓN: Se usa datetime.now() como default para que coincida con el tipo DateTimeField.
    fecha_pago = models.DateTimeField(default=datetime.now, verbose_name="Fecha del Pago")
    
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Registrado Por")
    recibo_pdf = models.FileField(upload_to='recibos/', blank=True, null=True, verbose_name="Recibo/Comprobante")
    # Campos para ventas internacionales
    monto_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Monto en USD")
    tipo_cambio_aplicado = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="Tipo de Cambio aplicado")
    
    # Campos para confirmación de pagos por transferencia/tarjeta
    confirmado = models.BooleanField(default=False, verbose_name="Confirmado por Contador")
    confirmado_por = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='abonos_confirmados',
        verbose_name="Confirmado Por",
        limit_choices_to={'perfil__rol': 'CONTADOR'}
    )
    confirmado_en = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Confirmación")
    
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

    class Meta:
        verbose_name = "Servicio logístico"
        verbose_name_plural = "Servicios logísticos"
        ordering = ['orden', 'pk']
        unique_together = ('venta', 'codigo_servicio')

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
    ultima_contrasena = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name="Última Contraseña Asignada"
    )
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
    ]
    
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notificaciones',
        verbose_name="Usuario"
        # Ahora puede ser JEFE, CONTADOR o VENDEDOR
    )
    tipo = models.CharField(
        max_length=20,
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


# ------------------- SIGNALS (Sin cambios) -------------------

@receiver(post_save, sender=VentaViaje)
def crear_registros_iniciales(sender, instance, created, **kwargs):
    """
    Asegura la creación del registro de Logística al crear una VentaViaje.
    """
    if created:
        Logistica.objects.get_or_create(venta=instance)