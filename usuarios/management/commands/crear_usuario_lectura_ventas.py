"""
Crea el usuario consultor_ventas con perfil solo lectura ventas (dashboard calendario + listado/detalle de ventas).
Uso: python manage.py crear_usuario_lectura_ventas
Si el usuario ya existe, solo se actualiza el flag solo_lectura_ventas.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from usuarios.models import Perfil


class Command(BaseCommand):
    help = "Crea el usuario consultor_ventas con contraseña Movums2026 y perfil solo lectura ventas."

    def handle(self, *args, **options):
        username = "consultor_ventas"
        password = "Movums2026"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": "Consultor",
                "last_name": "Ventas",
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Usuario '{username}' creado."))
        else:
            self.stdout.write(self.style.WARNING(f"Usuario '{username}' ya existía (no se cambió la contraseña)."))

        perfil = user.perfil
        if not perfil.solo_lectura_ventas:
            perfil.solo_lectura_ventas = True
            perfil.save(update_fields=["solo_lectura_ventas"])
            self.stdout.write(self.style.SUCCESS("Perfil actualizado: solo_lectura_ventas = True."))
        else:
            self.stdout.write("Perfil ya tenía solo_lectura_ventas activo.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Credenciales (solo si acabas de crear el usuario):"))
        self.stdout.write(f"  Usuario: {username}")
        self.stdout.write(f"  Contraseña: {password}")
        self.stdout.write("")
        self.stdout.write("El usuario puede entrar al dashboard (solo calendario) y ver ventas en solo lectura.")
        self.stdout.write("Recomendación: cambiar la contraseña tras el primer acceso.")
