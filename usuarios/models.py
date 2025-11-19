# usuarios/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Perfil(models.Model):
    """Extiende el modelo User de Django para añadir roles y tipo de vendedor."""
    
    # Relación 1:1 con el usuario base de Django
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # ------------------- Roles de Acceso -------------------
    ROL_CHOICES = [
        ('JEFE', 'Jefe (Acceso Total)'),
        ('CONTADOR', 'Contador (Solo Pagos/Reportes)'),
        ('VENDEDOR', 'Vendedor (Ventas/Clientes)'),
    ]
    rol = models.CharField(max_length=10, choices=ROL_CHOICES, default='VENDEDOR')

    # ------------------- Esquema de Comisiones (Futuro) -------------------
    TIPO_VENDEDOR_CHOICES = [
        ('OFICINA', 'Oficina'),
        ('ISLA', 'Isla de Venta'),
        ('CAMPO', 'Campo / Externo'),
    ]
    tipo_vendedor = models.CharField(max_length=10, choices=TIPO_VENDEDOR_CHOICES, default='OFICINA',
                                     help_text="Usado para calcular el esquema de comisiones.")

    def __str__(self):
        return f'{self.user.username} - {self.get_rol_display()}'

# ------------------- Signals para crear el Perfil automáticamente -------------------
@receiver(post_save, sender=User)
def crear_o_actualizar_perfil_usuario(sender, instance, created, **kwargs):
    """Crea el Perfil automáticamente cuando se crea un nuevo User."""
    if created:
        Perfil.objects.create(user=instance)
    # Si el usuario ya existe, asegura que el perfil se guarde
    instance.perfil.save()