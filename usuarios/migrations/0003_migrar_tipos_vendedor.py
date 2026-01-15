# Generated migration to migrate existing tipo_vendedor values
from django.db import migrations

def migrar_tipos_vendedor(apps, schema_editor):
    """Migra los tipos de vendedor antiguos a los nuevos valores."""
    Perfil = apps.get_model('usuarios', 'Perfil')
    
    # Migración de tipos
    # OFICINA -> MOSTRADOR
    Perfil.objects.filter(tipo_vendedor='OFICINA').update(tipo_vendedor='MOSTRADOR')
    
    # CAMPO -> CAMPO (se mantiene igual)
    # No se necesita migración para CAMPO ya que el valor se mantiene
    
    # ISLA -> ISLA (se mantiene igual, pero ahora es "Asesor de Isla")
    # No se necesita migración para ISLA ya que el valor se mantiene

def revertir_migracion(apps, schema_editor):
    """Revierte la migración si es necesario."""
    Perfil = apps.get_model('usuarios', 'Perfil')
    
    # Revertir MOSTRADOR -> OFICINA
    Perfil.objects.filter(tipo_vendedor='MOSTRADOR').update(tipo_vendedor='OFICINA')

class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0002_alter_perfil_rol_alter_perfil_tipo_vendedor'),
    ]

    operations = [
        migrations.RunPython(migrar_tipos_vendedor, revertir_migracion),
    ]













