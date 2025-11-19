from django import forms
from .models import Cliente
from django.core.exceptions import ValidationError

class ClienteForm(forms.ModelForm):
    """
    Formulario especializado para la creación y edición de clientes,
    aplicando validaciones condicionales según el tipo (Particular/Empresa).
    """
    class Meta:
        model = Cliente
        # Incluimos todos los campos, la validación se encarga de requerir/limpiar
        fields = '__all__'
        
        # Widgets para aplicar clases de Bootstrap para estilizado
        widgets = {
            'tipo_cliente': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Juan'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Pérez'}),
            'nombre_empresa': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: Movums S.A. de C.V.'}),
            'rfc': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: RFC123456789'}),
            'direccion_fiscal': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3, 'placeholder': 'Calle, número, colonia...'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ej: 5512345678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'contacto@ejemplo.com'}),
            'fuente_contacto': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'notas': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3}),
            'fecha_nacimiento': forms.DateInput(attrs={'class': 'form-control rounded-3', 'type': 'date'}),
            'documento_identificacion': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'preferencias_viaje': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3}),
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
            cleaned_data['fecha_nacimiento'] = None
            cleaned_data['documento_identificacion'] = None


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
            
        # Validación común: Teléfono y Email (si aplica)
        if not cleaned_data.get('telefono'):
             self.add_error('telefono', 'El número de teléfono es obligatorio para contacto.')

        return cleaned_data
