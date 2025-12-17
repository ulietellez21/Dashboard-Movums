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
    DetalleComisionesView,
    ExportarComisionesExcelView,
    ProveedorListCreateView,
    ProveedorUpdateView,
    ProveedorDeleteView,
    MarcarNotificacionVistaView,
    EliminarNotificacionView,
    IncrementarCotizacionClienteView,
    GenerarCotizacionDocxView,
    EliminarConfirmacionView,
    ConfirmarPagoView,
    ConfirmarAbonoView,
    CancelarVentaView,
    ClienteKilometrosResumenView,
    
    # ----------------------------------------------------
    # IMPORTACIÓN DE LA NUEVA VISTA DE PDF DEL CONTRATO
    # Asumo que la vista para el contrato se llama ContratoVentaPDFView
    ContratoVentaPDFView, 
    # Si la renombraste como ContratoGeneradoDetailView, cámbiala a ese nombre aquí
    # Si la vista es solo para mostrar el HTML del contrato y no generar el PDF, 
    # mantendrías ContratoGeneradoDetailView (asumo que es ContratoVentaPDFView ahora)
    # ----------------------------------------------------
    
    # Plantillas de Confirmación
    ListarConfirmacionesView,
    CrearVueloUnicoView,
    CrearVueloRedondoView,
    CrearHospedajeView,
    CrearTrasladoView,
    CrearGenericaView,
    GenerarDocumentoConfirmacionView,
    preview_promociones,
    
    # Gestión de Comprobantes y Pagos por Confirmar
    SubirComprobanteAbonoView,
    SubirComprobanteAperturaView,
    PagosPorConfirmarView,
    ConfirmarPagoDesdeListaView,
)

# app_name = 'ventas' 

urlpatterns = [
    # 1. Dashboard (General)
    path('dashboard/', DashboardView.as_view(), name='dashboard'), 
    
    # 2. Reportes y Logística
    path('logistica-pendiente/', LogisticaPendienteView.as_view(), name='logistica_pendiente'), 
    path('reporte-financiero/', ReporteFinancieroView.as_view(), name='reporte_financiero'),
    path('comisiones/', ComisionesVendedoresView.as_view(), name='reporte_comisiones'),
    path('comisiones/<int:pk>/detalle/', DetalleComisionesView.as_view(), name='detalle_comisiones'),
    path('comisiones/<int:pk>/exportar-excel/', ExportarComisionesExcelView.as_view(), name='exportar_comisiones_excel'),
    path('promociones/preview/', preview_promociones, name='preview_promociones'),
    path('proveedores/', ProveedorListCreateView.as_view(), name='proveedores'),
    path('proveedores/<int:pk>/editar/', ProveedorUpdateView.as_view(), name='editar_proveedor'),
    path('proveedores/<int:pk>/eliminar/', ProveedorDeleteView.as_view(), name='eliminar_proveedor'),
    
    # 2.1 Notificaciones (AJAX)
    path('notificaciones/<int:pk>/marcar-vista/', MarcarNotificacionVistaView.as_view(), name='marcar_notificacion_vista'),
    path('notificaciones/<int:pk>/eliminar/', EliminarNotificacionView.as_view(), name='eliminar_notificacion'),
    path('notificaciones/<int:notificacion_id>/confirmar-pago/', ConfirmarPagoView.as_view(), name='confirmar_pago'),
    path('abonos/<int:abono_id>/confirmar/', ConfirmarAbonoView.as_view(), name='confirmar_abono'),
    
    # 2.2 Gestión de Comprobantes y Pagos por Confirmar
    path('pagos-por-confirmar/', PagosPorConfirmarView.as_view(), name='pagos_por_confirmar'),
    path('abonos/<int:pk>/subir-comprobante/', SubirComprobanteAbonoView.as_view(), name='subir_comprobante_abono'),
    path('ventas/<int:pk>/subir-comprobante-apertura/', SubirComprobanteAperturaView.as_view(), name='subir_comprobante_apertura'),
    path('pagos/<str:tipo>/<int:pk>/confirmar/', ConfirmarPagoDesdeListaView.as_view(), name='confirmar_pago_desde_lista'),
    
    # 2.2 Confirmaciones de Venta
    path('confirmaciones/<int:pk>/eliminar/', EliminarConfirmacionView.as_view(), name='eliminar_confirmacion'),

    # 3. CRUD de Ventas
    path('crear/', VentaViajeCreateView.as_view(), name='crear_venta'),
    path('clientes/<int:cliente_id>/kilometros/', ClienteKilometrosResumenView.as_view(), name='cliente_kilometros_resumen'),
    path('<int:pk>/eliminar/', VentaViajeDeleteView.as_view(), name='eliminar_venta'),
    path('<int:pk>/editar/', VentaViajeUpdateView.as_view(), name='editar_venta'),
    path('<int:pk>/cancelar/', CancelarVentaView.as_view(), name='cancelar_venta'),

    
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
    path(
        'cotizaciones/generar-docx/',
        GenerarCotizacionDocxView.as_view(),
        name='generar_cotizacion_docx'
    ),
    path(
        '<slug:slug>-<int:pk>/cotizaciones/contador/',
        IncrementarCotizacionClienteView.as_view(),
        name='incrementar_cotizaciones_cliente'
    ),
    
    # 3.4 RUTAS PARA PLANTILLAS DE CONFIRMACIÓN
    path(
        '<slug:slug>-<int:pk>/confirmaciones/',
        ListarConfirmacionesView.as_view(),
        name='listar_confirmaciones'
    ),
    path(
        '<slug:slug>-<int:pk>/confirmaciones/vuelo-unico/',
        CrearVueloUnicoView.as_view(),
        name='crear_vuelo_unico'
    ),
    path(
        '<slug:slug>-<int:pk>/confirmaciones/vuelo-redondo/',
        CrearVueloRedondoView.as_view(),
        name='crear_vuelo_redondo'
    ),
    path(
        '<slug:slug>-<int:pk>/confirmaciones/hospedaje/',
        CrearHospedajeView.as_view(),
        name='crear_hospedaje'
    ),
    path(
        '<slug:slug>-<int:pk>/confirmaciones/traslado/',
        CrearTrasladoView.as_view(),
        name='crear_traslado'
    ),
    path(
        '<slug:slug>-<int:pk>/confirmaciones/generica/',
        CrearGenericaView.as_view(),
        name='crear_generica'
    ),
    path(
        '<slug:slug>-<int:pk>/confirmaciones/generar-documento/',
        GenerarDocumentoConfirmacionView.as_view(),
        name='generar_documento_confirmacion'
    ),

    # Rutas Base (Debe ir al final para no anular otras rutas)
    path('', VentaViajeListView.as_view(), name='lista_ventas'), 
]