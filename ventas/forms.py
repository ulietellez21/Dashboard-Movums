from django import forms
from django.forms import modelformset_factory
from .models import AbonoPago, Logistica, VentaViaje, Proveedor, Ejecutivo, LogisticaServicio # Aseguramos la importación de VentaViaje
from django.contrib.auth.models import User
from crm.models import Cliente # Importamos Cliente para usarlo en el queryset si es necesario
from crm.services import KilometrosService
from decimal import Decimal
from datetime import date

# Widget personalizado para fechas que use formato ISO para inputs de tipo 'date'
class ISODateInput(forms.DateInput):
    """
    Widget personalizado para DateInput que formatea las fechas en formato ISO (YYYY-MM-DD)
    cuando el atributo type='date' está presente. Esto es necesario porque los inputs
    de tipo 'date' en HTML5 requieren formato ISO.
    """
    def get_context(self, name, value, attrs):
        """
        Sobrescribe get_context para forzar formato ISO cuando type='date'.
        """
        context = super().get_context(name, value, attrs)
        # Si el widget es de tipo 'date', formatear el valor en ISO
        widget_attrs = context['widget']['attrs']
        if widget_attrs.get('type') == 'date' and value:
            if isinstance(value, date):
                context['widget']['value'] = value.strftime('%Y-%m-%d')
            elif isinstance(value, str):
                # Si el valor ya está en formato ISO, dejarlo tal cual
                if not (len(value) == 10 and value[4] == '-' and value[7] == '-'):
                    # Si no está en formato ISO, intentar parsearlo
                    try:
                        from django.utils.dateparse import parse_date
                        parsed_date = parse_date(value)
                        if parsed_date:
                            context['widget']['value'] = parsed_date.strftime('%Y-%m-%d')
                    except:
                        pass
        return context

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
    # Campo adicional para seleccionar el tipo de usuario/rol
    tipo_usuario = forms.ChoiceField(
        choices=[
            ('VENDEDOR', 'Vendedor'),
            ('CONTADOR', 'Contador'),
        ],
        initial='VENDEDOR',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tipo de Usuario',
        help_text='Selecciona el tipo de usuario que se creará en el sistema.'
    )
    
    class Meta:
        model = Ejecutivo
        fields = [
            'nombre_completo',
            'direccion',
            'telefono',
            'email',
            'ubicacion_asignada',
            'tipo_vendedor',
            'sueldo_base',
            'documento_pdf',
        ]
        widgets = {
            'nombre_completo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre y apellidos'}),
            'direccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Calle, número, ciudad, estado'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+52 55 1234 5678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejecutivo@agencia.com'}),
            'ubicacion_asignada': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Aeropuerto CDMX'}),
            'tipo_vendedor': forms.Select(attrs={'class': 'form-select'}),
            'sueldo_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Ej. 12000.00'}),
            'documento_pdf': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'documento_pdf': 'Opcional. Solo se permiten archivos PDF.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si estamos editando un ejecutivo existente, precargar el tipo_usuario desde el perfil del usuario
        if self.instance and self.instance.pk and self.instance.usuario:
            perfil = getattr(self.instance.usuario, 'perfil', None)
            if perfil and perfil.rol in ['VENDEDOR', 'CONTADOR']:
                self.fields['tipo_usuario'].initial = perfil.rol

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
            'traslado_confirmado',
            'tickets_confirmado'
        ]
        labels = {
            'vuelo_confirmado': 'Vuelo Confirmado',
            'hospedaje_reservado': 'Hospedaje Reservado',
            'traslado_confirmado': 'Traslado Confirmado',
            'tickets_confirmado': 'Tickets Confirmados'
        }
        widgets = {
             'vuelo_confirmado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
             'hospedaje_reservado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'traslado_confirmado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tickets_confirmado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si hay una instancia, ocultar campos de servicios no contratados
        if self.instance and self.instance.pk:
            venta = self.instance.venta
            servicios_contratados = []
            
            if venta.servicios_seleccionados:
                servicios_codes = [s.strip() for s in venta.servicios_seleccionados.split(',')]
                servicios_contratados = servicios_codes
            
            # Ocultar campos de servicios no contratados
            if 'VUE' not in servicios_contratados:
                self.fields['vuelo_confirmado'].widget = forms.HiddenInput()
            if 'HOS' not in servicios_contratados:
                self.fields['hospedaje_reservado'].widget = forms.HiddenInput()
            if 'TRA' not in servicios_contratados:
                self.fields['traslado_confirmado'].widget = forms.HiddenInput()
            if 'TOU' not in servicios_contratados:
                self.fields['tickets_confirmado'].widget = forms.HiddenInput()


class LogisticaServicioForm(forms.ModelForm):
    class Meta:
        model = LogisticaServicio
        fields = ['monto_planeado', 'pagado', 'notas']
        widgets = {
            'monto_planeado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'pagado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notas': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Notas internas opcionales'}),
        }
        labels = {
            'monto_planeado': 'Monto planificado',
            'pagado': 'Marcar como pagado',
            'notas': 'Notas',
        }


LogisticaServicioFormSet = modelformset_factory(
    LogisticaServicio,
    form=LogisticaServicioForm,
    extra=0,
    can_delete=False
)

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
            'modo_pago_apertura',
            'costo_neto', 
            'fecha_vencimiento_pago',
            'aplica_descuento_kilometros',
            'descuento_kilometros_mxn',
            
            # ❌ Campos eliminados: 'tipo_cambio_usd', 'tipo_contrato', 'tipo_vuelo', 'estado', y todos los 'servicio_*' booleanos.
        ]
        widgets = {
            # Textareas
            'pasajeros': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),

            # Selecciones
            'tipo_viaje': forms.Select(attrs={'class': 'form-select'}),
            'modo_pago_apertura': forms.Select(attrs={'class': 'form-select'}),

            # Archivos
            'documentos_cliente': forms.ClearableFileInput(attrs={'class': 'form-control'}),

            # Fechas - Usar widget personalizado que formatea en ISO
            'fecha_inicio_viaje': ISODateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin_viaje': ISODateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_vencimiento_pago': ISODateInput(attrs={'type': 'date', 'class': 'form-control'}),

            # Montos
            'costo_neto': forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
            'costo_venta_final': forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
            'cantidad_apertura': forms.NumberInput(attrs={'step': 'any', 'class': 'form-control'}),
            'aplica_descuento_kilometros': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'descuento_kilometros_mxn': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        """
        Sobrescribe el init para precargar 'servicios_seleccionados' 
        si el objeto existe y tiene códigos en 'servicios_seleccionados'.
        Convierte los códigos del modelo (VUE, HOS, etc.) a nombres del formulario.
        Agrega campos dinámicos de proveedores por servicio.
        """
        # Obtener la instancia antes de llamar a super
        instance = kwargs.get('instance', None)

        # Mapeo de servicios del formulario a servicios de proveedores
        SERVICIO_PROVEEDOR_MAP = {
            'Vuelo': 'VUELOS',
            'Hospedaje': 'HOTELES',
            'Tour': 'TOURS',
        }
        
        # Preparar valores iniciales - IMPORTANTE: NO interferir con la carga automática de Django
        # Solo preparar valores para campos que Django ModelForm no puede cargar automáticamente
        existing_initial = kwargs.pop('initial', {}) or {}
        dynamic_initial = {}
        
        # Si estamos editando, preparar valores iniciales
        if instance and instance.pk:
            # 1. Preparar valores para servicios_seleccionados
            if instance.servicios_seleccionados:
                codigos = [c.strip() for c in instance.servicios_seleccionados.split(',') if c.strip()]
                nombres_servicios = []
                for codigo in codigos:
                    nombre = SERVICIO_MAP_REVERSE.get(codigo)
                    if nombre and nombre in [choice[0] for choice in SERVICIO_CHOICES]:
                        nombres_servicios.append(nombre)
                if nombres_servicios:
                    existing_initial['servicios_seleccionados'] = nombres_servicios
                    dynamic_initial['servicios_seleccionados'] = nombres_servicios
            
            # 2. Preparar valores para fechas - asegurar que se pasen explícitamente
            # Django debería cargarlas automáticamente, pero las pasamos explícitamente
            # Para widgets de tipo 'date', el valor debe estar en formato ISO (YYYY-MM-DD)
            if instance.fecha_inicio_viaje:
                existing_initial['fecha_inicio_viaje'] = instance.fecha_inicio_viaje
            if instance.fecha_fin_viaje:
                existing_initial['fecha_fin_viaje'] = instance.fecha_fin_viaje
            if instance.fecha_vencimiento_pago:
                existing_initial['fecha_vencimiento_pago'] = instance.fecha_vencimiento_pago
            
            # 3. Preparar valores para proveedores desde servicios_detalle
            # Estos se aplicarán DESPUÉS de crear los campos dinámicos
            # Formato esperado: "Vuelo - Proveedor: NombreProveedor" o solo "Vuelo" si no hay proveedor
            # IMPORTANTE: Si servicios_seleccionados está vacío pero servicios_detalle tiene servicios,
            # también debemos extraer los servicios desde servicios_detalle para prellenar los checkboxes
            if instance.servicios_detalle:
                servicios_detalle = instance.servicios_detalle.split('\n')
                
                # Si no hay servicios_seleccionados prellenados, intentar extraerlos desde servicios_detalle
                if not existing_initial.get('servicios_seleccionados'):
                    servicios_from_detalle = []
                    for servicio_linea in servicios_detalle:
                        servicio_linea = servicio_linea.strip()
                        if not servicio_linea:
                            continue
                        
                        # Extraer el nombre del servicio (puede tener o no el formato con proveedor)
                        if ' - Proveedor: ' in servicio_linea:
                            nombre_servicio = servicio_linea.split(' - Proveedor: ')[0].strip()
                        else:
                            nombre_servicio = servicio_linea.strip()
                        
                        # Si el nombre está en las opciones válidas, agregarlo
                        if nombre_servicio in [choice[0] for choice in SERVICIO_CHOICES]:
                            if nombre_servicio not in servicios_from_detalle:
                                servicios_from_detalle.append(nombre_servicio)
                    
                    if servicios_from_detalle:
                        existing_initial['servicios_seleccionados'] = servicios_from_detalle
                        dynamic_initial['servicios_seleccionados'] = servicios_from_detalle
                
                # Ahora procesar proveedores desde servicios_detalle
                for servicio_linea in servicios_detalle:
                    servicio_linea = servicio_linea.strip()
                    if not servicio_linea:
                        continue
                    
                    # Verificar si la línea tiene el formato con proveedor
                    if ' - Proveedor: ' in servicio_linea:
                        partes = servicio_linea.split(' - Proveedor: ')
                        if len(partes) == 2:
                            nombre_servicio = partes[0].strip()
                            nombre_proveedor = partes[1].strip()
                            
                            if nombre_servicio in SERVICIO_PROVEEDOR_MAP:
                                # Servicio con dropdown de proveedores
                                field_name = f'proveedor_{nombre_servicio.lower().replace(" ", "_")}'
                                try:
                                    proveedor_obj = Proveedor.objects.get(nombre=nombre_proveedor)
                                    dynamic_initial[field_name] = proveedor_obj
                                except Proveedor.DoesNotExist:
                                    # Si no se encuentra el proveedor, intentar buscar por nombre similar
                                    try:
                                        proveedor_obj = Proveedor.objects.filter(nombre__icontains=nombre_proveedor).first()
                                        if proveedor_obj:
                                            dynamic_initial[field_name] = proveedor_obj
                                    except:
                                        pass
                            else:
                                # Servicio con campo de texto
                                field_name = f'proveedor_{nombre_servicio.lower().replace(" ", "_").replace("/", "_")}'
                                dynamic_initial[field_name] = nombre_proveedor
                    else:
                        # La línea solo tiene el nombre del servicio, sin proveedor
                        # Esto es válido, simplemente no establecemos ningún proveedor
                        pass
        
        # IMPORTANTE: Django ModelForm pasa los valores de la instancia como 'initial'
        # en el parámetro 'object_data' a BaseForm.__init__(). Si pasamos 'initial' aquí,
        # Django lo combinará con object_data (object_data.update(initial)).
        # Por lo tanto, pasamos las fechas aquí para que Django las procese correctamente.
        if existing_initial:
            kwargs['initial'] = existing_initial
        
        # Llamar a super para inicializar el formulario base
        # Django ModelForm automáticamente carga los valores de la instancia
        super().__init__(*args, **kwargs)
        
        # Guardar dynamic_initial como atributo de instancia para usarlo más tarde
        self._dynamic_initial = dynamic_initial
        
        # CRÍTICO: Después de super().__init__(), Django ya ha procesado el formulario.
        # Necesitamos asegurarnos de que los valores iniciales estén correctamente establecidos.
        # Django ModelForm debería haberlos cargado desde la instancia, pero verificamos y forzamos si es necesario.
        
        # Crear campos dinámicos de proveedores DESPUÉS de super().__init__()
        # para servicios específicos (con dropdown)
        for servicio_nombre, servicio_codigo in SERVICIO_PROVEEDOR_MAP.items():
            field_name = f'proveedor_{servicio_nombre.lower().replace(" ", "_")}'
            if field_name not in self.fields:
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
            if field_name not in self.fields:
                self.fields[field_name] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(attrs={
                        'class': 'form-control proveedor-text',
                        'data-servicio': servicio_nombre,
                        'placeholder': f'Nombre del proveedor de {servicio_nombre}'
                    }),
                    label=f"Proveedor de {servicio_nombre}"
                )
        
        # IMPORTANTE: Después de crear los campos dinámicos, establecer sus valores iniciales
        # Solo si el formulario NO está bound (sin datos POST)
        if not self.is_bound and self.instance and self.instance.pk:
            # 1. Establecer valores iniciales para campos dinámicos de proveedores
            # IMPORTANTE: Asegurarse de que los valores se establezcan ANTES de que el template los acceda
            for key, value in self._dynamic_initial.items():
                if key.startswith('proveedor_') and key in self.fields:
                    # Establecer el valor en form.initial (esto es lo que el template accede)
                    self.initial[key] = value
                    # También establecer el valor en el campo directamente
                    self.fields[key].initial = value
                    # DEBUG: Verificar que el valor se está estableciendo
                    # print(f"DEBUG: Establecido proveedor {key} = {value} (tipo: {type(value)})")
            
            # 2. CRÍTICO: Asegurar que las fechas estén correctamente establecidas
            # Django ModelForm debería haberlas cargado automáticamente desde la instancia
            # pero las verificamos y establecemos explícitamente para estar seguros
            # IMPORTANTE: Para inputs de tipo 'date', establecer el valor directamente en el widget
            # en formato ISO (YYYY-MM-DD) que es lo que requiere HTML5
            if self.instance.fecha_inicio_viaje:
                fecha_valor = self.instance.fecha_inicio_viaje
                # Asegurar que esté en form.initial
                self.initial['fecha_inicio_viaje'] = fecha_valor
                # También en el campo
                self.fields['fecha_inicio_viaje'].initial = fecha_valor
                # Para widgets de tipo 'date', establecer el valor en formato ISO directamente
                if hasattr(self.fields['fecha_inicio_viaje'].widget, 'attrs'):
                    if self.fields['fecha_inicio_viaje'].widget.attrs.get('type') == 'date':
                        self.fields['fecha_inicio_viaje'].widget.attrs['value'] = fecha_valor.strftime('%Y-%m-%d')
            
            if self.instance.fecha_fin_viaje:
                fecha_valor = self.instance.fecha_fin_viaje
                self.initial['fecha_fin_viaje'] = fecha_valor
                self.fields['fecha_fin_viaje'].initial = fecha_valor
                if hasattr(self.fields['fecha_fin_viaje'].widget, 'attrs'):
                    if self.fields['fecha_fin_viaje'].widget.attrs.get('type') == 'date':
                        self.fields['fecha_fin_viaje'].widget.attrs['value'] = fecha_valor.strftime('%Y-%m-%d')
            
            if self.instance.fecha_vencimiento_pago:
                fecha_valor = self.instance.fecha_vencimiento_pago
                self.initial['fecha_vencimiento_pago'] = fecha_valor
                self.fields['fecha_vencimiento_pago'].initial = fecha_valor
                if hasattr(self.fields['fecha_vencimiento_pago'].widget, 'attrs'):
                    if self.fields['fecha_vencimiento_pago'].widget.attrs.get('type') == 'date':
                        self.fields['fecha_vencimiento_pago'].widget.attrs['value'] = fecha_valor.strftime('%Y-%m-%d')
        
        # Agregar campos de edición solo cuando se está editando (no al crear)
        if self.instance and self.instance.pk:
            # Campo costo_modificacion
            self.fields['costo_modificacion'] = forms.DecimalField(
                max_digits=10,
                decimal_places=2,
                required=False,
                initial=Decimal('0.00'),
                widget=forms.NumberInput(attrs={
                    'step': 'any',
                    'class': 'form-control',
                    'placeholder': '0.00'
                }),
                label='Costo de Modificación',
                help_text='Costo adicional por modificar esta venta. Se sumará al costo total.'
            )

    def clean(self):
        cleaned_data = super().clean()
        aplica_descuento = cleaned_data.get('aplica_descuento_kilometros')
        costo_venta = cleaned_data.get('costo_venta_final') or Decimal('0.00')
        cliente = cleaned_data.get('cliente')
        descuento = Decimal('0.00')
        credito_disponible = Decimal('0.00')
        participa_programa = False

        if cliente:
            resumen = KilometrosService.resumen_cliente(cliente)
            if resumen:
                participa_programa = resumen.get('participa', False)
                valor_equivalente = resumen.get('valor_equivalente') or Decimal('0.00')
                credito_disponible = valor_equivalente if isinstance(valor_equivalente, Decimal) else Decimal(str(valor_equivalente))

        if aplica_descuento and costo_venta > 0:
            if not cliente:
                self.add_error('cliente', "Selecciona un cliente para aplicar el descuento de Kilómetros Movums.")
                aplica_descuento = False
            elif not participa_programa:
                self.add_error('aplica_descuento_kilometros', "El cliente no participa en Kilómetros Movums.")
                aplica_descuento = False
            else:
                max_por_regla = (costo_venta * Decimal('0.10')).quantize(Decimal('0.01'))
                max_por_credito = credito_disponible.quantize(Decimal('0.01'))
                descuento = min(max_por_regla, max_por_credito)
                if descuento <= 0:
                    self.add_error('aplica_descuento_kilometros', "El cliente no tiene saldo disponible para aplicar el descuento.")
                    aplica_descuento = False
        else:
            aplica_descuento = False

        costo_modificacion = cleaned_data.get('costo_modificacion')
        if costo_modificacion is not None and costo_modificacion < 0:
            self.add_error('costo_modificacion', "El costo de modificación debe ser mayor o igual a 0.")

        cleaned_data['aplica_descuento_kilometros'] = aplica_descuento
        cleaned_data['descuento_kilometros_mxn'] = descuento if aplica_descuento else Decimal('0.00')
        return cleaned_data


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