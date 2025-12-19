# Generated migration to migrate ubicacion_asignada to oficina
from django.db import migrations

def migrar_ubicacion_a_oficina(apps, schema_editor):
    """Migra los valores de ubicacion_asignada a oficina antes de eliminar el campo."""
    Ejecutivo = apps.get_model('ventas', 'Ejecutivo')
    
    # Copiar ubicacion_asignada a oficina para todos los ejecutivos existentes
    for ejecutivo in Ejecutivo.objects.all():
        if hasattr(ejecutivo, 'ubicacion_asignada') and ejecutivo.ubicacion_asignada:
            ejecutivo.oficina = ejecutivo.ubicacion_asignada
            ejecutivo.save(update_fields=['oficina'])

def revertir_migracion(apps, schema_editor):
    """Revierte la migración si es necesario."""
    Ejecutivo = apps.get_model('ventas', 'Ejecutivo')
    
    # No podemos revertir completamente porque ubicacion_asignada ya no existirá
    # Esta función está aquí solo para completitud
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0043_agregar_campos_ejecutivo'),
    ]

    operations = [
        migrations.RunPython(migrar_ubicacion_a_oficina, revertir_migracion),
        migrations.RemoveField(
            model_name='ejecutivo',
            name='ubicacion_asignada',
        ),
    ]

