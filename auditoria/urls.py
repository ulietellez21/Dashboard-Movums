from django.urls import path
from .views import HistorialMovimientosView, HistorialMovimientosAjaxView

app_name = 'auditoria'

urlpatterns = [
    path('historial/', HistorialMovimientosView.as_view(), name='historial_movimientos'),
    path('historial/ajax/', HistorialMovimientosAjaxView.as_view(), name='historial_movimientos_ajax'),
]










