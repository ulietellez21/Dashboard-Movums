# Generated migration to migrate existing tipo_vendedor values in Ejecutivo
from django.db import migrations

def migrar_tipos_ejecutivo(apps, schema_editor):
    """Migra los tipos de vendedor antiguos a los nuevos valores en Ejecutivo."""
    Ejecutivo = apps.get_model('ventas', 'Ejecutivo')
    
    # Migración de tipos
    # OFICINA -> MOSTRADOR
    Ejecutivo.objects.filter(tipo_vendedor='OFICINA').update(tipo_vendedor='MOSTRADOR')
    
    # CALLE -> CAMPO
    Ejecutivo.objects.filter(tipo_vendedor='CALLE').update(tipo_vendedor='CAMPO')

def revertir_migracion(apps, schema_editor):
    """Revierte la migración si es necesario."""
    Ejecutivo = apps.get_model('ventas', 'Ejecutivo')
    
    # Revertir MOSTRADOR -> OFICINA
    Ejecutivo.objects.filter(tipo_vendedor='MOSTRADOR').update(tipo_vendedor='OFICINA')
    
    # Revertir CAMPO -> CALLE
    Ejecutivo.objects.filter(tipo_vendedor='CAMPO').update(tipo_vendedor='CALLE')

class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0041_alter_ejecutivo_tipo_vendedor'),
    ]

    operations = [
        migrations.RunPython(migrar_tipos_ejecutivo, revertir_migracion),
    ]













