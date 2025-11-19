# usuarios/admin.py
from django.contrib import admin
from .models import Perfil

@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('user', 'rol', 'tipo_vendedor')
    list_filter = ('rol', 'tipo_vendedor')
    search_fields = ('user__username', 'rol')