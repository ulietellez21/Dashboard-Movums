from django import forms
from django.forms import modelformset_factory
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
import json
from django.db.models import Case, When, Value, IntegerField
from .models import AbonoPago, Logistica, VentaViaje, Proveedor, Ejecutivo, LogisticaServicio, Cotizacion, AbonoProveedor, SolicitudCancelacion # Aseguramos la importación de VentaViaje
from django.contrib.auth.models import User
from crm.models import Cliente # Importamos Cliente para usarlo en el queryset si es necesario
from crm.services import KilometrosService
from ventas.services.promociones import PromocionesService
from ventas.services.cotizaciones_campo import aplicar_ajustes_cotizacion_campo
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date


class SafeProveedorModelChoiceField(forms.ModelChoiceField):
    """
    ModelChoiceField para Proveedor que evita MultipleObjectsReturned:
    usa filter().first() en lugar de get() al resolver el valor.
    """
    def to_python(self, value):
        if value in self.empty_values:
            return None
        key = self.to_field_name or 'pk'
        try:
            return self.queryset.get(**{key: value})
        except (ValueError, TypeError):
            raise forms.ValidationError(
                self.error_messages['invalid_choice'],
                code='invalid_choice',
                params={'value': value},
            )
        except ObjectDoesNotExist:
            raise forms.ValidationError(
                self.error_messages['invalid_choice'],
                code='invalid_choice',
                params={'value': value},
            )
        except MultipleObjectsReturned:
            return self.queryset.filter(**{key: value}).order_by('pk').first()

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
            'metodo_pago_preferencial',
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
            'metodo_pago_preferencial': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'genera_factura': 'Marca esta casilla si el proveedor emite factura automáticamente.',
            'metodo_pago_preferencial': 'Si está activo, las ventas nacionales con este proveedor mostrarán la tabla de abonos al proveedor.',
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


class OficinaForm(forms.ModelForm):
    """Formulario para crear y editar oficinas."""
    
    class Meta:
        from .models import Oficina
        model = Oficina
        fields = [
            'nombre',
            'direccion',
            'ubicacion',
            'responsable',
            'encargado',
            'tipo',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Oficina Central, Sucursal Norte'
            }),
            'direccion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Calle, número, ciudad, estado, código postal'
            }),
            'ubicacion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. Local 15, Piso 2, Oficina 201'
            }),
            'responsable': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre del responsable'
            }),
            'encargado': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre del encargado'
            }),
            'tipo': forms.Select(attrs={
                'class': 'form-select'
            }),
        }
        labels = {
            'nombre': 'Nombre de la Oficina',
            'direccion': 'Dirección',
            'ubicacion': 'Ubicación',
            'responsable': 'Responsable',
            'encargado': 'Encargado',
            'tipo': 'Tipo de Oficina',
        }
        help_texts = {
            'direccion': 'Dirección completa (punto en el mapa)',
            'ubicacion': 'Descripción de ubicación dentro de plaza/edificio',
        }


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
            'oficina': forms.Select(attrs={'class': 'form-select'}),
            'tipo_vendedor': forms.Select(attrs={'class': 'form-select'}),
            'sueldo_base': forms.TextInput(attrs={'class': 'form-control', 'type': 'text', 'inputmode': 'decimal', 'placeholder': 'Ej. $12,000.00'}),
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
        
        # Actualizar queryset de oficina para mostrar solo oficinas activas
        from .models import Oficina
        self.fields['oficina'].queryset = Oficina.objects.filter(activa=True).order_by('nombre')

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
        tipo_usuario = self.cleaned_data.get('tipo_usuario')
        
        # El email es obligatorio si:
        # 1. Es un ejecutivo nuevo (no tiene pk), O
        # 2. Es un ejecutivo existente que no tiene usuario (necesita crear uno)
        requiere_email = False
        if not self.instance or not self.instance.pk:
            # Es un ejecutivo nuevo
            requiere_email = True
        elif not self.instance.usuario:
            # Es un ejecutivo existente pero sin usuario (se necesita crear uno)
            requiere_email = True
        
        if requiere_email and not email:
            raise forms.ValidationError("El correo electrónico es obligatorio para generar las credenciales del usuario.")
        
        # Verificar que el email no esté en uso por otro ejecutivo (solo si se proporciona un email)
        if email:
            from .models import Ejecutivo
            from django.contrib.auth.models import User
            
            # Verificar en la tabla Ejecutivo
            ejecutivos_con_email = Ejecutivo.objects.filter(email=email)
            if self.instance and self.instance.pk:
                ejecutivos_con_email = ejecutivos_con_email.exclude(pk=self.instance.pk)
            if ejecutivos_con_email.exists():
                raise forms.ValidationError("Este correo electrónico ya está registrado para otro ejecutivo.")
            
            # Verificar en la tabla User (importante: validar que no esté en uso por otro usuario)
            # Solo validar si estamos creando un nuevo ejecutivo o editando uno sin usuario
            if requiere_email:
                usuarios_con_email = User.objects.filter(email__iexact=email)
                # Si estamos editando y el ejecutivo tiene usuario, excluir ese usuario de la validación
                if self.instance and self.instance.pk and self.instance.usuario:
                    usuarios_con_email = usuarios_con_email.exclude(pk=self.instance.usuario.pk)
                if usuarios_con_email.exists():
                    raise forms.ValidationError("Este correo electrónico ya está registrado por otro usuario en el sistema.")
        
        return email

    def clean_sueldo_base(self):
        sueldo = self.cleaned_data.get('sueldo_base')
        if sueldo is None or sueldo <= 0:
            raise forms.ValidationError("El sueldo base debe ser mayor a 0.")
        return sueldo


# ------------------- AbonoProveedor Forms -------------------

class SolicitarAbonoProveedorForm(forms.ModelForm):
    """Formulario para que un vendedor solicite un abono a proveedor."""
    
    # Redefinir monto como CharField para manejar formato de moneda
    monto = forms.CharField(
        label="Monto a Abonar",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0.00',
            'type': 'text',
            'inputmode': 'decimal'
        }),
        help_text='Monto en MXN a abonar al proveedor'
    )
    
    # Redefinir tipo_cambio_aplicado como CharField para manejar formato
    tipo_cambio_aplicado = forms.CharField(
        label="Tipo de Cambio Aplicado",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '0.0000',
            'type': 'text',
            'inputmode': 'decimal'
        }),
        help_text='Tipo de cambio del día para convertir MXN a USD (requerido solo para ventas internacionales)'
    )
    
    class Meta:
        model = AbonoProveedor
        fields = ['proveedor', 'monto', 'tipo_cambio_aplicado', 'nota_solicitud']
        widgets = {
            'proveedor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Aerolínea XYZ, Hotel ABC, etc.'
            }),
            'nota_solicitud': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notas o comentarios sobre el abono solicitado...'
            }),
        }
        help_texts = {
            'proveedor': 'Nombre del proveedor al que se abonará (texto libre)',
            'nota_solicitud': 'Notas adicionales sobre esta solicitud',
        }
    
    def __init__(self, *args, **kwargs):
        self.venta = kwargs.pop('venta', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Pre-llenar el campo de proveedor si la venta ya tiene uno asignado
        if self.venta and self.venta.proveedor:
            self.fields['proveedor'].initial = self.venta.proveedor.nombre
        
        # Para ventas internacionales: monto en USD; para nacionales: monto en MXN
        if self.venta and self.venta.tipo_viaje == 'INT':
            self.fields['monto'].label = "Monto (USD)"
            self.fields['monto'].help_text = 'Monto en USD a abonar al proveedor'
            self.fields['tipo_cambio_aplicado'].required = True
            self.fields['tipo_cambio_aplicado'].help_text = 'Tipo de cambio del día (MXN/USD) para registrar el abono'
        else:
            self.fields['monto'].label = "Monto (MXN)"
            self.fields['monto'].help_text = 'Monto en MXN a abonar al proveedor'
        
        if self.venta and self.venta.tipo_viaje in ('NAC', 'INT_MXN'):
            self.fields['tipo_cambio_aplicado'].required = False
            self.fields['tipo_cambio_aplicado'].help_text = 'Tipo de cambio (opcional, solo si se requiere conversión a USD)'
        elif self.venta and self.venta.tipo_viaje == 'INT':
            pass  # ya configurado arriba
        else:
            self.fields['tipo_cambio_aplicado'].required = True
            self.fields['tipo_cambio_aplicado'].help_text = 'Tipo de cambio del día para convertir MXN a USD'
    
    def clean_proveedor(self):
        proveedor = self.cleaned_data.get('proveedor')
        if not proveedor or not proveedor.strip():
            raise forms.ValidationError("Debes especificar el nombre del proveedor.")
        return proveedor.strip()
    
    def clean_monto(self):
        """Limpia el formato de moneda (quita $ y comas) antes de validar."""
        monto_raw = self.cleaned_data.get('monto')
        
        # Si no hay valor, retornar None para que Django muestre el error de campo requerido
        if not monto_raw:
            raise forms.ValidationError("Este campo es obligatorio.")
        
        # Si es string, limpiar formato (quitar $, comas y espacios)
        if isinstance(monto_raw, str):
            # Remover símbolos de moneda y formateo
            monto_limpio = monto_raw.replace('$', '').replace(',', '').replace(' ', '').replace('USD', '').strip()
            if not monto_limpio:
                raise forms.ValidationError("Este campo es obligatorio.")
            try:
                monto = Decimal(monto_limpio)
            except (ValueError, InvalidOperation):
                raise forms.ValidationError("El monto debe ser un número válido.")
        elif isinstance(monto_raw, Decimal):
            monto = monto_raw
        else:
            try:
                monto = Decimal(str(monto_raw))
            except (ValueError, InvalidOperation):
                raise forms.ValidationError("El monto debe ser un número válido.")
        
        if monto <= 0:
            raise forms.ValidationError("El monto debe ser mayor a 0.")
        return monto
    
    def clean_tipo_cambio_aplicado(self):
        """Limpia el formato del tipo de cambio antes de validar."""
        tipo_cambio_raw = self.cleaned_data.get('tipo_cambio_aplicado')
        
        # Si no hay valor y es venta internacional, es requerido
        if not tipo_cambio_raw:
            if self.venta and self.venta.tipo_viaje == 'INT':
                raise forms.ValidationError("Este campo es obligatorio para ventas internacionales.")
            # Para ventas nacionales, puede ser None
            return None
        
        # Si es string, limpiar formato
        if isinstance(tipo_cambio_raw, str):
            tipo_cambio_limpio = tipo_cambio_raw.replace('$', '').replace(',', '').replace(' ', '').replace('USD', '').strip()
            if not tipo_cambio_limpio:
                if self.venta and self.venta.tipo_viaje == 'INT':
                    raise forms.ValidationError("Este campo es obligatorio para ventas internacionales.")
                return None
            try:
                tipo_cambio = Decimal(tipo_cambio_limpio)
            except (ValueError, InvalidOperation):
                raise forms.ValidationError("El tipo de cambio debe ser un número válido.")
        elif isinstance(tipo_cambio_raw, Decimal):
            tipo_cambio = tipo_cambio_raw
        else:
            try:
                tipo_cambio = Decimal(str(tipo_cambio_raw))
            except (ValueError, InvalidOperation):
                raise forms.ValidationError("El tipo de cambio debe ser un número válido.")
        
        if tipo_cambio <= 0:
            raise forms.ValidationError("El tipo de cambio debe ser mayor a 0.")
        return tipo_cambio
    
    def clean(self):
        cleaned_data = super().clean()
        tipo_cambio = cleaned_data.get('tipo_cambio_aplicado')
        monto = cleaned_data.get('monto')
        
        if not monto:
            return cleaned_data
        
        # Ventas internacionales: el campo "monto" recibe USD; guardamos monto_usd y monto (MXN) = monto_usd * tc
        if self.venta and self.venta.tipo_viaje == 'INT':
            cleaned_data['monto_usd'] = monto
            if tipo_cambio and tipo_cambio > 0:
                cleaned_data['monto'] = (monto * tipo_cambio).quantize(Decimal('0.01'))
            else:
                # Sin TC no podemos calcular MXN; mantener monto igual (se validó tipo_cambio en INT)
                cleaned_data['monto_usd'] = monto
        else:
            # Ventas nacionales: monto es MXN; monto_usd opcional
            if tipo_cambio and tipo_cambio > 0 and monto:
                cleaned_data['monto_usd'] = (monto / tipo_cambio).quantize(Decimal('0.01'))
            else:
                cleaned_data['monto_usd'] = None
        
        return cleaned_data
    
    def save(self, commit=True):
        """Guarda el formulario; asegura monto_usd en la instancia cuando esté en cleaned_data."""
        instance = super().save(commit=False)
        if 'monto_usd' in self.cleaned_data and self.cleaned_data['monto_usd'] is not None:
            instance.monto_usd = self.cleaned_data['monto_usd']
        if commit:
            instance.save()
        return instance


class ConfirmarAbonoProveedorForm(forms.ModelForm):
    """Formulario para que un contador confirme un abono a proveedor con comprobante."""
    
    class Meta:
        model = AbonoProveedor
        fields = ['comprobante', 'nota_confirmacion']
        widgets = {
            'comprobante': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*,.pdf'
            }),
            'nota_confirmacion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Notas adicionales sobre la confirmación del abono...'
            }),
        }
        help_texts = {
            'comprobante': 'Sube el comprobante de pago al proveedor (imagen o PDF)',
            'nota_confirmacion': 'Notas adicionales sobre la confirmación',
        }
    
    def clean_comprobante(self):
        comprobante = self.cleaned_data.get('comprobante')
        if not comprobante:
            raise forms.ValidationError("Debes subir un comprobante para confirmar el abono.")
        return comprobante


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
        fields = ['monto', 'forma_pago', 'registrado_por', 'requiere_factura'] 
        widgets = {
            'forma_pago': forms.Select(attrs={'class': 'form-select'}), 
            'requiere_factura': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'requiere_factura': 'Requiere factura por este abono',
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
    """Formulario para actualizar servicios de logística."""
    
    # Redefinimos monto_planeado como CharField para que acepte "$" y comas sin fallar
    monto_planeado = forms.CharField(
        label="Monto planificado",
        widget=forms.TextInput(attrs={
            'placeholder': 'Ej: 1500.00',
            'class': 'form-control',
            'type': 'text',  # Importante que sea text para permitir formato de moneda
            'inputmode': 'decimal'
        }),
        required=False
    )
    
    class Meta:
        model = LogisticaServicio
        fields = ['monto_planeado', 'pagado', 'opcion_proveedor']  # Eliminado 'notas'
        widgets = {
            'pagado': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'opcion_proveedor': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Ej: Aeroméxico, Hotel Fiesta Inn, etc.'
            }),
        }
        labels = {
            'pagado': 'Marcar como pagado',
            'opcion_proveedor': 'Opción del proveedor',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si el valor inicial es 0.00, mostrarlo como campo vacío
        if self.instance and self.instance.pk:
            monto = self.instance.monto_planeado
            if monto is not None and monto == Decimal('0.00'):
                self.initial['monto_planeado'] = ''
        elif 'initial' in kwargs and 'monto_planeado' in kwargs['initial']:
            monto = kwargs['initial']['monto_planeado']
            if monto is not None and monto == Decimal('0.00'):
                kwargs['initial']['monto_planeado'] = ''
        # También verificar si viene del formulario sin datos (nuevo servicio)
        if not self.is_bound and not self.instance.pk:
            # Si es un nuevo servicio sin valor, dejar vacío
            if 'monto_planeado' not in self.initial or self.initial.get('monto_planeado') == Decimal('0.00'):
                self.initial['monto_planeado'] = ''
    
    def clean_monto_planeado(self):
        """Limpia el formato de moneda (quita $ y comas) antes de validar."""
        monto = self.cleaned_data.get('monto_planeado')
        if monto:
            # Si es string, limpiar formato (quitar $, USD, comas y espacios)
            if isinstance(monto, str):
                # Remover símbolos de moneda y formateo
                monto_limpio = monto.replace('$', '').replace('USD', '').replace(',', '').replace(' ', '').strip()
                # Si después de limpiar está vacío, retornar None
                if not monto_limpio:
                    return None
                try:
                    monto = Decimal(monto_limpio)
                except (ValueError, InvalidOperation):
                    raise forms.ValidationError("Ingresa un monto válido.")
            # Validar que el monto sea positivo o cero
            if monto < 0:
                raise forms.ValidationError("El monto no puede ser negativo.")
        # Si no hay monto o es 0, retornar 0.00 para guardar en la BD
        return monto if monto else Decimal('0.00')


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
            'requiere_factura_apertura',
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
            'requiere_factura_apertura': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

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
                    
                    # Verificar si la línea tiene el formato con proveedor (y posiblemente opción)
                    if ' - Proveedor: ' in servicio_linea:
                        # Formato puede ser:
                        # "Servicio - Proveedor: Nombre"
                        # "Servicio - Proveedor: Nombre - Opción: Opción elegida"
                        partes = servicio_linea.split(' - Proveedor: ')
                        if len(partes) == 2:
                            nombre_servicio = partes[0].strip()
                            resto = partes[1].strip()
                            
                            # Separar proveedor y opción si existe
                            if ' - Opción: ' in resto:
                                proveedor_parte, opcion_parte = resto.split(' - Opción: ', 1)
                                nombre_proveedor = proveedor_parte.strip()
                                nombre_opcion = opcion_parte.strip()
                            else:
                                nombre_proveedor = resto.strip()
                                nombre_opcion = None
                            
                            if nombre_servicio in SERVICIO_PROVEEDOR_MAP:
                                # Servicio con dropdown de proveedores
                                # Usar filter().first() por si hay varios Proveedor con el mismo nombre (evita MultipleObjectsReturned)
                                field_name = f'proveedor_{nombre_servicio.lower().replace(" ", "_")}'
                                proveedor_obj = Proveedor.objects.filter(nombre=nombre_proveedor).order_by('pk').first()
                                if not proveedor_obj:
                                    proveedor_obj = Proveedor.objects.filter(nombre__icontains=nombre_proveedor).order_by('pk').first()
                                if proveedor_obj:
                                    dynamic_initial[field_name] = proveedor_obj
                                    if nombre_opcion:
                                        opcion_field_name = f'{field_name}_opcion'
                                        dynamic_initial[opcion_field_name] = nombre_opcion
                            else:
                                # Servicio con campo de texto
                                field_name = f'proveedor_{nombre_servicio.lower().replace(" ", "_").replace("/", "_")}'
                                dynamic_initial[field_name] = nombre_proveedor
                                # Añadir opción si existe
                                if nombre_opcion:
                                    opcion_field_name = f'{field_name}_opcion'
                                    dynamic_initial[opcion_field_name] = nombre_opcion
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
            # Usar filter().first() por si hay varios con el mismo nombre (evita MultipleObjectsReturned)
            def buscar_proveedor_por_nombre(nombre_proveedor):
                if not nombre_proveedor:
                    return None
                proveedor = Proveedor.objects.filter(nombre=nombre_proveedor).order_by('pk').first()
                if not proveedor:
                    proveedor = Proveedor.objects.filter(nombre__icontains=nombre_proveedor).order_by('pk').first()
                return proveedor
            
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
                # Para paquete, usar 'Paquete' como servicio principal (no 'Vuelo' y 'Hospedaje' por separado)
                paquete = propuestas.get('paquete', {})
                if isinstance(paquete, dict):
                    # Pre-seleccionar servicio Paquete (no Vuelo y Hospedaje por separado)
                    if 'servicios_seleccionados' not in existing_initial:
                        existing_initial['servicios_seleccionados'] = []
                        dynamic_initial['servicios_seleccionados'] = []
                    if 'Paquete' not in existing_initial['servicios_seleccionados']:
                        existing_initial['servicios_seleccionados'].append('Paquete')
                        if 'servicios_seleccionados' in dynamic_initial:
                            dynamic_initial['servicios_seleccionados'].append('Paquete')
                        else:
                            dynamic_initial['servicios_seleccionados'] = existing_initial['servicios_seleccionados'].copy()
                    
                    # Procesar vuelo (para proveedor, pero no para servicios_seleccionados)
                    vuelo = paquete.get('vuelo', {})
                    if isinstance(vuelo, dict):
                        nombre_aerolinea = vuelo.get('aerolinea', '')
                        if nombre_aerolinea:
                            proveedor = buscar_proveedor_por_nombre(nombre_aerolinea)
                            if proveedor:
                                dynamic_initial['proveedor_vuelo'] = proveedor
                    
                    # Procesar hotel (para proveedor, pero no para servicios_seleccionados)
                    hotel = paquete.get('hotel', {})
                    if isinstance(hotel, dict):
                        nombre_hotel = hotel.get('nombre', '')
                        if nombre_hotel:
                            proveedor = buscar_proveedor_por_nombre(nombre_hotel)
                            if proveedor:
                                dynamic_initial['proveedor_hospedaje'] = proveedor
            
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
        from django.db.models import Q
        for servicio_nombre, servicio_codigo in SERVICIO_PROVEEDOR_MAP.items():
            field_name = f'proveedor_{servicio_nombre.lower().replace(" ", "_")}'
            if field_name not in self.fields:
                # Queryset: proveedores del servicio o "TODO". Incluir siempre el proveedor inicial si existe (para edición).
                initial_proveedor = dynamic_initial.get(field_name)
                initial_pk = initial_proveedor.pk if isinstance(initial_proveedor, Proveedor) else None
                q = Q(servicios__icontains=servicio_codigo) | Q(servicios__icontains='TODO')
                if initial_pk:
                    q = q | Q(pk=initial_pk)
                queryset = Proveedor.objects.filter(q).distinct().order_by('nombre')
                
                self.fields[field_name] = SafeProveedorModelChoiceField(
                    queryset=queryset,
                    required=False,
                    widget=forms.Select(attrs={
                        'class': 'form-select proveedor-select',
                        'data-servicio': servicio_nombre
                    }),
                    label=f"Proveedor de {servicio_nombre}",
                    empty_label="Selecciona un proveedor"
                )
                
                # Añadir campo de opción para este proveedor
                opcion_field_name = f'{field_name}_opcion'
                self.fields[opcion_field_name] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(attrs={
                        'class': 'form-control proveedor-opcion-input',
                        'data-proveedor-field': field_name,
                        'data-servicio': servicio_nombre,
                        'placeholder': f'Opción elegida (ej. Aerolínea, Hotel, Agencia, etc.)'
                    }),
                    label=f"Opción de {servicio_nombre}",
                    help_text=f"Especifica la opción elegida del proveedor (ej. nombre de aerolínea, hotel, etc.)"
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
                
                # Añadir campo de opción para este proveedor (texto)
                opcion_field_name = f'{field_name}_opcion'
                self.fields[opcion_field_name] = forms.CharField(
                    required=False,
                    widget=forms.TextInput(attrs={
                        'class': 'form-control proveedor-opcion-input',
                        'data-proveedor-field': field_name,
                        'data-servicio': servicio_nombre,
                        'placeholder': f'Opción elegida (ej. Aerolínea, Hotel, Agencia, etc.)'
                    }),
                    label=f"Opción de {servicio_nombre}",
                    help_text=f"Especifica la opción elegida del proveedor (ej. nombre de aerolínea, hotel, etc.)"
                )
        
        # IMPORTANTE: Después de crear los campos dinámicos, establecer sus valores iniciales
        # Aplicar tanto para ventas existentes como para nuevas ventas (desde cotización)
        if not self.is_bound:
            # 1. Establecer valores iniciales para campos dinámicos de proveedores y opciones
            # IMPORTANTE: Asegurarse de que los valores se establezcan ANTES de que el template los acceda
            for key, value in self._dynamic_initial.items():
                if (key.startswith('proveedor_') or key.endswith('_opcion')) and key in self.fields:
                    # Conservar proveedor (instancia) y opción (texto) para que al editar se muestren correctamente
                    self.initial[key] = value
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
            
            # Para ventas internacionales: mostrar valores en USD (campo o conversión legacy)
            if instance and instance.pk and instance.tipo_viaje == 'INT':
                # Cantidad de apertura en USD (campo o legacy)
                apertura_usd = getattr(instance, 'cantidad_apertura_usd', None)
                if apertura_usd is None and instance.tipo_cambio and instance.cantidad_apertura:
                    apertura_usd = (instance.cantidad_apertura / instance.tipo_cambio).quantize(Decimal('0.01'))
                if apertura_usd is not None and apertura_usd > 0:
                    existing_initial['cantidad_apertura'] = apertura_usd
                    dynamic_initial['cantidad_apertura'] = apertura_usd
                # Costo neto en USD (campo o legacy)
                costo_neto_usd = getattr(instance, 'costo_neto_usd', None)
                if costo_neto_usd is None and instance.tipo_cambio and instance.costo_neto:
                    costo_neto_usd = (instance.costo_neto / instance.tipo_cambio).quantize(Decimal('0.01'))
                if costo_neto_usd is not None and costo_neto_usd > 0:
                    existing_initial['costo_neto'] = costo_neto_usd
                    dynamic_initial['costo_neto'] = costo_neto_usd
                # Costo de modificación en USD (campo o legacy)
                mod_usd = getattr(instance, 'costo_modificacion_usd', None)
                if mod_usd is None and instance.tipo_cambio and instance.costo_modificacion:
                    mod_usd = (instance.costo_modificacion / instance.tipo_cambio).quantize(Decimal('0.01'))
                if mod_usd is not None and mod_usd != 0 and 'costo_modificacion' in existing_initial:
                    existing_initial['costo_modificacion'] = mod_usd
                    dynamic_initial['costo_modificacion'] = mod_usd
        
        # Configurar help_text y required para documentos_cliente (múltiples archivos)
        if 'documentos_cliente' in self.fields:
            # Cambiar el campo a nuestro campo personalizado
            self.fields['documentos_cliente'] = MultipleFileField(
                required=False,
                widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': '*/*'}),
                help_text=""
            )
        
        # Agregar campos de edición solo cuando se está editando una venta existente
        if self.instance and self.instance.pk:
            # SEGURIDAD: JEFE/ADMIN puede ver y ajustar el acumulado (restar o cambiar); resto ve 0 y suma al guardar
            from usuarios import permissions as perm
            _user = getattr(self.request, 'user', None)
            puede_ajustar = _user and (_user.is_superuser or perm.has_full_access(_user, self.request))
            if puede_ajustar:
                initial_mod = getattr(self.instance, 'costo_modificacion', None) or Decimal('0.00')
                help_mod = 'Puede ajustar o reducir el total acumulado de modificaciones. Este valor reemplaza el acumulado al guardar.'
            else:
                initial_mod = Decimal('0.00')
                help_mod = 'Costo adicional por modificar esta venta. Se sumará al costo total. Deje en 0 si no aplica.'
            self.fields['costo_modificacion'] = forms.DecimalField(
                max_digits=10,
                decimal_places=2,
                required=False,
                initial=initial_mod,
                widget=forms.TextInput(attrs={
                    'class': 'form-control',
                    'placeholder': '0.00'
                }),
                label='Costo de Modificación',
                help_text=help_mod
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

        # Servicios Contratados (punto 2) es obligatorio: al menos un servicio debe estar seleccionado
        servicios_seleccionados = cleaned_data.get('servicios_seleccionados', [])
        if not servicios_seleccionados:
            self.add_error(
                'servicios_seleccionados',
                'Por favor, llene los campos de Servicios Contratados: seleccione al menos un servicio para poder continuar.'
            )

        # Validar que si se selecciona "Trámites de Documentación", se especifique el tipo de trámite
        if servicios_seleccionados and 'Trámites de Documentación' in servicios_seleccionados:
            tipo_tramite = cleaned_data.get('tipo_tramite_documentacion', '').strip()
            if not tipo_tramite:
                self.add_error('tipo_tramite_documentacion', 'Debes seleccionar si es trámite de Visa o Pasaporte cuando seleccionas "Trámites de Documentación".')

        # ✅ NUEVO: Lógica para "Directo a Proveedor" (PRO)
        modo_pago_apertura = cleaned_data.get('modo_pago_apertura')
        if modo_pago_apertura == 'PRO':
            # Calcular el total final con descuentos
            costo_venta_final = cleaned_data.get('costo_venta_final') or Decimal('0.00')
            costo_modificacion = cleaned_data.get('costo_modificacion') or Decimal('0.00')
            descuento_km = cleaned_data.get('descuento_kilometros_mxn') or Decimal('0.00')
            descuento_promo = cleaned_data.get('descuento_promociones_mxn') or Decimal('0.00')
            
            # Convertir a Decimal si vienen como string
            if isinstance(costo_venta_final, str):
                try:
                    costo_venta_final = Decimal(costo_venta_final.replace(',', ''))
                except (ValueError, InvalidOperation):
                    costo_venta_final = Decimal('0.00')
            if isinstance(costo_modificacion, str):
                try:
                    costo_modificacion = Decimal(costo_modificacion.replace(',', ''))
                except (ValueError, InvalidOperation):
                    costo_modificacion = Decimal('0.00')
            if isinstance(descuento_km, str):
                try:
                    descuento_km = Decimal(descuento_km.replace(',', ''))
                except (ValueError, InvalidOperation):
                    descuento_km = Decimal('0.00')
            if isinstance(descuento_promo, str):
                try:
                    descuento_promo = Decimal(descuento_promo.replace(',', ''))
                except (ValueError, InvalidOperation):
                    descuento_promo = Decimal('0.00')
            
            costo_base = costo_venta_final + costo_modificacion
            total_descuentos = descuento_km + descuento_promo
            total_final = max(Decimal('0.00'), costo_base - total_descuentos)
            
            # Establecer cantidad_apertura igual al total final
            cleaned_data['cantidad_apertura'] = total_final

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
        
        # ✅ NUEVO: Lógica para "Directo a Proveedor" (PRO) - Después de limpiar valores
        modo_pago_apertura = cleaned_data.get('modo_pago_apertura')
        if modo_pago_apertura == 'PRO':
            # Obtener valores ya limpios
            costo_venta_final = cleaned_data.get('costo_venta_final') or Decimal('0.00')
            costo_modificacion = cleaned_data.get('costo_modificacion') or Decimal('0.00')
            descuento_km = cleaned_data.get('descuento_kilometros_mxn') or Decimal('0.00')
            descuento_promo = cleaned_data.get('descuento_promociones_mxn') or Decimal('0.00')
            
            # Calcular total final
            costo_base = costo_venta_final + costo_modificacion
            total_descuentos = descuento_km + descuento_promo
            total_final = max(Decimal('0.00'), costo_base - total_descuentos)
            
            # Establecer cantidad_apertura igual al total final
            cleaned_data['cantidad_apertura'] = total_final

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
            
            # Calcular el total en USD (ventas INT se guardan solo en USD; tipo_cambio es referencia)
            total_usd = tarifa_base_usd + impuestos_usd + suplementos_usd + tours_usd

            # Guardar en campos USD; no convertir a MXN (cantidades INT en dólares)
            if total_usd > 0:
                cleaned_data['costo_venta_final_usd'] = total_usd.quantize(Decimal('0.01'))
                cleaned_data['costo_venta_final'] = Decimal('0.00')  # INT: no usar MXN

            costo_neto_usd = limpiar_valor_moneda(cleaned_data.get('costo_neto')) or Decimal('0.00')
            cleaned_data['costo_neto_usd'] = costo_neto_usd.quantize(Decimal('0.01')) if costo_neto_usd else Decimal('0.00')
            cleaned_data['costo_neto'] = Decimal('0.00')  # INT: no usar MXN

            cantidad_apertura_usd = limpiar_valor_moneda(cleaned_data.get('cantidad_apertura')) or Decimal('0.00')
            cleaned_data['cantidad_apertura_usd'] = cantidad_apertura_usd.quantize(Decimal('0.01')) if cantidad_apertura_usd else None
            # Directo a Proveedor (PRO): apertura = total en USD
            if modo_pago_apertura == 'PRO' and total_usd > 0:
                cleaned_data['cantidad_apertura_usd'] = total_usd.quantize(Decimal('0.01'))
            cleaned_data['cantidad_apertura'] = Decimal('0.00')  # INT: no usar MXN

            costo_mod = limpiar_valor_moneda(cleaned_data.get('costo_modificacion')) or Decimal('0.00')
            cleaned_data['costo_modificacion_usd'] = costo_mod.quantize(Decimal('0.01')) if costo_mod else Decimal('0.00')
            cleaned_data['costo_modificacion'] = Decimal('0.00')  # INT: no usar MXN
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
        base_total = None
        if tipo_viaje == 'INT':
            total_usd = (cleaned_data.get('costo_venta_final_usd') or Decimal('0.00')) + (cleaned_data.get('costo_modificacion_usd') or Decimal('0.00'))
            tc = cleaned_data.get('tipo_cambio') or Decimal('0.0000')
            if tc > 0:
                base_total = (total_usd * tc).quantize(Decimal('0.01'))
        else:
            costo_mod = getattr(self.instance, 'costo_modificacion', Decimal('0.00')) or Decimal('0.00')
            base_total = (cleaned_data.get('costo_venta_final') or Decimal('0.00')) + costo_mod
        if cliente and tipo_viaje and base_total is not None:
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
            
            # Obtener la promoción seleccionada del radio button (solo una promoción puede estar seleccionada)
            promocion_seleccionada_id = self.data.get('promocion_seleccionada', '').strip()
            
            # Si hay una promoción seleccionada, aplicar solo esa
            if promocion_seleccionada_id:
                try:
                    promocion_seleccionada_id = int(promocion_seleccionada_id)
                    for p in promos:
                        promo = p['promo']
                        # Solo aplicar la promoción seleccionada
                        if promo.id == promocion_seleccionada_id:
                            aceptadas.append(p)
                            # Solo sumar el descuento si es de tipo DESCUENTO
                            if p.get('monto_descuento') and p['monto_descuento'] > 0:
                                total_desc += p['monto_descuento']
                            if p.get('km_bono') and p['km_bono'] > 0:
                                self.promos_km.append({'promo': promo, 'km_bono': p['km_bono']})
                                resumen_list.append(f"{promo.nombre} (+{p['km_bono']} km)")
                            else:
                                resumen_list.append(f"{promo.nombre} (-${p['monto_descuento']})")
                            break  # Solo una promoción seleccionada
                except (ValueError, TypeError):
                    # Si el ID no es válido, no aplicar ninguna promoción
                    pass
            else:
                # Si no hay promoción seleccionada explícitamente, aplicar solo las que no requieren confirmación
                # (comportamiento de respaldo para compatibilidad)
                for p in promos:
                    promo = p['promo']
                    requiere = p.get('requiere_confirmacion', False)
                    # Solo aplicar si no requiere confirmación (automáticas)
                    if not requiere:
                        aceptadas.append(p)
                        if p.get('monto_descuento') and p['monto_descuento'] > 0:
                            total_desc += p['monto_descuento']
                        if p.get('km_bono') and p['km_bono'] > 0:
                            self.promos_km.append({'promo': promo, 'km_bono': p['km_bono']})
                            resumen_list.append(f"{promo.nombre} (+{p['km_bono']} km)")
                        else:
                            resumen_list.append(f"{promo.nombre} (-${p['monto_descuento']})")
                        # Solo aplicar la primera automática (para mantener compatibilidad con el comportamiento anterior)
                        break

            self.promos_aplicadas_aceptadas = aceptadas
            self.total_descuento_promos = total_desc
            self.resumen_promos_text = "; ".join(resumen_list)

            # Nota: El descuento de promociones se guarda en descuento_promociones_mxn
            # y se aplica junto con el descuento de kilómetros al calcular el total final.
            # No restamos aquí del costo_venta_final para mantener la transparencia del cálculo.

        # ------------------- Kilómetros Movums -------------------
        cleaned_data['aplica_descuento_kilometros'] = aplica_descuento
        cleaned_data['descuento_kilometros_mxn'] = descuento if aplica_descuento else Decimal('0.00')
        
        # ✅ INTEGRIDAD: Validar que fecha_fin_viaje >= fecha_inicio_viaje
        fecha_inicio = cleaned_data.get('fecha_inicio_viaje')
        fecha_fin = cleaned_data.get('fecha_fin_viaje')
        
        if fecha_inicio and fecha_fin and fecha_fin < fecha_inicio:
            self.add_error(
                'fecha_fin_viaje',
                'La fecha de regreso debe ser igual o posterior a la fecha de inicio del viaje.'
            )
        
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

                # Obtener proveedor y opción para este servicio
                proveedor_info = ""
                opcion_info = ""
                if nombre in SERVICIO_PROVEEDOR_MAP:
                    # Servicio con dropdown de proveedores
                    field_name = f'proveedor_{nombre.lower().replace(" ", "_")}'
                    proveedor = self.cleaned_data.get(field_name)
                    if proveedor:
                        proveedor_info = f" - Proveedor: {proveedor.nombre}"
                        # Obtener opción si existe
                        opcion_field_name = f'{field_name}_opcion'
                        opcion_texto = self.cleaned_data.get(opcion_field_name, '').strip()
                        if opcion_texto:
                            opcion_info = f" - Opción: {opcion_texto}"
                else:
                    # Servicio con campo de texto
                    field_name = f'proveedor_{nombre.lower().replace(" ", "_").replace("/", "_")}'
                    proveedor_texto = self.cleaned_data.get(field_name, '').strip()
                    if proveedor_texto:
                        proveedor_info = f" - Proveedor: {proveedor_texto}"
                        # Obtener opción si existe
                        opcion_field_name = f'{field_name}_opcion'
                        opcion_texto = self.cleaned_data.get(opcion_field_name, '').strip()
                        if opcion_texto:
                            opcion_info = f" - Opción: {opcion_texto}"

                # Si es "Trámites de Documentación", agregar el tipo de trámite
                tipo_tramite_info = ""
                if nombre == "Trámites de Documentación":
                    tipo_tramite = self.cleaned_data.get('tipo_tramite_documentacion', '').strip()
                    if tipo_tramite:
                        tipo_tramite_display = "Visa" if tipo_tramite == "VISA" else "Pasaporte"
                        tipo_tramite_info = f" - Tipo: {tipo_tramite_display}"

                servicios_detalle_list.append(f"{nombre}{tipo_tramite_info}{proveedor_info}{opcion_info}")

        # Guardar códigos separados por coma en 'servicios_seleccionados' (ej: "VUE,HOS,SEG")
        instance.servicios_seleccionados = ','.join(servicios_codigos) if servicios_codigos else ''

        # Guardar nombres completos con proveedores separados por línea nueva en 'servicios_detalle'
        instance.servicios_detalle = '\n'.join(servicios_detalle_list) if servicios_detalle_list else ''

        # Si hay un proveedor principal seleccionado (del dropdown), guardarlo en el campo proveedor
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

        # Ventas internacionales: persistir campos USD (fuente de verdad; no MXN)
        if self.cleaned_data.get('tipo_viaje') == 'INT':
            instance.cantidad_apertura_usd = self.cleaned_data.get('cantidad_apertura_usd')
            instance.costo_venta_final_usd = self.cleaned_data.get('costo_venta_final_usd')
            instance.costo_neto_usd = self.cleaned_data.get('costo_neto_usd')
            instance.costo_modificacion_usd = self.cleaned_data.get('costo_modificacion_usd')

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
                ).distinct().order_by('nombre'),
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
                ).distinct().order_by('nombre'),
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
            ).distinct().order_by('nombre'),
            required=False,
            empty_label="Selecciona una aerolínea...",
            widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'paquete_proveedor_vuelo'}),
            label='Aerolínea'
        )
        self.fields['paquete_proveedor_vuelo'].label_from_instance = label_from_nombre
        
        self.fields['paquete_proveedor_hotel'] = forms.ModelChoiceField(
            queryset=Proveedor.objects.filter(
                servicios__icontains='HOTELES'
            ).distinct().order_by('nombre'),
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
            ).distinct().order_by('nombre'),
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
            ).distinct().order_by('nombre'),
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
        
        # Validar que la suma de adultos y menores coincida con el total de pasajeros
        pasajeros = cleaned.get('pasajeros')
        adultos = cleaned.get('adultos')
        menores = cleaned.get('menores')
        
        # Convertir a enteros si vienen como strings o None
        if pasajeros is not None:
            try:
                pasajeros = int(pasajeros) if not isinstance(pasajeros, int) else pasajeros
            except (ValueError, TypeError):
                pasajeros = None
        
        if adultos is not None:
            try:
                adultos = int(adultos) if not isinstance(adultos, int) else adultos
            except (ValueError, TypeError):
                adultos = None
        
        if menores is not None:
            try:
                menores = int(menores) if not isinstance(menores, int) else menores
            except (ValueError, TypeError):
                menores = None
        
        # Solo validar si todos los campos tienen valores válidos
        if pasajeros is not None and adultos is not None and menores is not None:
            suma_adultos_menores = adultos + menores
            if pasajeros != suma_adultos_menores:
                error_msg = (
                    f"El número total de pasajeros ({pasajeros}) no coincide con la suma de adultos "
                    f"({adultos}) y menores ({menores}). Por favor, rectifica los números para que "
                    f"adultos + menores = {pasajeros} pasajeros."
                )
                self.add_error('adultos', error_msg)
                self.add_error('menores', error_msg)
        
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
        
        # Establecer fecha_cotizacion automáticamente si no existe (fecha actual)
        if 'fecha_cotizacion' not in instance.propuestas or not instance.propuestas.get('fecha_cotizacion'):
            from django.utils import timezone
            instance.propuestas['fecha_cotizacion'] = timezone.localdate().isoformat()
        
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
        
        # Aplicar ajustes para asesores de campo
        # Los ajustes se aplican SIEMPRE para asesores de campo, independientemente de la forma de pago
        if instance.vendedor:
            try:
                # Obtener tipo de cambio si está disponible en las propuestas
                tipo_cambio = None
                if isinstance(propuestas, dict):
                    # Buscar tipo de cambio en diferentes lugares de las propuestas
                    tipo_cambio_str = propuestas.get('tipo_cambio')
                    if tipo_cambio_str:
                        try:
                            tipo_cambio = Decimal(str(tipo_cambio_str))
                        except (ValueError, InvalidOperation):
                            pass
                
                # Aplicar ajustes de campo
                resultado_ajustes = aplicar_ajustes_cotizacion_campo(instance, tipo_cambio=tipo_cambio)
                
                # Actualizar el total_estimado con el total final después de ajustes
                if resultado_ajustes['total_ajustes'] > Decimal('0.00'):
                    instance.total_estimado = resultado_ajustes['total_final']
                    
                    # Guardar información de ajustes en las propuestas para referencia
                    if not isinstance(instance.propuestas, dict):
                        instance.propuestas = {}
                    
                    # Guardar información de ajustes aplicados
                    instance.propuestas['ajustes_campo'] = {
                        'aplicado': True,
                        'ajustes': resultado_ajustes['ajustes_aplicados'],
                        'total_ajustes': str(resultado_ajustes['total_ajustes']),
                        'total_base': str(total_estimado),
                        'total_final': str(resultado_ajustes['total_final'])
                    }
            except Exception as e:
                # Si hay algún error al aplicar ajustes, continuar sin ajustes
                # pero registrar el error para debugging
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error al aplicar ajustes de campo en cotización: {e}")
        
        if commit:
            instance.save()
        return instance


# ------------------- CotizacionAdjudicarForm -------------------

class CotizacionAdjudicarForm(forms.Form):
    """Formulario para adjudicar una cotización a un vendedor (por ahora solo asesores de campo)."""
    vendedor = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Adjudicar a',
        help_text='Seleccione el asesor de campo al que se adjudicará esta cotización.'
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if request and request.user.is_authenticated:
            from usuarios import permissions as perm
            self.fields['vendedor'].queryset = perm.get_queryset_vendedores_adjudicables(request.user, request)


# ------------------- SolicitudCancelacionForm -------------------

class SolicitudCancelacionForm(forms.ModelForm):
    """Formulario para solicitar la cancelación de una venta."""
    
    class Meta:
        model = SolicitudCancelacion
        fields = ['motivo']
        widgets = {
            'motivo': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Describe el motivo de la cancelación de la venta...',
                'required': True
            }),
        }
        labels = {
            'motivo': 'Motivo de la Cancelación',
        }
        help_texts = {
            'motivo': 'Proporciona una explicación detallada del motivo por el cual se solicita cancelar esta venta.',
        }
    
    def clean_motivo(self):
        motivo = self.cleaned_data.get('motivo')
        if motivo and len(motivo.strip()) < 10:
            raise forms.ValidationError('El motivo de cancelación debe tener al menos 10 caracteres.')
        return motivo
