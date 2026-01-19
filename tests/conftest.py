"""
Configuración global de pytest para el proyecto Django.
Define fixtures compartidas para todos los tests.
"""
import pytest
from django.contrib.auth.models import User
from crm.models import Cliente
from decimal import Decimal


@pytest.fixture
def admin_user(db):
    """Crea un usuario administrador para tests."""
    return User.objects.create_user(
        username='admin_test',
        email='admin@test.com',
        password='testpass123',
        is_staff=True,
        is_superuser=True,
        first_name='Admin',
        last_name='Test'
    )


@pytest.fixture
def normal_user(db):
    """Crea un usuario normal para tests."""
    return User.objects.create_user(
        username='user_test',
        email='user@test.com',
        password='testpass123',
        first_name='Usuario',
        last_name='Test'
    )


@pytest.fixture
def cliente_particular(db):
    """Crea un cliente particular para tests."""
    return Cliente.objects.create(
        tipo_cliente='PARTICULAR',
        nombre='Juan',
        apellido='Pérez',
        email='juan.perez@test.com',
        telefono='5551234567',
        genero='M'
    )


@pytest.fixture
def cliente_empresa(db):
    """Crea un cliente empresa para tests."""
    return Cliente.objects.create(
        tipo_cliente='EMPRESA',
        nombre_empresa='Empresa Test S.A. de C.V.',
        email='contacto@empresa-test.com',
        telefono='5559876543',
        rfc='ETS123456789'
    )
