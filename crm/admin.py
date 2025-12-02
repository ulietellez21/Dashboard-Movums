# crm/admin.py
from django.contrib import admin
from .models import Cliente, HistorialKilometros

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'email', 'kilometros_disponibles', 'fecha_registro')
    search_fields = ('nombre', 'telefono', 'email', 'documento_identificacion')
    list_filter = ('fecha_registro', 'participa_kilometros')


@admin.register(HistorialKilometros)
class HistorialKilometrosAdmin(admin.ModelAdmin):
    list_display = ('cliente', 'tipo_evento', 'kilometros', 'fecha_registro', 'venta')
    list_filter = ('tipo_evento', 'fecha_registro')
    search_fields = ('cliente__nombre', 'cliente__apellido', 'descripcion')