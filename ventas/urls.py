from django.urls import path
from .views import (
    ComprobanteAbonoPDFView,
    DashboardView,
    VentaViajeListView,
    VentaViajeDetailView,
    VentaViajeCreateView,
    VentaViajeUpdateView,
    LogisticaPendienteView, 
    ReporteFinancieroView,
    VentaViajeDeleteView, 
    ComisionesVendedoresView,
    ProveedorListCreateView,
    MarcarNotificacionVistaView,
    EliminarNotificacionView,
    EliminarConfirmacionView,
    
    # ----------------------------------------------------
    # IMPORTACIÓN DE LA NUEVA VISTA DE PDF DEL CONTRATO
    # Asumo que la vista para el contrato se llama ContratoVentaPDFView
    ContratoVentaPDFView, 
    # Si la renombraste como ContratoGeneradoDetailView, cámbiala a ese nombre aquí
    # Si la vista es solo para mostrar el HTML del contrato y no generar el PDF, 
    # mantendrías ContratoGeneradoDetailView (asumo que es ContratoVentaPDFView ahora)
    # ----------------------------------------------------
)

# app_name = 'ventas' 

urlpatterns = [
    # 1. Dashboard (General)
    path('dashboard/', DashboardView.as_view(), name='dashboard'), 
    
    # 2. Reportes y Logística
    path('logistica-pendiente/', LogisticaPendienteView.as_view(), name='logistica_pendiente'), 
    path('reporte-financiero/', ReporteFinancieroView.as_view(), name='reporte_financiero'),
    path('comisiones/', ComisionesVendedoresView.as_view(), name='reporte_comisiones'),
    path('proveedores/', ProveedorListCreateView.as_view(), name='proveedores'),
    
    # 2.1 Notificaciones (AJAX)
    path('notificaciones/<int:pk>/marcar-vista/', MarcarNotificacionVistaView.as_view(), name='marcar_notificacion_vista'),
    path('notificaciones/<int:pk>/eliminar/', EliminarNotificacionView.as_view(), name='eliminar_notificacion'),
    
    # 2.2 Confirmaciones de Venta
    path('confirmaciones/<int:pk>/eliminar/', EliminarConfirmacionView.as_view(), name='eliminar_confirmacion'),

    # 3. CRUD de Ventas
    path('crear/', VentaViajeCreateView.as_view(), name='crear_venta'),
    path('<int:pk>/eliminar/', VentaViajeDeleteView.as_view(), name='eliminar_venta'),
    path('<int:pk>/editar/', VentaViajeUpdateView.as_view(), name='editar_venta'),

    
    # ******************************************************************************
    # RUTAS DINÁMICAS (Usando SLUG y PK)
    # ******************************************************************************
    
    # 3.1 RUTA DETALLE: Usa SLUG y PK (la que ya tienes)
    path(
        '<slug:slug>-<int:pk>/', 
        VentaViajeDetailView.as_view(), 
        name='detalle_venta'
    ),

    # 3.2 NUEVA RUTA PDF CONTRATO (Debe usar SLUG y PK)
    # Ejemplo: /ventas/viaje-cliente-123/123/contrato-venta/
    path(
        '<slug:slug>-<int:pk>/contrato-venta/', 
        ContratoVentaPDFView.as_view(), 
        name='generar_contrato_pdf' # Nombre clave para el botón
    ),

    # 3.3 RUTA PDF COMPROBANTE DE ABONOS (Actualizada para usar SLUG y PK)
    # Es más consistente usar SLUG y PK, aunque la vista sólo use PK internamente
    path(
        '<slug:slug>-<int:pk>/comprobante-abonos/', 
        ComprobanteAbonoPDFView.as_view(), 
        name='comprobante_abonos_pdf'
    ),

    # Rutas Base (Debe ir al final para no anular otras rutas)
    path('', VentaViajeListView.as_view(), name='lista_ventas'), 
]