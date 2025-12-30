from django import forms
from django.forms import modelformset_factory
import json
from django.db.models import Case, When, Value, IntegerField
from .models import AbonoPago, Logistica, VentaViaje, Proveedor, Ejecutivo, LogisticaServicio, Cotizacion # Aseguramos la importación de VentaViaje
from django.contrib.auth.models import User
from crm.models import Cliente # Importamos Cliente para usarlo en el queryset si es necesario
from crm.services import KilometrosService
from ventas.services.promociones import PromocionesService
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
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
            archivos = files.getlist(name)
            # Filtrar archivos vacíos o inválidos
            archivos_validos = []
            for archivo in archivos:
                # Verificar que el archivo tenga nombre y tamaño
                if archivo and hasattr(archivo, 'name') and hasattr(archivo, 'size'):
                    if archivo.name and archivo.size > 0:
                        archivos_validos.append(archivo)
            return archivos_validos if archivos_validos else None
        return None
    
    def value_omitted_from_data(self, data, files, name):
        # Indica si el campo fue omitido del formulario
        # Si no está en files, se considera omitido (no se envió)
        return name not in files

# Campo personalizado para manejar múltiples archivos
class MultipleFileField(forms.FileField):
    """Campo personalizado que permite múltiples archivos pero guarda solo el primero"""
    
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput)
        kwargs.setdefault('required', False)
        super().__init__(*args, **kwargs)
    
    def to_python(self, data):
        # Si no hay datos, retornar None (campo opcional)
        if data in self.empty_values or data is None:
            return None
        
        # Si es una lista, procesar el primer elemento
        if isinstance(data, list):
            if not data:
                return None
            # Validar solo el primer archivo (los demás se manejan en la vista)
            data = data[0]
        
        # Verificar que el dato sea un archivo válido antes de validar
        if not hasattr(data, 'name') or not hasattr(data, 'size'):
            return None
        
        # Llamar al método padre para validar el archivo
        try:
            return super().to_python(data)
        except forms.ValidationError:
            # Si falla la validación, retornar None (campo opcional)
            return None
    
    def clean(self, data, initial=None):
        # Si no hay datos y estamos editando, mantener el valor inicial
        if data in self.empty_values or data is None:
            if initial:
                return initial
            return None
        
        # Si es una lista, procesar el primer elemento para validación
        if isinstance(data, list):
            if not data:
                if initial:
                    return initial
                return None
            # Validar solo el primer archivo
            data = data[0]
        
        # Verificar que el dato sea un archivo válido antes de validar
        if not hasattr(data, 'name') or not hasattr(data, 'size'):
            if initial:
                return initial
            return None
        
        # Llamar al método padre para validar
        try:
            return super().clean(data, initial)
        except forms.ValidationError as e:
            # Si falla la validación y estamos editando, mantener el valor inicial
            if initial:
                return initial
            # Si no hay valor inicial, propagar el error solo si el campo es requerido
            if self.required:
                raise
            return None


# Definición de las opciones de servicio para el Multi-Selector
SERVICIO_CHOICES = [
    ('Vuelo', 'Vuelo'),
    ('Hospedaje', 'Hospedaje'),
    ('Alojamiento Alterno', 'Alojamiento Alterno'),
    ('Traslado', 'Traslado'),
    ('Tour y Actividades', 'Tour y Actividades'),
    ('Circuito Internacional', 'Circuito Internacional'),
    ('Renta de Auto', 'Renta de Auto'),
    ('Paquete', 'Paquete'),
    ('Crucero', 'Crucero'),
    ('Seguro de Viaje', 'Seguro de Viaje'),
    ('Trámites de Documentación', 'Trámites de Documentación'),
]

# Diccionario de mapeo: nombres del formulario -> códigos del modelo
SERVICIO_MAP = {
    'Vuelo': 'VUE',
    'Hospedaje': 'HOS',
    'Alojamiento Alterno': 'ALO',
    'Traslado': 'TRA',
    'Tour y Actividades': 'TOU',
    'Circuito Internacional': 'CIR',
    'Renta de Auto': 'REN',
    'Paquete': 'PAQ',
    'Crucero': 'CRU',
    'Seguro de Viaje': 'SEG',
    'Trámites de Documentación': 'DOC',
    'Otros Servicios': 'OTR',
}

# Diccionario inverso: códigos del modelo -> nombres del formulario
SERVICIO_MAP_REVERSE = {v: k for k, v in SERVICIO_MAP.items()}
# Mapeo adicional para códigos que pueden venir del modelo pero no están en el formulario
SERVICIO_MAP_REVERSE.update({
    'VUE': 'Vuelo',
    'HOS': 'Hospedaje',
    'ALO': 'Alojamiento Alterno',
    'TRA': 'Traslado',
    'TOU': 'Tour y Actividades',
    'CIR': 'Circuito Internacional',
    'REN': 'Renta de Auto',
    'PAQ': 'Paquete',
    'CRU': 'Crucero',
    'SEG': 'Seguro de Viaje',
    'DOC': 'Trámites de Documentación',
    'OTR': 'Otros Servicios',
})


# ------------------- ProveedorForm -------------------

class ProveedorForm(forms.ModelForm):
    # ✅ Campo personalizado para selección múltiple de servicios
    servicios = forms.MultipleChoiceField(
        choices=Proveedor.SERVICIO_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Servicios que Ofrece",
        help_text="Selecciona uno o más servicios que ofrece este proveedor."
    )

    class Meta:
        model = Proveedor
        fields = [
            'nombre',
            'razon_social',
            'rfc',
            'condiciones_comerciales',
            'telefono',
            'ejecutivo',
            'telefono_ejecutivo',
            'email_ejecutivo',
            'servicios',
            'link',
            'genera_factura',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Aeroméxico'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Aeroméxico, S.A. de C.V.'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. AMX123456789'}),
            'condiciones_comerciales': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Términos, condiciones y acuerdos comerciales...'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. +52 55 1234 5678'}),
            'ejecutivo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del ejecutivo'}),
            'telefono_ejecutivo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. +52 55 1234 5678'}),
            'email_ejecutivo': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejecutivo@proveedor.com'}),
            'link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://www.proveedor.com'}),
            'genera_factura': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'genera_factura': 'Marca esta casilla si el proveedor emite factura automáticamente.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si hay una instancia (edición), cargar los servicios seleccionados
        if self.instance and self.instance.pk and self.instance.servicios:
            self.fields['servicios'].initial = [
                s.strip() for s in self.instance.servicios.split(',') if s.strip()
            ]

    def clean_servicios(self):
        servicios = self.cleaned_data.get('servicios', [])
        # Retornar la lista tal cual (MultipleChoiceField espera una lista)
        return servicios if servicios else []

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Guardar servicios como string separado por comas
        servicios = self.cleaned_data.get('servicios', [])
        instance.servicios = ','.join(servicios) if servicios else ''
        if commit:
            instance.save()
        return instance


class EjecutivoForm(forms.ModelForm):
    # Campo adicional para seleccionar el tipo de usuario/rol
    tipo_usuario = forms.ChoiceField(
        choices=[
            ('DIRECTOR_GENERAL', 'Director General'),
            ('DIRECTOR_VENTAS', 'Director de Ventas'),
            ('DIRECTOR_ADMINISTRATIVO', 'Director Administrativo'),
            ('GERENTE', 'Gerente'),
            ('CONTADOR', 'Contador'),
            ('VENDEDOR', 'Asesor'),
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
            'oficina',
            'tipo_vendedor',
            'sueldo_base',
            'fecha_ingreso',
            'fecha_nacimiento',
            'acta_nacimiento',
            'ine_imagen',
            'comprobante_domicilio',
        ]
        widgets = {
            'nombre_completo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre y apellidos'}),
            'direccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Calle, número, ciudad, estado'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+52 55 1234 5678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejecutivo@agencia.com'}),
            'oficina': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Oficina Central, Sucursal Norte'}),
            'tipo_vendedor': forms.Select(attrs={'class': 'form-select'}),
            'sueldo_base': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Ej. 12000.00'}),
            'fecha_ingreso': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_nacimiento': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'acta_nacimiento': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'}),
            'ine_imagen': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'}),
            'comprobante_domicilio': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'}),
        }
        help_texts = {
            'acta_nacimiento': 'Opcional. Sube el acta de nacimiento en formato PDF o imagen (JPG, PNG).',
            'ine_imagen': 'Opcional. Sube la identificación oficial (INE) en formato PDF o imagen (JPG, PNG).',
            'comprobante_domicilio': 'Opcional. Sube el comprobante de domicilio en formato PDF o imagen (JPG, PNG).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si estamos editando un ejecutivo existente, precargar el tipo_usuario desde el perfil del usuario
        if self.instance and self.instance.pk and self.instance.usuario:
            perfil = getattr(self.instance.usuario, 'perfil', None)
            if perfil and perfil.rol in ['JEFE', 'DIRECTOR_GENERAL', 'DIRECTOR_VENTAS', 'DIRECTOR_ADMINISTRATIVO', 'GERENTE', 'CONTADOR', 'VENDEDOR']:
                self.fields['tipo_usuario'].initial = perfil.rol
        
        # Hacer el campo tipo_vendedor opcional inicialmente
        # La validación condicional se hará en clean()
        self.fields['tipo_vendedor'].required = False

    def clean(self):
        """Validación condicional: tipo_vendedor solo es requerido si tipo_usuario es VENDEDOR."""
        cleaned_data = super().clean()
        tipo_usuario = cleaned_data.get('tipo_usuario')
        tipo_vendedor = cleaned_data.get('tipo_vendedor')
        
        # Si el tipo de usuario es VENDEDOR, entonces tipo_vendedor es obligatorio
        if tipo_usuario == 'VENDEDOR':
            if not tipo_vendedor:
                self.add_error('tipo_vendedor', 'Este campo es obligatorio cuando el tipo de usuario es Asesor.')
        else:
            # Si el tipo de usuario NO es VENDEDOR, establecer tipo_vendedor al valor por defecto del modelo
            # para evitar errores de validación, pero no es relevante para estos roles
            # Esto asegura que el campo tenga un valor válido aunque no se use
            cleaned_data['tipo_vendedor'] = 'MOSTRADOR'  # Valor por defecto del modelo
        
        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError("El correo electrónico es obligatorio para generar las credenciales.")
        
        # Verificar que el email no esté en uso por otro ejecutivo
        if email:
            from .models import Ejecutivo
            ejecutivos_con_email = Ejecutivo.objects.filter(email=email)
            if self.instance and self.instance.pk:
                ejecutivos_con_email = ejecutivos_con_email.exclude(pk=self.instance.pk)
            if ejecutivos_con_email.exists():
                raise forms.ValidationError("Este correo electrónico ya está registrado para otro ejecutivo.")
        
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
    
    # Redefinimos monto como CharField para que acepte "$" y comas sin fallar
    monto = forms.CharField(
        label="Monto del Abono",
        widget=forms.TextInput(attrs={
            'placeholder': 'Ej: 1500.00', 
            'class': 'form-control', 
            'type': 'text'  # Importante que sea text
        })
    )
    
    registrado_por = forms.ModelChoiceField(
        queryset=User.objects.all(),
        widget=forms.HiddenInput(),
        required=False  
    )

    class Meta:
        model = AbonoPago
        fields = ['monto', 'forma_pago', 'registrado_por'] 
        widgets = {
            'forma_pago': forms.Select(attrs={'class': 'form-select'}), 
        }
    
    def clean_monto(self):
        """Limpia el formato de moneda (quita $ y comas) antes de validar."""
        monto = self.cleaned_data.get('monto')
        if monto:
            # Si es string, limpiar formato (quitar $, USD, comas y espacios)
            if isinstance(monto, str):
                # Remover símbolos de moneda y formateo
                monto_limpio = monto.replace('$', '').replace('USD', '').replace(',', '').replace(' ', '').strip()
                try:
                    monto = Decimal(monto_limpio)
                except (ValueError, InvalidOperation):
                    raise forms.ValidationError("Ingresa un monto válido.")
            # Validar que el monto sea positivo
            if monto <= 0:
                raise forms.ValidationError("El monto debe ser mayor a cero.")
        return monto

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
    # El queryset se simplifica, el ordenamiento se hará en __init__ con optgroups
    cliente = forms.ModelChoiceField(
        queryset=Cliente.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select select2', 'id': 'id_cliente'}), 
        label="Cliente Asociado"
    )
    
    
    def _label_from_cliente(self, obj):
        """Personaliza el label para incluir información del tipo de cliente (método legacy, ya no se usa con optgroups)"""
        if obj.tipo_cliente == 'EMPRESA':
            return f"🏢 {obj.nombre_completo_display}"
        else:
            return f"👤 {obj.nombre_completo_display}"

    # ✅ CAMPO NUEVO: Selector de Servicios Múltiple con Checkboxes (No está en el modelo, es un campo de formulario temporal)
    servicios_seleccionados = forms.MultipleChoiceField(
        choices=SERVICIO_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        label="Servicios Contratados",
        help_text="Selecciona uno o más servicios haciendo clic en las casillas."
    )
    
    # Campo para tipo de trámite de documentación (solo visible cuando se selecciona "Trámites de Documentación")
    tipo_tramite_documentacion = forms.ChoiceField(
        choices=[
            ('', 'Selecciona el tipo de trámite'),
            ('VISA', 'Trámite de Visa'),
            ('PASAPORTE', 'Trámite de Pasaporte'),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Tipo de Trámite",
        help_text="Selecciona si es trámite de visa o pasaporte."
    )

    class Meta:
        model = VentaViaje
        fields = [
            # Sección Cliente / Pasajeros / Contrato
            'cliente', 
            # 'proveedor',  # ❌ ELIMINADO: Se maneja por servicio individual
            'tipo_viaje', 
            'pasajeros',  # ✅ CAMPO NUEVO
            'edades_menores',
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
            
            # Campos para ventas internacionales (USD)
            'tarifa_base_usd',
            'impuestos_usd',
            'suplementos_usd',
            'tours_usd',
            'tipo_cambio',
            
            # ❌ Campos eliminados: 'tipo_cambio_usd', 'tipo_contrato', 'tipo_vuelo', 'estado', y todos los 'servicio_*' booleanos.
        ]
        widgets = {
            # Textareas
            'pasajeros': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'edades_menores': forms.Textarea(attrs={'rows': 2, 'class': 'form-control', 'placeholder': 'Ej: 5, 8, 12'}),

            # Selecciones
            'tipo_viaje': forms.Select(attrs={'class': 'form-select'}),
            'modo_pago_apertura': forms.Select(attrs={'class': 'form-select'}),

            # Archivos - Múltiples archivos (hasta 5)
            'documentos_cliente': MultipleFileInput(attrs={'class': 'form-control', 'accept': '*/*'}),

            # Fechas - Usar widget personalizado que formatea en ISO
            'fecha_inicio_viaje': ISODateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin_viaje': ISODateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_vencimiento_pago': ISODateInput(attrs={'type': 'date', 'class': 'form-control'}),

            # Montos
            'costo_neto': forms.TextInput(attrs={'class': 'form-control'}),
            'costo_venta_final': forms.TextInput(attrs={'class': 'form-control'}),
            'cantidad_apertura': forms.TextInput(attrs={'class': 'form-control'}),
            'aplica_descuento_kilometros': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'descuento_kilometros_mxn': forms.HiddenInput(),
            # Campos para ventas internacionales (USD)
            'tarifa_base_usd': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'impuestos_usd': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'suplementos_usd': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'tours_usd': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'tipo_cambio': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0.0000'}),
        }

    def __init__(self, *args, **kwargs):
        """
        Sobrescribe el init para precargar 'servicios_seleccionados' 
        si el objeto existe y tiene códigos en 'servicios_seleccionados'.
        Convierte los códigos del modelo (VUE, HOS, etc.) a nombres del formulario.
        Agrega campos dinámicos de proveedores por servicio.
        """
        # Extraer request si está presente
        self.request = kwargs.pop('request', None)
        
        # Obtener la instancia antes de llamar a super
        instance = kwargs.get('instance', None)

        # Mapeo de servicios del formulario a servicios de proveedores
        SERVICIO_PROVEEDOR_MAP = {
            'Vuelo': 'VUELOS',
            'Hospedaje': 'HOTELES',
            'Alojamiento Alterno': 'ALOJAMIENTO_ALTERNO',
            'Traslado': 'TRASLADOS',
            'Tour y Actividades': 'TOURS',
            'Circuito Internacional': 'CIRCUITOS',
            'Renta de Auto': 'RENTA_AUTOS',
            'Paquete': 'PAQUETES',
            'Crucero': 'CRUCERO',
            'Seguro de Viaje': 'SEGUROS_VIAJE',
            'Trámites de Documentación': 'TRAMITE_DOCS',
        }
        
        # Preparar valores iniciales - IMPORTANTE: NO interferir con la carga automática de Django
        # Solo preparar valores para campos que Django ModelForm no puede cargar automáticamente
        # Preservar los valores iniciales que puedan venir de la vista (ej: desde cotización)
        existing_initial = kwargs.pop('initial', {}) or {}
        dynamic_initial = {}
        
        # Preservar valores iniciales que ya vienen establecidos (ej: desde VentaViajeCreateView)
        # Estos se combinarán con los valores que establezcamos aquí
        
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
        
        # 4. Preparar valores para proveedores desde cotización origen (si existe)
        # Esto se aplica cuando la venta se crea desde una cotización
        # Primero verificar si hay datos en la sesión (nueva venta desde cotización)
        cot = None
        if not instance or not instance.pk:
            # Si es una nueva venta, verificar si hay datos de cotización en la sesión
            if self.request and hasattr(self.request, 'session'):
                cotizacion_data = self.request.session.get('cotizacion_convertir', {})
                if cotizacion_data.get('cotizacion_id'):
                    try:
                        from .models import Cotizacion
                        cot = Cotizacion.objects.filter(pk=cotizacion_data['cotizacion_id']).first()
                        # Limpiar la sesión después de usarla
                        if 'cotizacion_convertir' in self.request.session:
                            del self.request.session['cotizacion_convertir']
                    except Exception:
                        pass
        
        # Si hay instancia con cotización origen, usar esa
        if instance and instance.cotizacion_origen:
            cot = instance.cotizacion_origen
        
        if cot:
            propuestas = cot.propuestas if isinstance(cot.propuestas, dict) else {}
            tipo_cotizacion = propuestas.get('tipo', '')
            
            # Función auxiliar para buscar proveedor por nombre
            def buscar_proveedor_por_nombre(nombre_proveedor):
                if not nombre_proveedor:
                    return None
                try:
                    # Intentar búsqueda exacta primero
                    return Proveedor.objects.get(nombre=nombre_proveedor)
                except Proveedor.DoesNotExist:
                    # Intentar búsqueda parcial
                    return Proveedor.objects.filter(nombre__icontains=nombre_proveedor).first()
            
            # Obtener índices seleccionados de la sesión (si existen)
            opcion_vuelo_index = None
            opcion_hotel_index = None
            
            if self.request and hasattr(self.request, 'session'):
                # Intentar obtener los índices de la sesión usando el slug de la cotización
                session_key = f'cotizacion_{cot.slug}_opcion_vuelo'
                opcion_vuelo_index = self.request.session.get(session_key)
                session_key_hotel = f'cotizacion_{cot.slug}_opcion_hotel'
                opcion_hotel_index = self.request.session.get(session_key_hotel)
                
                # Limpiar la sesión después de usarla
                if session_key in self.request.session:
                    del self.request.session[session_key]
                if session_key_hotel in self.request.session:
                    del self.request.session[session_key_hotel]
            
            # Procesar según el tipo de cotización
            if tipo_cotizacion == 'vuelos' and propuestas.get('vuelos'):
                # Para vuelos, usar la opción seleccionada o la primera por defecto
                vuelos = propuestas.get('vuelos', [])
                if vuelos and len(vuelos) > 0:
                    # Determinar qué índice usar
                    try:
                        indice = int(opcion_vuelo_index) if opcion_vuelo_index is not None else 0
                        if indice < 0 or indice >= len(vuelos):
                            indice = 0
                    except (ValueError, TypeError):
                        indice = 0
                    
                    # Tomar el vuelo seleccionado
                    vuelo_seleccionado = vuelos[indice] if isinstance(vuelos, list) else vuelos.get(f'propuesta_{indice + 1}', {})
                    if isinstance(vuelo_seleccionado, dict):
                        nombre_aerolinea = vuelo_seleccionado.get('aerolinea', '')
                        if nombre_aerolinea:
                            proveedor = buscar_proveedor_por_nombre(nombre_aerolinea)
                            if proveedor:
                                dynamic_initial['proveedor_vuelo'] = proveedor
                                # Pre-seleccionar servicio Vuelo
                                if 'servicios_seleccionados' not in existing_initial:
                                    existing_initial['servicios_seleccionados'] = []
                                    dynamic_initial['servicios_seleccionados'] = []
                                if 'Vuelo' not in existing_initial['servicios_seleccionados']:
                                    existing_initial['servicios_seleccionados'].append('Vuelo')
                                    if 'servicios_seleccionados' in dynamic_initial:
                                        dynamic_initial['servicios_seleccionados'].append('Vuelo')
                                    else:
                                        dynamic_initial['servicios_seleccionados'] = existing_initial['servicios_seleccionados'].copy()
            
            elif tipo_cotizacion == 'hospedaje' and propuestas.get('hoteles'):
                # Para hospedaje, usar la opción seleccionada o la primera por defecto
                hoteles = propuestas.get('hoteles', [])
                if hoteles and len(hoteles) > 0:
                    # Determinar qué índice usar
                    try:
                        indice = int(opcion_hotel_index) if opcion_hotel_index is not None else 0
                        if indice < 0 or indice >= len(hoteles):
                            indice = 0
                    except (ValueError, TypeError):
                        indice = 0
                    
                    # Tomar el hotel seleccionado
                    hotel_seleccionado = hoteles[indice] if isinstance(hoteles, list) else hoteles.get(f'propuesta_{indice + 1}', {})
                    if isinstance(hotel_seleccionado, dict):
                        nombre_hotel = hotel_seleccionado.get('nombre', '')
                        if nombre_hotel:
                            proveedor = buscar_proveedor_por_nombre(nombre_hotel)
                            if proveedor:
                                dynamic_initial['proveedor_hospedaje'] = proveedor
                                # Pre-seleccionar servicio Hospedaje
                                if 'servicios_seleccionados' not in existing_initial:
                                    existing_initial['servicios_seleccionados'] = []
                                    dynamic_initial['servicios_seleccionados'] = []
                                if 'Hospedaje' not in existing_initial['servicios_seleccionados']:
                                    existing_initial['servicios_seleccionados'].append('Hospedaje')
                                    if 'servicios_seleccionados' in dynamic_initial:
                                        dynamic_initial['servicios_seleccionados'].append('Hospedaje')
                                    else:
                                        dynamic_initial['servicios_seleccionados'] = existing_initial['servicios_seleccionados'].copy()
            
            elif tipo_cotizacion == 'paquete' and propuestas.get('paquete'):
                # Para paquete, procesar vuelo y hotel
                paquete = propuestas.get('paquete', {})
                if isinstance(paquete, dict):
                    # Procesar vuelo
                    vuelo = paquete.get('vuelo', {})
                    if isinstance(vuelo, dict):
                        nombre_aerolinea = vuelo.get('aerolinea', '')
                        if nombre_aerolinea:
                            proveedor = buscar_proveedor_por_nombre(nombre_aerolinea)
                            if proveedor:
                                dynamic_initial['proveedor_vuelo'] = proveedor
                                # Pre-seleccionar servicio Vuelo
                                if 'servicios_seleccionados' not in existing_initial:
                                    existing_initial['servicios_seleccionados'] = []
                                    dynamic_initial['servicios_seleccionados'] = []
                                if 'Vuelo' not in existing_initial['servicios_seleccionados']:
                                    existing_initial['servicios_seleccionados'].append('Vuelo')
                                    if 'servicios_seleccionados' in dynamic_initial:
                                        dynamic_initial['servicios_seleccionados'].append('Vuelo')
                                    else:
                                        dynamic_initial['servicios_seleccionados'] = existing_initial['servicios_seleccionados'].copy()
                    
                    # Procesar hotel
                    hotel = paquete.get('hotel', {})
                    if isinstance(hotel, dict):
                        nombre_hotel = hotel.get('nombre', '')
                        if nombre_hotel:
                            proveedor = buscar_proveedor_por_nombre(nombre_hotel)
                            if proveedor:
                                dynamic_initial['proveedor_hospedaje'] = proveedor
                                # Pre-seleccionar servicio Hospedaje
                                if 'servicios_seleccionados' not in existing_initial:
                                    existing_initial['servicios_seleccionados'] = []
                                    dynamic_initial['servicios_seleccionados'] = []
                                if 'Hospedaje' not in existing_initial['servicios_seleccionados']:
                                    existing_initial['servicios_seleccionados'].append('Hospedaje')
                                    if 'servicios_seleccionados' in dynamic_initial:
                                        dynamic_initial['servicios_seleccionados'].append('Hospedaje')
                                    else:
                                        dynamic_initial['servicios_seleccionados'] = existing_initial['servicios_seleccionados'].copy()
            
            elif tipo_cotizacion == 'tours' and propuestas.get('tours'):
                # Para tours, procesar el proveedor de tours
                tours = propuestas.get('tours', {})
                if isinstance(tours, dict):
                    nombre_proveedor = tours.get('proveedor', '')
                    if nombre_proveedor:
                        proveedor = buscar_proveedor_por_nombre(nombre_proveedor)
                        if proveedor:
                            dynamic_initial['proveedor_tour_y_actividades'] = proveedor
                            # Pre-seleccionar servicio Tour y Actividades
                            if 'servicios_seleccionados' not in existing_initial:
                                existing_initial['servicios_seleccionados'] = []
                                dynamic_initial['servicios_seleccionados'] = []
                            if 'Tour y Actividades' not in existing_initial['servicios_seleccionados']:
                                existing_initial['servicios_seleccionados'].append('Tour y Actividades')
                                if 'servicios_seleccionados' in dynamic_initial:
                                    dynamic_initial['servicios_seleccionados'].append('Tour y Actividades')
                                else:
                                    dynamic_initial['servicios_seleccionados'] = existing_initial['servicios_seleccionados'].copy()
            
            elif tipo_cotizacion == 'traslados' and propuestas.get('traslados'):
                # Para traslados, procesar el proveedor de traslados
                traslados = propuestas.get('traslados', {})
                if isinstance(traslados, dict):
                    nombre_proveedor = traslados.get('proveedor', '')
                    if nombre_proveedor:
                        proveedor = buscar_proveedor_por_nombre(nombre_proveedor)
                        if proveedor:
                            dynamic_initial['proveedor_traslado'] = proveedor
                            # Pre-seleccionar servicio Traslado
                            if 'servicios_seleccionados' not in existing_initial:
                                existing_initial['servicios_seleccionados'] = []
                                dynamic_initial['servicios_seleccionados'] = []
                            if 'Traslado' not in existing_initial['servicios_seleccionados']:
                                existing_initial['servicios_seleccionados'].append('Traslado')
                                if 'servicios_seleccionados' in dynamic_initial:
                                    dynamic_initial['servicios_seleccionados'].append('Traslado')
                                else:
                                    dynamic_initial['servicios_seleccionados'] = existing_initial['servicios_seleccionados'].copy()
        
        # IMPORTANTE: Django ModelForm pasa los valores de la instancia como 'initial'
        # en el parámetro 'object_data' a BaseForm.__init__(). Si pasamos 'initial' aquí,
        # Django lo combinará con object_data (object_data.update(initial)).
        # Por lo tanto, pasamos las fechas aquí para que Django las procese correctamente.
        if existing_initial:
            kwargs['initial'] = existing_initial
        
        # Llamar a super para inicializar el formulario base
        # Django ModelForm automáticamente carga los valores de la instancia
        super().__init__(*args, **kwargs)
        
        # ========== LÓGICA DE AGRUPACIÓN Y ORDENAMIENTO DE CLIENTES ==========
        # Esta lógica debe ejecutarse DESPUÉS de super().__init__() para que los campos estén disponibles
        if 'cliente' in self.fields:
            # Placeholder para Select2 y opción vacía inicial
            self.fields['cliente'].empty_label = "Selecciona un cliente"
            self.fields['cliente'].widget.attrs['data-placeholder'] = "Selecciona un cliente"
            
            # 1. Obtener Particulares ordenados alfabéticamente
            particulares = Cliente.objects.filter(tipo_cliente='PARTICULAR').order_by('apellido', 'nombre')
            opciones_particulares = []
            for c in particulares:
                # Usamos el emoji para que el JS lo detecte y coloree
                label = f"👤 {c.nombre_completo_display}"
                opciones_particulares.append((c.id, label))
            
            # 2. Obtener Empresas ordenadas alfabéticamente
            empresas = Cliente.objects.filter(tipo_cliente='EMPRESA').order_by('nombre_empresa')
            opciones_empresas = []
            for c in empresas:
                label = f"🏢 {c.nombre_completo_display}"
                opciones_empresas.append((c.id, label))
            
            # 3. Crear la estructura de grupos (Optgroups)
            # El formato es: [('Nombre Grupo', [opciones]), ...]
            grouped_choices = []
            
            if opciones_particulares:
                grouped_choices.append(('Particulares', opciones_particulares))
            
            if opciones_empresas:
                grouped_choices.append(('Empresas', opciones_empresas))
            
            # 4. Asignar las opciones agrupadas
            # El formato de optgroups en Django es: [('Nombre Grupo', [(value, label), ...]), ...]
            # Agregamos siempre una opción vacía inicial para permitir limpiar la selección
            final_choices = [('', 'Selecciona un cliente')]
            final_choices.extend(grouped_choices)
            self.fields['cliente'].choices = final_choices
        # ========== FIN DE LÓGICA DE AGRUPACIÓN DE CLIENTES ==========
        
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
                # ✅ Filtrar proveedores que ofrecen este servicio o "TODO"
                # El campo 'servicios' es un TextField que almacena códigos separados por comas
                from django.db.models import Q
                queryset = Proveedor.objects.filter(
                    Q(servicios__icontains=servicio_codigo) | Q(servicios__icontains='TODO')
                ).order_by('nombre')
                
                self.fields[field_name] = forms.ModelChoiceField(
                    queryset=queryset,
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
        # Aplicar tanto para ventas existentes como para nuevas ventas (desde cotización)
        if not self.is_bound:
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
            
            # 2. Establecer servicios_seleccionados si hay valores en dynamic_initial
            # Combinar con valores que puedan venir de la vista (ej: desde cotización)
            servicios_dynamic = self._dynamic_initial.get('servicios_seleccionados', [])
            servicios_existing = self.initial.get('servicios_seleccionados', [])
            # Combinar ambos, evitando duplicados
            servicios_combinados = list(set(servicios_dynamic + (servicios_existing if isinstance(servicios_existing, list) else [])))
            if servicios_combinados:
                self.initial['servicios_seleccionados'] = servicios_combinados
                self.fields['servicios_seleccionados'].initial = servicios_combinados
            
            # 3. Establecer costo_venta_final si viene de cotización
            # Asegurar que el valor se establezca explícitamente después de super().__init__()
            if 'costo_venta_final' in self.initial:
                costo_final = self.initial['costo_venta_final']
                # Convertir Decimal a float para NumberInput
                if isinstance(costo_final, Decimal):
                    costo_final_float = float(costo_final)
                else:
                    costo_final_float = float(costo_final) if costo_final else 0.0
                
                # Establecer en el campo
                if 'costo_venta_final' in self.fields and costo_final:
                    self.fields['costo_venta_final'].initial = costo_final_float
                    # También establecer en el widget para asegurar que se muestre
                    if hasattr(self.fields['costo_venta_final'], 'widget'):
                        # Para NumberInput, el valor se establece en el atributo 'value'
                        self.fields['costo_venta_final'].widget.attrs['value'] = str(costo_final_float)
            
            # 3. CRÍTICO: Asegurar que las fechas estén correctamente establecidas
            # Django ModelForm debería haberlas cargado automáticamente desde la instancia
            # pero las verificamos y establecemos explícitamente para estar seguros
            # IMPORTANTE: Para inputs de tipo 'date', establecer el valor directamente en el widget
            # en formato ISO (YYYY-MM-DD) que es lo que requiere HTML5
            if self.instance and self.instance.pk and self.instance.fecha_inicio_viaje:
                fecha_valor = self.instance.fecha_inicio_viaje
                # Asegurar que esté en form.initial
                self.initial['fecha_inicio_viaje'] = fecha_valor
                # También en el campo
                self.fields['fecha_inicio_viaje'].initial = fecha_valor
                # Para widgets de tipo 'date', establecer el valor en formato ISO directamente
                if hasattr(self.fields['fecha_inicio_viaje'].widget, 'attrs'):
                    if self.fields['fecha_inicio_viaje'].widget.attrs.get('type') == 'date':
                        self.fields['fecha_inicio_viaje'].widget.attrs['value'] = fecha_valor.strftime('%Y-%m-%d')
            
            if self.instance and self.instance.pk and self.instance.fecha_fin_viaje:
                fecha_valor = self.instance.fecha_fin_viaje
                self.initial['fecha_fin_viaje'] = fecha_valor
                self.fields['fecha_fin_viaje'].initial = fecha_valor
                if hasattr(self.fields['fecha_fin_viaje'].widget, 'attrs'):
                    if self.fields['fecha_fin_viaje'].widget.attrs.get('type') == 'date':
                        self.fields['fecha_fin_viaje'].widget.attrs['value'] = fecha_valor.strftime('%Y-%m-%d')
            
            if self.instance and self.instance.pk and self.instance.fecha_vencimiento_pago:
                fecha_valor = self.instance.fecha_vencimiento_pago
                self.initial['fecha_vencimiento_pago'] = fecha_valor
                self.fields['fecha_vencimiento_pago'].initial = fecha_valor
                if hasattr(self.fields['fecha_vencimiento_pago'].widget, 'attrs'):
                    if self.fields['fecha_vencimiento_pago'].widget.attrs.get('type') == 'date':
                        self.fields['fecha_vencimiento_pago'].widget.attrs['value'] = fecha_valor.strftime('%Y-%m-%d')
            
            # Para ventas internacionales, convertir valores de MXN a USD para mostrar en el formulario
            if instance and instance.pk and instance.tipo_viaje == 'INT' and instance.tipo_cambio and instance.tipo_cambio > 0:
                # Los campos USD ya están en USD, no necesitan conversión
                # La cantidad de apertura está en MXN, convertirla a USD para mostrar
                if instance.cantidad_apertura and instance.cantidad_apertura > 0:
                    cantidad_apertura_usd = (instance.cantidad_apertura / instance.tipo_cambio).quantize(Decimal('0.01'))
                    existing_initial['cantidad_apertura'] = cantidad_apertura_usd
                    dynamic_initial['cantidad_apertura'] = cantidad_apertura_usd
                # El costo_neto está en MXN, convertirla a USD para mostrar
                if instance.costo_neto and instance.costo_neto > 0:
                    costo_neto_usd = (instance.costo_neto / instance.tipo_cambio).quantize(Decimal('0.01'))
                    existing_initial['costo_neto'] = costo_neto_usd
                    dynamic_initial['costo_neto'] = costo_neto_usd
        
        # Configurar help_text y required para documentos_cliente (múltiples archivos)
        if 'documentos_cliente' in self.fields:
            # Cambiar el campo a nuestro campo personalizado
            self.fields['documentos_cliente'] = MultipleFileField(
                required=False,
                widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': '*/*'}),
                help_text=""
            )
        
        # Agregar campos de edición solo cuando se está editando una venta existente
        # y que ya tenga algún costo de modificación o que haya sido guardada previamente
        if self.instance and self.instance.pk:
            # Solo mostrar costo_modificacion si la venta ya tiene un valor o si tiene abonos/confirmaciones
            # Esto evita mostrarlo en ventas recién creadas desde cotización
            mostrar_costo_modificacion = False
            if hasattr(self.instance, 'costo_modificacion') and self.instance.costo_modificacion:
                if self.instance.costo_modificacion > 0:
                    mostrar_costo_modificacion = True
            # También mostrar si la venta tiene abonos confirmados (ya fue procesada)
            if hasattr(self.instance, 'abonos'):
                if self.instance.abonos.filter(confirmado=True).exists():
                    mostrar_costo_modificacion = True
            
            if mostrar_costo_modificacion:
                # Campo costo_modificacion
                self.fields['costo_modificacion'] = forms.DecimalField(
                    max_digits=10,
                    decimal_places=2,
                    required=False,
                    initial=getattr(self.instance, 'costo_modificacion', Decimal('0.00')),
                    widget=forms.TextInput(attrs={
                        'class': 'form-control',
                        'placeholder': '0.00'
                    }),
                    label='Costo de Modificación',
                    help_text='Costo adicional por modificar esta venta. Se sumará al costo total.'
                )

    def clean_documentos_cliente(self):
        """Valida que no se suban más de 5 archivos y maneja múltiples archivos"""
        # El valor ya viene procesado por MultipleFileField.to_python()
        # que retorna el primer archivo o None
        documentos = self.cleaned_data.get('documentos_cliente')
        
        # Si no hay documentos, mantener el existente si se está editando
        if not documentos:
            if self.instance and self.instance.pk and hasattr(self.instance, 'documentos_cliente') and self.instance.documentos_cliente:
                return self.instance.documentos_cliente
            return None
        
        # El campo personalizado ya validó el primer archivo
        # La validación de cantidad se hace en la vista usando request.FILES
        return documentos

    def clean(self):
        cleaned_data = super().clean()
        
        # Validar que si se selecciona "Trámites de Documentación", se especifique el tipo de trámite
        servicios_seleccionados = cleaned_data.get('servicios_seleccionados', [])
        if 'Trámites de Documentación' in servicios_seleccionados:
            tipo_tramite = cleaned_data.get('tipo_tramite_documentacion', '').strip()
            if not tipo_tramite:
                self.add_error('tipo_tramite_documentacion', 'Debes seleccionar si es trámite de Visa o Pasaporte cuando seleccionas "Trámites de Documentación".')
        
        tipo_viaje = cleaned_data.get('tipo_viaje', 'NAC')
        
        # Desactivar Kilómetros Movums para ventas internacionales
        if tipo_viaje == 'INT':
            aplica_descuento = False
            descuento = Decimal('0.00')
        else:
            aplica_descuento = cleaned_data.get('aplica_descuento_kilometros')
            # Regla: máximo 10% del valor total reservado (costo_venta_final)
            costo_cliente = cleaned_data.get('costo_venta_final') or Decimal('0.00')
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

            if aplica_descuento and costo_cliente > 0:
                if not cliente:
                    self.add_error('cliente', "Selecciona un cliente para aplicar el descuento de Kilómetros Movums.")
                    aplica_descuento = False
                elif not participa_programa:
                    self.add_error('aplica_descuento_kilometros', "El cliente no participa en Kilómetros Movums.")
                    aplica_descuento = False
                else:
                    # Máximo 10% del valor total reservado
                    # Usar ROUND_HALF_UP: del 1-4 baja, del 5-9 sube (redondeo estándar)
                    from decimal import ROUND_HALF_UP
                    max_por_regla = (costo_cliente * Decimal('0.10')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    max_por_credito = credito_disponible.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    descuento = min(max_por_regla, max_por_credito).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if descuento <= 0:
                        self.add_error('aplica_descuento_kilometros', "El cliente no tiene saldo disponible para aplicar el descuento.")
                        aplica_descuento = False
            else:
                aplica_descuento = False

        # Función auxiliar para limpiar valores con formato de moneda
        def limpiar_valor_moneda(valor):
            """Limpia un valor que puede tener formato de moneda ($, comas, etc.)"""
            if valor is None or valor == '':
                return None
            if isinstance(valor, Decimal):
                return valor
            # Convertir a string y limpiar
            valor_str = str(valor).strip()
            # Remover símbolos de moneda y comas
            valor_str = valor_str.replace('$', '').replace(',', '').replace('USD', '').replace(' ', '')
            try:
                return Decimal(valor_str)
            except (ValueError, InvalidOperation):
                return None
        
        # Limpiar valores monetarios antes de procesarlos
        if 'costo_venta_final' in cleaned_data:
            cleaned_data['costo_venta_final'] = limpiar_valor_moneda(cleaned_data.get('costo_venta_final')) or Decimal('0.00')
        if 'cantidad_apertura' in cleaned_data:
            cleaned_data['cantidad_apertura'] = limpiar_valor_moneda(cleaned_data.get('cantidad_apertura')) or Decimal('0.00')
        if 'costo_neto' in cleaned_data:
            cleaned_data['costo_neto'] = limpiar_valor_moneda(cleaned_data.get('costo_neto')) or Decimal('0.00')
        
        costo_modificacion = cleaned_data.get('costo_modificacion')
        if costo_modificacion is not None:
            costo_modificacion_limpio = limpiar_valor_moneda(costo_modificacion)
            if costo_modificacion_limpio is not None:
                cleaned_data['costo_modificacion'] = costo_modificacion_limpio
                if costo_modificacion_limpio < 0:
                    self.add_error('costo_modificacion', "El costo de modificación debe ser mayor o igual a 0.")
            else:
                cleaned_data['costo_modificacion'] = Decimal('0.00')

        # ------------------- LÓGICA PARA VENTAS INTERNACIONALES (USD) -------------------
        tipo_viaje = cleaned_data.get('tipo_viaje', 'NAC')
        if tipo_viaje == 'INT':
            # Validar que se proporcionen los campos USD para ventas internacionales
            # Limpiar valores USD antes de procesarlos
            tarifa_base_usd = limpiar_valor_moneda(cleaned_data.get('tarifa_base_usd')) or Decimal('0.00')
            impuestos_usd = limpiar_valor_moneda(cleaned_data.get('impuestos_usd')) or Decimal('0.00')
            suplementos_usd = limpiar_valor_moneda(cleaned_data.get('suplementos_usd')) or Decimal('0.00')
            tours_usd = limpiar_valor_moneda(cleaned_data.get('tours_usd')) or Decimal('0.00')
            tipo_cambio = limpiar_valor_moneda(cleaned_data.get('tipo_cambio')) or Decimal('0.0000')
            
            # Actualizar cleaned_data con valores limpios
            cleaned_data['tarifa_base_usd'] = tarifa_base_usd
            cleaned_data['impuestos_usd'] = impuestos_usd
            cleaned_data['suplementos_usd'] = suplementos_usd
            cleaned_data['tours_usd'] = tours_usd
            cleaned_data['tipo_cambio'] = tipo_cambio
            
            # Validar que el tipo de cambio sea mayor a 0
            if tipo_cambio <= 0:
                self.add_error('tipo_cambio', "El tipo de cambio debe ser mayor a 0 para ventas internacionales.")
            
            # Validar que todos los campos USD estén llenos
            if tarifa_base_usd == 0 and impuestos_usd == 0 and suplementos_usd == 0 and tours_usd == 0:
                self.add_error('tarifa_base_usd', "Para ventas internacionales, debes llenar al menos uno de los campos: Tarifa Base, Impuestos, Suplementos o Tours.")
            
            # Calcular el total en USD
            total_usd = tarifa_base_usd + impuestos_usd + suplementos_usd + tours_usd
            
            # Convertir a MXN usando el tipo de cambio
            if tipo_cambio > 0 and total_usd > 0:
                # Para ventas internacionales, calcular costo_venta_final desde USD
                costo_venta_final_mxn = total_usd * tipo_cambio
                cleaned_data['costo_venta_final'] = costo_venta_final_mxn.quantize(Decimal('0.01'))
                
                # El costo_neto también se ingresa en USD en el formulario, convertir a MXN
                costo_neto_usd = cleaned_data.get('costo_neto') or Decimal('0.00')
                if costo_neto_usd > 0:
                    costo_neto_mxn = costo_neto_usd * tipo_cambio
                    cleaned_data['costo_neto'] = costo_neto_mxn.quantize(Decimal('0.01'))
                
                # La cantidad de apertura se maneja en USD en el formulario, pero se guarda en MXN
                # Si el usuario ingresa cantidad de apertura, asumimos que está en USD y la convertimos
                cantidad_apertura_usd = cleaned_data.get('cantidad_apertura') or Decimal('0.00')
                if cantidad_apertura_usd > 0:
                    # Convertir cantidad de apertura de USD a MXN
                    cantidad_apertura_mxn = cantidad_apertura_usd * tipo_cambio
                    cleaned_data['cantidad_apertura'] = cantidad_apertura_mxn.quantize(Decimal('0.01'))
        else:
            # Para ventas nacionales, limpiar los campos USD
            cleaned_data['tarifa_base_usd'] = Decimal('0.00')
            cleaned_data['impuestos_usd'] = Decimal('0.00')
            cleaned_data['suplementos_usd'] = Decimal('0.00')
            cleaned_data['tours_usd'] = Decimal('0.00')
            cleaned_data['tipo_cambio'] = Decimal('0.0000')

        # ------------------- PROMOCIONES CONFIGURABLES -------------------
        self.promos_calculadas = []
        self.promos_aplicadas_aceptadas = []
        self.total_descuento_promos = Decimal('0.00')
        self.resumen_promos_text = ""
        self.promos_km = []

        cliente = cleaned_data.get('cliente')
        tipo_viaje = cleaned_data.get('tipo_viaje')
        if cliente and tipo_viaje and cleaned_data.get('costo_venta_final') is not None:
            costo_mod = getattr(self.instance, 'costo_modificacion', Decimal('0.00')) or Decimal('0.00')
            base_total = (cleaned_data.get('costo_venta_final') or Decimal('0.00')) + costo_mod
            promos = PromocionesService.obtener_promos_aplicables(
                cliente=cliente,
                tipo_viaje=tipo_viaje,
                total_base_mxn=base_total,
                fecha_ref=date.today()
            )
            self.promos_calculadas = promos
            aceptadas = []
            resumen_list = []
            total_desc = Decimal('0.00')
            for p in promos:
                promo = p['promo']
                requiere = p.get('requiere_confirmacion', False)
                aplicar = True
                if requiere:
                    aplicar = self.data.get(f"aplicar_promo_{promo.id}", "on") in ["on", "true", "1"]
                if not aplicar:
                    continue
                aceptadas.append(p)
                total_desc += p['monto_descuento']
                if p.get('km_bono') and p['km_bono'] > 0:
                    self.promos_km.append({'promo': promo, 'km_bono': p['km_bono']})
                    resumen_list.append(f"{promo.nombre} (+{p['km_bono']} km)")
                else:
                    resumen_list.append(f"{promo.nombre} (-${p['monto_descuento']})")

            self.promos_aplicadas_aceptadas = aceptadas
            self.total_descuento_promos = total_desc
            self.resumen_promos_text = "; ".join(resumen_list)

            if total_desc > 0:
                # Ajustar el costo_venta_final para reflejar el descuento, sin tocar costo_modificacion
                nuevo_total = (cleaned_data.get('costo_venta_final') or Decimal('0.00')) - total_desc
                cleaned_data['costo_venta_final'] = max(Decimal('0.00'), nuevo_total)

        # ------------------- Kilómetros Movums -------------------
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
            'Alojamiento Alterno': 'ALOJAMIENTO_ALTERNO',
            'Traslado': 'TRASLADOS',
            'Tour y Actividades': 'TOURS',
            'Circuito Internacional': 'CIRCUITOS',
            'Renta de Auto': 'RENTA_AUTOS',
            'Paquete': 'PAQUETES',
            'Crucero': 'CRUCERO',
            'Seguro de Viaje': 'SEGUROS_VIAJE',
            'Trámites de Documentación': 'TRAMITE_DOCS',
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
                
                # Si es "Trámites de Documentación", agregar el tipo de trámite
                tipo_tramite_info = ""
                if nombre == "Trámites de Documentación":
                    tipo_tramite = self.cleaned_data.get('tipo_tramite_documentacion', '').strip()
                    if tipo_tramite:
                        tipo_tramite_display = "Visa" if tipo_tramite == "VISA" else "Pasaporte"
                        tipo_tramite_info = f" - Tipo: {tipo_tramite_display}"
                
                servicios_detalle_list.append(f"{nombre}{tipo_tramite_info}{proveedor_info}")
        
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

        # Guardar resumen y monto de promociones
        instance.descuento_promociones_mxn = getattr(self, 'total_descuento_promos', Decimal('0.00'))
        instance.resumen_promociones = getattr(self, 'resumen_promos_text', '') or ''

        if commit:
            instance.save()

            # Guardar promociones aplicadas (through)
            from ventas.models import VentaPromocionAplicada
            VentaPromocionAplicada.objects.filter(venta=instance).delete()
            for p in getattr(self, 'promos_aplicadas_aceptadas', []):
                promo = p['promo']
                VentaPromocionAplicada.objects.create(
                    venta=instance,
                    promocion=promo,
                    nombre_promocion=promo.nombre,
                    porcentaje_aplicado=p.get('porcentaje') or Decimal('0.00'),
                    monto_descuento=p.get('monto_descuento') or Decimal('0.00'),
                    requiere_confirmacion_snapshot=p.get('requiere_confirmacion', False),
                    km_bono=p.get('km_bono') or Decimal('0.00'),
                )
            # Marcar que no se ha aplicado aún como pago
            instance.descuento_promociones_aplicado_como_pago = False
            instance.save(update_fields=['descuento_promociones_aplicado_como_pago'])
        return instance


# ------------------- CotizacionForm -------------------
class CotizacionForm(forms.ModelForm):
    # Campos extra para estructurar propuestas como en el modal anterior
    fecha_cotizacion = forms.DateField(required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'class': 'form-control'}))
    tipo = forms.ChoiceField(
        choices=[
            ('vuelos', '✈️ Vuelos'),
            ('hospedaje', '🏨 Hospedaje'),
            ('paquete', '🧳 Paquete'),
            ('tours', '🗺️ Tours'),
            ('traslados', '🚗 Traslados'),
            ('renta_autos', '🚙 Renta de Autos'),
            ('generica', '📄 Plantilla Genérica'),
        ],
        required=True,
        widget=forms.Select(attrs={'class': 'form-select form-select-lg', 'id': 'tipoCotizacionSelect'})
    )
    vuelo_propuesta_1 = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    vuelo_propuesta_2 = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    hotel_propuesta_1 = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    hotel_propuesta_2 = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    paquete_vuelo = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    paquete_hotel = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    tour_descripcion = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))
    generica_contenido = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}))

    class Meta:
        model = Cotizacion
        fields = [
            'cliente',
            'titulo',
            'tipo',
            'fecha_cotizacion',
            'origen',
            'destino',
            'dias',
            'noches',
            'fecha_inicio',
            'fecha_fin',
            'pasajeros',
            'adultos',
            'menores',
            'edades_menores',
            'notas',
            'propuestas',
            'vuelo_propuesta_1',
            'vuelo_propuesta_2',
            'hotel_propuesta_1',
            'hotel_propuesta_2',
            'paquete_vuelo',
            'paquete_hotel',
            'tour_descripcion',
            'generica_contenido',
        ]
        widgets = {
            'cliente': forms.Select(attrs={'class': 'form-select select2'}),
            'titulo': forms.TextInput(attrs={'class': 'form-control'}),
            'origen': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Guadalajara'}),
            'destino': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Cancún'}),
            'dias': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'noches': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'fecha_inicio': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_fin': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'pasajeros': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'adultos': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'menores': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'edades_menores': forms.HiddenInput(attrs={'id': 'id_edades_menores'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'propuestas': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Función auxiliar para mostrar solo el nombre del proveedor
        def label_from_nombre(obj):
            return obj.nombre
        
        # Agregar campos dinámicos para seleccionar proveedores
        # Para vuelos (3 opciones)
        for i in range(1, 4):
            self.fields[f'vuelo_proveedor_{i}'] = forms.ModelChoiceField(
                queryset=Proveedor.objects.filter(
                    servicios__icontains='VUELOS'
                ).order_by('nombre'),
                required=False,
                empty_label="Selecciona una aerolínea...",
                widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': f'vuelo_proveedor_{i}'}),
                label=f'Aerolínea Opción {i}'
            )
            # Personalizar para mostrar solo el nombre sin servicios
            self.fields[f'vuelo_proveedor_{i}'].label_from_instance = label_from_nombre
        
        # Para hospedaje (3 opciones)
        for i in range(1, 4):
            self.fields[f'hotel_proveedor_{i}'] = forms.ModelChoiceField(
                queryset=Proveedor.objects.filter(
                    servicios__icontains='HOTELES'
                ).order_by('nombre'),
                required=False,
                empty_label="Selecciona un hotel...",
                widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': f'hotel_proveedor_{i}'}),
                label=f'Hotel Opción {i}'
            )
            # Personalizar para mostrar solo el nombre sin servicios
            self.fields[f'hotel_proveedor_{i}'].label_from_instance = label_from_nombre
        
        # Para paquete (vuelo y hotel)
        self.fields['paquete_proveedor_vuelo'] = forms.ModelChoiceField(
            queryset=Proveedor.objects.filter(
                servicios__icontains='VUELOS'
            ).order_by('nombre'),
            required=False,
            empty_label="Selecciona una aerolínea...",
            widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'paquete_proveedor_vuelo'}),
            label='Aerolínea'
        )
        self.fields['paquete_proveedor_vuelo'].label_from_instance = label_from_nombre
        
        self.fields['paquete_proveedor_hotel'] = forms.ModelChoiceField(
            queryset=Proveedor.objects.filter(
                servicios__icontains='HOTELES'
            ).order_by('nombre'),
            required=False,
            empty_label="Selecciona un hotel...",
            widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'paquete_proveedor_hotel'}),
            label='Hotel'
        )
        self.fields['paquete_proveedor_hotel'].label_from_instance = label_from_nombre
        
        # Para tours
        self.fields['tour_proveedor'] = forms.ModelChoiceField(
            queryset=Proveedor.objects.filter(
                servicios__icontains='TOURS'
            ).order_by('nombre'),
            required=False,
            empty_label="Selecciona un proveedor de tours...",
            widget=forms.Select(attrs={'class': 'form-select', 'id': 'tour_proveedor'}),
            label='Proveedor de Tours'
        )
        self.fields['tour_proveedor'].label_from_instance = label_from_nombre
        
        # Para traslados
        self.fields['traslado_proveedor'] = forms.ModelChoiceField(
            queryset=Proveedor.objects.filter(
                servicios__icontains='TRASLADOS'
            ).order_by('nombre'),
            required=False,
            empty_label="Selecciona un proveedor de traslados...",
            widget=forms.Select(attrs={'class': 'form-select', 'id': 'traslado_proveedor'}),
            label='Proveedor de Traslados'
        )
        self.fields['traslado_proveedor'].label_from_instance = label_from_nombre
        
        # Para renta de autos (campo de texto libre)
        self.fields['renta_autos_arrendadora'] = forms.CharField(
            required=False,
            widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'renta_autos_arrendadora', 'placeholder': 'Ej: Hertz, Avis, Budget, etc.'}),
            label='Arrendadora'
        )
        
        # Si hay una instancia (edición), inicializar propuestas con el valor guardado
        if self.instance and self.instance.pk and self.instance.propuestas:
            # Asegurar que propuestas sea un diccionario
            if isinstance(self.instance.propuestas, dict):
                self.fields['propuestas'].initial = json.dumps(self.instance.propuestas)
            elif isinstance(self.instance.propuestas, str):
                try:
                    # Si ya es un string JSON válido, usarlo directamente
                    json.loads(self.instance.propuestas)
                    self.fields['propuestas'].initial = self.instance.propuestas
                except (json.JSONDecodeError, TypeError):
                    # Si no es JSON válido, inicializar como objeto vacío
                    self.fields['propuestas'].initial = '{}'
            else:
                self.fields['propuestas'].initial = '{}'
        else:
            # Si es una nueva cotización, inicializar con objeto vacío
            self.fields['propuestas'].initial = '{}'

    def clean(self):
        cleaned = super().clean()
        propuestas_raw = cleaned.get('propuestas')
        if isinstance(propuestas_raw, str):
            try:
                propuestas = json.loads(propuestas_raw)
            except Exception:
                propuestas = {}
        else:
            propuestas = propuestas_raw or {}
        
        # Asegurar que el tipo se guarde en propuestas
        tipo = cleaned.get('tipo')
        if tipo:
            propuestas['tipo'] = tipo
        
        # Si el tipo es 'paquete', asegurar que el objeto paquete exista
        if tipo == 'paquete':
            if 'paquete' not in propuestas:
                propuestas['paquete'] = {
                    'vuelo': {},
                    'hotel': {},
                    'tours': []
                }
            # Asegurar que vuelo y hotel existan dentro de paquete
            if 'vuelo' not in propuestas.get('paquete', {}):
                propuestas.setdefault('paquete', {})['vuelo'] = {}
            if 'hotel' not in propuestas.get('paquete', {}):
                propuestas.setdefault('paquete', {})['hotel'] = {}
            if 'tours' not in propuestas.get('paquete', {}):
                propuestas.setdefault('paquete', {})['tours'] = []
        
        cleaned['propuestas'] = propuestas
        return cleaned
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Asegurar que propuestas sea un diccionario, no un string o None
        if instance.propuestas is None:
            instance.propuestas = {}
        elif isinstance(instance.propuestas, str):
            try:
                instance.propuestas = json.loads(instance.propuestas)
            except (json.JSONDecodeError, TypeError):
                instance.propuestas = {}
        
        # Si propuestas está vacío o no es un dict, inicializarlo
        if not isinstance(instance.propuestas, dict):
            instance.propuestas = {}
        
        # Asegurar que el tipo esté en propuestas
        tipo = self.cleaned_data.get('tipo', 'vuelos')
        if 'tipo' not in instance.propuestas:
            instance.propuestas['tipo'] = tipo
        
        # CRÍTICO: Si el tipo es 'paquete', asegurar que el objeto paquete exista y tenga la estructura correcta
        if tipo == 'paquete':
            # Si no existe el objeto paquete, crearlo con estructura completa
            if 'paquete' not in instance.propuestas:
                instance.propuestas['paquete'] = {
                    'vuelo': {
                        'aerolinea': '',
                        'salida': '',
                        'regreso': '',
                        'incluye': '',
                        'total': '',
                        'forma_pago': ''
                    },
                    'hotel': {
                        'nombre': '',
                        'habitacion': '',
                        'direccion': '',
                        'plan': '',
                        'notas': '',
                        'total': '',
                        'forma_pago': ''
                    },
                    'total': '',
                    'forma_pago': '',
                    'tours': []
                }
            else:
                # Asegurar que tenga la estructura completa incluso si existe
                paquete = instance.propuestas['paquete']
                if 'vuelo' not in paquete:
                    paquete['vuelo'] = {}
                if 'hotel' not in paquete:
                    paquete['hotel'] = {}
                if 'tours' not in paquete:
                    paquete['tours'] = []
                if 'total' not in paquete:
                    paquete['total'] = ''
                if 'forma_pago' not in paquete:
                    paquete['forma_pago'] = ''
        
        # Calcular total_estimado según el tipo de cotización
        def limpiar_y_convertir_total(valor):
            """Convierte un string de total (puede tener comas) a Decimal"""
            if not valor:
                return Decimal('0.00')
            try:
                valor_limpio = str(valor).replace(',', '').replace('$', '').strip()
                return Decimal(valor_limpio)
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        
        total_estimado = Decimal('0.00')
        propuestas = instance.propuestas if isinstance(instance.propuestas, dict) else {}
        tipo = propuestas.get('tipo', '')
        
        if tipo == 'tours' and propuestas.get('tours'):
            # Para tours, sumar todos los totales
            tours = propuestas.get('tours', {})
            tours_list = []
            if isinstance(tours, list):
                tours_list = tours
            else:
                tours_list = [tours] if tours else []
            
            for tour in tours_list:
                if isinstance(tour, dict) and tour.get('total'):
                    total_tour = limpiar_y_convertir_total(tour.get('total'))
                    total_estimado += total_tour
        elif tipo == 'paquete' and propuestas.get('paquete'):
            # Para paquete, usar el total del paquete si existe
            paquete = propuestas.get('paquete', {})
            if isinstance(paquete, dict) and paquete.get('total'):
                total_estimado = limpiar_y_convertir_total(paquete.get('total'))
        elif tipo == 'vuelos' and propuestas.get('vuelos'):
            # Para vuelos, usar el total del primer vuelo
            vuelos = propuestas.get('vuelos', [])
            if vuelos and len(vuelos) > 0 and isinstance(vuelos[0], dict) and vuelos[0].get('total'):
                total_estimado = limpiar_y_convertir_total(vuelos[0].get('total'))
        elif tipo == 'hospedaje' and propuestas.get('hoteles'):
            # Para hospedaje, usar el total del primer hotel
            hoteles = propuestas.get('hoteles', [])
            if hoteles and len(hoteles) > 0 and isinstance(hoteles[0], dict) and hoteles[0].get('total'):
                total_estimado = limpiar_y_convertir_total(hoteles[0].get('total'))
        elif tipo == 'traslados' and propuestas.get('traslados'):
            # Para traslados, usar el total
            traslados = propuestas.get('traslados', {})
            if isinstance(traslados, dict) and traslados.get('total'):
                total_estimado = limpiar_y_convertir_total(traslados.get('total'))
        elif tipo == 'renta_autos' and propuestas.get('renta_autos'):
            # Para renta_autos, usar el total
            renta_autos = propuestas.get('renta_autos', {})
            if isinstance(renta_autos, dict) and renta_autos.get('total'):
                total_estimado = limpiar_y_convertir_total(renta_autos.get('total'))
        
        instance.total_estimado = total_estimado
        
        if commit:
            instance.save()
        return instance
