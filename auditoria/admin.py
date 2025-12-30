from django.contrib import admin
from .models import HistorialMovimiento


@admin.register(HistorialMovimiento)
class HistorialMovimientoAdmin(admin.ModelAdmin):
    list_display = ('fecha_hora', 'tipo_evento', 'usuario', 'nivel', 'descripcion_corta')
    list_filter = ('tipo_evento', 'nivel', 'fecha_hora')
    search_fields = ('descripcion', 'usuario__username')
    readonly_fields = ('fecha_hora', 'content_type', 'object_id', 'objeto_relacionado')
    date_hierarchy = 'fecha_hora'
    ordering = ('-fecha_hora',)
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('fecha_hora', 'tipo_evento', 'nivel', 'usuario')
        }),
        ('Descripción', {
            'fields': ('descripcion',)
        }),
        ('Objeto Relacionado', {
            'fields': ('content_type', 'object_id', 'objeto_relacionado'),
            'classes': ('collapse',)
        }),
        ('Información Adicional', {
            'fields': ('datos_adicionales', 'ip_address'),
            'classes': ('collapse',)
        }),
    )

