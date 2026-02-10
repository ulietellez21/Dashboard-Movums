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
        ('DIRECTOR_GENERAL', 'Director General'),
        ('DIRECTOR_VENTAS', 'Director de Ventas'),
        ('DIRECTOR_ADMINISTRATIVO', 'Director Administrativo'),
        ('GERENTE', 'Gerente'),
        ('CONTADOR', 'Contador (Solo Pagos/Reportes)'),
        ('VENDEDOR', 'Asesor (Ventas/Clientes)'),  # Mantenemos VENDEDOR internamente, display como "Asesor"
    ]
    rol = models.CharField(max_length=25, choices=ROL_CHOICES, default='VENDEDOR')

    # ------------------- Esquema de Comisiones (Futuro) -------------------
    TIPO_VENDEDOR_CHOICES = [
        ('MOSTRADOR', 'Asesor de Mostrador'),
        ('CAMPO', 'Asesor de Campo'),
        ('ISLA', 'Asesor de Isla'),
    ]
    tipo_vendedor = models.CharField(max_length=10, choices=TIPO_VENDEDOR_CHOICES, default='MOSTRADOR',
                                     help_text="Usado para calcular el esquema de comisiones. Solo aplica para usuarios con rol Asesor.")

    # Oficina asignada (para rol GERENTE: solo ve ventas/clientes/cotizaciones de esta oficina)
    oficina = models.ForeignKey(
        'ventas.Oficina',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='perfiles_gerente',
        verbose_name='Oficina asignada',
        help_text='Solo para rol Gerente: limita la vista a datos de esta oficina.'
    )

    def __str__(self):
        return f'{self.user.username} - {self.get_rol_display()}'

# ------------------- Signals para crear el Perfil automáticamente -------------------
@receiver(post_save, sender=User)
def crear_o_actualizar_perfil_usuario(sender, instance, created, raw=False, **kwargs):
    """Crea o actualiza el Perfil automáticamente cuando se persiste un User."""
    if raw:
        # Evita ejecutar la señal durante loaddata/fixtures
        return

    if created:
        Perfil.objects.create(user=instance)
    else:
        # Si el usuario ya existe, asegura que el perfil refleje los cambios
        instance.perfil.save()