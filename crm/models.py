from django.db import models
from decimal import Decimal

class Cliente(models.Model):
    """Almacena la información de contacto y detalles de los clientes,
    diferenciando entre Particulares y Empresas.
    """
    
    # ------------------- DEFINICIONES CLAVE -------------------
    TIPO_CHOICES = [
        ('PARTICULAR', 'Particular'),
        ('EMPRESA', 'Empresa'),
    ]
    
    FUENTE_CHOICES = [
        ('WEB', 'Página Web'),
        ('RED', 'Redes Sociales'),
        ('REF', 'Referido'),
        ('OTR', 'Otro'),
    ]
    
    GENERO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Femenino'),
        ('NS', 'Sin Especificar'),
    ]
    
    # ------------------- Tipo de Cliente -------------------
    tipo_cliente = models.CharField(
        max_length=10, 
        choices=TIPO_CHOICES, 
        default='PARTICULAR',
        verbose_name="Tipo de Cliente"
    )
    
    # ------------------- Información del Particular (Opcional) -------------------
    nombre = models.CharField(max_length=150, blank=True, null=True)
    apellido = models.CharField(max_length=100, blank=True, null=True)
    genero = models.CharField(
        max_length=2,
        choices=GENERO_CHOICES,
        default='NS',
        verbose_name="Género"
    )
    nacionalidad = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nacionalidad")
    
    # ------------------- Información de la Empresa (Opcional) -------------------
    nombre_empresa = models.CharField(
        max_length=150, 
        blank=True, 
        null=True, 
        verbose_name="Razón Social / Nombre de la Empresa"
    )
    rfc = models.CharField(
        max_length=13, 
        unique=True, 
        blank=True, 
        null=True, 
        verbose_name="RFC / ID Fiscal"
    )
    direccion_fiscal = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Dirección Fiscal para Facturación"
    )
    industria = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Industria"
    )
    politicas_viaje_internas = models.TextField(
        blank=True,
        null=True,
        verbose_name="Políticas de Viaje Internas",
        help_text="Políticas y restricciones de viaje de la empresa"
    )
    responsable_administrativo = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Responsable Administrativo"
    )
    credito = models.BooleanField(
        default=False,
        verbose_name="Crédito (si aplica)",
        help_text="Indica si la empresa tiene línea de crédito"
    )
    monto_credito = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Monto de Crédito Asignado",
        help_text="Monto de crédito asignado a la empresa (si aplica)"
    )
    
    # ------------------- Campos Comunes -------------------
    telefono = models.CharField(
        max_length=20, 
        unique=True, 
        help_text="Necesario para el envío de WhatsApp.",
        verbose_name="Teléfono Móvil"
    )
    telefono_adicional = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Teléfono Adicional"
    )
    email = models.EmailField(blank=True, null=True, verbose_name="Correo Electrónico")
    
    fuente_contacto = models.CharField(max_length=3, choices=FUENTE_CHOICES, default='OTR')
    
    notas = models.TextField(blank=True, null=True)
    
    # ------------------- Datos Adicionales del Particular -------------------
    fecha_nacimiento = models.DateField(blank=True, null=True)
    
    # INE
    ine_imagen = models.ImageField(
        upload_to='clientes/ine/',
        blank=True,
        null=True,
        verbose_name="Imagen INE"
    )
    
    # Visa (opcional)
    visa_numero = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Visa")
    visa_vigencia = models.DateField(blank=True, null=True, verbose_name="Vigencia de Visa")
    
    # Pasaporte (opcional)
    pasaporte_numero = models.CharField(max_length=50, blank=True, null=True, verbose_name="Número de Pasaporte")
    pasaporte_vigencia = models.DateField(blank=True, null=True, verbose_name="Vigencia de Pasaporte")
    
    # Campo legacy - mantener por compatibilidad
    documento_identificacion = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                                   help_text="Pasaporte, INE u otra identificación.")
    
    # Empresa asociada (para particulares que pertenecen a una empresa)
    empresa_asociada = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='empleados',
        limit_choices_to={'tipo_cliente': 'EMPRESA'},
        verbose_name="Empresa Asociada"
    )
    
    preferencias_viaje = models.TextField(blank=True, help_text="Notas sobre sus gustos de viaje (Playa, Aventura...).")
    
    # ------------------- Fechas de Control -------------------
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    # ------------------- Métricas -------------------
    cotizaciones_generadas = models.PositiveIntegerField(
        default=0,
        verbose_name="Total de cotizaciones generadas"
    )

    participa_kilometros = models.BooleanField(
        default=True,
        verbose_name="Participa en Kilómetros Movums"
    )
    referencia_programa = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        help_text="Código o nota interna para el programa de lealtad."
    )
    referido_por = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='referidos',
        verbose_name="Referido por"
    )
    kilometros_acumulados = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Kilómetros acumulados históricos"
    )
    kilometros_disponibles = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Kilómetros disponibles"
    )
    ultima_fecha_km = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Última acumulación de kilómetros"
    )
    fecha_ultimo_bono_cumple = models.DateField(
        blank=True,
        null=True,
        verbose_name="Último bono de cumpleaños aplicado"
    )

    # ------------------- PROPIEDAD AGREGADA PARA USO EXTERNO -------------------
    @property
    def nombre_completo_display(self):
        """Retorna el nombre completo (Particular) o el nombre de la empresa para slugs/display."""
        if self.tipo_cliente == 'EMPRESA' and self.nombre_empresa:
            return self.nombre_empresa
        
        # Para particulares o empresas sin razón social
        full_name = f"{self.nombre or ''} {self.apellido or ''}".strip()
        return full_name if full_name else f"Cliente ID: {self.pk}"

    # ------------------- Métodos -------------------
    def __str__(self):
        """Muestra la Razón Social o el Nombre Completo según el tipo para el Admin."""
        # Ahora el método __str__ usa la propiedad
        return self.nombre_completo_display 

    def whatsapp_url(self):
        """Genera el enlace de WhatsApp para el cliente."""
        if self.telefono:
            # Eliminar caracteres no numéricos
            numero_limpio = ''.join(filter(str.isdigit, self.telefono))
            return f"https://wa.me/{numero_limpio}"
        return "#"
    
    @property
    def ultima_venta(self):
        """Retorna el último viaje/venta asociado a este cliente."""
        # Asumiendo que el related_name en VentaViaje a Cliente es 'ventas_asociadas'
        try:
            return self.ventas_asociadas.order_by('-fecha_creacion').first() 
        except:
            return None

    @property
    def valor_kilometros_disponibles(self):
        return (self.kilometros_disponibles or Decimal('0.00')) * Decimal('0.05')


class HistorialKilometros(models.Model):
    TIPO_EVENTO = [
        ('COMPRA', 'Compra de servicios'),
        ('REFERIDO', 'Bonificación por referido'),
        ('CUMPLE', 'Bonificación por cumpleaños'),
        ('CAMPANIA', 'Campaña especial'),
        ('AJUSTE', 'Ajuste manual'),
        ('REDENCION', 'Redención aplicada'),
        ('EXPIRACION', 'Expiración de kilómetros'),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name='historial_kilometros'
    )
    tipo_evento = models.CharField(max_length=12, choices=TIPO_EVENTO)
    descripcion = models.CharField(max_length=255, blank=True, null=True)
    kilometros = models.DecimalField(max_digits=12, decimal_places=2)
    multiplicador = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1.00'))
    valor_equivalente = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_expiracion = models.DateTimeField(blank=True, null=True)
    venta = models.ForeignKey(
        'ventas.VentaViaje',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_kilometros'
    )
    es_redencion = models.BooleanField(default=False)
    expirado = models.BooleanField(default=False, help_text="Indica si este movimiento ya fue procesado para expiración.")

    class Meta:
        ordering = ['-fecha_registro']

    def __str__(self):
        return f"{self.tipo_evento} - {self.kilometros} km ({self.cliente})"


class PromocionKilometros(models.Model):
    """
    Promociones configurables para descuentos o campañas de lealtad.
    """

    TIPO_CHOICES = [
        ('DESCUENTO', 'Descuento % sobre total'),
        ('KM', 'Bonificación de Kilómetros'),
    ]

    CONDICION_CHOICES = [
        ('SIEMPRE', 'Siempre'),
        ('CUMPLE', 'Cumpleaños del cliente'),
        ('MES', 'Mes específico'),
        ('RANGO', 'Rango de fechas'),
    ]

    ALCANCE_CHOICES = [
        ('TODAS', 'Todas las ventas'),
        ('NAC', 'Solo ventas nacionales'),
        ('INT', 'Solo ventas internacionales'),
    ]

    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default='DESCUENTO')
    porcentaje_descuento = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    monto_tope_mxn = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    condicion = models.CharField(max_length=20, choices=CONDICION_CHOICES, default='SIEMPRE')
    valor_condicion = models.CharField(max_length=20, blank=True, null=True, help_text="Ej: mes=2, o día/mes 14-02")
    alcance = models.CharField(max_length=10, choices=ALCANCE_CHOICES, default='TODAS')

    requiere_confirmacion = models.BooleanField(default=False)

    fecha_inicio = models.DateField(blank=True, null=True)
    fecha_fin = models.DateField(blank=True, null=True)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    # Solo para tipo KM: cantidad de kilómetros a bonificar
    kilometros_bono = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Solo aplica si el tipo es Bonificación de Kilómetros."
    )

    class Meta:
        ordering = ['-creada_en']
        verbose_name = "Promoción de Kilómetros"
        verbose_name_plural = "Promociones de Kilómetros"

    def __str__(self):
        return self.nombre