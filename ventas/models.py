import os

from django.db import models
from django.db.models import Sum
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.urls import reverse
# from crm.models import Cliente # NO se importa aquí, se usa la cadena de referencia
from decimal import Decimal
from datetime import date, datetime # Se asegura la importación de datetime
from django.utils.text import slugify 
from django.core.validators import FileExtensionValidator

# ------------------- MODELO CENTRAL: VentaViaje -------------------

class VentaViaje(models.Model):
    """
    Modelo central que almacena los detalles de la venta, servicios y el estado financiero.
    """
    
    # ------------------- CONSTANTES DE SERVICIOS -------------------
    SERVICIOS_CHOICES = [
        ('VUE', 'Vuelo'),
        ('HOS', 'Hospedaje'),
        ('TRA', 'Traslado (Transporte terrestre)'),
        ('TOU', 'Tour/Excursión'),
        ('CIR', 'Circuito Internacional'),
        ('REN', 'Renta de Auto'),
        ('PAQ', 'Paquete Todo Incluido'),
        ('CRU', 'Crucero'),
        ('SEG', 'Seguro de Viaje'),
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
    
    fecha_vencimiento_pago = models.DateField(
        null=True, 
        blank=True,
        verbose_name="Fecha Límite de Pago Total"
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

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    # ------------------- Propiedades y Métodos -------------------
    
    def save(self, *args, **kwargs):
        """
        Sobrescrive save(). Genera el slug único ANTES de guardar.
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
            
        # 2. Primera y Única llamada a save() para asignar el self.pk.
        super().save(*args, **kwargs) 
        
        # 3. Generar o actualizar el Contrato solo después de que el objeto tiene PK
        if self.pk:
            try:
                # Importación local para evitar bucles de importación
                from .utils import generar_contrato_para_venta 

                generar_contrato_para_venta(self.pk)
            except Exception as e:
                # Se mantiene la impresión de advertencia
                print(f"Advertencia: Falló la generación del contrato para Venta {self.pk}: {e}")

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
        # Incluye el monto de apertura/anticipo más los abonos registrados
        total_abonos = self.abonos.aggregate(Sum('monto'))['monto__sum']
        total_abonos = total_abonos if total_abonos is not None else Decimal('0.00')
        # Sumar el monto de apertura al total pagado
        monto_apertura = self.cantidad_apertura if self.cantidad_apertura else Decimal('0.00')
        return total_abonos + monto_apertura

    @property
    def saldo_restante(self):
        saldo = self.costo_venta_final - self.total_pagado
        # Crucial para la estabilidad del dashboard: el saldo nunca es negativo
        return max(Decimal('0.00'), saldo)
    
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


    def __str__(self):
        # Se mantiene la asunción de nombre_completo_display en el Cliente
        return f"Venta {self.pk} - Cliente {self.cliente} ({self.slug})"

    class Meta:
        verbose_name = "Venta de Viaje"
        verbose_name_plural = "Ventas de Viajes"

# ------------------- MODELO: AbonoPago (Corregido el default de fecha_pago) -------------------

class AbonoPago(models.Model):
    """Registra cada pago o abono realizado por el cliente."""
    FORMA_PAGO_CHOICES = [
        ('TRN', 'Transferencia'),
        ('EFE', 'Efectivo'),
        ('TAR', 'Tarjeta'),
        ('DEP', 'Depósito'),
        ('PPL', 'PayPal/Digital'),
    ]
    
    venta = models.ForeignKey(VentaViaje, on_delete=models.CASCADE, related_name='abonos', verbose_name="Venta Asociada")
    monto = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monto del Abono")
    forma_pago = models.CharField(max_length=3, choices=FORMA_PAGO_CHOICES, default='TRN', verbose_name="Forma de Pago") 
    
    # ✅ CORRECCIÓN: Se usa datetime.now() como default para que coincida con el tipo DateTimeField.
    fecha_pago = models.DateTimeField(default=datetime.now, verbose_name="Fecha del Pago")
    
    registrado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Registrado Por")
    recibo_pdf = models.FileField(upload_to='recibos/', blank=True, null=True, verbose_name="Recibo/Comprobante")

    def __str__(self):
        return f"Abono de ${self.monto} ({self.get_forma_pago_display()}) para Venta {self.venta.pk}"

    class Meta:
        verbose_name = "Abono o Pago"
        verbose_name_plural = "Abonos y Pagos"


# ------------------- MODELO: Logistica (Sin cambios) -------------------

class Logistica(models.Model):
    """Rastrea el estado de confirmación de los servicios para una VentaViaje."""
    venta = models.OneToOneField(VentaViaje, on_delete=models.CASCADE, related_name='logistica', verbose_name="Venta Asociada")
    vuelo_confirmado = models.BooleanField(default=False, verbose_name="Vuelo/Transporte Confirmado")
    hospedaje_reservado = models.BooleanField(default=False, verbose_name="Hospedaje Reservado")
    seguro_emitido = models.BooleanField(default=False, verbose_name="Seguro de Viaje Emitido")
    documentos_enviados = models.BooleanField(default=False, verbose_name="Documentación Final Enviada al Cliente")
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Registro de Logística"
        verbose_name_plural = "Registros de Logística"
        
    def __str__(self):
        return f"Logística para Venta {self.venta.pk}"
    
    @property
    def is_fully_confirmed(self):
        return self.vuelo_confirmado and self.hospedaje_reservado and self.seguro_emitido and self.documentos_enviados

    def get_fields(self):
        fields_data = []
        for field in self._meta.fields:
            if isinstance(field, models.BooleanField) and field.name not in ('id', 'venta'):
                fields_data.append({
                    'label': field.verbose_name,
                    'value': getattr(self, field.name),
                    'name': field.name 
                })
        return fields_data


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
        ('TOURS', 'Tours'),
        ('TODO', 'Todo'),
    ]

    nombre = models.CharField(max_length=255, verbose_name="Nombre del Proveedor")
    telefono = models.CharField(max_length=30, blank=True, verbose_name="Teléfono")
    ejecutivo = models.CharField(max_length=255, blank=True, verbose_name="Ejecutivo a Cargo")
    servicio = models.CharField(max_length=10, choices=SERVICIO_CHOICES, verbose_name="Servicio que Ofrece")
    link = models.URLField(blank=True, verbose_name="Link del Proveedor")
    genera_factura = models.BooleanField(default=False, verbose_name="Genera Factura Automática")
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.get_servicio_display()})"


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

class Ejecutivo(models.Model):
    """
    Representa a los ejecutivos/vendedores gestionados por el usuario Jefe.
    """
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
    ubicacion_asignada = models.CharField(max_length=150, verbose_name="Ubicación Asignada")
    sueldo_base = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('10000.00'),
        verbose_name="Sueldo Base"
    )
    documento_pdf = models.FileField(
        upload_to='ejecutivos/%Y/%m/%d/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        verbose_name="Documentos Personales (PDF)"
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
    """Modelo para almacenar notificaciones para el usuario JEFE."""
    TIPO_CHOICES = [
        ('ABONO', 'Abono Registrado'),
        ('LIQUIDACION', 'Venta Liquidada'),
        ('APERTURA', 'Apertura Registrada'),
        ('LOGISTICA', 'Cambio en Logística'),
    ]
    
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notificaciones',
        verbose_name="Usuario",
        limit_choices_to={'perfil__rol': 'JEFE'}  # Solo para JEFE
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
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de Creación")
    vista = models.BooleanField(default=False, verbose_name="Vista")
    fecha_vista = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de Vista")
    
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


# ------------------- SIGNALS (Sin cambios) -------------------

@receiver(post_save, sender=VentaViaje)
def crear_registros_iniciales(sender, instance, created, **kwargs):
    """
    Asegura la creación del registro de Logística al crear una VentaViaje.
    """
    if created:
        Logistica.objects.get_or_create(venta=instance)