# crm/admin.py
from django.contrib import admin
from .models import Cliente

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'email', 'fecha_registro')
    search_fields = ('nombre', 'telefono', 'email', 'documento_identificacion')
    list_filter = ('fecha_registro',)