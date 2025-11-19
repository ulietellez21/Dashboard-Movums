from django.db import models

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
    
    # ------------------- Campos Comunes -------------------
    telefono = models.CharField(
        max_length=20, 
        unique=True, 
        help_text="Necesario para el envío de WhatsApp."
    )
    email = models.EmailField(blank=True, null=True)
    
    fuente_contacto = models.CharField(max_length=3, choices=FUENTE_CHOICES, default='OTR')
    
    notas = models.TextField(blank=True, null=True)
    
    # ------------------- Datos Adicionales del Particular -------------------
    fecha_nacimiento = models.DateField(blank=True, null=True)
    documento_identificacion = models.CharField(max_length=50, unique=True, blank=True, null=True,
                                                   help_text="Pasaporte, INE u otra identificación.")
    preferencias_viaje = models.TextField(blank=True, help_text="Notas sobre sus gustos de viaje (Playa, Aventura...).")
    
    # ------------------- Fechas de Control -------------------
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

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