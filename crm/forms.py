from django import forms
from .models import Cliente, PromocionKilometros
from django.core.exceptions import ValidationError
from decimal import Decimal

class ClienteForm(forms.ModelForm):
    """
    Formulario especializado para la creación y edición de clientes,
    aplicando validaciones condicionales según el tipo (Particular/Empresa).
    """
    class Meta:
        model = Cliente
        # Excluimos campos automáticos/calculados que no deben ser editables
        exclude = [
            'cotizaciones_generadas',  # Campo automático
            'kilometros_acumulados',  # Campo automático con default=0.00
            'kilometros_disponibles',  # Campo automático con default=0.00
            'ultima_fecha_km',  # Campo automático
            'fecha_ultimo_bono_cumple',  # Campo automático
            'fecha_registro',  # Campo automático
            'fecha_actualizacion',  # Campo automático
            'documento_identificacion',  # Campo legacy
        ]
        
        # Widgets para aplicar clases de Bootstrap para estilizado
        widgets = {
            'tipo_cliente': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Juan'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Pérez'}),
            'genero': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'nacionalidad': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Mexicana'}),
            'nombre_empresa': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Movums S.A. de C.V.'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: RFC123456789'}),
            'direccion_fiscal': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3, 'placeholder': 'Calle, número, colonia...'}),
            'industria': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Tecnología, Manufactura, Servicios...'}),
            'politicas_viaje_internas': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 4, 'placeholder': 'Políticas y restricciones de viaje de la empresa'}),
            'responsable_administrativo': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Nombre del responsable'}),
            'credito': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'monto_credito': forms.NumberInput(attrs={'class': 'form-control rounded-3', 'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: 5512345678'}),
            'telefono_adicional': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: 5587654321'}),
            'email': forms.EmailInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'contacto@ejemplo.com'}),
            'fuente_contacto': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'notas': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3}),
            'fecha_nacimiento': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control rounded-3', 'type': 'date'}),
            'ine_imagen': forms.ClearableFileInput(attrs={'class': 'form-control rounded-3', 'accept': 'image/*'}),
            'visa_numero': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Número de visa'}),
            'visa_vigencia': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control rounded-3', 'type': 'date'}),
            'pasaporte_numero': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Número de pasaporte'}),
            'pasaporte_vigencia': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control rounded-3', 'type': 'date'}),
            'empresa_asociada': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'preferencias_viaje': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3}),
            'participa_kilometros': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'referencia_programa': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Número de tarjeta'}),
            'referido_por': forms.Select(attrs={'class': 'form-select rounded-3'}),
        }
        
    def clean(self):
        """
        Sobreescribe la validación para hacer campos obligatorios
        solo si corresponden al tipo de cliente seleccionado.
        """
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo_cliente')

        if tipo == 'EMPRESA':
            # --- VALIDACIÓN para Empresas ---
            if not cleaned_data.get('nombre_empresa'):
                self.add_error('nombre_empresa', 'La Razón Social/Nombre de la Empresa es obligatorio.')
            if not cleaned_data.get('rfc'):
                self.add_error('rfc', 'El RFC / ID Fiscal es obligatorio para la facturación.')
            if not cleaned_data.get('direccion_fiscal'):
                self.add_error('direccion_fiscal', 'La Dirección Fiscal es obligatoria.')
            
            # --- LIMPIEZA: Asegurarse de que los campos de particular sean NULL ---
            # Esto evita guardar datos irrelevantes en la BD
            cleaned_data['nombre'] = None
            cleaned_data['apellido'] = None
            cleaned_data['genero'] = 'NS'
            cleaned_data['nacionalidad'] = None
            cleaned_data['fecha_nacimiento'] = None
            cleaned_data['ine_imagen'] = None
            cleaned_data['visa_numero'] = None
            cleaned_data['visa_vigencia'] = None
            cleaned_data['pasaporte_numero'] = None
            cleaned_data['pasaporte_vigencia'] = None
            cleaned_data['empresa_asociada'] = None


        elif tipo == 'PARTICULAR':
            # --- VALIDACIÓN para Particulares ---
            if not cleaned_data.get('nombre'):
                self.add_error('nombre', 'El Nombre es obligatorio para particulares.')
            if not cleaned_data.get('apellido'):
                self.add_error('apellido', 'El Apellido es obligatorio para particulares.')
                
            # --- LIMPIEZA: Asegurarse de que los campos de empresa sean NULL ---
            cleaned_data['nombre_empresa'] = None
            cleaned_data['rfc'] = None
            cleaned_data['direccion_fiscal'] = None
            cleaned_data['industria'] = None
            cleaned_data['politicas_viaje_internas'] = None
            cleaned_data['responsable_administrativo'] = None
            cleaned_data['credito'] = False
            cleaned_data['monto_credito'] = None
            
        # Validación común: Teléfono y Email (si aplica)
        if not cleaned_data.get('telefono'):
             self.add_error('telefono', 'El número de teléfono es obligatorio para contacto.')

        return cleaned_data
    
    def save(self, commit=True):
        """
        Sobreescribe el método save para asegurar que los campos automáticos
        tengan sus valores por defecto al crear un nuevo cliente.
        """
        instance = super().save(commit=False)
        
        # Si es un nuevo cliente (sin pk), inicializar campos automáticos
        if not instance.pk:
            if instance.cotizaciones_generadas is None:
                instance.cotizaciones_generadas = 0
            if instance.kilometros_acumulados is None:
                instance.kilometros_acumulados = Decimal('0.00')
            if instance.kilometros_disponibles is None:
                instance.kilometros_disponibles = Decimal('0.00')
        
        if commit:
            instance.save()
        return instance


class PromocionKilometrosForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ordenar clientes por nombre o nombre_empresa
        if 'clientes' in self.fields:
            from crm.models import Cliente
            self.fields['clientes'].queryset = Cliente.objects.all().order_by('nombre', 'nombre_empresa')
    
    class Meta:
        model = PromocionKilometros
        fields = [
            'nombre',
            'descripcion',
            'tipo',
            'porcentaje_descuento',
            'monto_tope_mxn',
            'condicion',
            'valor_condicion',
            'alcance',
            'clientes',
            'requiere_confirmacion',
            'kilometros_bono',
            'fecha_inicio',
            'fecha_fin',
            'activa',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la promoción'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción breve'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'porcentaje_descuento': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.00'}),
            'monto_tope_mxn': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.00'}),
            'condicion': forms.Select(attrs={'class': 'form-select'}),
            'valor_condicion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 2 para mes, 14-02 para cumple'}),
            'alcance': forms.Select(attrs={'class': 'form-select', 'id': 'id_alcance'}),
            'clientes': forms.SelectMultiple(attrs={
                'class': 'form-select',
                'id': 'id_clientes',
                'size': '8',
                'style': 'min-height: 200px; width: 100%; display: none;'
            }),
            'requiere_confirmacion': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'kilometros_bono': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.00'}),
            'fecha_inicio': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'fecha_fin': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'clientes': 'Clientes específicos',
        }
        help_texts = {
            'clientes': 'Selecciona uno o más clientes. Solo aplica si el alcance es "Cliente(s) específico(s)".',
        }

    def clean(self):
        cleaned = super().clean()
        fi = cleaned.get('fecha_inicio')
        ff = cleaned.get('fecha_fin')
        if fi and ff and ff < fi:
            self.add_error('fecha_fin', 'La fecha fin debe ser mayor o igual a la fecha inicio.')
        porcentaje = cleaned.get('porcentaje_descuento')
        if porcentaje is not None and porcentaje < 0:
            self.add_error('porcentaje_descuento', 'El porcentaje no puede ser negativo.')
        tipo = cleaned.get('tipo')
        km = cleaned.get('kilometros_bono') or Decimal('0.00')
        if tipo == 'KM' and km <= 0:
            self.add_error('kilometros_bono', 'Ingresa kilómetros mayores a 0 para bonificar.')
        
        # Validar que si el alcance es CLIENTE_ESPECIFICO, se seleccione al menos un cliente
        alcance = cleaned.get('alcance')
        clientes = cleaned.get('clientes')
        if alcance == 'CLIENTE_ESPECIFICO':
            if not clientes or len(clientes) == 0:
                self.add_error('clientes', 'Debes seleccionar al menos un cliente cuando el alcance es "Cliente(s) específico(s)".')
        
        return cleaned