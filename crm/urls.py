# crm/urls.py

from django.urls import path
# Importar la función eliminar_cliente
from .views import (
    ClienteListView, 
    ClienteDetailView, 
    ClienteCreateView, 
    ClienteUpdateView,
    eliminar_cliente # <--- NUEVA IMPORTACIÓN
)

urlpatterns = [
    # /crm/ -> Lista todos los clientes (ClienteListView)
    path('', ClienteListView.as_view(), name='lista_clientes'),
    
    # /crm/crear/ -> Formulario para nuevo cliente (ClienteCreateView)
    path('crear/', ClienteCreateView.as_view(), name='crear_cliente'),
    
    # /crm/123/editar/ -> Edita un cliente específico (ClienteUpdateView)
    path('<int:pk>/editar/', ClienteUpdateView.as_view(), name='editar_cliente'),
    
    # /crm/123/eliminar/ -> Elimina un cliente específico (función require_POST)
    # Debe ir antes del detalle para evitar conflictos
    path('<int:pk>/eliminar/', eliminar_cliente, name='eliminar_cliente'), # <--- NUEVA RUTA
    
    # /crm/123/ -> Muestra el detalle de un cliente específico (ClienteDetailView)
    path('<int:pk>/', ClienteDetailView.as_view(), name='detalle_cliente'),
]