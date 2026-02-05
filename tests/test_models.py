"""
Tests básicos para los modelos principales del proyecto.
Smoke tests para verificar que los modelos funcionan correctamente.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from crm.models import Cliente
from ventas.models import VentaViaje
from decimal import Decimal
from datetime import date, timedelta


@pytest.mark.django_db
class TestClienteModel:
    """Tests para el modelo Cliente."""
    
    def test_crear_cliente_particular(self, db):
        """Test: Verificar que se puede crear un cliente particular correctamente."""
        cliente = Cliente.objects.create(
            tipo_cliente='PARTICULAR',
            nombre='María',
            apellido='González',
            email='maria.gonzalez@test.com',
            telefono='5551112233',
            genero='F'
        )
        
        assert cliente.pk is not None
        assert cliente.tipo_cliente == 'PARTICULAR'
        assert cliente.nombre == 'María'
        assert cliente.apellido == 'González'
        assert cliente.email == 'maria.gonzalez@test.com'
    
    def test_crear_cliente_empresa(self, db):
        """Test: Verificar que se puede crear un cliente empresa correctamente."""
        cliente = Cliente.objects.create(
            tipo_cliente='EMPRESA',
            nombre_empresa='Corporativo Test S.A. de C.V.',
            email='info@corporativo-test.com',
            telefono='5552223344',
            rfc='CTS987654321'
        )
        
        assert cliente.pk is not None
        assert cliente.tipo_cliente == 'EMPRESA'
        assert cliente.nombre_empresa == 'Corporativo Test S.A. de C.V.'
        assert cliente.rfc == 'CTS987654321'
    
    def test_cliente_str_particular(self, cliente_particular):
        """Test: Verificar que __str__ de Cliente (particular) devuelve el texto esperado."""
        expected_str = cliente_particular.nombre_completo_display
        assert str(cliente_particular) == expected_str
        assert str(cliente_particular) == 'Juan Pérez'
    
    def test_cliente_str_empresa(self, cliente_empresa):
        """Test: Verificar que __str__ de Cliente (empresa) devuelve el texto esperado."""
        expected_str = cliente_empresa.nombre_completo_display
        assert str(cliente_empresa) == expected_str
        assert str(cliente_empresa) == 'Empresa Test S.A. de C.V.'
    
    def test_cliente_nombre_completo_display_particular(self, cliente_particular):
        """Test: Verificar la propiedad nombre_completo_display para particular."""
        assert cliente_particular.nombre_completo_display == 'Juan Pérez'
    
    def test_cliente_nombre_completo_display_empresa(self, cliente_empresa):
        """Test: Verificar la propiedad nombre_completo_display para empresa."""
        assert cliente_empresa.nombre_completo_display == 'Empresa Test S.A. de C.V.'


@pytest.mark.django_db
class TestVentaViajeModel:
    """Tests para el modelo VentaViaje."""
    
    def test_crear_venta_viaje(self, cliente_particular, normal_user, db):
        """Test: Verificar que se puede crear una VentaViaje correctamente."""
        fecha_inicio = date.today() + timedelta(days=30)
        fecha_fin = fecha_inicio + timedelta(days=7)
        
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=fecha_inicio,
            fecha_fin_viaje=fecha_fin,
            costo_venta_final=Decimal('10000.00'),
            cantidad_apertura=Decimal('3000.00'),
            costo_neto=Decimal('8000.00')
        )
        
        assert venta.pk is not None
        assert venta.cliente == cliente_particular
        assert venta.vendedor == normal_user
        assert venta.tipo_viaje == 'NAC'
        assert venta.costo_venta_final == Decimal('10000.00')
    
    def test_venta_viaje_str(self, cliente_particular, normal_user, db):
        """Test: Verificar que __str__ de VentaViaje devuelve el texto esperado."""
        fecha_inicio = date.today() + timedelta(days=30)
        
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=fecha_inicio,
            costo_venta_final=Decimal('10000.00'),
            cantidad_apertura=Decimal('3000.00'),
            costo_neto=Decimal('8000.00')
        )
        
        # El __str__ usa: f"Venta {self.pk} - Cliente {self.cliente} ({self.slug})"
        str_representation = str(venta)
        assert 'Venta' in str_representation
        assert str(venta.pk) in str_representation
        assert str(cliente_particular) in str_representation

    def test_venta_tiene_puede_solicitar_abonos_proveedor(self, cliente_particular, normal_user, db):
        """VentaViaje debe tener la propiedad puede_solicitar_abonos_proveedor (evita AttributeError en vistas)."""
        fecha_inicio = date.today() + timedelta(days=30)
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=fecha_inicio,
            costo_venta_final=Decimal('10000.00'),
            cantidad_apertura=Decimal('3000.00'),
            costo_neto=Decimal('8000.00'),
        )
        assert hasattr(venta, "puede_solicitar_abonos_proveedor"), (
            "VentaViaje debe tener propiedad puede_solicitar_abonos_proveedor; "
            "incluir ventas/models.py en el mismo commit que ventas/views.py al desplegar."
        )
        result = venta.puede_solicitar_abonos_proveedor
        assert isinstance(result, bool)
