from django import forms
from .models import AbonoPago, Logistica, VentaViaje, Proveedor, Ejecutivo # Aseguramos la importación de VentaViaje
from django.contrib.auth.models import User
from crm.models import Cliente # Importamos Cliente para usarlo en el queryset si es necesario

# Widget personalizado para soportar selección múltiple de archivos
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True
    
    def __init__(self, attrs=None):
        super().__init__(attrs)
        if attrs is not None:
            self.attrs = attrs.copy()
        else:
            self.attrs = {}
        # Asegurar que el atributo multiple esté presente
        self.attrs['multiple'] = True
    
    def render(self, name, value, attrs=None, renderer=None):
        # Asegurar que el atributo multiple se incluya en el HTML
        if attrs is None:
            attrs = {}
        attrs = {**self.attrs, **attrs}
        attrs['multiple'] = True
        return super().render(name, value, attrs, renderer)
    
    def value_from_datadict(self, data, files, name):
        # Retorna una lista de archivos cuando hay múltiples seleccionados
        # Django manejará esto automáticamente si el atributo multiple está presente
        if name in files:
            return files.getlist(name)
        return None

# Definición de las opciones de servicio para el Multi-Selector
SERVICIO_CHOICES = [
    ('Vuelo', 'Vuelo'),
    ('Hospedaje', 'Hospedaje'),
    ('Traslado', 'Traslado (Transporte terrestre)'),
    ('Tour', 'Tour/Excursión'),
    ('Circuito Int', 'Circuito Internacional'),
    ('Renta Auto', 'Renta de Auto'),
    ('Paquete Todo Incluido', 'Paquete Todo Incluido'),
    ('Crucero', 'Crucero'),
    ('Seguro de Viaje', 'Seguro de Viaje'),
    ('Trámite de Visa', 'Trámite de Visa'),
    ('Trámite de Pasaporte', 'Trámite de Pasaporte'),
]

# Diccionario de mapeo: nombres del formulario -> códigos del modelo
SERVICIO_MAP = {
    'Vuelo': 'VUE',
    'Hospedaje': 'HOS',
    'Traslado': 'TRA',
    'Tour': 'TOU',
    'Circuito Int': 'CIR',
    'Renta Auto': 'REN',
    'Paquete Todo Incluido': 'PAQ',
    'Crucero': 'CRU',
    'Seguro de Viaje': 'SEG',
    'Trámite de Visa': 'OTR',  # Mapeado a "Otros Servicios"
    'Trámite de Pasaporte': 'OTR',  # Mapeado a "Otros Servicios"
}

# Diccionario inverso: códigos del modelo -> nombres del formulario
SERVICIO_MAP_REVERSE = {v: k for k, v in SERVICIO_MAP.items()}
# Mapeo adicional para códigos que pueden venir del modelo pero no están en el formulario
SERVICIO_MAP_REVERSE.update({
    'VUE': 'Vuelo',
    'HOS': 'Hospedaje',
    'TRA': 'Traslado',
    'TOU': 'Tour',
    'CIR': 'Circuito Int',
    'REN': 'Renta Auto',
    'PAQ': 'Paquete Todo Incluido',
    'CRU': 'Crucero',
    'SEG': 'Seguro de Viaje',
    'OTR': 'Trámite de Visa',  # Por defecto, mapear OTR a Trámite de Visa
})


# ------------------- ProveedorForm -------------------

class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            'nombre',
            'telefono',
            'ejecutivo',
            'servicio',
            'link',
            'genera_factura',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Aeroméxico'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. +52 55 1234 5678'}),
            'ejecutivo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del ejecutivo'}),
            'servicio': forms.Select(attrs={'class': 'form-select'}),
            'link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.proveedor.com'}),
            'genera_factura': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'genera_factura': 'Marca esta casilla si el proveedor emite factura automáticamente.',
        }


class EjecutivoForm(forms.ModelForm):
    class Meta:
        model = Ejecutivo
        fields = [
            'nombre_completo',
            'direccion',
            'telefono',
            'email',
            'ubicacion_asignada',
            'sueldo_base',
            'documento_pdf',
        ]
        widgets = {
            'nombre_completo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre y apellidos'}),
            'direccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Calle, número, ciudad, estado'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+52 55 1234 5678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejecutivo@agencia.com'}),
            'ubicacion_asignada': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Aeropuerto CDMX'}),
            'sueldo_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Ej. 12000.00'}),
            'documento_pdf': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'documento_pdf': 'Opcional. Solo se permiten archivos PDF.',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError("El correo electrónico es obligatorio para generar las credenciales.")
        return email

    def clean_sueldo_base(self):
        sueldo = self.cleaned_data.get('sueldo_base')
        if sueldo is None or sueldo <= 0:
            raise forms.ValidationError("El sueldo base debe ser mayor a 0.")
        return sueldo


class ConfirmacionVentaForm(forms.Form):
    archivos = forms.FileField(
        label="Archivos de confirmación",
        widget=MultipleFileInput(attrs={'class': 'form-control', 'multiple': True}),
        help_text="Adjunta uno o varios archivos (PDF, imágenes, etc.).",
        required=False  # La validación se hace en la vista con request.FILES.getlist()
    )
    nota = forms.CharField(
        label="Descripción / Nota",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Voucher hotel, boletos de vuelo, etc.'})
    )
    
    def clean_archivos(self):
        # Este método no se ejecutará normalmente porque value_from_datadict retorna una lista
        # La validación real se hace en la vista
        return self.cleaned_data.get('archivos')


# ------------------- AbonoPagoForm (Mantenido) -------------------

class AbonoPagoForm(forms.ModelForm):
    """Formulario para registrar un abono pago en la vista de detalle de la venta."""
    
    registrado_por = forms.ModelChoiceField(
        queryset=User.objects.all(),
        widget=forms.HiddenInput(),
        required=False  
    )

    class Meta:
        model = AbonoPago
        fields = ['monto', 'forma_pago', 'registrado_por'] 
        widgets = {
            'monto': forms.NumberInput(attrs={'placeholder': 'Ej: 1500.00', 'step': 'any', 'class': 'form-control'}),
            'forma_pago': forms.Select(attrs={'class': 'form-select'}), 
        }

# ------------------- LogisticaForm (Mantenido) -------------------

class LogisticaForm(forms.ModelForm):
    """Formulario para actualizar el estado de los servicios de Logística."""
    class Meta:
        model = Logistica
        fields = [
            'vuelo_confirmado', 
            'hospedaje_reservado', 
            'seguro_emitido', 
            'documentos_enviados'
        ]
        labels = {
            'vuelo_confirmado': 'Vuelo/Transporte Confirmado',
            'hospedaje_reservado': 'Hospedaje Reservado',
            'seguro_emitido': 'Seguro de Viaje Emitido',
            'documentos_enviados': 'Documentación enviada'
        }
        widgets = {
             'vuelo_confirmado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
             'hospedaje_reservado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
             'seguro_emitido': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
             'documentos_enviados': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ------------------- VentaViajeForm (CORREGIDO) -------------------

class VentaViajeForm(forms.ModelForm):
    
    # Campo para filtrar Clientes
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all().order_by('apellido'),
        widget=forms.Select(attrs={'class': 'form-select select2'}), 
        label="Cliente Asociado"
    )

    # ✅ CAMPO NUEVO: Selector de Servicios Múltiple con Checkboxes (No está en el modelo, es un campo de formulario temporal)
    servicios_seleccionados = forms.MultipleChoiceField(
        choices=SERVICIO_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Servicios Contratados",
        help_text="Selecciona uno o más servicios haciendo clic en las casillas."
    )

    class Meta:
        model = VentaViaje
        fields = [
            # Sección Cliente / Pasajeros / Contrato
            'cliente', 
            # 'proveedor',  # ❌ ELIMINADO: Se maneja por servicio individual
            'tipo_viaje', 
            'pasajeros',  # ✅ CAMPO NUEVO
            'documentos_cliente', 
            
            # Sección Servicios (servicios_seleccionados se añade arriba)
            # El campo 'servicios_detalle' se completará automáticamente desde 'servicios_seleccionados'
            
            # Fechas y Costos
            'fecha_inicio_viaje', 
            'fecha_fin_viaje', 
            'costo_venta_final', 
            'cantidad_apertura', 
            'costo_neto', 
            'fecha_vencimiento_pago',
            
            # ❌ Campos eliminados: 'tipo_cambio_usd', 'tipo_contrato', 'tipo_vuelo', y todos los 'servicio_*' booleanos.
        ]
        widgets = {
            # Textareas
            'pasajeros': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),

            # Selecciones
            'tipo_viaje': forms.Select(attrs={'class': 'form-select'}),

            # Archivos
            'documentos_cliente': forms.ClearableFileInput(attrs={'class': 'form-control'}),

            # Fechas
            'fecha_inicio_viaje': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin_viaje': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_vencimiento_pago': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),

            # Montos
            'costo_neto': forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
            'costo_venta_final': forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
            'cantidad_apertura': forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        """
        Sobrescribe el init para precargar 'servicios_seleccionados' 
        si el objeto existe y tiene códigos en 'servicios_seleccionados'.
        Convierte los códigos del modelo (VUE, HOS, etc.) a nombres del formulario.
        Agrega campos dinámicos de proveedores por servicio.
        """
        super().__init__(*args, **kwargs)

        # Mapeo de servicios del formulario a servicios de proveedores
        SERVICIO_PROVEEDOR_MAP = {
            'Vuelo': 'VUELOS',
            'Hospedaje': 'HOTELES',
            'Tour': 'TOURS',
        }
        
        # Crear campos dinámicos de proveedores para servicios específicos
        for servicio_nombre, servicio_codigo in SERVICIO_PROVEEDOR_MAP.items():
            # Campo para seleccionar proveedor (dropdown)
            field_name = f'proveedor_{servicio_nombre.lower().replace(" ", "_")}'
            self.fields[field_name] = forms.ModelChoiceField(
                queryset=Proveedor.objects.filter(
                    servicio__in=[servicio_codigo, 'TODO']
                ).order_by('nombre'),
                required=False,
                widget=forms.Select(attrs={
                    'class': 'form-select proveedor-select',
                    'data-servicio': servicio_nombre
                }),
                label=f"Proveedor de {servicio_nombre}",
                empty_label="Selecciona un proveedor"
            )
        
        # Crear campos de texto para otros servicios
        otros_servicios = ['Traslado', 'Circuito Int', 'Renta Auto', 'Paquete Todo Incluido', 
                          'Crucero', 'Seguro de Viaje', 'Trámite de Visa', 'Trámite de Pasaporte']
        for servicio_nombre in otros_servicios:
            field_name = f'proveedor_{servicio_nombre.lower().replace(" ", "_").replace("/", "_")}'
            self.fields[field_name] = forms.CharField(
                required=False,
                widget=forms.TextInput(attrs={
                    'class': 'form-control proveedor-text',
                    'data-servicio': servicio_nombre,
                    'placeholder': f'Nombre del proveedor de {servicio_nombre}'
                }),
                label=f"Proveedor de {servicio_nombre}"
            )
        
        # Si estamos editando una instancia (instance), convertimos códigos a nombres
        if self.instance and self.instance.pk and self.instance.servicios_seleccionados:
            # Recuperamos los códigos del campo servicios_seleccionados (separados por coma)
            codigos = [c.strip() for c in self.instance.servicios_seleccionados.split(',') if c.strip()]
            
            # Convertir códigos a nombres del formulario usando el diccionario inverso
            nombres_servicios = []
            for codigo in codigos:
                nombre = SERVICIO_MAP_REVERSE.get(codigo)
                if nombre and nombre in [choice[0] for choice in SERVICIO_CHOICES]:
                    nombres_servicios.append(nombre)
            
            # Precargar el campo con los nombres convertidos
            if nombres_servicios:
                self.initial['servicios_seleccionados'] = nombres_servicios


    def save(self, commit=True):
        """
        Sobrescribe save() para tomar los servicios seleccionados del formulario,
        convertirlos a códigos del modelo y guardarlos en 'servicios_seleccionados'.
        Los nombres completos y proveedores se guardan en 'servicios_detalle' para referencia.
        """
        instance = super().save(commit=False)

        # Capturar la lista de servicios seleccionados del formulario (nombres completos)
        servicios_nombres = self.cleaned_data.get('servicios_seleccionados', [])
        
        # Convertir nombres a códigos usando el diccionario de mapeo
        servicios_codigos = []
        servicios_detalle_list = []
        
        # Mapeo de servicios con dropdown de proveedores
        SERVICIO_PROVEEDOR_MAP = {
            'Vuelo': 'VUELOS',
            'Hospedaje': 'HOTELES',
            'Tour': 'TOURS',
        }
        
        for nombre in servicios_nombres:
            codigo = SERVICIO_MAP.get(nombre)
            if codigo:
                servicios_codigos.append(codigo)
                
                # Obtener proveedor para este servicio
                proveedor_info = ""
                if nombre in SERVICIO_PROVEEDOR_MAP:
                    # Servicio con dropdown de proveedores
                    field_name = f'proveedor_{nombre.lower().replace(" ", "_")}'
                    proveedor = self.cleaned_data.get(field_name)
                    if proveedor:
                        proveedor_info = f" - Proveedor: {proveedor.nombre}"
                else:
                    # Servicio con campo de texto
                    field_name = f'proveedor_{nombre.lower().replace(" ", "_").replace("/", "_")}'
                    proveedor_texto = self.cleaned_data.get(field_name, '').strip()
                    if proveedor_texto:
                        proveedor_info = f" - Proveedor: {proveedor_texto}"
                
                servicios_detalle_list.append(f"{nombre}{proveedor_info}")
        
        # Guardar códigos separados por coma en 'servicios_seleccionados' (ej: "VUE,HOS,SEG")
        instance.servicios_seleccionados = ','.join(servicios_codigos) if servicios_codigos else ''
        
        # Guardar nombres completos con proveedores separados por línea nueva en 'servicios_detalle'
        instance.servicios_detalle = '\n'.join(servicios_detalle_list) if servicios_detalle_list else ''
        
        # Si hay un proveedor principal seleccionado (del dropdown), guardarlo en el campo proveedor
        # Por ahora, tomamos el primer proveedor seleccionado de los servicios con dropdown
        for nombre in servicios_nombres:
            if nombre in SERVICIO_PROVEEDOR_MAP:
                field_name = f'proveedor_{nombre.lower().replace(" ", "_")}'
                proveedor = self.cleaned_data.get(field_name)
                if proveedor:
                    instance.proveedor = proveedor
                    break
        
        if commit:
            instance.save()
        return instance