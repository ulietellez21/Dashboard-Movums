# agencia_web/urls.py (CORREGIDO)
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LogoutView, LoginView # <-- Añadimos LoginView
from django.conf import settings
from django.conf.urls.static import static
from ventas.views import DashboardView

urlpatterns = [
    # Rutas de administración
    path('admin/', admin.site.urls),
    
    # 🚨 RUTA DE LOGIN (Usamos la vista integrada de Django)
    # Redirige a la URL configurada en settings.py (LOGIN_REDIRECT_URL = '/')
    path('login/', LoginView.as_view(template_name='registration/login.html'), name='login'),

    # RUTA DE LOGOUT
    # Redirige a la URL con nombre 'login' después de cerrar sesión
    path('logout/', LogoutView.as_view(next_page='/login/'), name='logout'), 
    
    # Dashboard principal
    path('', DashboardView.as_view(), name='dashboard'),
    
    # Rutas de aplicaciones
    path('crm/', include('crm.urls')),
    path('ventas/', include('ventas.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)