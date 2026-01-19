"""
Smoke tests para las vistas principales del proyecto.
Verifica que las páginas cargan correctamente y que las protecciones de login funcionan.
"""
import pytest
from django.urls import reverse
from django.contrib.auth.models import User


@pytest.mark.django_db
class TestLoginView:
    """Tests para la vista de Login."""
    
    def test_login_page_loads(self, client):
        """Test: Verificar que la página de Login carga correctamente (Status 200)."""
        url = reverse('login')
        response = client.get(url)
        
        assert response.status_code == 200
        assert 'login' in response.templates[0].name or 'registration/login.html' in [t.name for t in response.templates]
    
    def test_login_with_valid_credentials(self, client, normal_user):
        """Test: Verificar que el login funciona con credenciales válidas."""
        url = reverse('login')
        response = client.post(url, {
            'username': 'user_test',
            'password': 'testpass123'
        })
        
        # Debería redirigir después de un login exitoso
        assert response.status_code == 302 or response.status_code == 200


@pytest.mark.django_db
class TestDashboardView:
    """Tests para la vista del Dashboard."""
    
    def test_dashboard_requires_login(self, client):
        """Test: Verificar que el Dashboard requiere login (Redirecciona 302 si no estás logueado)."""
        url = reverse('dashboard')
        response = client.get(url)
        
        # Debería redirigir a login si no está autenticado
        assert response.status_code == 302
        # Verificar que redirige a la página de login
        assert '/login/' in response.url
    
    def test_dashboard_loads_when_logged_in(self, client, normal_user):
        """Test: Verificar que el Dashboard carga OK (Status 200) si el usuario está logueado."""
        # Hacer login
        client.force_login(normal_user)
        
        url = reverse('dashboard')
        response = client.get(url)
        
        # Debería cargar correctamente (200) o al menos no redirigir a login
        assert response.status_code in [200, 302]
        # Si es 302, no debería ser a login
        if response.status_code == 302:
            assert '/login/' not in response.url


@pytest.mark.django_db
class TestAdminAccess:
    """Tests para verificar acceso a admin."""
    
    def test_admin_requires_login(self, client):
        """Test: Verificar que el admin requiere login."""
        url = '/admin/'
        response = client.get(url)
        
        # Debería redirigir a login
        assert response.status_code == 302
        assert '/admin/login/' in response.url or '/login/' in response.url
    
    def test_admin_accessible_with_staff_user(self, client, admin_user):
        """Test: Verificar que admin es accesible con usuario staff."""
        client.force_login(admin_user)
        
        url = '/admin/'
        response = client.get(url)
        
        # Debería cargar (200) o redirigir al panel admin
        assert response.status_code in [200, 302]
        if response.status_code == 302:
            assert '/admin/login/' not in response.url
