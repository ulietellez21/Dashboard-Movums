from django.contrib import admin
from django import forms # <--- ¡IMPORTANTE! Se necesita para el formulario
from django.utils.html import format_html
# Importamos Sum para referencia (aunque no se usa en este archivo)
from django.db.models import Sum 
from .models import (
    VentaViaje,
    AbonoPago,
    Logistica,
    ContratoPlantilla,
    ContratoGenerado,
    Proveedor,
    ConfirmacionVenta,
    LogisticaServicio,
) # Importar modelos

# =================================================================
# 0. Formulario Personalizado para VentaViaje (Maneja CheckboxSelectMultiple)
# =================================================================

class VentaViajeForm(forms.ModelForm):
    
    # 1. Definimos el campo 'servicios_seleccionados' para usar el widget CheckboxSelectMultiple
    servicios_seleccionados = forms.MultipleChoiceField(
        # Usamos los choices definidos en el modelo VentaViaje
        choices=VentaViaje.SERVICIOS_CHOICES, 
        required=False,
        # Este es el widget que muestra las casillas de verificación
        widget=forms.CheckboxSelectMultiple, 
        label="Servicios Incluidos (Selección Múltiple)",
    )

    class Meta:
        model = VentaViaje
        fields = '__all__' 

    # 2. Inicialización: Convierte el valor de la BD (cadena "VUE,HOS") a lista (['VUE', 'HOS'])
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Si existe una instancia, tomamos el valor de la BD
            service_string = self.instance.servicios_seleccionados
            if service_string:
                # Carga la cadena separada por comas y la convierte en una lista de Python
                self.initial['servicios_seleccionados'] = [s.strip() for s in service_string.split(',')]
            else:
                self.initial['servicios_seleccionados'] = []

    # 3. Limpieza: Convierte el valor del formulario (lista ['VUE', 'HOS']) a cadena ("VUE,HOS")
    def clean_servicios_seleccionados(self):
        # Obtiene la lista limpia de códigos seleccionados
        service_list = self.cleaned_data['servicios_seleccionados']
        
        # Devuelve una cadena separada por comas para guardar en el TextField del modelo
        return ','.join(service_list)


# =================================================================
# 1. AbonoPago Admin & Inlines
# =================================================================

# --- AbonoPago Admin (Se registra al final) ---
class AbonoPagoAdmin(admin.ModelAdmin):
    list_display = ('venta', 'monto', 'forma_pago', 'fecha_pago', 'registrado_por')
    list_filter = ('fecha_pago', 'forma_pago', 'registrado_por')
    search_fields = ('venta__id', 'venta__cliente__nombre_empresa', 'venta__cliente__nombre', 'venta__cliente__apellido')
    date_hierarchy = 'fecha_pago'

# --- AbonoPago Inline ---
class AbonoPagoInline(admin.TabularInline):
    model = AbonoPago
    extra = 0
    fields = ('monto', 'forma_pago', 'registrado_por') 
    readonly_fields = ('registrado_por',) 
    
    def save_model(self, request, obj, form, change):
        if not obj.registrado_por_id:
            obj.registrado_por = request.user
        super().save_model(request, obj, form, change)

# --- Logistica Admin Inline ---
class LogisticaInline(admin.TabularInline):
    model = Logistica
    max_num = 1
    can_delete = False
    fields = ('vuelo_confirmado', 'hospedaje_reservado', 'traslado_confirmado', 'tickets_confirmado')
    readonly_fields = ()


# --- ContratoGenerado Inline (Para ver el contrato en la Venta) ---
class ContratoGeneradoInline(admin.StackedInline):
    model = ContratoGenerado
    max_num = 1
    can_delete = False
    fields = ('plantilla', 'contenido_final', 'fecha_generacion')
    readonly_fields = ('plantilla', 'contenido_final', 'fecha_generacion')
    verbose_name_plural = 'Contrato Generado (Automático)'


# =================================================================
# 2. VentaViaje Admin (Modelo Principal)
# =================================================================

@admin.register(VentaViaje)
class VentaViajeAdmin(admin.ModelAdmin):
    
    # ASIGNACIÓN DEL FORMULARIO PERSONALIZADO (Clave para los checkboxes)
    form = VentaViajeForm 
    
    # ------------------- Métodos de Visualización -------------------
    
    def display_saldo_restante(self, obj):
        """Muestra la propiedad dinámica saldo_restante, formateada y con color."""
        saldo = obj.saldo_restante
        color = 'red' if saldo > 0 else 'green'
        return format_html(f'<span style="color: {color}; font-weight: bold;">${saldo:,.2f}</span>')
    display_saldo_restante.short_description = 'Saldo Pendiente'
    display_saldo_restante.admin_order_field = 'costo_venta_final' 
    
    # ------------------- Configuración de Admin -------------------

    list_display = (
        'id', 
        'cliente', 
        'vendedor', 
        'tipo_viaje', 
        'proveedor',
        'servicios_seleccionados_display', # Mostramos el resumen de servicios
        'costo_venta_final', 
        'display_saldo_restante', 
        'fecha_inicio_viaje'
    )
    
    list_filter = ('vendedor', 'tipo_viaje', 'fecha_inicio_viaje') 
    
    search_fields = ('cliente__nombre_empresa', 'cliente__nombre', 'cliente__apellido', 'cliente__rfc', 'vendedor__username', 'id')
    ordering = ('-fecha_creacion',)
    
    inlines = [LogisticaInline, ContratoGeneradoInline, AbonoPagoInline]
    
    # Definimos la estructura de la página de edición de la venta (ACTUALIZADO)
    fieldsets = (
        ('Información Básica y Cliente', {
            'fields': (
                ('cliente', 'vendedor'), 
                'proveedor',
                'tipo_viaje', 
                'servicios_seleccionados', # Usa el CheckboxSelectMultiple gracias al VentaViajeForm
                'servicios_detalle',        # Campo de detalle de servicios (Texto libre)
                'pasajeros', 
                'documentos_cliente', 
                ('fecha_inicio_viaje', 'fecha_fin_viaje')
            ),
        }),
        ('Costos y Finanzas', {
            # Se eliminaron campos obsoletos como 'tipo_cambio_usd'
            'fields': ('costo_venta_final', 'cantidad_apertura', 'costo_neto', 'display_saldo_restante', 'fecha_vencimiento_pago'), 
        }),
        # La sección 'Configuración Interna' se eliminó porque sus campos ya no existen
    )
    
    readonly_fields = ('display_saldo_restante', 'servicios_seleccionados_display')

    # Sobrescribimos save_model para asignar el vendedor automáticamente al crear
    def save_model(self, request, obj, form, change):
        if not obj.vendedor_id:
            obj.vendedor = request.user
        super().save_model(request, obj, form, change)


# =================================================================
# 3. Modelos Secundarios (Registrados con @admin.register)
# =================================================================

@admin.register(ContratoPlantilla)
class ContratoPlantillaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'fecha_actualizacion')
    list_filter = ('tipo',)
    search_fields = ('nombre', 'contenido_base')
    fieldsets = (
        (None, {
            'fields': ('nombre', 'tipo', 'contenido_base'),
            'description': 'Aquí se define la plantilla base. Usar variables de sustitución en formato Python como {cliente_nombre_completo}, {costo_total}, etc.',
        }),
    )

@admin.register(ContratoGenerado)
class ContratoGeneradoAdmin(admin.ModelAdmin):
    list_display = ('venta', 'plantilla', 'fecha_generacion')
    search_fields = ('venta__cliente__nombre_empresa', 'venta__cliente__nombre', 'venta__cliente__apellido', 'venta__id')
    date_hierarchy = 'fecha_generacion'
    # Solo lectura ya que se genera automáticamente
    readonly_fields = ('venta', 'plantilla', 'contenido_final', 'fecha_generacion')
    

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'servicio', 'telefono', 'ejecutivo', 'genera_factura', 'link_externo', 'fecha_actualizacion')
    list_filter = ('servicio', 'genera_factura')
    search_fields = ('nombre', 'telefono', 'ejecutivo')
    ordering = ('nombre',)

    def link_externo(self, obj):
        if obj.link:
            return format_html('<a href="{0}" target="_blank" rel="noopener">Abrir</a>', obj.link)
        return '—'
    link_externo.short_description = "Link"


@admin.register(ConfirmacionVenta)
class ConfirmacionVentaAdmin(admin.ModelAdmin):
    list_display = ('venta', 'nombre_archivo', 'subido_por', 'fecha_subida')
    list_filter = ('fecha_subida', 'subido_por')
    search_fields = ('venta__cliente__nombre', 'venta__cliente__apellido', 'venta__cliente__nombre_empresa', 'nota', 'archivo')
    autocomplete_fields = ('venta', 'subido_por')


@admin.register(LogisticaServicio)
class LogisticaServicioAdmin(admin.ModelAdmin):
    list_display = ('venta', 'nombre_servicio', 'monto_planeado', 'pagado', 'fecha_pagado')
    list_filter = ('pagado', 'codigo_servicio')
    search_fields = ('venta__id', 'venta__cliente__nombre', 'venta__cliente__apellido', 'nombre_servicio')
    raw_id_fields = ('venta',)
    readonly_fields = ('fecha_pagado',)

# --- 4. Registrar AbonoPagoAdmin ---
admin.site.register(AbonoPago, AbonoPagoAdmin)