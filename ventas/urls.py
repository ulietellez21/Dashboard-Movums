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
    # Nuevas vistas de comisiones robustas
    ComisionesMensualesView,
    DetalleComisionesMensualesView,
    ExportarComisionesMensualesExcelView,
    ExportarComisionesMensualesTodosExcelView,
    GestionRolesView,
    EjecutivoDetailView,
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
    CotizacionListView,
    CotizacionCreateView,
    CotizacionUpdateView,
    CotizacionDetailView,
    CotizacionDocxView,
    CotizacionPDFView,
    CotizacionConvertirView,
    
    # ----------------------------------------------------
    # IMPORTACIÓN DE LA NUEVA VISTA DE PDF DEL CONTRATO
    ContratoVentaPDFView, 
    
    # Plantillas de Confirmación
    ListarConfirmacionesView,
    CrearVueloUnicoView,
    CrearVueloRedondoView,
    CrearHospedajeView,
    CrearTrasladoView,
    CrearGenericaView,
    EliminarPlantillaConfirmacionView,
    GenerarDocumentoConfirmacionView,
    preview_promociones,
    
    # Gestión de Comprobantes y Pagos por Confirmar
    SubirComprobanteAbonoView,
    SubirComprobanteAperturaView,
    PagosPorConfirmarView,
    ConfirmarPagoDesdeListaView,
    
    # Abonos a Proveedor (Ventas Internacionales)
    SolicitarAbonoProveedorView,
    AprobarAbonoProveedorView,
    ConfirmarAbonoProveedorView,
    CancelarAbonoProveedorView,
    ListaAbonosProveedorView,
)

# app_name = 'ventas' 

urlpatterns = [
    # 1. Dashboard (General)
    path('dashboard/', DashboardView.as_view(), name='dashboard'), 
    
    # 2. Reportes y Logística
    path('logistica-pendiente/', LogisticaPendienteView.as_view(), name='logistica_pendiente'), 
    path('reporte-financiero/', ReporteFinancieroView.as_view(), name='reporte_financiero'),
    # Comisiones (Legacy - mantener por compatibilidad)
    path('comisiones/', ComisionesVendedoresView.as_view(), name='reporte_comisiones'),
    path('comisiones/<int:pk>/detalle/', DetalleComisionesView.as_view(), name='detalle_comisiones'),
    path('comisiones/<int:pk>/exportar-excel/', ExportarComisionesExcelView.as_view(), name='exportar_comisiones_excel'),
    # Comisiones Mensuales (Sistema Robusto - MOSTRADOR)
    path('comisiones-mensuales/', ComisionesMensualesView.as_view(), name='comisiones_mensuales'),
    path('comisiones-mensuales/<int:pk>/detalle/', DetalleComisionesMensualesView.as_view(), name='detalle_comisiones_mensuales'),
    path('comisiones-mensuales/<int:pk>/exportar-excel/', ExportarComisionesMensualesExcelView.as_view(), name='exportar_comisiones_mensuales_excel'),
    path('comisiones-mensuales/exportar-todos-excel/', ExportarComisionesMensualesTodosExcelView.as_view(), name='exportar_comisiones_mensuales_todos_excel'),
    path('gestion-roles/', GestionRolesView.as_view(), name='gestion_roles'),
    path('gestion-roles/ejecutivo/<int:pk>/', EjecutivoDetailView.as_view(), name='ejecutivo_detail'),
    
    # Cotizaciones
    path('cotizaciones/', CotizacionListView.as_view(), name='cotizaciones_lista'),
    path('cotizaciones/nueva/', CotizacionCreateView.as_view(), name='cotizacion_crear'),
    path('cotizaciones/<slug:slug>/', CotizacionDetailView.as_view(), name='cotizacion_detalle'),
    path('cotizaciones/<slug:slug>/editar/', CotizacionUpdateView.as_view(), name='cotizacion_editar'),
    path('cotizaciones/<slug:slug>/docx/', CotizacionDocxView.as_view(), name='cotizacion_docx'),  # Deprecated, mantener por compatibilidad
    path('cotizaciones/<slug:slug>/pdf/', CotizacionPDFView.as_view(), name='cotizacion_pdf'),
    path('cotizaciones/<slug:slug>/convertir/', CotizacionConvertirView.as_view(), name='cotizacion_convertir'),
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
    
    # 2.3 Abonos a Proveedor (Ventas Internacionales)
    path('abonos-proveedor/', ListaAbonosProveedorView.as_view(), name='lista_abonos_proveedor'),
    path('ventas/<int:pk>/abonos-proveedor/solicitar/', SolicitarAbonoProveedorView.as_view(), name='solicitar_abono_proveedor'),
    path('abonos-proveedor/<int:abono_id>/aprobar/', AprobarAbonoProveedorView.as_view(), name='aprobar_abono_proveedor'),
    path('abonos-proveedor/<int:abono_id>/confirmar/', ConfirmarAbonoProveedorView.as_view(), name='confirmar_abono_proveedor'),
    path('abonos-proveedor/<int:abono_id>/cancelar/', CancelarAbonoProveedorView.as_view(), name='cancelar_abono_proveedor'),

    # 3. CRUD de Ventas
    path('crear/', VentaViajeCreateView.as_view(), name='crear_venta'),
    path('clientes/<int:cliente_id>/kilometros/', ClienteKilometrosResumenView.as_view(), name='cliente_kilometros_resumen'),
    # path('<int:pk>/eliminar/', VentaViajeDeleteView.as_view(), name='eliminar_venta'),  # Eliminado: ventas no se eliminan manualmente
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
        '<slug:slug>-<int:pk>/confirmaciones/<int:plantilla_pk>/eliminar/',
        EliminarPlantillaConfirmacionView.as_view(),
        name='eliminar_plantilla_confirmacion'
    ),
    path(
        '<slug:slug>-<int:pk>/confirmaciones/generar-documento/',
        GenerarDocumentoConfirmacionView.as_view(),
        name='generar_documento_confirmacion'
    ),

    # Rutas Base (Debe ir al final para no anular otras rutas)
    path('', VentaViajeListView.as_view(), name='lista_ventas'), 
]