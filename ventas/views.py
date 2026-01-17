from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, View, DeleteView, TemplateView
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User 
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.db.models.functions import Coalesce
from django.db.models import Sum, Count, F, Q, Value, IntegerField, ExpressionWrapper
from django.db.models import DecimalField as ModelDecimalField
from django.db import transaction
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.conf import settings
from django.utils import timezone 
from django.utils import formats  # Para formatear fechas en el PDF
# IMPORTACIÓN CLAVE: Necesaria para generar slugs automáticamente
from django.utils.text import slugify 
from datetime import timedelta 
from collections import Counter
import math, re, logging, secrets, json, io, os
import datetime # Necesario para el contexto del PDF (campo now)
from decimal import Decimal, InvalidOperation # Importar Decimal para asegurar precisión en cálculos financieros

logger = logging.getLogger(__name__)

# Intento cargar WeasyPrint; si falla (por dependencias GTK), defino placeholders.
try:
    from weasyprint import HTML, CSS 
    WEASYPRINT_AVAILABLE = True
except ImportError:
    logger.warning("WeasyPrint no está disponible. La generación de PDF fallará.")
    class HTML:
        def __init__(self, string, base_url=None): pass
        def write_pdf(self): return b''
    class CSS: pass
    WEASYPRINT_AVAILABLE = False


from .models import (
    VentaViaje,
    AbonoPago,
    Logistica,
    LogisticaServicio,
    ContratoGenerado,
    Notificacion,
    Proveedor,
    ConfirmacionVenta,
    Ejecutivo,
    Oficina,
    PlantillaConfirmacion,
    Cotizacion,
    VentaPromocionAplicada,
)
from crm.models import Cliente
from crm.services import KilometrosService
from usuarios.models import Perfil
from .forms import (
    VentaViajeForm,
    LogisticaForm,
    LogisticaServicioFormSet,
    AbonoPagoForm,
    ProveedorForm,
    ConfirmacionVentaForm,
    EjecutivoForm,
    OficinaForm,
    CotizacionForm,
)
from .utils import numero_a_texto
from .services.logistica import (
    build_financial_summary,
    build_service_rows,
    build_logistica_card,
)

# Función auxiliar para obtener el rol, reutilizada en la nueva lógica
def get_user_role(user):
    """Asume el Perfil y devuelve el rol, o 'INVITADO' si no hay perfil."""
    try:
        return user.perfil.rol
    except AttributeError:
        return 'INVITADO'

class ContratoGeneradoDetailView(LoginRequiredMixin, DetailView):
    """
    Muestra los detalles de un contrato generado. 
    Se asume que el modelo 'VentaViaje' representa este contrato.
    """
    # Usamos VentaViaje como modelo por defecto. Ajustar si tienes un modelo ContratoGenerado dedicado.
    model = VentaViaje 
    template_name = 'ventas/contrato_generado_detalle.html' 
    context_object_name = 'contrato'

    def get_queryset(self):
        """Filtra para que solo el usuario autenticado pueda ver sus propias ventas/contratos."""
        # Se asume que el modelo VentaViaje tiene un campo 'vendedor' relacionado al usuario.
        return self.model.objects.filter(vendedor=self.request.user)

# ------------------- 1. DASHBOARD GERENCIAL -------------------

class DashboardView(LoginRequiredMixin, ListView):
    model = VentaViaje
    template_name = 'dashboard.html'
    context_object_name = 'ventas'

    def get_user_role(self, user):
        """Asume el Perfil y devuelve el rol, o 'INVITADO' si no hay perfil."""
        try:
            role = user.perfil.rol
            return role
        except AttributeError:
            logger.warning(f"Usuario {user.username} NO tiene perfil o rol definido. Rol: INVITADO")
            return 'INVITADO'


    def get_queryset(self):
        user = self.request.user
        user_rol = self.get_user_role(user)

        # Lógica de filtrado
        if user_rol in ['JEFE', 'CONTADOR']:
            queryset = VentaViaje.objects.all()
        elif user_rol == 'VENDEDOR':
            queryset = VentaViaje.objects.filter(vendedor=user)
        else:
            queryset = VentaViaje.objects.none()

        # Aplicar filtro por fecha de viaje (soporta fecha única o rango)
        fecha_filtro = self.request.GET.get('fecha_filtro')
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        # Prioridad: rango de fechas > fecha única
        if fecha_desde and fecha_hasta:
            try:
                from datetime import datetime
                fecha_desde_obj = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
                fecha_hasta_obj = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
                # Asegurar que desde <= hasta
                if fecha_desde_obj <= fecha_hasta_obj:
                    queryset = queryset.filter(fecha_inicio_viaje__range=[fecha_desde_obj, fecha_hasta_obj])
            except ValueError:
                pass
        elif fecha_filtro:
            try:
                from datetime import datetime
                fecha_obj = datetime.strptime(fecha_filtro, '%Y-%m-%d').date()
                queryset = queryset.filter(fecha_inicio_viaje=fecha_obj)
            except ValueError:
                pass

        return queryset.select_related('cliente', 'vendedor', 'proveedor').order_by('-fecha_inicio_viaje', '-fecha_creacion')

    def get_context_data(self, **kwargs):
        # Asegurar que object_list esté definido antes de llamar a super()
        if not hasattr(self, 'object_list'):
            self.object_list = self.get_queryset()
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        user_rol = self.get_user_role(user)
        context['user_rol'] = user_rol
        
        # Inicializar notificaciones vacías por defecto (para evitar errores en template)
        context['notificaciones'] = Notificacion.objects.none()
        context['notificaciones_count'] = 0

        # --- Lógica de KPIs (se mantiene para jefes/contadores) ---
        if user_rol in ['JEFE', 'CONTADOR']:
            # KPI 1: Saldo Pendiente Global
            total_vendido_agg = VentaViaje.objects.aggregate(Sum('costo_venta_final'))['costo_venta_final__sum']
            total_vendido = total_vendido_agg if total_vendido_agg is not None else Decimal('0.00')
            
            # Total pagado incluye abonos + montos de apertura
            total_abonos_agg = AbonoPago.objects.aggregate(Sum('monto'))['monto__sum']
            total_abonos = total_abonos_agg if total_abonos_agg is not None else Decimal('0.00')
            
            total_apertura_agg = VentaViaje.objects.aggregate(Sum('cantidad_apertura'))['cantidad_apertura__sum']
            total_apertura = total_apertura_agg if total_apertura_agg is not None else Decimal('0.00')
            
            total_pagado = total_abonos + total_apertura
            
            context['saldo_total_pendiente'] = total_vendido - total_pagado

            # KPI 2: Servicios Pendientes (Logística)
            # Filtrar solo ventas que tienen logística asociada
            context['alertas_logistica_count'] = VentaViaje.objects.filter(
                logistica__isnull=False
            ).filter(
                Q(logistica__vuelo_confirmado=False) |
                Q(logistica__hospedaje_reservado=False) |
                Q(logistica__traslado_confirmado=False) |
                Q(logistica__tickets_confirmado=False)
            ).count()
            
            # INNOVACIÓN 2: Ranking de Vendedores
            context['ranking_ventas'] = VentaViaje.objects.filter(
                vendedor__isnull=False,
            ).values('vendedor__username').annotate(
                num_ventas=Count('id'),
                total_vendido=Sum('costo_venta_final')
            ).order_by('-num_ventas', '-total_vendido')[:5]
            
            # INNOVACIÓN 3: Notificaciones (para JEFE) - Mostrar solo notificaciones no vistas
            if user_rol == 'JEFE':
                context['notificaciones'] = Notificacion.objects.filter(
                    usuario=user,
                    vista=False  # Solo mostrar notificaciones no vistas
                ).select_related('venta', 'venta__cliente', 'abono').order_by('-fecha_creacion')[:30]  # Últimas 30 no vistas
                context['notificaciones_count'] = Notificacion.objects.filter(
                    usuario=user,
                    vista=False
                ).count()  # Contador solo de no vistas
            # --- Lógica para CONTADOR (dentro del bloque JEFE/CONTADOR) ---
            elif user_rol == 'CONTADOR':
                # Notificaciones para CONTADOR: mostrar solo las no vistas
                # IMPORTANTE: Filtrar por vista=False para que desaparezcan al marcarlas
                notificaciones_contador = Notificacion.objects.filter(
                    usuario=user,
                    vista=False  # Solo mostrar notificaciones no vistas
                ).select_related('venta', 'venta__cliente', 'abono').prefetch_related('abono__confirmado_por').order_by('-fecha_creacion')
                
                # Convertir a lista para asegurar que se evalúe el QuerySet
                notificaciones_list = list(notificaciones_contador[:20])
                context['notificaciones'] = notificaciones_list
                context['notificaciones_count'] = len(notificaciones_list)
                
                # Para las secciones adicionales: obtener solo las pendientes
                notificaciones_pendientes_pagos = notificaciones_contador.filter(
                    tipo='PAGO_PENDIENTE',
                    confirmado=False
                )
                
                # Ventas con pagos pendientes de confirmación para el CONTADOR
                # Obtener todas las notificaciones pendientes y sus ventas relacionadas
                ventas_pendientes_ids = notificaciones_pendientes_pagos.values_list('venta_id', flat=True).distinct()
                if ventas_pendientes_ids:
                    context['ventas_pendientes'] = VentaViaje.objects.filter(
                        pk__in=ventas_pendientes_ids
                    ).select_related('cliente', 'vendedor').prefetch_related('abonos').order_by('-fecha_creacion')[:10]
                else:
                    context['ventas_pendientes'] = VentaViaje.objects.none()
                
                # Abonos pendientes de confirmación (para mostrar en el dashboard)
                context['abonos_pendientes'] = AbonoPago.objects.filter(
                    Q(forma_pago__in=['TRN', 'TAR', 'DEP']) & Q(confirmado=False)
                ).select_related('venta', 'venta__cliente', 'registrado_por').order_by('-fecha_pago')[:10]
                
                # Notificaciones de apertura pendiente (pagos de apertura sin abono asociado)
                context['notificaciones_apertura_pendiente'] = notificaciones_pendientes_pagos.filter(
                    abono__isnull=True  # Notificaciones sin abono son de apertura
                ).select_related('venta', 'venta__cliente').order_by('-fecha_creacion')[:10]
                
                # Contador de ventas con estado "En confirmación"
                context['ventas_en_confirmacion_count'] = VentaViaje.objects.filter(
                    estado_confirmacion='EN_CONFIRMACION'
                ).count()
            
        # --- Lógica de KPIs (se mantiene para vendedores) ---
        elif user_rol == 'VENDEDOR':
            # Notificaciones para VENDEDOR: solo las notificaciones creadas específicamente para este vendedor
            # IMPORTANTE: Simplificar la consulta - si la notificación está asignada al usuario, no hace falta filtrar por ventas
            # Filtrar por vista=False para que desaparezcan al marcarlas
            notificaciones_vendedor = Notificacion.objects.filter(
                usuario=user,  # Solo notificaciones creadas para este vendedor específico
                vista=False  # Solo mostrar notificaciones no vistas
            ).select_related('venta', 'venta__cliente', 'abono').order_by('-fecha_creacion')
            
            # Mostrar las últimas 30 no vistas
            context['notificaciones'] = notificaciones_vendedor[:30]
            context['notificaciones_count'] = notificaciones_vendedor.count()  # Contador solo de no vistas
            mis_ventas = VentaViaje.objects.filter(vendedor=user)
            
            # KPI 1: Mi Saldo Pendiente
            mi_total_vendido_agg = mis_ventas.aggregate(Sum('costo_venta_final'))['costo_venta_final__sum']
            mi_total_vendido = mi_total_vendido_agg if mi_total_vendido_agg is not None else Decimal('0.00')
            
            # Total pagado incluye abonos + montos de apertura
            mi_total_abonos_agg = AbonoPago.objects.filter(venta__vendedor=user).aggregate(Sum('monto'))['monto__sum']
            mi_total_abonos = mi_total_abonos_agg if mi_total_abonos_agg is not None else Decimal('0.00')
            
            mi_total_apertura_agg = mis_ventas.aggregate(Sum('cantidad_apertura'))['cantidad_apertura__sum']
            mi_total_apertura = mi_total_apertura_agg if mi_total_apertura_agg is not None else Decimal('0.00')
            
            mi_total_pagado = mi_total_abonos + mi_total_apertura
            
            context['mi_saldo_pendiente'] = mi_total_vendido - mi_total_pagado

            # KPI 2: Mis Ventas Cerradas (ventas donde el total pagado >= costo_venta_final)
            # El total pagado ahora incluye cantidad_apertura + abonos (calculado en la propiedad total_pagado)
            # Usamos una lista para evaluar la propiedad total_pagado de cada venta
            ventas_cerradas = 0
            for venta in mis_ventas:
                if venta.total_pagado >= venta.costo_venta_final:
                    ventas_cerradas += 1
            context['mis_ventas_cerradas'] = ventas_cerradas 

        # Agregar filtros de fecha al contexto
        context['fecha_filtro'] = self.request.GET.get('fecha_filtro', '')
        context['fecha_desde'] = self.request.GET.get('fecha_desde', '')
        context['fecha_hasta'] = self.request.GET.get('fecha_hasta', '')
        
        # Variables del template que pueden no estar definidas
        context.setdefault('total_ingresos_mtd', Decimal('0.00'))
        context.setdefault('total_ventas', 0)
        context.setdefault('nuevos_clientes_mtd', 0)
        context.setdefault('envios_pendientes', context.get('alertas_logistica_count', 0))
        
        # Preparar lista de ventas individuales para las cards (solo si hay filtro)
        if context['fecha_filtro'] or (context['fecha_desde'] and context['fecha_hasta']):
            context['ventas_filtradas'] = list(context['ventas'])[:50]  # Limitar a 50 para rendimiento
        else:
            context['ventas_filtradas'] = []

        return context

# ------------------- 2. LISTADO DE VENTAS - SOLUCIÓN AL ERROR DE ANOTACIÓN -------------------

class VentaViajeListView(LoginRequiredMixin, ListView):
    model = VentaViaje 
    template_name = 'ventas/venta_list.html'

    def get_queryset(self):
        user = self.request.user
        user_rol = get_user_role(user) 

        # 1. QuerySet Base (filtrado por permisos)
        if user_rol in ['JEFE', 'CONTADOR']:
            base_query = self.model.objects.all()
        elif user_rol == 'VENDEDOR':
            base_query = self.model.objects.filter(vendedor=user)
        else:
            base_query = self.model.objects.none()

        # 2. Aplicar filtro por folio/ID
        busqueda_folio = self.request.GET.get('busqueda_folio', '').strip()
        if busqueda_folio:
            # Buscar por folio o por ID numérico
            if busqueda_folio.isdigit():
                base_query = base_query.filter(Q(folio__icontains=busqueda_folio) | Q(pk=int(busqueda_folio)))
            else:
                base_query = base_query.filter(folio__icontains=busqueda_folio)
        
        # 3. Aplicar filtro por servicio
        busqueda_servicio = self.request.GET.get('busqueda_servicio', '').strip()
        if busqueda_servicio:
            if busqueda_servicio == 'VAR':
                # Buscar ventas con múltiples servicios (folio empieza con VAR)
                base_query = base_query.filter(folio__startswith='VAR-')
            else:
                # Buscar ventas que contengan este servicio
                base_query = base_query.filter(
                    Q(servicios_seleccionados__icontains=busqueda_servicio) | 
                    Q(folio__startswith=f'{busqueda_servicio}-')
                )
        
        # 4. Aplicar filtro por fecha de viaje si se proporciona (soporta fecha única o rango)
        fecha_filtro = self.request.GET.get('fecha_filtro')
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        # Prioridad: rango de fechas > fecha única
        if fecha_desde and fecha_hasta:
            try:
                from datetime import datetime
                fecha_desde_obj = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
                fecha_hasta_obj = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
                # Asegurar que desde <= hasta
                if fecha_desde_obj <= fecha_hasta_obj:
                    base_query = base_query.filter(fecha_inicio_viaje__range=[fecha_desde_obj, fecha_hasta_obj])
            except ValueError:
                pass
        elif fecha_filtro:
            try:
                from datetime import datetime
                fecha_obj = datetime.strptime(fecha_filtro, '%Y-%m-%d').date()
                base_query = base_query.filter(fecha_inicio_viaje=fecha_obj)
            except ValueError:
                pass

        # 3. Optimizar el queryset con select_related y prefetch_related para acceder a las propiedades del modelo
        queryset = base_query.select_related('cliente', 'vendedor').prefetch_related('abonos').order_by('-fecha_inicio_viaje', '-fecha_creacion')
        
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ventas_list = list(context['object_list'])  # Convertir a lista para usar propiedades del modelo

        # Separar ventas activas y cerradas
        # Las ventas canceladas van directamente a cerradas
        # Las ventas no canceladas se separan según si están pagadas o no
        ventas_activas = []
        ventas_cerradas = []
        
        for venta in ventas_list:
            # Si la venta está cancelada, va directamente a cerradas
            if venta.estado == 'CANCELADA':
                ventas_cerradas.append(venta)
            # Si no está cancelada, usar la propiedad esta_pagada para separarla
            elif venta.esta_pagada:
                # Venta completada/pagada (no cancelada)
                ventas_cerradas.append(venta)
            else:
                # Venta activa (no cancelada y no pagada completamente)
                ventas_activas.append(venta)
        
        # Convertir de vuelta a queryset o mantener como lista
        # Para mantener compatibilidad con el template, los pasamos como listas
        ventas_activas_qs = ventas_activas
        ventas_cerradas_qs = ventas_cerradas
        
        context['ventas_activas'] = ventas_activas_qs
        context['ventas_cerradas'] = ventas_cerradas_qs
        context['user_rol'] = get_user_role(self.request.user)
        context['ventas_para_cotizacion'] = ventas_list
        
        # Agregar filtros al contexto para mantenerlos en el formulario
        context['fecha_filtro'] = self.request.GET.get('fecha_filtro', '')
        context['fecha_desde'] = self.request.GET.get('fecha_desde', '')
        context['fecha_hasta'] = self.request.GET.get('fecha_hasta', '')
        context['busqueda_folio'] = self.request.GET.get('busqueda_folio', '')
        context['busqueda_servicio'] = self.request.GET.get('busqueda_servicio', '')
        
        # Para CONTADOR: agregar ventas con pagos pendientes de confirmación
        if context['user_rol'] == 'CONTADOR':
            # Ventas con estado "En confirmación" o con abonos pendientes
            ventas_pendientes_ids = list(AbonoPago.objects.filter(
                Q(forma_pago__in=['TRN', 'TAR', 'DEP']) & Q(confirmado=False)
            ).values_list('venta_id', flat=True).distinct())
            
            ventas_en_confirmacion_ids = list(VentaViaje.objects.filter(
                estado_confirmacion='EN_CONFIRMACION'
            ).values_list('pk', flat=True))
            
            # Combinar ambas listas y convertir a lista para el template
            todas_ids_pendientes = list(set(ventas_pendientes_ids + ventas_en_confirmacion_ids))
            context['ventas_pendientes_confirmacion_ids'] = todas_ids_pendientes

        cotizacion_payload = []
        for venta in ventas_list:
            cliente = venta.cliente
            fecha_inicio = venta.fecha_inicio_viaje.isoformat() if venta.fecha_inicio_viaje else ''
            fecha_fin = venta.fecha_fin_viaje.isoformat() if venta.fecha_fin_viaje else ''
            dias = None
            noches = None
            if venta.fecha_inicio_viaje and venta.fecha_fin_viaje:
                delta = (venta.fecha_fin_viaje - venta.fecha_inicio_viaje).days
                if delta >= 0:
                    dias = delta + 1
                    noches = max(delta, 0)

            cotizacion_payload.append({
                'id': venta.pk,
                'slug': venta.slug_safe,
                'cliente': cliente.nombre_completo_display,
                'cotizaciones': getattr(cliente, 'cotizaciones_generadas', 0),
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'dias': dias,
                'noches': noches,
                'increment_url': reverse('incrementar_cotizaciones_cliente', kwargs={'slug': venta.slug_safe, 'pk': venta.pk})
            })

        context['cotizacion_ventas_json'] = json.dumps(cotizacion_payload, ensure_ascii=False)
        context['cotizacion_fecha_hoy'] = timezone.localdate().isoformat()
        context['puede_generar_cotizacion'] = context['user_rol'] != 'CONTADOR' and bool(cotizacion_payload)
        
        del context['object_list'] 
        
        return context

# ------------------- 3. DETALLE DE VENTA MODIFICADA -------------------

class VentaViajeDetailView(LoginRequiredMixin, DetailView):
    model = VentaViaje
    template_name = 'ventas/venta_detail.html'
    context_object_name = 'venta'

    # ******************************************************************
    # NUEVO: Implementación de get_object para usar SLUG y PK
    # ******************************************************************
    def get_object(self, queryset=None):
        # 1. Recupera los parámetros de la URL
        pk = self.kwargs.get('pk')
        slug = self.kwargs.get('slug')
        
        # 2. Define el queryset base si no se proporciona uno
        if queryset is None:
            queryset = self.get_queryset()
            
        # 3. Busca el objeto utilizando ambos parámetros para asegurar unicidad
        try:
            # Usamos get_queryset() que ya trae el .select_related() si lo tienes configurado
            obj = queryset.filter(pk=pk, slug=slug).first()
            if obj:
                return obj
        except VentaViaje.DoesNotExist:
            pass # Continúa al manejo de error 404
            
        # 4. Si el objeto no se encuentra, levanta un error 404
        from django.http import Http404
        raise Http404("No se encontró la Venta de Viaje que coincide con el ID y el slug.")
    
    # ******************************************************************
    # FIN de get_object
    # ******************************************************************

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venta = self.object
        user_rol = get_user_role(self.request.user)
        context['user_rol'] = user_rol
        context['es_jefe'] = (user_rol == 'JEFE')
        
        # Marcar notificaciones pendientes como vistas al entrar al detalle
        # Esto hace que al hacer clic en "Ver Venta" la notificación se marque automáticamente
        if self.request.user.is_authenticated:
            Notificacion.objects.filter(
                usuario=self.request.user,
                venta=venta,
                vista=False
            ).update(vista=True, fecha_vista=timezone.now())
        
        # Verificar si existen abonos reales pendientes
        # Esto ayuda a determinar si la apertura está realmente pendiente o si solo hay abonos nuevos pendientes
        abonos_pendientes_reales = venta.abonos.filter(confirmado=False).exists()
        context['tiene_abonos_pendientes'] = abonos_pendientes_reales
        
        # Inicialización del Formulario de Abono
        context['abono_form'] = AbonoPagoForm(initial={'venta': venta.pk}) 
        # Abonos existentes, ordenados por fecha
        context['abonos'] = venta.abonos.all().order_by('-fecha_pago')

        # Control de habilitación de documentos (contrato y comprobante de abonos)
        tiene_abono_confirmado = venta.abonos.filter(confirmado=True).exists()
        
        # Si el pago de apertura es en efectivo (EFE), está confirmado automáticamente
        # Si es otro método de pago, necesita confirmación del contador
        apertura_confirmada = False
        if venta.cantidad_apertura > 0:
            if venta.modo_pago_apertura == 'EFE':
                # Pago en efectivo: confirmado automáticamente
                apertura_confirmada = True
            else:
                # Otros métodos de pago: necesita confirmación del contador
                apertura_confirmada = venta.estado_confirmacion == 'COMPLETADO'
        
        context['puede_generar_documentos'] = tiene_abono_confirmado or apertura_confirmada
        
        # Verificar si hay notificación de apertura pendiente para el CONTADOR
        if user_rol == 'CONTADOR':
            # Notificacion ya está importada al inicio del archivo
            context['notificacion_apertura_pendiente'] = Notificacion.objects.filter(
                usuario=self.request.user,
                venta=venta,
                tipo='PAGO_PENDIENTE',
                confirmado=False,
                abono__isnull=True  # Sin abono = apertura
            ).first()

        # Asegurar que exista registro de logística para sincronizar servicios
        try:
            venta.logistica
        except Logistica.DoesNotExist:
            Logistica.objects.create(venta=venta)
        mostrar_tab_logistica = self._puede_ver_logistica_tab(self.request.user, venta)
        context['mostrar_tab_logistica'] = mostrar_tab_logistica
        context['puede_editar_servicios_financieros'] = self._puede_gestionar_logistica_financiera(self.request.user, venta)
        if mostrar_tab_logistica:
            self._prepare_logistica_finanzas_context(context, venta)
        
        # Inicialización del Formulario de Confirmaciones
        context['confirmaciones'] = venta.confirmaciones.select_related('subido_por').order_by('-fecha_subida')
        context['confirmacion_form'] = ConfirmacionVentaForm()
        context['puede_subir_confirmaciones'] = self._puede_subir_confirmaciones(self.request.user, venta)
        
        # Calcular descuentos para el contexto
        descuento_km = venta.descuento_kilometros_mxn or Decimal('0.00')
        descuento_promo = venta.descuento_promociones_mxn or Decimal('0.00')
        total_descuentos = descuento_km + descuento_promo
        costo_base = (venta.costo_venta_final or Decimal('0.00')) + (venta.costo_modificacion or Decimal('0.00'))
        total_final = costo_base - total_descuentos
        
        context['total_descuentos'] = total_descuentos
        context['costo_base'] = costo_base
        context['total_final'] = total_final
        context['descuento_km'] = descuento_km
        context['descuento_promo'] = descuento_promo
        
        return context

    # ----------------------------------------------------------------------
    # MÉTODO POST: Para gestionar los formularios: Logística y Abonos
    # ----------------------------------------------------------------------
    def post(self, request, *args, **kwargs):
        # Es crucial establecer el objeto (VentaViaje) al inicio del POST
        # self.get_object() utiliza los nuevos kwargs (slug y pk)
        self.object = self.get_object() 
        context = self.get_context_data(object=self.object)
        
        # 1. Manejo del control financiero por servicio
        if 'actualizar_servicios_logistica' in request.POST:
            if not self._puede_gestionar_logistica_financiera(request.user, self.object):
                messages.error(request, "No tienes permiso para actualizar el control financiero de esta venta.")
                return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=logistica')

            # [NUEVO] Paso 1: Obtener una COPIA LIMPIA de los originales para referencia
            # Es vital hacer esto ANTES de validar el formset y en una variable separada
            # Usamos list() para asegurar que se traigan de la BD ahora mismo
            servicios_db_list = list(self.object.servicios_logisticos.all())
            originales_limpios = {s.pk: s for s in servicios_db_list}
            
            # Paso 2: Crear el formset normalmente
            servicios_qs = self.object.servicios_logisticos.all().order_by('orden', 'pk')
            formset = LogisticaServicioFormSet(
                request.POST,
                queryset=servicios_qs,
                prefix='servicios'
            )

            if formset.is_valid():
                # BLOQUEO TEMPORAL: Durante pruebas, TODOS los montos planificados ya asignados están bloqueados
                # TODO: En producción, implementar permisos por rol (GERENTE puede editar)
                total_pagado = self.object.total_pagado
                total_marcado_pagado = Decimal('0.00')
                
                for form in formset.forms:
                    if not form.cleaned_data:
                        continue
                    
                    servicio_id = form.instance.pk if form.instance.pk else None
                    # Usar la copia limpia de la BD para comparar
                    original = originales_limpios.get(servicio_id) if servicio_id else None
                    
                    if not original:
                        continue 
                    
                    # --- LÓGICA DE ACTUALIZACIÓN CON BLOQUEO TEMPORAL ---
                    
                    # 1. MONTO PLANIFICADO
                    # PROBLEMA RAÍZ: El formulario puede recibir valores incorrectos debido a:
                    # - Input hidden que no se envía correctamente
                    # - clean_monto_planeado que convierte None/empty a Decimal('0.00')
                    # - Conflictos entre input visible (disabled) e input hidden
                    # SOLUCIÓN: Si ya tiene monto asignado, SIEMPRE preservar el original de la BD
                    nuevo_monto = form.cleaned_data.get('monto_planeado')
                    
                    # BLOQUEO TEMPORAL: Si tiene monto ya asignado, PRESERVAR SIEMPRE el original
                    # (sin importar qué venga del formulario, incluso si es 0.00)
                    if original.monto_planeado and original.monto_planeado > Decimal('0.00'):
                        # IGNORAR completamente el valor del formulario y usar el original de la BD
                        nuevo_monto = original.monto_planeado
                    else:
                        # Si estaba vacío/sin asignar, aceptamos el valor nuevo (o 0 si viene vacío)
                        nuevo_monto = nuevo_monto or Decimal('0.00')
                    
                    # 2. ESTADO PAGADO
                    # BLOQUEO TEMPORAL: Una vez marcado como pagado, no se puede desmarcar
                    nuevo_pagado = form.cleaned_data.get('pagado', False)
                    if original.pagado:
                        # Una vez pagado, siempre mantener como pagado (bloqueo temporal)
                        nuevo_pagado = True
                    
                    # 3. OTROS CAMPOS (Siempre editables durante pruebas)
                    nuevo_opcion_proveedor = form.cleaned_data.get('opcion_proveedor', '')
                    
                    # --- APLICAR CAMBIOS ---
                    original.monto_planeado = nuevo_monto
                    original.pagado = nuevo_pagado
                    original.opcion_proveedor = nuevo_opcion_proveedor
                    
                    # Gestión de fecha de pago
                    if nuevo_pagado and not original.fecha_pagado:
                         original.fecha_pagado = timezone.now()
                    elif not nuevo_pagado:
                         original.fecha_pagado = None
                    
                    # Calcular total marcado como pagado para validación
                    if nuevo_pagado:
                        total_marcado_pagado += nuevo_monto
                
                # Validar que el total marcado como pagado no exceda el total pagado
                if total_marcado_pagado > total_pagado + Decimal('0.01'):
                    formset._non_form_errors = formset.error_class([
                        f"No puedes marcar como pagados ${total_marcado_pagado:,.2f} cuando solo hay ${total_pagado:,.2f} registrados en abonos y apertura."
                    ])
                    context = self.get_context_data()
                    self._prepare_logistica_finanzas_context(context, self.object, formset=formset, servicios_qs=servicios_qs)
                    return self.render_to_response(context)
                
                # Guardar todos los cambios (los objetos original ya están actualizados en el bucle anterior)
                for form in formset.forms:
                    if not form.cleaned_data:
                        continue
                    
                    servicio_id = form.instance.pk if form.instance.pk else None
                    original = originales_limpios.get(servicio_id) if servicio_id else None
                    
                    if original:
                        original.save(update_fields=['monto_planeado', 'pagado', 'fecha_pagado', 'opcion_proveedor'])

                messages.success(request, "Control por servicio actualizado correctamente.")
                return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=logistica')
            else:
                messages.error(request, "Revisa los montos ingresados para cada servicio.")

            self._prepare_logistica_finanzas_context(context, self.object, formset=formset, servicios_qs=servicios_qs)

        # 3. Manejo del Formulario de Abono
        elif 'registrar_abono' in request.POST:
            # CONTADOR solo lectura, no puede registrar abonos
            user_rol = request.user.perfil.rol if hasattr(request.user, 'perfil') else 'INVITADO'
            if user_rol == 'CONTADOR':
                messages.error(request, "No tienes permiso para registrar abonos. Solo puedes visualizarlos.")
                return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=abonos')
            
            abono_form = AbonoPagoForm(request.POST)
            if abono_form.is_valid():
                abono = abono_form.save(commit=False)
                abono.venta = self.object
                abono.registrado_por = request.user
                
                # Obtener la forma de pago del formulario
                forma_pago = abono_form.cleaned_data.get('forma_pago', 'EFE')
                
                # ⚠️ IMPORTANTE: Determinar si requiere confirmación del contador
                # Transferencia (TRN), Tarjeta (TAR) y Depósito (DEP) requieren confirmación
                # Solo Efectivo (EFE) se confirma automáticamente
                requiere_confirmacion = forma_pago in ['TRN', 'TAR', 'DEP']
                
                # Establecer el estado de confirmación ANTES de guardar
                if requiere_confirmacion:
                    # Transferencia, Tarjeta o Depósito: NO confirmado, requiere aprobación del contador
                    abono.confirmado = False
                    abono.confirmado_por = None
                    abono.confirmado_en = None
                else:
                    # Solo Efectivo se confirma automáticamente
                    abono.confirmado = True
                    abono.confirmado_por = None  # No requiere confirmación manual
                    abono.confirmado_en = timezone.now()  # Fecha de confirmación automática
                
                # Guardar el abono primero para obtener su PK
                abono.save()
                
                # Procesar según si requiere confirmación o no
                if requiere_confirmacion:
                    # ⚠️ FLUJO DE APROBACIÓN PARA TRANSFERENCIA/TARJETA/DEPÓSITO
                    # ✅ NUEVO FLUJO: NO se crean notificaciones automáticas
                    # Las notificaciones se crearán solo cuando se suba el comprobante
                    
                    # 1. Cambiar estado de venta a "En confirmación"
                    self.object.estado_confirmacion = 'EN_CONFIRMACION'
                    self.object.save(update_fields=['estado_confirmacion'])
                    
                    forma_pago_display = dict(AbonoPago.FORMA_PAGO_CHOICES).get(forma_pago, forma_pago)
                    messages.success(request, f"Abono de ${abono.monto:,.2f} ({forma_pago_display}) registrado exitosamente. ⏳ Por favor, sube el comprobante para enviarlo al contador.")
                else:
                    # ⚠️ FLUJO AUTOMÁTICO SOLO PARA EFECTIVO
                    
                    # Recalcular el total pagado después de guardar el abono
                    self.object.actualizar_estado_financiero()
                    
                    forma_pago_display = dict(AbonoPago.FORMA_PAGO_CHOICES).get(forma_pago, forma_pago)
                    
                    # Crear notificación para el VENDEDOR de la venta (si existe y no es quien registra el abono)
                    if self.object.vendedor and self.object.vendedor != request.user:
                        mensaje_vendedor = f"Abono registrado y confirmado en tu venta: ${abono.monto:,.2f} ({forma_pago_display}) - Venta #{self.object.pk} - Cliente: {self.object.cliente.nombre_completo_display}"
                        Notificacion.objects.create(
                            usuario=self.object.vendedor,
                            tipo='ABONO',
                            mensaje=mensaje_vendedor,
                            venta=self.object,
                            abono=abono,
                            confirmado=True
                        )
                    
                    # Si la venta se liquidó completamente, crear notificación de liquidación
                    if self.object.esta_pagada and self.object.vendedor:
                        mensaje_liquidacion = f"¡Venta #{self.object.pk} completamente liquidada! - Cliente: {self.object.cliente.nombre_completo_display} - Total: ${self.object.costo_venta_final:,.2f}"
                        Notificacion.objects.create(
                            usuario=self.object.vendedor,
                            tipo='LIQUIDACION',
                            mensaje=mensaje_liquidacion,
                            venta=self.object,
                            confirmado=False
                        )
                    
                    messages.success(request, f"Abono de ${abono.monto:,.2f} ({forma_pago_display}) registrado exitosamente. ✅ Confirmado automáticamente.")
                
                # Redirige a la pestaña de Abonos
                # ******************************************************************
                # IMPORTANTE: Se actualiza la redirección para usar SLUG y PK (YA ESTABA BIEN AQUÍ)
                # ******************************************************************
                return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=abonos')
            else:
                messages.error(request, "Error al registrar el abono. Revisa el monto y la forma de pago. ⚠️")
                context['abono_form'] = abono_form # Muestra el formulario con errores
                
        # 3. Manejo del formulario de confirmaciones
        elif 'registrar_confirmacion' in request.POST:
            if not self._puede_subir_confirmaciones(request.user, self.object):
                messages.error(request, "No tienes permiso para agregar confirmaciones a esta venta.")
                return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=confirmaciones')

            # Validar archivos directamente desde request.FILES
            archivos = request.FILES.getlist('archivos')
            nota = request.POST.get('nota', '').strip()

            if not archivos:
                messages.error(request, "Debes seleccionar al menos un archivo.")
                confirmacion_form = ConfirmacionVentaForm(request.POST, request.FILES)
                context['confirmacion_form'] = confirmacion_form
            else:
                # Procesar los archivos
                creadas = 0
                errores = []
                for archivo in archivos:
                    try:
                        ConfirmacionVenta.objects.create(
                            venta=self.object,
                            archivo=archivo,
                            nota=nota,
                            subido_por=request.user if request.user.is_authenticated else None
                        )
                        creadas += 1
                    except Exception as e:
                        errores.append(f"Error al guardar {archivo.name}: {str(e)}")

                if creadas > 0:
                    mensaje = f"Se cargaron {creadas} archivo(s) de confirmación correctamente."
                    if errores:
                        mensaje += " " + " ".join(errores)
                    messages.success(request, mensaje)
                else:
                    messages.error(request, "No se pudo cargar ningún archivo. " + " ".join(errores))
                
                return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=confirmaciones')

        # Si no hubo redirección exitosa, re-renderiza la respuesta con el contexto actualizado
        return self.render_to_response(context)

    def _puede_subir_confirmaciones(self, user, venta):
        """CONTADOR solo lectura, no puede subir confirmaciones."""
        if not user.is_authenticated:
            return False
        if user.is_superuser or user == venta.vendedor:
            return True
        rol = get_user_role(user).upper()
        # CONTADOR no puede subir confirmaciones, solo visualizarlas
        return 'JEFE' in rol

    # ------------------- Utilidades internas para logística financiera -------------------

    def _puede_ver_logistica_tab(self, user, venta):
        if not user or not user.is_authenticated:
            return False
        rol = get_user_role(user)
        if rol in ['JEFE', 'CONTADOR']:
            return True
        return rol == 'VENDEDOR' and venta.vendedor == user

    def _puede_gestionar_logistica_financiera(self, user, venta):
        if not user or not user.is_authenticated:
            return False
        rol = get_user_role(user)
        if rol == 'JEFE':
            return True
        return rol == 'VENDEDOR' and venta.vendedor == user

    def _sync_logistica_servicios(self, venta):
        servicios_codes = []
        if venta.servicios_seleccionados:
            servicios_codes = [
                code.strip() for code in venta.servicios_seleccionados.split(',')
                if code.strip()
            ]
        choices = dict(VentaViaje.SERVICIOS_CHOICES)
        existentes = {serv.codigo_servicio: serv for serv in venta.servicios_logisticos.all()}

        # Extraer opciones de proveedor desde servicios_detalle
        opciones_proveedor = {}
        if venta.servicios_detalle:
            servicios_detalle = venta.servicios_detalle.split('\n')
            for linea in servicios_detalle:
                linea = linea.strip()
                if not linea:
                    continue
                # Formato: "Servicio - Proveedor: Nombre - Opción: Opción elegida"
                if ' - Opción: ' in linea:
                    partes = linea.split(' - Opción: ')
                    if len(partes) == 2:
                        servicio_parte = partes[0].strip()
                        opcion = partes[1].strip()
                        # Extraer el nombre del servicio (antes de " - Proveedor:")
                        if ' - Proveedor: ' in servicio_parte:
                            nombre_servicio = servicio_parte.split(' - Proveedor: ')[0].strip()
                        else:
                            nombre_servicio = servicio_parte.strip()
                        opciones_proveedor[nombre_servicio] = opcion

        for idx, code in enumerate(servicios_codes):
            nombre = choices.get(code)
            if not nombre:
                continue
            opcion_proveedor = opciones_proveedor.get(nombre, '')
            if code not in existentes:
                # Para registros nuevos, asignar el valor parseado inicial
                LogisticaServicio.objects.create(
                    venta=venta,
                    codigo_servicio=code,
                    nombre_servicio=nombre,
                    orden=idx,
                    opcion_proveedor=opcion_proveedor
                )
            else:
                serv = existentes[code]
                update_fields = []
                if serv.orden != idx:
                    serv.orden = idx
                    update_fields.append('orden')
                # Solo actualizar opcion_proveedor si el campo en BD está vacío
                # Esto permite que las ediciones manuales del usuario persistan
                if not serv.opcion_proveedor or serv.opcion_proveedor.strip() == '':
                    if opcion_proveedor:  # Solo actualizar si hay un valor parseado
                        serv.opcion_proveedor = opcion_proveedor
                        update_fields.append('opcion_proveedor')
                if update_fields:
                    serv.save(update_fields=update_fields)

        # Eliminar servicios que ya no están contratados
        if servicios_codes:
            venta.servicios_logisticos.exclude(codigo_servicio__in=servicios_codes).delete()
        else:
            venta.servicios_logisticos.all().delete()

    def _prepare_logistica_finanzas_context(self, context, venta, formset=None, servicios_qs=None):
        if not context.get('mostrar_tab_logistica'):
            return

        self._sync_logistica_servicios(venta)
        if servicios_qs is None:
            servicios_qs = venta.servicios_logisticos.all().order_by('orden', 'pk')

        if formset is None:
            formset = LogisticaServicioFormSet(queryset=servicios_qs, prefix='servicios')

        # Determinar si el usuario es JEFE
        user_rol = get_user_role(self.request.user)
        es_jefe = (user_rol == 'JEFE')
        context['es_jefe'] = es_jefe
        
        # TEMPORAL PARA PRUEBAS: Bloquear todos los campos una vez asignados (incluido gerente)
        # TODO: Ajustar permisos por tipo de usuario más adelante
        if not context.get('puede_editar_servicios_financieros'):
            for form in formset.forms:
                for field in form.fields.values():
                    field.widget.attrs['disabled'] = 'disabled'
        else:
            # Bloquear campos una vez asignados (TEMPORAL: para todos, incluido gerente)
            for form in formset.forms:
                if form.instance and form.instance.pk:
                    # Bloquear monto_planeado si tiene valor (TEMPORAL: para todos)
                    if form.instance.monto_planeado and form.instance.monto_planeado > Decimal('0.00'):
                        form.fields['monto_planeado'].widget.attrs['disabled'] = 'disabled'
                        form.fields['monto_planeado'].widget.attrs['readonly'] = 'readonly'
                    
                    # Bloquear checkbox pagado si está marcado (TEMPORAL: para todos)
                    if form.instance.pagado:
                        form.fields['pagado'].widget.attrs['disabled'] = 'disabled'

        resumen = build_financial_summary(venta, servicios_qs)
        filas = build_service_rows(servicios_qs, resumen, list(formset.forms), venta=venta)

        context['servicios_financieros_formset'] = formset
        context['logistica_finanzas'] = resumen
        context['servicios_logisticos_rows'] = filas
        context['servicios_logisticos_queryset'] = servicios_qs

# ------------------- 3.1. ELIMINAR CONFIRMACIÓN DE VENTA -------------------

class EliminarConfirmacionView(LoginRequiredMixin, View):
    """Vista para eliminar una confirmación de venta."""
    
    def post(self, request, pk):
        try:
            confirmacion = get_object_or_404(ConfirmacionVenta, pk=pk)
            venta = confirmacion.venta
            
            # Verificar permisos (misma lógica que para subir)
            if not request.user.is_authenticated:
                messages.error(request, "Debes estar autenticado para realizar esta acción.")
                return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
            
            puede_eliminar = False
            if request.user.is_superuser or request.user == venta.vendedor:
                puede_eliminar = True
            else:
                rol = get_user_role(request.user).upper()
                # CONTADOR solo lectura, no puede eliminar confirmaciones
                puede_eliminar = 'JEFE' in rol
            
            if not puede_eliminar:
                messages.error(request, "No tienes permiso para eliminar confirmaciones de esta venta.")
                return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
            
            # Guardar información antes de eliminar
            nombre_archivo = confirmacion.nombre_archivo
            venta_pk = venta.pk
            venta_slug = venta.slug_safe
            
            # Eliminar el archivo físico si existe
            if confirmacion.archivo:
                try:
                    confirmacion.archivo.delete(save=False)
                except Exception as e:
                    logger.warning(f"No se pudo eliminar el archivo físico: {e}")
            
            # Eliminar el registro
            confirmacion.delete()
            
            messages.success(request, f"Confirmación '{nombre_archivo}' eliminada correctamente.")
            return redirect(reverse('detalle_venta', kwargs={'pk': venta_pk, 'slug': venta_slug}) + '?tab=confirmaciones')
            
        except ConfirmacionVenta.DoesNotExist:
            messages.error(request, "La confirmación no existe.")
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f"Error al eliminar la confirmación: {str(e)}")
            if 'venta' in locals():
                return redirect(reverse('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=confirmaciones')
            return redirect('dashboard')


# ------------------- 4. CREACIÓN Y EDICIÓN DE VENTA -------------------

class VentaViajeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = VentaViaje
    form_class = VentaViajeForm
    template_name = 'ventas/venta_form.html'
    
    def test_func(self):
        """Solo JEFE y VENDEDOR pueden crear ventas. CONTADOR solo lectura."""
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol in ['JEFE', 'VENDEDOR']
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para crear ventas. Solo puedes visualizarlas.")
        return redirect('lista_ventas')
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        
        # Pre-llenar valores desde cotización si existe (tiene prioridad)
        cot_slug = self.request.GET.get('cotizacion')
        cotizacion_data = self.request.session.get('cotizacion_convertir', {})
        
        # Pre-seleccionar cliente si viene en la URL (desde detalle del cliente)
        # Solo si no hay cotización (la cotización tiene prioridad)
        cliente_pk = self.request.GET.get('cliente_pk')
        if cliente_pk and not (cot_slug or cotizacion_data):
            if 'initial' not in kwargs:
                kwargs['initial'] = {}
            try:
                cliente = Cliente.objects.get(pk=cliente_pk)
                kwargs['initial']['cliente'] = cliente
            except Cliente.DoesNotExist:
                pass
        
        # Función auxiliar para limpiar y convertir totales
        def limpiar_y_convertir_total(valor):
            """Convierte un string de total (puede tener comas) a Decimal"""
            if not valor:
                return Decimal('0.00')
            try:
                # Remover comas y espacios, luego convertir a Decimal
                valor_limpio = str(valor).replace(',', '').replace('$', '').strip()
                return Decimal(valor_limpio)
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        
        if cot_slug or cotizacion_data:
            slug_a_usar = cot_slug or cotizacion_data.get('cotizacion_slug')
            if slug_a_usar:
                cot = Cotizacion.objects.filter(slug=slug_a_usar).first()
                if cot:
                    # Obtener el total de la sesión si está disponible (prioridad máxima)
                    total_cotizacion = Decimal('0.00')
                    
                    # 1. Intentar obtener TOTAL de la URL (Prioridad Máxima - Bypass de Sesión)
                    total_url = self.request.GET.get('total_b')
                    if total_url:
                        try:
                            # Limpiar y convertir
                            total_cotizacion = Decimal(str(total_url).replace(',', '').replace('$', ''))
                            logging.debug(f"Total recuperado VÍA URL (Bypass): {total_cotizacion}")
                        except (ValueError, InvalidOperation):
                            pass
                    
                    # 2. Si no vino en URL, intentar sesión (lógica original)
                    if total_cotizacion == Decimal('0.00') and cotizacion_data.get('total_cotizacion'):
                        try:
                            total_cotizacion = Decimal(cotizacion_data['total_cotizacion'])
                            logging.debug(f"Total recuperado de la sesión: {total_cotizacion}")
                        except (ValueError, InvalidOperation):
                            total_cotizacion = Decimal('0.00')
                    
                    # Calcular el costo final - SIEMPRE usar el total (URL tiene prioridad sobre sesión)
                    if total_cotizacion > 0:
                        costo_final = total_cotizacion
                        logging.debug(f"Usando total de la sesión: {costo_final}")
                    else:
                        # Solo si no hay total en la sesión, intentar obtenerlo de las propuestas
                        # Esto solo debería pasar si hay un error en el guardado de la sesión
                        propuestas = cot.propuestas if isinstance(cot.propuestas, dict) else {}
                        tipo_cot = propuestas.get('tipo', '')
                        # Intentar leer índice de la URL primero (Bypass de Sesión)
                        opcion_vuelo_index = self.request.GET.get('idx_b', '') or cotizacion_data.get('opcion_vuelo_index', '')
                        
                        if tipo_cot == 'vuelos' and propuestas.get('vuelos'):
                            vuelos = propuestas.get('vuelos', [])
                            if vuelos and len(vuelos) > 0:
                                # Intentar usar la opción seleccionada de la sesión
                                try:
                                    indice = int(opcion_vuelo_index) if opcion_vuelo_index else 0
                                    if indice < 0 or indice >= len(vuelos):
                                        indice = 0
                                except (ValueError, TypeError):
                                    indice = 0
                                
                                vuelo_seleccionado = vuelos[indice] if isinstance(vuelos, list) else vuelos.get(f'propuesta_{indice + 1}', {})
                                if isinstance(vuelo_seleccionado, dict) and vuelo_seleccionado.get('total'):
                                    total_primero = limpiar_y_convertir_total(vuelo_seleccionado.get('total'))
                                    if total_primero > 0:
                                        costo_final = total_primero
                                        logging.debug(f"Total obtenido de propuestas (índice {indice}): {costo_final}")
                                    else:
                                        costo_final = cot.total_estimado or Decimal('0.00')
                                else:
                                    costo_final = cot.total_estimado or Decimal('0.00')
                            elif tipo_cot == 'hospedaje' and propuestas.get('hoteles'):
                                hoteles = propuestas.get('hoteles', [])
                                if hoteles and len(hoteles) > 0:
                                    # Intentar leer índice de la URL primero (Bypass de Sesión)
                                    opcion_hotel_index = self.request.GET.get('idx_b', '') or cotizacion_data.get('opcion_hotel_index', '')
                                    try:
                                        indice = int(opcion_hotel_index) if opcion_hotel_index else 0
                                        if indice < 0 or indice >= len(hoteles):
                                            indice = 0
                                    except (ValueError, TypeError):
                                        indice = 0
                                    
                                    hotel_seleccionado = hoteles[indice] if isinstance(hoteles, list) else hoteles.get(f'propuesta_{indice + 1}', {})
                                    if isinstance(hotel_seleccionado, dict) and hotel_seleccionado.get('total'):
                                        total_primero = limpiar_y_convertir_total(hotel_seleccionado.get('total'))
                                        if total_primero > 0:
                                            costo_final = total_primero
                                            logging.debug(f"Total obtenido de propuestas hospedaje (get_form_kwargs, índice {indice}): {costo_final}")
                                        else:
                                            costo_final = cot.total_estimado or Decimal('0.00')
                                    else:
                                        costo_final = cot.total_estimado or Decimal('0.00')
                                else:
                                    costo_final = cot.total_estimado or Decimal('0.00')
                            else:
                                costo_final = cot.total_estimado or Decimal('0.00')
                        else:
                            costo_final = cot.total_estimado or Decimal('0.00')
                    
                    # Convertir Decimal a string para TextInput con formato de moneda
                    # El JavaScript aplicará el formato de moneda automáticamente
                    if isinstance(costo_final, Decimal):
                        # Convertir a string sin formato para que el JavaScript lo formatee
                        costo_final_value = str(costo_final)
                    else:
                        costo_final_value = str(costo_final) if costo_final else ''
                    
                    # Obtener edades de menores y servicios desde la sesión
                    edades_menores_valor = cotizacion_data.get('edades_menores', '')
                    # Si no está en la sesión, obtener directamente de la cotización y formatear
                    if not edades_menores_valor and cot.edades_menores and cot.edades_menores.strip():
                        edades = [e.strip() for e in cot.edades_menores.split(',') if e.strip()]
                        if edades:
                            # Crear formato con saltos de línea para cualquier cantidad de menores
                            edades_lista = [f"Menor {i+1} - {edad}" for i, edad in enumerate(edades)]
                            edades_menores_valor = '\n'.join(edades_lista)
                    
                    servicios_seleccionados_valor = cotizacion_data.get('servicios_seleccionados', [])
                    
                    # Establecer valores iniciales antes de inicializar el formulario
                    if 'initial' not in kwargs:
                        kwargs['initial'] = {}
                    kwargs['initial'].update({
                        'cliente': cot.cliente,
                        'fecha_inicio_viaje': cot.fecha_inicio,
                        'fecha_fin_viaje': cot.fecha_fin,
                        'edades_menores': edades_menores_valor,  # Prellenar con edades desde sesión
                        'costo_venta_final': costo_final_value,  # Usar string para TextInput con formato de moneda
                    })
                    
                    # Asegurar que el campo también tenga el valor directamente
                    if edades_menores_valor and 'edades_menores' in kwargs.get('initial', {}):
                        # El valor ya está en initial, Django lo usará automáticamente
                        pass
                    
                    # Prellenar servicios seleccionados en initial también
                    if servicios_seleccionados_valor:
                        kwargs['initial']['servicios_seleccionados'] = servicios_seleccionados_valor
        
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cliente = self._obtener_cliente_contextual(context.get('form'))
        context['cliente_preseleccionado'] = cliente
        if cliente:
            context['kilometros_cliente'] = KilometrosService.resumen_cliente(cliente)
        context['kilometros_meta'] = {
            'valor_por_km': KilometrosService.VALOR_PESO_POR_KM,
            'km_por_peso': KilometrosService.KM_POR_PESO,
            'max_porcentaje': KilometrosService.MAX_PORCENTAJE_REDENCION * 100,
        }
        # Prefill desde cotización
        cot_slug = self.request.GET.get('cotizacion')
        cotizacion_data = self.request.session.get('cotizacion_convertir', {})
        
        if cot_slug or cotizacion_data:
            # Usar el slug de la URL o de la sesión
            slug_a_usar = cot_slug or cotizacion_data.get('cotizacion_slug')
            if slug_a_usar:
                cot = Cotizacion.objects.filter(slug=slug_a_usar).first()
                if cot:
                    form = context.get('form')
                    if form:
                        inicial = form.initial.copy()
                        
                        # Función auxiliar para limpiar y convertir totales
                        def limpiar_y_convertir_total(valor):
                            """Convierte un string de total (puede tener comas) a Decimal"""
                            if not valor:
                                return Decimal('0.00')
                            try:
                                # Remover comas y espacios, luego convertir a Decimal
                                valor_limpio = str(valor).replace(',', '').replace('$', '').strip()
                                return Decimal(valor_limpio)
                            except (ValueError, InvalidOperation):
                                return Decimal('0.00')
                        
                        # Obtener el total de la sesión si está disponible
                        total_cotizacion = Decimal('0.00')
                        if cotizacion_data.get('total_cotizacion'):
                            try:
                                total_cotizacion = Decimal(cotizacion_data['total_cotizacion'])
                            except (ValueError, InvalidOperation):
                                total_cotizacion = Decimal('0.00')
                        
                        # Calcular el costo final - SIEMPRE usar el total de la sesión si está disponible
                        if total_cotizacion > 0:
                            costo_final = total_cotizacion
                            logging.debug(f"Usando total de la sesión (get_context_data): {costo_final}")
                        else:
                            # Solo si no hay total en la sesión, intentar obtenerlo de las propuestas
                            # Esto solo debería pasar si hay un error en el guardado de la sesión
                            propuestas = cot.propuestas if isinstance(cot.propuestas, dict) else {}
                            tipo_cot = propuestas.get('tipo', '')
                            # Intentar leer índice de la URL primero (Bypass de Sesión)
                            opcion_vuelo_index = self.request.GET.get('idx_b', '') or cotizacion_data.get('opcion_vuelo_index', '')
                            
                            if tipo_cot == 'vuelos' and propuestas.get('vuelos'):
                                vuelos = propuestas.get('vuelos', [])
                                if vuelos and len(vuelos) > 0:
                                    # Intentar usar la opción seleccionada de la sesión
                                    try:
                                        indice = int(opcion_vuelo_index) if opcion_vuelo_index else 0
                                        if indice < 0 or indice >= len(vuelos):
                                            indice = 0
                                    except (ValueError, TypeError):
                                        indice = 0
                                    
                                    vuelo_seleccionado = vuelos[indice] if isinstance(vuelos, list) else vuelos.get(f'propuesta_{indice + 1}', {})
                                    if isinstance(vuelo_seleccionado, dict) and vuelo_seleccionado.get('total'):
                                        total_primero = limpiar_y_convertir_total(vuelo_seleccionado.get('total'))
                                        if total_primero > 0:
                                            costo_final = total_primero
                                            logging.debug(f"Total obtenido de propuestas (get_context_data, índice {indice}): {costo_final}")
                                        else:
                                            costo_final = cot.total_estimado or Decimal('0.00')
                                    else:
                                        costo_final = cot.total_estimado or Decimal('0.00')
                                else:
                                    costo_final = cot.total_estimado or Decimal('0.00')
                            elif tipo_cot == 'hospedaje' and propuestas.get('hoteles'):
                                hoteles = propuestas.get('hoteles', [])
                                if hoteles and len(hoteles) > 0:
                                    # Intentar leer índice de la URL primero (Bypass de Sesión)
                                    opcion_hotel_index = self.request.GET.get('idx_b', '') or cotizacion_data.get('opcion_hotel_index', '')
                                    try:
                                        indice = int(opcion_hotel_index) if opcion_hotel_index else 0
                                        if indice < 0 or indice >= len(hoteles):
                                            indice = 0
                                    except (ValueError, TypeError):
                                        indice = 0
                                    
                                    hotel_seleccionado = hoteles[indice] if isinstance(hoteles, list) else hoteles.get(f'propuesta_{indice + 1}', {})
                                    if isinstance(hotel_seleccionado, dict) and hotel_seleccionado.get('total'):
                                        total_primero = limpiar_y_convertir_total(hotel_seleccionado.get('total'))
                                        if total_primero > 0:
                                            costo_final = total_primero
                                            logging.debug(f"Total obtenido de propuestas hospedaje (get_context_data, índice {indice}): {costo_final}")
                                        else:
                                            costo_final = cot.total_estimado or Decimal('0.00')
                                    else:
                                        costo_final = cot.total_estimado or Decimal('0.00')
                                else:
                                    costo_final = cot.total_estimado or Decimal('0.00')
                            else:
                                costo_final = cot.total_estimado or Decimal('0.00')
                        
                        # Convertir Decimal a string para TextInput con formato de moneda
                        # El JavaScript aplicará el formato de moneda automáticamente
                        if isinstance(costo_final, Decimal):
                            # Convertir a string sin formato para que el JavaScript lo formatee
                            costo_final_value = str(costo_final)
                        else:
                            costo_final_value = str(costo_final) if costo_final else ''
                        
                        # Obtener edades de menores y servicios desde la sesión
                        edades_menores_valor = cotizacion_data.get('edades_menores', '')
                        # Si no está en la sesión, obtener directamente de la cotización y formatear
                        if not edades_menores_valor and cot.edades_menores and cot.edades_menores.strip():
                            edades = [e.strip() for e in cot.edades_menores.split(',') if e.strip()]
                            if edades:
                                # Crear formato con saltos de línea para cualquier cantidad de menores
                                edades_lista = [f"Menor {i+1} - {edad}" for i, edad in enumerate(edades)]
                                edades_menores_valor = '\n'.join(edades_lista)
                        
                        servicios_seleccionados_valor = cotizacion_data.get('servicios_seleccionados', [])
                        
                        inicial.update({
                            'cliente': cot.cliente,
                            'fecha_inicio_viaje': cot.fecha_inicio,
                            'fecha_fin_viaje': cot.fecha_fin,
                            'pasajeros': '',  # Campo vacío, se llena manualmente
                            'edades_menores': edades_menores_valor,  # Prellenar con edades desde sesión
                            'costo_venta_final': costo_final_value,  # Usar string para TextInput con formato de moneda
                        })
                        
                        # Establecer initial primero
                        form.initial = inicial
                        
                        # Luego asegurar que los campos específicos tengan el valor directamente
                        if edades_menores_valor and 'edades_menores' in form.fields:
                            form.fields['edades_menores'].initial = edades_menores_valor
                        
                        # Prellenar servicios seleccionados
                        if servicios_seleccionados_valor and 'servicios_seleccionados' in form.fields:
                            form.fields['servicios_seleccionados'].initial = servicios_seleccionados_valor
                        
                        # Asegurar que el valor también se establezca en el campo directamente
                        if 'costo_venta_final' in form.fields:
                            form.fields['costo_venta_final'].initial = costo_final_value
                            # También establecer el valor en el widget para asegurar que se muestre
                            if hasattr(form.fields['costo_venta_final'], 'widget'):
                                form.fields['costo_venta_final'].widget.attrs['value'] = str(costo_final_value)
                        
                        context['form'] = form
                    context['cotizacion_origen'] = cot
        return context

    def _obtener_cliente_contextual(self, form=None):
        cliente_pk = self.request.GET.get('cliente_pk') or self.request.POST.get('cliente')
        cliente = None
        if cliente_pk:
            cliente = Cliente.objects.filter(pk=cliente_pk).first()
        elif form and form.initial.get('cliente'):
            inicial = form.initial.get('cliente')
            if isinstance(inicial, Cliente):
                cliente = inicial
            else:
                cliente = Cliente.objects.filter(pk=inicial).first()
        return cliente
    
    def form_valid(self, form):
        # 1. Guarda temporalmente la instancia sin enviarla a la base de datos (commit=False)
        instance = form.save(commit=False)
        
        # 2. Asigna el vendedor (que es el usuario logueado)
        instance.vendedor = self.request.user
        
        # Si viene de cotización, enlazar (verificar GET parameter o sesión)
        cot = None
        cot_slug = self.request.GET.get('cotizacion')
        if cot_slug:
            cot = Cotizacion.objects.filter(slug=cot_slug).first()
        else:
            # Verificar si hay datos en la sesión
            cotizacion_data = self.request.session.get('cotizacion_convertir', {})
            if cotizacion_data.get('cotizacion_id'):
                try:
                    cot = Cotizacion.objects.filter(pk=cotizacion_data['cotizacion_id']).first()
                    # Limpiar la sesión después de usarla
                    if 'cotizacion_convertir' in self.request.session:
                        del self.request.session['cotizacion_convertir']
                except Exception:
                    pass
        
        if cot:
            instance.cotizacion_origen = cot

        # 3. ¡IMPORTANTE! Eliminamos la lógica manual de generación de slug de aquí.
        # El modelo VentaViaje se encarga de generar y asegurar el slug único 
        # dentro de su método save() una vez que la PK ha sido asignada.
        
        # 4. Guarda la instancia, lo que dispara el método save() del modelo
        self.object = instance # Establece self.object para que get_success_url funcione
        self.object.save() 
        
        # 5. Llama a save_m2m (necesario si hay campos ManyToMany en VentaViajeForm)
        form.save_m2m() 
        
        # 5.1. KILÓMETROS MOVUMS: Primero redimir (si aplica), luego acumular sobre el total CON descuento
        try:
            # PRIMERO: Redimir kilómetros si se aplicó descuento
            if self.object.aplica_descuento_kilometros and self.object.descuento_kilometros_mxn > 0:
                # Calcular kilómetros a redimir: descuento_mxn / valor_por_km (0.05)
                km_a_redimir = (self.object.descuento_kilometros_mxn / KilometrosService.VALOR_PESO_POR_KM).quantize(Decimal('0.01'))
                if km_a_redimir > 0:
                    registro_redencion = KilometrosService.redimir(
                        cliente=self.object.cliente,
                        kilometros=km_a_redimir,
                        venta=self.object,
                        descripcion=f"Redención aplicada a venta #{self.object.pk}: ${self.object.descuento_kilometros_mxn:,.2f} MXN"
                    )
                    if registro_redencion:
                        logger.info(f"✅ Kilómetros redimidos para venta {self.object.pk}: {km_a_redimir} km (${self.object.descuento_kilometros_mxn:,.2f} MXN)")
                    else:
                        logger.warning(f"⚠️ No se pudieron redimir kilómetros para venta {self.object.pk} (posible saldo insuficiente)")
            
            # DESPUÉS: Acumular kilómetros por la compra
            # IMPORTANTE: Se acumula sobre el total CON descuento (después de aplicar el descuento de kilómetros)
            # según las reglas: "Cada $1 MXN gastado = 0.5 Kilómetro Movums"
            # El cliente gasta el costo_venta_final menos el descuento de kilómetros
            if self.object.cliente and self.object.cliente.participa_kilometros:
                # Calcular el monto sobre el cual acumular: costo_venta_final - descuento_kilometros_mxn
                monto_para_acumular = self.object.costo_venta_final
                if self.object.aplica_descuento_kilometros and self.object.descuento_kilometros_mxn > 0:
                    monto_para_acumular = monto_para_acumular - self.object.descuento_kilometros_mxn
                monto_para_acumular = max(Decimal('0.00'), monto_para_acumular)
                
                if monto_para_acumular > 0:
                    registro_acumulacion = KilometrosService.acumular_por_compra(
                        self.object.cliente, 
                        monto_para_acumular,  # Se acumula sobre el total con descuento
                        venta=self.object
                    )
                    if registro_acumulacion:
                        km_acumulados = monto_para_acumular * KilometrosService.KM_POR_PESO
                        logger.info(f"✅ Kilómetros acumulados para venta {self.object.pk}: {km_acumulados} km (por ${monto_para_acumular:,.2f} MXN)")
            
            # ACUMULAR BONOS DE PROMOCIONES (tipo 'KM')
            # Obtener promociones aplicadas con bonos de kilómetros
            promociones_aplicadas = getattr(form, 'promos_km', [])
            bonos_acumulados = 0
            for promo_data in promociones_aplicadas:
                km_bono = promo_data.get('km_bono', Decimal('0.00'))
                promocion = promo_data.get('promo')
                if km_bono and km_bono > 0 and promocion:
                    registro_bono = KilometrosService.acumular_bono_promocion(
                        cliente=self.object.cliente,
                        kilometros=km_bono,
                        venta=self.object,
                        promocion=promocion,
                        descripcion=f"Bono de promoción: {promocion.nombre}"
                    )
                    if registro_bono:
                        bonos_acumulados += km_bono
                        logger.info(
                            f"✅ Bono de kilómetros acumulado para venta {self.object.pk}: "
                            f"{km_bono} km (Promoción: {promocion.nombre}, Cliente: {self.object.cliente.pk})"
                        )
                    else:
                        logger.warning(
                            f"⚠️ No se pudo acumular bono de promoción para venta {self.object.pk}: "
                            f"{km_bono} km (Promoción: {promocion.nombre if promocion else 'N/A'})"
                        )
            
            if bonos_acumulados > 0:
                logger.info(
                    f"📊 RESUMEN VENTA {self.object.pk}: "
                    f"Total bonos acumulados: {bonos_acumulados:,.2f} km, "
                    f"Cliente: {self.object.cliente.pk if self.object.cliente else 'N/A'}"
                )
        except Exception:
            logger.exception(
                f"❌ Error procesando kilómetros Movums para la venta {self.object.pk} "
                f"(Cliente: {self.object.cliente.pk if self.object.cliente else 'N/A'})"
            )
    
        # 5.1. Lógica de notificaciones para apertura con Transferencia/Tarjeta
        # ✅ NUEVO FLUJO: NO se crean notificaciones automáticas
        # Las notificaciones se crearán solo cuando se suba el comprobante
        modo_pago = form.cleaned_data.get('modo_pago_apertura', 'EFE')
        cantidad_apertura = form.cleaned_data.get('cantidad_apertura', Decimal('0.00'))
        
        if modo_pago == 'CRE':
            # Para crédito: estado EN_CONFIRMACION y cantidad_apertura = 0
            self.object.estado_confirmacion = 'EN_CONFIRMACION'
            self.object.cantidad_apertura = Decimal('0.00')
            self.object.save(update_fields=['estado_confirmacion', 'cantidad_apertura'])
        elif cantidad_apertura > 0 and modo_pago in ['TRN', 'TAR', 'DEP']:
            # Cambiar estado a "En confirmación"
            self.object.estado_confirmacion = 'EN_CONFIRMACION'
            self.object.save(update_fields=['estado_confirmacion'])
        elif cantidad_apertura > 0 and modo_pago == 'EFE':
            # Si es efectivo, se marca como completado automáticamente
            self.object.estado_confirmacion = 'COMPLETADO'
            self.object.save(update_fields=['estado_confirmacion'])
            
            # Crear notificación para el VENDEDOR (si existe)
            if self.object.vendedor:
                mensaje_vendedor_apertura = f"Apertura registrada y confirmada en tu venta #{self.object.pk}: ${cantidad_apertura:,.2f} (Efectivo) - Cliente: {self.object.cliente.nombre_completo_display}"
                Notificacion.objects.create(
                    usuario=self.object.vendedor,
                    tipo='APERTURA',
                    mensaje=mensaje_vendedor_apertura,
                    venta=self.object,
                    confirmado=True
                )
    
        messages.success(self.request, "Venta creada exitosamente. ¡No olvides gestionar la logística!")
        
        # 6. Retorna la respuesta de redirección usando la URL de éxito
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        # Redirección correcta a la vista de detalle (AHORA CON SLUG)
        return reverse_lazy('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe})


class ClienteKilometrosResumenView(LoginRequiredMixin, View):
    """Devuelve el resumen de Kilómetros Movums del cliente para el formulario de ventas."""

    def get(self, request, cliente_id, *args, **kwargs):
        try:
            cliente = get_object_or_404(Cliente, pk=cliente_id)
            resumen = KilometrosService.resumen_cliente(cliente)
        except Exception as e:
            logger.error(f"Error al obtener resumen de kilómetros para cliente {cliente_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': 'Error al obtener los datos de Kilómetros.'
            }, status=500)

        if not resumen:
            return JsonResponse({
                'success': False,
                'message': 'No se encontraron datos de Kilómetros para este cliente.'
            }, status=404)

        def decimal_to_str(value):
            if value is None:
                return "0.00"
            return format(value, '.2f')

        data = {
            'cliente': cliente.nombre_completo_display,
            'participa': resumen.get('participa', False),
            'disponible': decimal_to_str(resumen.get('disponible')),
            'valor_equivalente': decimal_to_str(resumen.get('valor_equivalente')),
            'total_acumulado': decimal_to_str(resumen.get('total_acumulado')),
            'ultima_fecha': resumen.get('ultima_fecha').isoformat() if resumen.get('ultima_fecha') else None,
        }
        return JsonResponse({'success': True, 'data': data})

class VentaViajeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = VentaViaje
    form_class = VentaViajeForm
    template_name = 'ventas/venta_form.html' # Usar el template de formulario si es UpdateView

    def test_func(self):
        # Solo el vendedor que creó la venta o el JEFE pueden editarla. CONTADOR solo lectura.
        venta = self.get_object()
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        if user_rol == 'CONTADOR':
            return False
        return venta.vendedor == self.request.user or user_rol == 'JEFE'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs

    def handle_no_permission(self):
        venta = self.get_object()
        messages.error(self.request, "No tienes permiso para editar esta venta.")
        # Se asegura de usar 'detalle_venta' para la redirección de error (AHORA CON SLUG)
        return HttpResponseRedirect(reverse_lazy('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cliente = self.object.cliente if self.object else None
        context['cliente_preseleccionado'] = cliente
        if cliente:
            context['kilometros_cliente'] = KilometrosService.resumen_cliente(cliente)
        context['kilometros_meta'] = {
            'valor_por_km': KilometrosService.VALOR_PESO_POR_KM,
            'km_por_peso': KilometrosService.KM_POR_PESO,
            'max_porcentaje': KilometrosService.MAX_PORCENTAJE_REDENCION * 100,
        }
        return context

    def form_valid(self, form):
        """
        Maneja la validación del formulario y actualiza el costo total
        incluyendo el costo de modificación si se proporciona.
        """
        # Obtener valores anteriores ANTES de guardar
        venta_anterior = VentaViaje.objects.get(pk=form.instance.pk)
        aplica_descuento_anterior = venta_anterior.aplica_descuento_kilometros
        descuento_anterior = venta_anterior.descuento_kilometros_mxn or Decimal('0.00')
        
        # Obtener el costo de modificación del formulario
        costo_modificacion = form.cleaned_data.get('costo_modificacion', Decimal('0.00')) or Decimal('0.00')
        previo_modificacion = form.instance.costo_modificacion or Decimal('0.00')
        
        # Guardar la instancia
        self.object = form.save()
        
        # Obtener valores nuevos DESPUÉS de guardar
        aplica_descuento_nuevo = self.object.aplica_descuento_kilometros
        descuento_nuevo = self.object.descuento_kilometros_mxn or Decimal('0.00')
        
        mensaje = "Venta actualizada correctamente."
        if costo_modificacion > 0:
            total_mod = previo_modificacion + costo_modificacion
            self.object.costo_modificacion = total_mod
            self.object.save(update_fields=['costo_modificacion'])
            mensaje = (
                f"Venta actualizada correctamente. "
                f"Costo adicional por modificación: ${costo_modificacion:,.2f}. "
                f"Total acumulado en modificaciones: ${total_mod:,.2f}."
            )
        else:
            if self.object.costo_modificacion != previo_modificacion:
                self.object.costo_modificacion = previo_modificacion
                self.object.save(update_fields=['costo_modificacion'])
        
        # Manejar cambios en descuento de kilómetros
        if self.object.cliente and self.object.cliente.participa_kilometros:
            try:
                # Si se aplicó descuento por primera vez o aumentó el descuento
                if aplica_descuento_nuevo and descuento_nuevo > 0:
                    if not aplica_descuento_anterior:
                        # Primera vez que se aplica descuento
                        km_a_redimir = (descuento_nuevo / KilometrosService.VALOR_PESO_POR_KM).quantize(Decimal('0.01'))
                        if km_a_redimir > 0:
                            registro_redencion = KilometrosService.redimir(
                                cliente=self.object.cliente,
                                kilometros=km_a_redimir,
                                venta=self.object,
                                descripcion=f"Redención aplicada a venta #{self.object.pk}: ${descuento_nuevo:,.2f} MXN"
                            )
                            if registro_redencion:
                                logger.info(f"✅ Kilómetros redimidos en actualización de venta {self.object.pk}: {km_a_redimir} km")
                    elif descuento_nuevo != descuento_anterior:
                        # El descuento cambió
                        diferencia = descuento_nuevo - descuento_anterior
                        if diferencia > 0:
                            # Descuento aumentó, redimir kilómetros adicionales
                            km_diferencia = (diferencia / KilometrosService.VALOR_PESO_POR_KM).quantize(Decimal('0.01'))
                            if km_diferencia > 0:
                                registro_redencion = KilometrosService.redimir(
                                    cliente=self.object.cliente,
                                    kilometros=km_diferencia,
                                    venta=self.object,
                                    descripcion=f"Redención adicional aplicada a venta #{self.object.pk}: ${diferencia:,.2f} MXN"
                                )
                                if registro_redencion:
                                    logger.info(f"✅ Kilómetros adicionales redimidos en actualización de venta {self.object.pk}: {km_diferencia} km")
                        # Si diferencia < 0, no podemos "devolver" kilómetros ya redimidos
            except Exception:
                logger.exception("❌ Error procesando redención de kilómetros en actualización de venta %s", self.object.pk)
        
        # Manejar cambios en promociones con bonos de kilómetros
        if self.object.cliente and self.object.cliente.participa_kilometros:
            try:
                # Obtener promociones anteriores (con bonos de kilómetros)
                promociones_anteriores = {
                    vpa.promocion_id: vpa.km_bono 
                    for vpa in venta_anterior.promociones_aplicadas.filter(km_bono__gt=0)
                }
                
                # Obtener promociones nuevas (con bonos de kilómetros)
                promociones_nuevas = {}
                promociones_aplicadas_actuales_qs = self.object.promociones_aplicadas.filter(km_bono__gt=0)
                promociones_aplicadas_actuales_dict = {vpa.promocion_id: vpa for vpa in promociones_aplicadas_actuales_qs}
                for vpa in promociones_aplicadas_actuales_qs:
                    promociones_nuevas[vpa.promocion_id] = vpa.km_bono
                
                # Identificar promociones agregadas, eliminadas y modificadas
                promociones_agregadas = set(promociones_nuevas.keys()) - set(promociones_anteriores.keys())
                promociones_eliminadas = set(promociones_anteriores.keys()) - set(promociones_nuevas.keys())
                promociones_modificadas = {
                    promo_id: (promociones_anteriores[promo_id], promociones_nuevas[promo_id])
                    for promo_id in set(promociones_anteriores.keys()) & set(promociones_nuevas.keys())
                    if promociones_anteriores[promo_id] != promociones_nuevas[promo_id]
                }
                
                # Acumular bonos de promociones nuevas
                for promo_id in promociones_agregadas:
                    vpa = promociones_aplicadas_actuales_dict.get(promo_id)
                    if vpa and vpa.km_bono > 0:
                        registro_bono = KilometrosService.acumular_bono_promocion(
                            cliente=self.object.cliente,
                            kilometros=vpa.km_bono,
                            venta=self.object,
                            promocion=vpa.promocion,
                            descripcion=f"Bono de promoción agregado: {vpa.nombre_promocion}"
                        )
                        if registro_bono:
                            logger.info(
                                f"✅ Bono de promoción acumulado en actualización de venta {self.object.pk}: "
                                f"{vpa.km_bono} km ({vpa.nombre_promocion}, Cliente: {self.object.cliente.pk})"
                            )
                
                # Revertir bonos de promociones eliminadas
                for promo_id in promociones_eliminadas:
                    km_bono_anterior = promociones_anteriores[promo_id]
                    if km_bono_anterior > 0:
                        # Buscar el registro original en HistorialKilometros para obtener la promoción
                        from crm.models import HistorialKilometros
                        movimiento_original = HistorialKilometros.objects.filter(
                            venta=self.object,
                            tipo_evento='BONO_PROMOCION',
                            kilometros=km_bono_anterior
                        ).first()
                        
                        promocion_obj = None
                        if movimiento_original and 'promoción' in movimiento_original.descripcion.lower():
                            # Intentar obtener la promoción desde el nombre en la descripción
                            try:
                                from crm.models import PromocionKilometros
                                nombre_promo = movimiento_original.descripcion.split(':')[-1].strip()
                                promocion_obj = PromocionKilometros.objects.filter(nombre=nombre_promo).first()
                            except:
                                pass
                        
                        registro_reversion = KilometrosService.revertir_bono_promocion(
                            cliente=self.object.cliente,
                            kilometros=km_bono_anterior,
                            venta=self.object,
                            promocion=promocion_obj,
                            descripcion=f"Reversión de bono de promoción eliminada: {km_bono_anterior} km"
                        )
                        if registro_reversion:
                            logger.info(
                                f"✅ Bono de promoción revertido en actualización de venta {self.object.pk}: "
                                f"{km_bono_anterior} km (Cliente: {self.object.cliente.pk})"
                            )
                
                # Ajustar bonos de promociones modificadas
                for promo_id, (km_anterior, km_nuevo) in promociones_modificadas.items():
                    vpa = promociones_aplicadas_actuales_dict.get(promo_id)
                    diferencia = km_nuevo - km_anterior
                    if diferencia > 0:
                        # El bono aumentó, acumular la diferencia
                        registro_bono = KilometrosService.acumular_bono_promocion(
                            cliente=self.object.cliente,
                            kilometros=diferencia,
                            venta=self.object,
                            promocion=vpa.promocion if vpa else None,
                            descripcion=f"Ajuste de bono de promoción: {vpa.nombre_promocion if vpa else 'Promoción'} (+{diferencia} km)"
                        )
                        if registro_bono:
                            logger.info(
                                f"✅ Bono de promoción ajustado (aumento) en venta {self.object.pk}: "
                                f"+{diferencia} km (Cliente: {self.object.cliente.pk})"
                            )
                    elif diferencia < 0:
                        # El bono disminuyó, revertir la diferencia
                        registro_reversion = KilometrosService.revertir_bono_promocion(
                            cliente=self.object.cliente,
                            kilometros=abs(diferencia),
                            venta=self.object,
                            promocion=vpa.promocion if vpa else None,
                            descripcion=f"Ajuste de bono de promoción: {vpa.nombre_promocion if vpa else 'Promoción'} (-{abs(diferencia)} km)"
                        )
                        if registro_reversion:
                            logger.info(
                                f"✅ Bono de promoción ajustado (disminución) en venta {self.object.pk}: "
                                f"-{abs(diferencia)} km (Cliente: {self.object.cliente.pk})"
                            )
            except Exception:
                logger.exception("❌ Error procesando bonos de promociones en actualización de venta %s", self.object.pk)
        
        self.object.actualizar_estado_financiero()
        messages.success(self.request, mensaje)
        return super().form_valid(form)
    
    def get_success_url(self):
        # Se asegura de usar 'detalle_venta' para la redirección de éxito (AHORA CON SLUG)
        return reverse_lazy('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe})


class CancelarVentaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Vista para cancelar una venta cambiando su estado a CANCELADA."""
    
    def test_func(self):
        """Solo el vendedor que creó la venta o el JEFE pueden cancelarla. CONTADOR solo lectura."""
        venta = get_object_or_404(VentaViaje, pk=self.kwargs['pk'])
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        if user_rol == 'CONTADOR':
            return False
        return venta.vendedor == self.request.user or user_rol == 'JEFE'
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para cancelar esta venta.")
        return redirect('lista_ventas')
    
    def post(self, request, *args, **kwargs):
        venta = get_object_or_404(VentaViaje, pk=self.kwargs['pk'])
        
        # Verificar si la venta ya estaba cancelada
        ya_estaba_cancelada = venta.estado == 'CANCELADA'
        
        venta.estado = 'CANCELADA'
        venta.save(update_fields=['estado'])
        
        # Revertir kilómetros Movums si la venta no estaba previamente cancelada
        if not ya_estaba_cancelada:
            try:
                resultado = KilometrosService.revertir_por_cancelacion(venta)
                if resultado['revertidos'] > 0:
                    mensaje_reversion = f"La venta #{venta.pk} ha sido cancelada exitosamente."
                    detalles = []
                    if resultado['km_totales'] > 0:
                        detalles.append(f"Se revirtieron {resultado['km_totales']:,.2f} km acumulados")
                    if resultado.get('km_devueltos', 0) > 0:
                        detalles.append(f"Se devolvieron {resultado['km_devueltos']:,.2f} km redimidos")
                    
                    if detalles:
                        mensaje_reversion += " " + " y ".join(detalles) + "."
                    
                    logger.info(
                        f"✅ Kilómetros procesados por cancelación de venta {venta.pk}: "
                        f"{resultado['km_totales']:,.2f} km revertidos, "
                        f"{resultado.get('km_devueltos', 0):,.2f} km devueltos "
                        f"({resultado['revertidos']} movimientos)"
                    )
                    messages.success(request, mensaje_reversion)
                else:
                    messages.success(request, f"La venta #{venta.pk} ha sido cancelada exitosamente.")
            except Exception as e:
                logger.exception(f"❌ Error al revertir kilómetros por cancelación de venta {venta.pk}: {e}")
                messages.warning(
                    request, 
                    f"La venta #{venta.pk} ha sido cancelada, pero hubo un error al revertir los kilómetros Movums. "
                    "Por favor, verifica manualmente el historial de kilómetros del cliente."
                )
        else:
            messages.info(request, f"La venta #{venta.pk} ya estaba cancelada.")
        
        # Crear notificación para JEFE sobre la cancelación
        jefes = User.objects.filter(perfil__rol='JEFE')
        mensaje = f"La venta #{venta.pk} - Cliente: {venta.cliente.nombre_completo_display} ha sido cancelada por {request.user.username}"
        
        for jefe in jefes:
            Notificacion.objects.create(
                usuario=jefe,
                tipo='CANCELACION',
                mensaje=mensaje,
                venta=venta,
                confirmado=False
            )
        
        return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)


# ------------------- 5. GESTIÓN DE ABONOS (REMOVIDA/INTEGRADA) -------------------
# NOTA: La vista AbonoPagoCreateView ha sido eliminada. La funcionalidad se maneja
# directamente en el método post de VentaViajeDetailView (Sección 3) para un
# flujo de trabajo más limpio con formularios anidados.

# ------------------- 6. GESTIÓN DE LOGÍSTICA (STANDALONE) -------------------

class LogisticaUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Logistica
    form_class = LogisticaForm
    template_name = 'ventas/logistica_form.html'
    # Espera un PK de la VentaViaje en la URL, no del objeto Logistica
    pk_url_kwarg = 'venta_pk' 

    def get_object(self, queryset=None):
        # Busca el objeto Logistica relacionado con el PK de la VentaViaje
        return get_object_or_404(Logistica, venta__pk=self.kwargs['venta_pk'])

    def test_func(self):
        # Solo JEFES o el VENDEDOR de la venta pueden acceder. CONTADOR solo lectura.
        venta = self.get_object().venta
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        
        return user_rol == 'JEFE' or venta.vendedor == self.request.user

    def get_success_url(self):
        messages.success(self.request, "Logística actualizada correctamente.")
        venta = self.object.venta
        # CORRECCIÓN: Ahora incluye el slug para la redirección de éxito.
        # Redirige al detalle de la venta, con el tab de Logística activo
        return reverse_lazy('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=logistica'


# ------------------- 7. ALERTA LOGÍSTICA PENDIENTE (INNOVACIÓN 3) -------------------

class LogisticaPendienteView(LoginRequiredMixin, ListView):
    model = VentaViaje
    template_name = 'ventas/logistica_pendiente.html'
    context_object_name = 'ventas'

    STATUS_META = {
        'pending': ('danger', 'Pendiente'),
        'ready': ('warning text-dark', 'Listo para pagar'),
        'paid': ('success', 'Pagado'),
    }

    ESTADO_META = {
        'pendiente': ('danger', 'Servicios pendientes'),
        'ready': ('warning text-dark', 'Fondos disponibles'),
        'completo': ('success', 'Servicios cubiertos'),
        'sin_servicios': ('secondary', 'Sin servicios planificados'),
    }

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)

        self.user_role = get_user_role(request.user)
        if self.user_role in ('JEFE', 'CONTADOR', 'VENDEDOR'):
            return super().dispatch(request, *args, **kwargs)

        messages.error(request, "No tienes permiso para acceder al tablero de logística.")
        return redirect(reverse('dashboard'))

    def get_queryset(self):
        queryset = (
            self.model.objects
            .filter(servicios_logisticos__isnull=False)
            .select_related('cliente', 'vendedor')
            .prefetch_related('servicios_logisticos')
            .distinct()
            .order_by('fecha_inicio_viaje')
        )

        if self.user_role == 'VENDEDOR':
            queryset = queryset.filter(vendedor=self.request.user)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ventas = context.get('ventas') or []

        tablero = []
        stats = Counter({'pending': 0, 'ready': 0, 'paid': 0})

        for venta in ventas:
            card = build_logistica_card(venta)
            tablero.append(card)
            for servicio in card['servicios']:
                stats[servicio['status']] += 1

        context.update({
            'user_rol': self.user_role,
            'tablero_logistica': tablero,
            'stats_servicios': stats,
            'mostrando_propias': self.user_role == 'VENDEDOR',
            'puede_ver_todos': self.user_role in ('JEFE', 'CONTADOR'),
        })
        return context

# ------------------- 8. REPORTE FINANCIERO -------------------

class ReporteFinancieroView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = 'ventas/reporte_financiero.html'

    def test_func(self):
        # Solo JEFES o CONTADORES pueden ver esta vista.
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol in ['JEFE', 'CONTADOR']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # --- 1. CÁLCULOS PRINCIPALES DE AGREGACIÓN ---
        
        # 1.1 Ingreso Bruto Total (Total Venta)
        total_ventas = VentaViaje.objects.aggregate(
            total_ventas_sum=Sum('costo_venta_final')
        ).get('total_ventas_sum') or Decimal('0.00')

        # 1.2 Total Pagos Recibidos (Total Pagado = Abonos + Montos de Apertura)
        total_abonos = AbonoPago.objects.aggregate(
            total_abonos_sum=Sum('monto')
        ).get('total_abonos_sum') or Decimal('0.00')
        
        total_apertura = VentaViaje.objects.aggregate(
            total_apertura_sum=Sum('cantidad_apertura')
        ).get('total_apertura_sum') or Decimal('0.00')
        
        total_pagado = total_abonos + total_apertura

        # 1.3 Saldo Pendiente (CxC)
        saldo_pendiente = total_ventas - total_pagado
        
        # Aseguramos que los valores sean Decimal
        total_ventas = Decimal(total_ventas)
        total_pagado = Decimal(total_pagado)
        saldo_pendiente = Decimal(saldo_pendiente)

        # --- 2. INYECCIÓN DE TOTALES EN EL CONTEXTO ---
        context['total_ventas'] = total_ventas
        context['total_pagado'] = total_pagado
        context['saldo_pendiente'] = saldo_pendiente

        # --- 3. CÁLCULO DE CONSISTENCIA ---
        
        # Pagos Esperados: (Total Venta - Saldo Pendiente)
        pagos_esperados = total_ventas - saldo_pendiente
        
        # Diferencia: Debe ser 0 si el cálculo es consistente.
        diferencia = total_pagado - pagos_esperados
        
        # 3.1 Diccionario para la sección de Consistencia
        context['consistencia'] = {
            'real': total_pagado, 
            'esperado': pagos_esperados, 
            'diferencia': diferencia,
            # Usamos una tolerancia pequeña para los decimales
            'es_consistente': abs(diferencia) < Decimal('0.01') 
        }
        
        # 4. Lista de usuarios para el filtro del historial
        context['usuarios'] = User.objects.filter(is_active=True).order_by('username')
        
        # 5. Últimos 5 movimientos para la vista previa
        try:
            from auditoria.models import HistorialMovimiento
            
            ultimos_movimientos = HistorialMovimiento.objects.select_related('usuario', 'content_type').order_by('-fecha_hora')[:5]
            
            # Preparar los movimientos con enlaces
            movimientos_preview = []
            for mov in ultimos_movimientos:
                enlace_url = None
                enlace_texto = None
                
                if mov.content_type and mov.object_id:
                    try:
                        obj = mov.content_type.get_object_for_this_type(pk=mov.object_id)
                        # Si el objeto es un AbonoPago, obtener la venta relacionada
                        if isinstance(obj, AbonoPago):
                            venta = obj.venta
                            enlace_url = reverse('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=abonos'
                            enlace_texto = f"Ver Venta #{venta.pk}"
                        elif isinstance(obj, VentaViaje):
                            enlace_url = reverse('detalle_venta', kwargs={'pk': obj.pk, 'slug': obj.slug_safe})
                            # Si es un movimiento de abono, agregar parámetro para ir directo a la pestaña de abonos
                            if mov.tipo_evento in ['ABONO_REGISTRADO', 'ABONO_CONFIRMADO', 'ABONO_ELIMINADO']:
                                enlace_url += '?tab=abonos'
                            enlace_texto = f"Ver Venta #{obj.pk}"
                        elif isinstance(obj, Cotizacion):
                            enlace_url = reverse('detalle_cotizacion', kwargs={'slug': obj.slug})
                            enlace_texto = "Ver Cotización"
                        elif isinstance(obj, Cliente):
                            enlace_url = reverse('detalle_cliente', kwargs={'pk': obj.pk})
                            enlace_texto = "Ver Cliente"
                    except Exception as e:
                        pass
                
                movimientos_preview.append({
                    'movimiento': mov,
                    'enlace_url': enlace_url,
                    'enlace_texto': enlace_texto,
                })
            
            context['ultimos_movimientos'] = movimientos_preview
        except ImportError:
            context['ultimos_movimientos'] = []
        
        return context

# ------------------- 9. GENERACIÓN DE PDF (INNOVACIÓN 4) -------------------

class ComprobanteAbonoPDFView(LoginRequiredMixin, DetailView):
    model = VentaViaje
    
    def get(self, request, *args, **kwargs):
        if not WEASYPRINT_AVAILABLE:
             # Si WeasyPrint no está cargado, devuelve un error 503 o un mensaje simple
             return HttpResponse("Error en la generación de PDF. Faltan dependencias (GTK3).", status=503)

        # Usamos el mismo método get_object que maneja PK y SLUG
        self.object = self.get_object() 
        venta = self.object
        
        # Calcular totales para el PDF (usar la propiedad total_pagado que ya incluye apertura confirmada)
        total_pagado = venta.total_pagado
        saldo_restante = venta.saldo_restante
        
        # Calcular descuentos y totales igual que en VentaViajeDetailView
        descuento_km = venta.descuento_kilometros_mxn or Decimal('0.00')
        descuento_promo = venta.descuento_promociones_mxn or Decimal('0.00')
        total_descuentos = descuento_km + descuento_promo
        costo_base = (venta.costo_venta_final or Decimal('0.00')) + (venta.costo_modificacion or Decimal('0.00'))
        total_final = costo_base - total_descuentos
        
        # Preparar ruta absoluta file:// para el membrete (WeasyPrint necesita URL absoluta)
        membrete_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'membrete_movums.jpg')
        membrete_url = None
        if os.path.exists(membrete_path):
            # Crear URL file:// absoluta para WeasyPrint
            membrete_abs_path = os.path.abspath(membrete_path)
            # En Windows, necesitamos ajustar el formato de la ruta
            if os.name == 'nt':
                membrete_url = f"file:///{membrete_abs_path.replace(os.sep, '/')}"
            else:
                membrete_url = f"file://{membrete_abs_path}"
        
        # Obtener el contexto para la plantilla HTML
        context = {
            'venta': venta,
            'now': datetime.datetime.now(),
            'total_pagado': total_pagado,
            'saldo_restante': saldo_restante,
            # Incluir TODOS los abonos para el detalle en el PDF (mostrar todos, incluso pendientes)
            'abonos': venta.abonos.all().order_by('fecha_pago'),
            'membrete_url': membrete_url,  # URL absoluta file:// para WeasyPrint
            'STATIC_URL': settings.STATIC_URL,
            # Información financiera completa igual que en detalle de venta
            'total_descuentos': total_descuentos,
            'costo_base': costo_base,
            'total_final': total_final,
            'descuento_km': descuento_km,
            'descuento_promo': descuento_promo,
        }

        # 1. Renderizar la plantilla HTML
        html_string = render_to_string('ventas/comprobante_abonos_pdf.html', context, request=request)
        
        # 2. Generar el PDF con WeasyPrint
        # Obtener rutas de archivos estáticos para recursos como imágenes
        static_dir = os.path.join(settings.BASE_DIR, 'static')
        static_dir_abs = os.path.abspath(static_dir)
        base_url = f"file://{static_dir_abs}/"
        
        html = HTML(string=html_string, base_url=base_url)
        pdf_file = html.write_pdf(stylesheets=[]) # Dejar la lista vacía a menos que se necesite un CSS específico

        # 3. Preparar la respuesta HTTP
        response = HttpResponse(pdf_file, content_type='application/pdf')
        filename = f"Comprobante_Venta_{venta.pk}.pdf"
        # Usar 'inline' si se quiere mostrar en el navegador o 'attachment' para forzar la descarga
        response['Content-Disposition'] = f'attachment; filename="{filename}"' 
        
        return response
    
# ------------------- 10. NUEVA VISTA PARA EL CONTRATO (LA QUE NECESITAS) -------------------
class ContratoVentaPDFView(LoginRequiredMixin, DetailView):
    """
    Vista para generar el Contrato de Venta en formato DOCX.
    Utiliza python-docx para generar un documento Word editable.
    """
    model = VentaViaje
    
    def get(self, request, *args, **kwargs):
        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Inches
            from docx.oxml.ns import qn
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError:
            return HttpResponse("Error: python-docx no está instalado. Ejecuta: pip install python-docx", status=500)

        self.object = self.get_object() 
        venta = self.object
        cliente = venta.cliente
        
        # Calcular saldo pendiente (asegurarse de que no sea negativo)
        from decimal import Decimal
        saldo_pendiente = max(Decimal('0.00'), venta.costo_total_con_modificacion - venta.total_pagado)
        
        # Usar plantilla con membrete si existe
        template_path = os.path.join(settings.BASE_DIR, 'static', 'docx', 'membrete.docx')
        if os.path.exists(template_path):
            doc = Document(template_path)
        else:
            doc = Document()
        
        # Configurar fuente predeterminada Arial 12
        style = doc.styles['Normal']
        style.font.name = 'Arial'
        style.font.size = Pt(12)
        style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
        
        MOVUMS_BLUE = RGBColor(0, 74, 142)  # #004a8e
        TEXT_COLOR = RGBColor(47, 47, 47)  # #2f2f2f
        
        def set_run_font(run, size=12, bold=False, color=TEXT_COLOR):
            run.font.name = 'Arial'
            run.font.size = Pt(size)
            run.bold = bold
            run.font.color.rgb = color
        
        def add_paragraph(doc_obj, text='', size=12, bold=False, color=TEXT_COLOR, space_before=0, space_after=0, alignment=None):
            paragraph = doc_obj.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(space_before)
            paragraph.paragraph_format.space_after = Pt(space_after)
            if alignment:
                paragraph.alignment = alignment
            if text:
                run = paragraph.add_run(text)
                set_run_font(run, size=size, bold=bold, color=color)
            return paragraph
        
        def format_date(value):
            if not value:
                return '-'
            try:
                if isinstance(value, datetime.date):
                    return value.strftime('%d/%m/%Y')
                return str(value)
            except:
                return '-'
        
        def format_currency(value):
            if value in (None, '', 0):
                return '0.00'
            try:
                number = Decimal(str(value).replace(',', ''))
            except:
                return str(value)
            return f"{number:,.2f}"
        
        # Título principal
        titulo = add_paragraph(doc, 'CONTRATO DE SERVICIOS TURÍSTICOS', size=18, bold=True, color=MOVUMS_BLUE, space_after=10, alignment=WD_ALIGN_PARAGRAPH.CENTER)
        
        # Sección 1: DATOS GENERALES DEL CLIENTE
        add_paragraph(doc, '1. DATOS GENERALES DEL CLIENTE', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        # Nombre completo
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Nombre completo: ')
        set_run_font(run1, size=12, bold=True)
        if cliente.nombre_completo_display:
            run2 = p.add_run(cliente.nombre_completo_display)
            set_run_font(run2, size=12)
        else:
            run2 = p.add_run('________________________')
            set_run_font(run2, size=12)
            run2.font.underline = True
        
        # Teléfono
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Teléfono: ')
        set_run_font(run1, size=12, bold=True)
        if cliente.telefono:
            run2 = p.add_run(cliente.telefono)
            set_run_font(run2, size=12)
        else:
            run2 = p.add_run('________________________')
            set_run_font(run2, size=12)
            run2.font.underline = True
        
        # Email
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Correo electrónico: ')
        set_run_font(run1, size=12, bold=True)
        if cliente.email:
            run2 = p.add_run(cliente.email)
            set_run_font(run2, size=12)
        else:
            run2 = p.add_run('________________________')
            set_run_font(run2, size=12)
            run2.font.underline = True
        
        # Identificación
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Identificación oficial: ')
        set_run_font(run1, size=12, bold=True)
        if cliente.documento_identificacion:
            run2 = p.add_run(cliente.documento_identificacion)
            set_run_font(run2, size=12)
        else:
            run2 = p.add_run('________________________')
            set_run_font(run2, size=12)
            run2.font.underline = True
        run3 = p.add_run('  INE / Pasaporte / Otro: ')
        set_run_font(run3, size=12)
        # El tipo de identificación siempre va con línea porque no lo tenemos en el sistema
        run4 = p.add_run('________')
        set_run_font(run4, size=12)
        run4.font.underline = True
        
        # Acompañantes
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Acompañantes:')
        set_run_font(run1, size=12, bold=True)
        
        # Procesar acompañantes: quitar saltos de línea y separar con comas
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(4)
        run1 = p.add_run('• Nombre(s) y edad(es): ')
        set_run_font(run1, size=12, bold=True)
        if venta.pasajeros:
            # Limpiar el texto: quitar saltos de línea y espacios extra, separar con comas
            pasajeros_texto = venta.pasajeros.replace('\n', ', ').replace('\r', ', ')
            # Limpiar espacios múltiples y comas múltiples
            import re
            pasajeros_texto = re.sub(r'\s+', ' ', pasajeros_texto)
            pasajeros_texto = re.sub(r',\s*,', ',', pasajeros_texto)
            pasajeros_texto = pasajeros_texto.strip().rstrip(',')
            run2 = p.add_run(pasajeros_texto)
            set_run_font(run2, size=12)
        else:
            run2 = p.add_run('________________________')
            set_run_font(run2, size=12)
            run2.font.underline = True
        
        # Sección 2: DATOS DEL SERVICIO TURÍSTICO CONTRATADO
        add_paragraph(doc, '2. DATOS DEL SERVICIO TURÍSTICO CONTRATADO', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        campos_servicio = [
            ('Nombre del Paquete:', ''),
            ('Destino(s):', ''),
            ('Fecha de inicio:', format_date(venta.fecha_inicio_viaje) if venta.fecha_inicio_viaje else '//2025'),
            ('Fecha de término:', format_date(venta.fecha_fin_viaje) if venta.fecha_fin_viaje else '//2025'),
            ('Número total de viajeros:', ''),
        ]
        
        for label, value in campos_servicio:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            run1 = p.add_run(f'{label} ')
            set_run_font(run1, size=12, bold=True)
            if value:
                run2 = p.add_run(value)
                set_run_font(run2, size=12)
            else:
                run2 = p.add_run('________________________')
                set_run_font(run2, size=12)
                run2.font.underline = True
        
        # Sección 3: TRANSPORTE
        add_paragraph(doc, '3. TRANSPORTE', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Tipo de transporte: ')
        set_run_font(run1, size=12, bold=True)
        run2 = p.add_run('________________________')
        set_run_font(run2, size=12)
        run2.font.underline = True
        run3 = p.add_run('  Avión / Autobús / Transporte terrestre privado / Otro')
        set_run_font(run3, size=12)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Proveedor: ')
        set_run_font(run1, size=12, bold=True)
        if venta.proveedor:
            run2 = p.add_run(venta.proveedor.nombre)
            set_run_font(run2, size=12)
        else:
            run2 = p.add_run('________________________')
            set_run_font(run2, size=12)
            run2.font.underline = True
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Número de viaje o clave de reservación: ')
        set_run_font(run1, size=12, bold=True)
        run2 = p.add_run('________________________')
        set_run_font(run2, size=12)
        run2.font.underline = True
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Incluye equipaje?: ')
        set_run_font(run1, size=12, bold=True)
        run2 = p.add_run('________________________')
        set_run_font(run2, size=12)
        run2.font.underline = True
        run3 = p.add_run('  Sí / No / Detallar: ')
        set_run_font(run3, size=12)
        run4 = p.add_run('________________________')
        set_run_font(run4, size=12)
        run4.font.underline = True
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('(La AGENCIA no garantiza horarios o cambios operados por el transportista.)')
        set_run_font(run, size=11, color=RGBColor(102, 102, 102))
        run.italic = True
        
        # Sección 4: HOSPEDAJE
        add_paragraph(doc, '4. HOSPEDAJE', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        campos_hospedaje = [
            ('Hotel:', ''),
            ('Categoría:', ''),
            ('Dirección:', ''),
            ('Noches incluidas:', ''),
            ('Tipo de habitación:', ''),
        ]
        
        for label, value in campos_hospedaje:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(6)
            run1 = p.add_run(f'{label} ')
            set_run_font(run1, size=12, bold=True)
            run2 = p.add_run('________________________')
            set_run_font(run2, size=12)
            run2.font.underline = True
        
        # Plan de alimentos
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Plan de alimentos:')
        set_run_font(run1, size=12, bold=True)
        
        planes = ['Sólo hospedaje', 'Desayuno', 'Media pensión', 'Todo incluido', 'Otro:']
        for plan in planes:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            run1 = p.add_run('○ ')
            set_run_font(run1, size=12)
            run2 = p.add_run(plan)
            set_run_font(run2, size=12)
            if plan == 'Otro:':
                run3 = p.add_run(' ________________________')
                set_run_font(run3, size=12)
                run3.font.underline = True
        
        # Sección 5: SERVICIOS ADICIONALES INCLUIDOS
        add_paragraph(doc, '5. SERVICIOS ADICIONALES INCLUIDOS', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('(Marca los que apliquen)')
        set_run_font(run, size=11, color=RGBColor(102, 102, 102))
        run.italic = True
        
        servicios_adicionales = [
            'Traslado aeropuerto-hotel-aeropuerto',
            ('Tours o excursiones (describir):', True),
            'Coordinador o guía turístico',
            'Entradas o accesos',
            'Seguro de viajero nacional (si aplica)',
            ('Otros servicios incluidos:', True),
        ]
        
        for servicio in servicios_adicionales:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            run1 = p.add_run('☐ ')
            set_run_font(run1, size=12)
            if isinstance(servicio, tuple):
                run2 = p.add_run(servicio[0])
                set_run_font(run2, size=12)
                run3 = p.add_run(' ________________________')
                set_run_font(run3, size=12)
                run3.font.underline = True
            else:
                run2 = p.add_run(servicio)
                set_run_font(run2, size=12)
        
        # Sección 6: SERVICIOS NO INCLUIDOS
        doc.add_page_break()
        add_paragraph(doc, '6. SERVICIOS NO INCLUIDOS', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('(Para evitar reclamaciones)')
        set_run_font(run, size=11, color=RGBColor(102, 102, 102))
        run.italic = True
        
        servicios_no_incluidos = [
            'Impuestos locales, resort fees o cuotas gubernamentales',
            'Propinas',
            'Servicios no listados como incluidos',
            'Actividades opcionales',
            'Gastos personales',
            'Sobrepeso de equipaje',
            'Comidas no contempladas',
        ]
        
        for servicio in servicios_no_incluidos:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(f'• {servicio}')
            set_run_font(run, size=12)
        
        # Sección 7: PRECIO Y CONDICIONES ECONÓMICAS
        add_paragraph(doc, '7. PRECIO Y CONDICIONES ECONÓMICAS', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        # Precio total
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Precio total del paquete: ')
        set_run_font(run1, size=12, bold=True)
        if venta.tipo_viaje == 'INT':
            if venta.costo_total_con_modificacion_usd:
                run2 = p.add_run(f'USD ${format_currency(venta.costo_total_con_modificacion_usd)}')
                set_run_font(run2, size=12)
            else:
                run2 = p.add_run('USD $________________________')
                set_run_font(run2, size=12)
                run2.font.underline = True
        else:
            if venta.costo_total_con_modificacion:
                run2 = p.add_run(f'${format_currency(venta.costo_total_con_modificacion)} MXN')
                set_run_font(run2, size=12)
            else:
                run2 = p.add_run('$________________________ MXN')
                set_run_font(run2, size=12)
                run2.font.underline = True
        
        # Anticipo recibido
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Anticipo recibido: ')
        set_run_font(run1, size=12, bold=True)
        if venta.tipo_viaje == 'INT':
            if venta.cantidad_apertura_usd:
                run2 = p.add_run(f'USD ${format_currency(venta.cantidad_apertura_usd)}')
                set_run_font(run2, size=12)
            else:
                run2 = p.add_run('USD $________________________ MXN')
                set_run_font(run2, size=12)
                run2.font.underline = True
        else:
            if venta.cantidad_apertura:
                run2 = p.add_run(f'${format_currency(venta.cantidad_apertura)} MXN')
                set_run_font(run2, size=12)
            else:
                run2 = p.add_run('$________________________ MXN')
                set_run_font(run2, size=12)
                run2.font.underline = True
        
        # Saldo pendiente
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Saldo pendiente: ')
        set_run_font(run1, size=12, bold=True)
        if venta.tipo_viaje == 'INT':
            if venta.saldo_restante_usd:
                run2 = p.add_run(f'USD ${format_currency(venta.saldo_restante_usd)}')
                set_run_font(run2, size=12)
            else:
                run2 = p.add_run('USD $________________________ MXN')
                set_run_font(run2, size=12)
                run2.font.underline = True
        else:
            if saldo_pendiente:
                run2 = p.add_run(f'${format_currency(saldo_pendiente)} MXN')
                set_run_font(run2, size=12)
            else:
                run2 = p.add_run('$________________________ MXN')
                set_run_font(run2, size=12)
                run2.font.underline = True
        
        # Fecha límite de pago
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Fecha límite de pago total: ')
        set_run_font(run1, size=12, bold=True)
        run2 = p.add_run('________________________')
        set_run_font(run2, size=12)
        run2.font.underline = True
        if venta.fecha_vencimiento_pago:
            run3 = p.add_run(f' {format_date(venta.fecha_vencimiento_pago)}')
            set_run_font(run3, size=12)
        else:
            run3 = p.add_run(' //2025')
            set_run_font(run3, size=12)
        
        # Desglose de pagos
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.5)
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Desglose de pagos (si aplica):')
        set_run_font(run1, size=12, bold=True)
        
        for i in range(1, 4):
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(1.0)
            p.paragraph_format.space_after = Pt(4)
            run1 = p.add_run(f'Parcialidad {i}: $________________________  Fecha: ________________________ //2025')
            set_run_font(run1, size=12)
            # Subrayar espacios en blanco
            for run in p.runs:
                if '________________' in run.text:
                    run.font.underline = True
        
        # Sección 8: DOCUMENTACIÓN ENTREGADA AL CLIENTE
        doc.add_page_break()
        add_paragraph(doc, '8. DOCUMENTACIÓN ENTREGADA AL CLIENTE', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        documentacion = [
            'Contrato firmado',
            'Copia de esta caratula',
            'Itinerario preliminar',
            'Políticas del proveedor',
            'Comprobantes de pago',
            'Claves de reservación',
            'Información de contacto para emergencias',
        ]
        
        for doc_item in documentacion:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(f'☐ {doc_item}')
            set_run_font(run, size=12)
        
        # Sección 9: DECLARACIÓN DEL CLIENTE
        add_paragraph(doc, '9. DECLARACIÓN DEL CLIENTE', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('EL CLIENTE declara que:')
        set_run_font(run1, size=12, bold=True)
        
        declaraciones = [
            'Ha revisado y entendido toda la información contenida en este Anexo.',
            'Proporcionó datos veraces y completos.',
            'Acepta las condiciones del servicio, políticas de proveedores y cláusulas del contrato.',
        ]
        
        for decl in declaraciones:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(f'• {decl}')
            set_run_font(run, size=12)
        
        # Sección 10: TÉRMINOS Y CONDICIONES
        doc.add_page_break()
        add_paragraph(doc, '10. TÉRMINOS Y CONDICIONES', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=8)
        
        # Título del contrato
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(8)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run('CONTRATO DE MEDIACIÓN PARA LA PRESTACIÓN DE SERVICIOS TURÍSTICOS')
        set_run_font(run, size=12, bold=True)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        run = p.add_run('QUE CELEBRAN POR UNA PARTE LA AGENCIA DE VIAJES "GRUPO IMVED, S.A. DE C.V." ACTUANDO EN USO DE SU NOMBRE COMERCIAL MOVUMS THE TRAVEL STORE, EN ADELANTE DENOMINADA COMO "LA AGENCIA", Y POR LA OTRA EL (LA) C')
        set_run_font(run, size=12)
        run2 = p.add_run('________________________')
        set_run_font(run2, size=12)
        run2.font.underline = True
        run3 = p.add_run(' A QUIEN EN LO SUCESIVO SE LE DENOMINARÁ "EL CLIENTE", AL TENOR DE LAS SIGUIENTES DEFINICIONES, DECLARACIONES Y CLÁUSULAS:')
        set_run_font(run3, size=12)
        
        # GLOSARIO
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('GLOSARIO')
        set_run_font(run, size=12, bold=True)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run('Para efectos del presente contrato, se entiende por:')
        set_run_font(run, size=12)
        
        glosario_items = [
            'Agencia: Es el proveedor de servicios turísticos que intermedia, contrata u ofrece servicios o productos turístico nacionales, previo pago de un precio cierto y determinado.',
            'Cliente: Consumidor que contrata los servicios turísticos nacionales mediante el pago de un precio cierto y determinado.',
            'Paquete turístico: Integración de uno o más servicios turísticos en un solo producto, ofrecidos al Cliente y detallado en el Anexo del presente contrato.',
            'Servicio turístico: Prestación de carácter comercial en transporte nacional, hospedaje, alimentación, excursiones u otros servicios relacionados, detallados en el Anexo del presente contrato.',
            'Caratula: Documento que detalla servicios, fechas, precios y condiciones del servicio turístico contratado.',
        ]
        
        for item in glosario_items:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run1 = p.add_run('◆ ')
            set_run_font(run1, size=12)
            run2 = p.add_run(item)
            set_run_font(run2, size=12)
        
        # DECLARACIONES
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('DECLARACIONES')
        set_run_font(run, size=12, bold=True)
        
        # Declaración I - LA AGENCIA
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('I. Declara LA AGENCIA:')
        set_run_font(run, size=12, bold=True)
        
        declaraciones_agencia = [
            'Ser una persona moral legalmente constituida conforme a las leyes mexicanas.',
            'Ser un Prestador de Servicios Turísticos con Razón Social: GRUPO IMVED, S.A. de C.V.',
            'Ser la única propietaria de la marca MOVUMS THE TRAVEL STORE',
            'RFC GIM190722FS7 y domicilio ubicado en: Plaza Mora, Juárez Sur, 321, interior 18, Colonia Centro, Texcoco, Estado de México, C.P. 56100.',
            'Teléfono, correo electrónico y horario de atención al público: 59 59319954, 5951255279 ventas@movums.com, lunes a sábado de 09:00 a 18:00 horas.',
            'Contar con infraestructura, personal capacitado y experiencia suficiente para la prestación de los servicios turísticos contratados.',
            'Haber informado previamente al Cliente sobre los precios, tarifas, condiciones, características y costo total del servicio turístico contratado.',
        ]
        
        for item in declaraciones_agencia:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run1 = p.add_run('◆ ')
            set_run_font(run1, size=12)
            run2 = p.add_run(item)
            set_run_font(run2, size=12)
        
        # Declaración II - EL CLIENTE
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('II. Declara EL CLIENTE:')
        set_run_font(run, size=12, bold=True)
        
        declaraciones_cliente = [
            'Ser persona física/moral con capacidad legal y económica para obligarse en términos del presente contrato.',
            'En caso de persona moral: Ser una persona moral legalmente constituida conforme a las leyes mexicanas, conforme lo acredita con copia del instrumento número ____________, de fecha ___________, otorgado ante la Fe del Notario Público Número ____, de ____________, y que el(la) C. _________ __________________ en este acto interviene en su carácter de Representante Legal, calidad que acredita con copia del instrumento número _______, de fecha _________, otorgada ante la Fe del Notario Público número _______ del _________, facultad y calidad que no le han sido revocadas, modificadas o limitadas a la fecha de firma del presente contrato.',
            'Encontrarse inscrito en el Registro Federal de Contribuyentes con la clave que ha manifestado.',
            'Haber recibido previamente de LA AGENCIA información útil, precisa, veraz y detallada sobre los servicios objeto del presente contrato.',
            'Proporciona su nombre, domicilio, número telefónico y correo electrónico, tal y como lo ha señalado en la caratula de prestación de servicios, acreditando los mismos con copia de los documentos idóneos para tal efecto.',
        ]
        
        for item in declaraciones_cliente:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.5)
            p.paragraph_format.space_after = Pt(4)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run1 = p.add_run('◆ ')
            set_run_font(run1, size=12)
            # Procesar líneas en blanco en el texto
            item_text = item
            parts = item_text.split('____________')
            for i, part in enumerate(parts):
                if part:
                    run2 = p.add_run(part)
                    set_run_font(run2, size=12)
                if i < len(parts) - 1:
                    run_blank = p.add_run('____________')
                    set_run_font(run_blank, size=12)
                    run_blank.font.underline = True
        
        # CLÁUSULAS - 3 saltos de línea para bajar de página
        add_paragraph(doc, '', space_after=0)
        add_paragraph(doc, '', space_after=0)
        add_paragraph(doc, '', space_after=0)
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('CLÁUSULAS')
        set_run_font(run, size=12, bold=True)
        
        # Cláusulas
        clausulas = [
            ('PRIMERA. CONSENTIMIENTO.', 'Las partes manifiestan su voluntad de celebrar el presente contrato, cuya naturaleza jurídica es la mediación para la prestación de servicios turísticos.'),
            ('SEGUNDA. OBJETO.', 'LA AGENCIA intermediará, contratará u ofrecerá servicios turísticos detallados en la CARATULA, previo pago del Cliente de un precio cierto y determinado.'),
            ('TERCERA. PRECIO, FORMA Y LUGAR DE PAGO.', 'Las partes manifiestan su conformidad en que el precio total a pagar por EL CLIENTE como contraprestación del Servicio turístico, es la cantidad que por cada concepto se indica en la CARATULA de este Contrato. El importe señalado en la CARATULA, contempla todas las cantidades y conceptos referentes al Servicio turístico, por lo que LA AGENCIA se obliga a respetar en todo momento dicho costo sin poder cobrar otra cantidad o condicionar la prestación del Servicio turístico contratado a la adquisición de otro servicio no requerido por El cliente, salvo que El cliente autorice de manera escrita algún otro cobro no estipulado en el presente Contrato. EL CLIENTE efectuará el pago pactado por el Servicio turístico señalado en la caratula del presente Contrato en los términos y condiciones acordadas pudiendo ser:\na) Al contado: en efectivo, con tarjeta de débito, tarjeta de crédito, transferencia bancaria, y/o cheque en el domicilio de la agencia en moneda nacional, sin menoscabo de poderlo hacer en moneda extranjera al tipo de cambio publicado en el Diario Oficial de la Federación al día en que el pago se efectúe.\nb) A plazos: El cliente podrá, previo acuerdo con La agencia a pagar en parcialidades, para lo cual, La agencia deberá de entregar a El CLIENTE la información por escrito de las fechas, así como los montos parciales a pagar.\nc) En caso de que El cliente realice el pago con cheque y no se cubra el pago por causas imputables al librador, La agencia tendrá el derecho de realizar el cobro adicional del 20% (veinte por ciento) del valor del documento, por concepto de daños y perjuicios, en caso de que el cheque sea devuelto por causas imputables al librador, conforme al artículo 193 de la Ley General del Títulos y Operaciones de Crédito.'),
            ('QUINTA. OBLIGACIONES DE LA AGENCIA.', 'LA AGENCIA SE OBLIGA A:\nA) Cumplir lo pactado en el contrato.\nB) Entregar a EL CLIENTE copia del contrato y constancias de reservación.\nC) Proporcionar a EL CLIENTE boletos, claves de reservación y documentos de viaje.\nD) Auxiliar a EL CLIENTE en emergencias y gestionar indemnizaciones relacionadas con el servicio contratado\nE) Solicitar los Servicios turísticos que se especifican en la caratula de este Contrato por cuenta de EL CLIENTE de acuerdo a la disponibilidad de los mismos, a contratarlos fungiendo como intermediario entre éste y las personas encargadas de proporcionar directamente el Servicio turístico.\nF) Coadyuvar a EL CLIENTE para reclamar ante el prestador del servicio final, las indemnizaciones que correspondan.\nG) Respetar la Ley Federal de Protección al Consumidor y la NOM-010-TUR-2001.'),
            ('SEXTA. OBLIGACIONES DE EL CLIENTE:', 'Cumplir con lo establecido en el presente contrato:\nA) Proporcionar previo a la prestación del servicio los datos generales veraces y documentos requeridos para los servicios contratados (como pueden ser de manera enunciativa más no limitativa, el nombre, edad, identificación, comprobante de domicilio, pasaporte, visas, vacunas, constancia de situación fiscal, número telefónico, correo electrónico). Proporcionará sus propios datos y documentos de su persona así como el de las personas que lo acompañen.\nB) Realizar pagos a la AGENCIA conforme a lo pactado en el presente contrato.\nC) Respetar reglamentos de prestadores finales.\nD) Notificar por lo menos con CINCO DÍAS HÁBILES y por escrito a LA AGENCIA cualquier cambio o cancelación una vez aceptado el servicio.'),
            ('SÉPTIMA. VIGENCIA.', 'El contrato estará vigente mientras se presten los servicios y se cumplan las obligaciones de pago, tiempo en que el presente Contrato surtirá todos sus efectos legales.'),
            ('OCTAVA. CASO FORTUITO Y FUERZA MAYOR.', 'Se entiende por caso fortuito o fuerza mayor aquellos hechos o acontecimientos ajenos a la voluntad de las partes, que sean imprevisibles, irresistibles, insuperables y que no provengan de negligencia, dolo o falta de cuidado de alguna de ellas. No se considerarán caso fortuito o fuerza mayor las enfermedades personales de EL CLIENTE o de sus acompañantes. EL CLIENTE reconoce que la AGENCIA no será responsable por errores, omisiones, falta de entrega de documentos, información incompleta o inexacta, ni por cualquier otra actuación u omisión atribuible al propio CLIENTE que afecte la reservación, emisión de boletos, acceso a servicios turísticos, cambios, cancelaciones o cualquier trámite derivado del presente contrato. Cuando el servicio turístico no pueda prestarse total o parcialmente por caso fortuito o fuerza mayor, la AGENCIA reembolsará a EL CLIENTE las cantidades que, conforme a las políticas de los prestadores finales (aerolíneas, hoteles, operadores, etc.), sean efectivamente recuperables y devueltas a la AGENCIA. EL CLIENTE tendrá derecho a recibir el reembolso correspondiente únicamente respecto de los importes efectivamente recuperados. En caso de que el servicio turístico se haya prestado de manera parcial, EL CLIENTE tendrá derecho a un reembolso proporcional exclusivamente respecto de los servicios no utilizados, conforme a lo que determine el proveedor correspondiente.'),
            ('NOVENA. CAMBIOS DE ORDEN DE LOS SERVICIOS CON AUTORIZACIÓN DE EL CLIENTE.', 'La agencia podrá modificar el orden de los Servicios turísticos indicados en el presente Contrato, para un mejor desarrollo de los mismos o por las causas que así lo justifiquen, siempre y cuando respete la cantidad y calidad de los Servicios turísticos que se hayan contratado. Este será con la autorización por escrito de EL CLIENTE, sea cual fuese la causa. El cliente no podrá hacer cambios de fechas, rutas, ni servicios, sin previa autorización de La agencia, en caso de que dichos cambios tengan un costo, éste será indicado en al CARATULA del presente Contrato. EL CLIENTE reconoce que, una vez firmado el presente contrato y realizado el anticipo, pago parcial o total, los pagos efectuados no son cancelables ni reembolsables, en virtud de que la AGENCIA realiza de manera inmediata gestiones, reservaciones y pagos a terceros proveedores, los cuales se rigen por políticas propias de cancelación y reembolso que no dependen de la AGENCIA. EL CLIENTE acepta que cualquier solicitud de cambio, corrección o modificación respecto a fechas, nombres, itinerarios, servicios contratados o cualquier otro aspecto, estará sujeta a la disponibilidad de los proveedores, así como al pago de cargos adicionales o penalidades, conforme a las políticas vigentes de dichos proveedores.'),
            ('DÉCIMA. CANCELACIÓN.', 'EL CLIENTE reconoce que, una vez firmado el presente Contrato y realizado el anticipo, pago parcial o total, los pagos no son cancelables ni reembolsables, debido a que la AGENCIA realiza de manera inmediata pagos, reservaciones y gestiones con terceros proveedores, cuyas políticas no permiten cancelaciones ni devoluciones. Cualquier solicitud de cancelación o modificación deberá realizarse por escrito, pero no dará derecho a devolución, salvo que algún proveedor permita recuperar total o parcialmente los montos pagados, caso en el cual la AGENCIA entregará al CLIENTE únicamente las cantidades efectivamente devueltas por dicho proveedor. Las modificaciones estarán sujetas a disponibilidad y podrán generar cargos adicionales conforme a las políticas de los prestadores finales. La presente cláusula aplica únicamente a solicitudes voluntarias de cancelación formuladas por EL CLIENTE. Lo anterior es independiente de las consecuencias aplicables por rescisión por incumplimiento, reguladas en las cláusulas siguientes.'),
            ('DÉCIMA PRIMERA. VUELOS.', 'EL CLIENTE reconoce que los servicios aéreos incluidos en el paquete vacacional son operados exclusivamente por la aerolínea correspondiente, por lo que Movums The Travel Store no es responsable por cambios de itinerario, demoras, reprogramaciones, sobreventas, cancelaciones, modificaciones operativas o cualquier otra decisión adoptada por la aerolínea, toda vez que dichos actos son ajenos al control de la AGENCIA. EL CLIENTE acepta que toda compensación, reembolso, cambio o beneficio derivado de acciones de la aerolínea está sujeto exclusivamente a las políticas y procedimientos de dicha aerolínea, y que la AGENCIA actuará únicamente como intermediaria en la gestión correspondiente.'),
            ('DÉCIMA SEGUNDA. RESCISIÓN.', 'Procede si alguna parte incumple lo pactado o si el servicio no corresponde a lo solicitado. En caso de rescisión del presente Contrato, la parte que incumpla deberá de pagar lo correspondiente a la pena convencional. La AGENCIA podrá dar por terminado el presente contrato cuando EL CLIENTE no realice los depósitos o pagos en las fechas pactadas. En este supuesto, la AGENCIA notificará al CLIENTE mediante los medios de contacto proporcionados, y dicha terminación se considerará efectiva desde la fecha del incumplimiento. El CLIENTE reconoce que la falta de pago oportuno constituye un incumplimiento del contrato y acepta que los anticipos podrán aplicarse a cargos, penalidades o gastos ya generados conforme a las políticas de proveedores y prestadores de servicios turísticos. La rescisión no será considerada como una cancelación voluntaria, sino como una consecuencia jurídica del incumplimiento de cualquiera de las partes.'),
            ('DÉCIMA TERCERA. PENA CONVENCIONAL.', 'La parte incumplida pagará el 20% (veinte por ciento) del precio total del servicio, sin incluir IVA.'),
            ('DÉCIMA CUARTA. RESERVACIONES Y PAGOS.', 'La aceptación y formalización del presente contrato se considerará efectiva una vez que EL CLIENTE envíe el contrato debidamente firmado y efectúe el anticipo, pago parcial o total, mismo que no es reembolsable, en virtud de que Movums The Travel Store realiza gestiones inmediatas con terceros proveedores para asegurar la disponibilidad de los servicios solicitados.'),
            ('DÉCIMA QUINTA. JURISDICCIÓN.', 'Las partes se someten a PROFECO y, en su caso, a tribunales competentes de Texcoco, Estado de México.'),
        ]
        
        for idx, (titulo, contenido) in enumerate(clausulas):
            # Salto de página antes de QUINTA. OBLIGACIONES DE LA AGENCIA
            if 'QUINTA. OBLIGACIONES DE LA AGENCIA' in titulo:
                doc.add_page_break()
            
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(4)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            run1 = p.add_run(titulo)
            set_run_font(run1, size=12, bold=True)
            
            # Procesar el contenido que puede tener saltos de línea y subsecciones
            contenido_lines = contenido.split('\n')
            for i, line in enumerate(contenido_lines):
                if i == 0 and line.strip():
                    # Primera línea va en el mismo párrafo
                    run2 = p.add_run(' ' + line)
                    set_run_font(run2, size=12)
                elif line.strip():
                    # Líneas subsecuentes en nuevos párrafos
                    p2 = doc.add_paragraph()
                    p2.paragraph_format.left_indent = Inches(0.5)
                    p2.paragraph_format.space_after = Pt(3)
                    p2.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    run = p2.add_run(line)
                    set_run_font(run, size=12)
        
        # Sección 11: FIRMAS (combinada con las firmas del contrato)
        add_paragraph(doc, '11. FIRMAS', size=14, bold=True, color=MOVUMS_BLUE, space_before=15, space_after=10)
        
        # Firma Cliente
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('CLIENTE')
        set_run_font(run, size=12, bold=True)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(15)
        run1 = p.add_run('Nombre y firma: ')
        set_run_font(run1, size=12, bold=True)
        run2 = p.add_run('___________________________________________')
        set_run_font(run2, size=12)
        run2.font.underline = True
        
        # Firma Agencia
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(6)
        run = p.add_run('AGENCIA – Movums The Travel Store')
        set_run_font(run, size=12, bold=True)
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Nombre y firma del representante: ')
        set_run_font(run1, size=12, bold=True)
        run2 = p.add_run('____________________________')
        set_run_font(run2, size=12)
        run2.font.underline = True
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        run1 = p.add_run('Fecha: ')
        set_run_font(run1, size=12, bold=True)
        run2 = p.add_run('//2025')
        set_run_font(run2, size=12)
        
        # Preparar respuesta HTTP
        from io import BytesIO
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        nombre_cliente_safe = venta.cliente.nombre_completo_display.replace(' ', '_').replace('/', '_')
        filename = f"Contrato_Venta_{venta.pk}_{nombre_cliente_safe}.docx"
        
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(len(buffer.getvalue()))
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        buffer.close()
        return response

# ------------------- 11. ELIMINACIÓN DE VENTA -------------------

class VentaViajeDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Vista para eliminar una VentaViaje.
    Solo accesible para roles 'JEFE' y solo cuando la venta está cerrada, liquidada o cancelada.
    """
    model = VentaViaje
    template_name = 'ventas/venta_confirm_delete.html' 
    success_url = reverse_lazy('lista_ventas')

    def test_func(self):
        # Solo permite eliminar a JEFE
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        if user_rol != 'JEFE':
            return False
        
        # Verificar que la venta esté cerrada, liquidada o cancelada
        venta = self.get_object()
        
        # Una venta está cerrada/liquidada si:
        # 1. estado_confirmacion == 'COMPLETADO' (pagada completamente)
        # 2. O esta_pagada == True (saldo <= 0)
        esta_liquidada = venta.estado_confirmacion == 'COMPLETADO' or venta.esta_pagada
        
        # Una venta está cancelada si:
        # estado == 'CANCELADA'
        esta_cancelada = venta.estado == 'CANCELADA'
        
        # Solo se puede eliminar si está liquidada o cancelada
        return esta_liquidada or esta_cancelada

    def handle_no_permission(self):
        # Redirige al detalle de la venta si no tiene permiso o la venta no está en estado válido
        venta = self.get_object()
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        
        if user_rol != 'JEFE':
            messages.error(self.request, "Solo el JEFE puede eliminar ventas.")
        else:
            messages.error(self.request, "Solo se pueden eliminar ventas que estén cerradas, liquidadas o canceladas.")
        
        return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
    
# ------------------- 12. REPORTE DE COMISIONES POR VENDEDOR -------------------

def calcular_comision_por_tipo(total_ventas, tipo_vendedor):
    """
    Calcula la comisión según el tipo de vendedor y el total de ventas.
    
    Sistema de comisiones:
    - OFICINA (Ventas Internas): Escalonado
      * $0 - $99,999: 1%
      * $100,000 - $199,999: 2%
      * $200,000 - $299,999: 3%
      * $300,000 - $399,999: 4%
      * $400,000 - $500,000: 5%
      * Más de $500,000: 5% (tope máximo)
    
    - CALLE (Ventas de Campo): Fijo 4%
    
    Args:
        total_ventas: Decimal - Total de ventas pagadas del vendedor
        tipo_vendedor: str - 'OFICINA' o 'CALLE'
    
    Returns:
        tuple: (porcentaje_comision, monto_comision)
            porcentaje_comision: Decimal (ej: 0.03 para 3%)
            monto_comision: Decimal (monto calculado)
    """
    if tipo_vendedor == 'CALLE':
        # Ejecutivos de Ventas de Campo: 4% fijo siempre
        porcentaje = Decimal('0.04')
        return porcentaje, total_ventas * porcentaje
    
    elif tipo_vendedor == 'OFICINA':
        # Ejecutivos de Ventas Internas: Sistema escalonado
        if total_ventas < Decimal('100000'):
            porcentaje = Decimal('0.01')  # 1%
        elif total_ventas < Decimal('200000'):
            porcentaje = Decimal('0.02')  # 2%
        elif total_ventas < Decimal('300000'):
            porcentaje = Decimal('0.03')  # 3%
        elif total_ventas < Decimal('400000'):
            porcentaje = Decimal('0.04')  # 4%
        else:  # >= $400,000 (hasta $500,000 y más, máximo 5%)
            porcentaje = Decimal('0.05')  # 5%
        
        return porcentaje, total_ventas * porcentaje
    
    # Fallback: Por defecto 4% si no se identifica (nunca debería llegar aquí)
    porcentaje = Decimal('0.04')
    return porcentaje, total_ventas * porcentaje


class ComisionesVendedoresView(LoginRequiredMixin, TemplateView):
    """
    Muestra un reporte de sueldo fijo y comisiones calculadas.
    - JEFE: Ve a todos los vendedores de la agencia.
    - VENDEDOR: Solo ve su propia información.
    """
    template_name = 'ventas/comisiones_vendedores.html'
    
    # SUELDO BASE POR DEFECTO (si no tiene ejecutivo asociado)
    SUELDO_BASE = Decimal('10000.00') 

    def get_queryset_base(self):
        """Prepara el queryset base de ventas con el total pagado."""
        # Anota el total pagado en cada venta para poder filtrar por ventas cerradas/activas.
        return VentaViaje.objects.annotate(
            total_abonos=Sum('abonos__monto')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        vendedores_query = User.objects.filter(perfil__rol='VENDEDOR').order_by('username')
        
        # 1. Determinar qué usuarios ver
        if user_rol == 'VENDEDOR':
            # Si es vendedor, solo se ve a sí mismo
            vendedores_a_mostrar = User.objects.filter(pk=self.request.user.pk)
        elif user_rol in ['JEFE', 'CONTADOR']:
            # Si es jefe o contador, ve a todos los vendedores (solo lectura para contador)
            vendedores_a_mostrar = vendedores_query
        else:
            # Otros roles no deberían acceder
            vendedores_a_mostrar = User.objects.none() 

        # 2. Obtener todas las ventas del queryset base
        # Nota: No podemos filtrar directamente por total_pagado (es una propiedad de Python)
        # así que obtenemos todas las ventas y luego filtramos en Python
        ventas_base = self.get_queryset_base()

        lista_comisiones = []
        
        for vendedor in vendedores_a_mostrar:
            # Filtra las ventas solo por el vendedor actual
            ventas_vendedor = ventas_base.filter(vendedor=vendedor)
            
            # Filtrar en Python las ventas que están pagadas al 100%
            # (usando la propiedad total_pagado que incluye apertura + abonos confirmados)
            ventas_pagadas_vendedor = [
                venta for venta in ventas_vendedor 
                if venta.total_pagado >= venta.costo_total_con_modificacion
            ]
            ejecutivo = getattr(vendedor, 'ejecutivo_asociado', None)
            sueldo_base = ejecutivo.sueldo_base if ejecutivo and ejecutivo.sueldo_base else self.SUELDO_BASE

            # Obtener tipo de vendedor (por defecto OFICINA si no tiene ejecutivo asociado)
            tipo_vendedor = ejecutivo.tipo_vendedor if ejecutivo else 'OFICINA'

            # Suma el costo final de las ventas pagadas (base para la comisión)
            total_ventas_pagadas = sum(
                venta.costo_venta_final for venta in ventas_pagadas_vendedor
            ) or Decimal('0.00')
            
            # CÁLCULO DE COMISIÓN según tipo de vendedor
            porcentaje_comision, comision_ganada = calcular_comision_por_tipo(
                total_ventas_pagadas, 
                tipo_vendedor
            )
            ingreso_total = sueldo_base + comision_ganada

            lista_comisiones.append({
                'vendedor': vendedor,
                'sueldo_base': sueldo_base,
                'comision_porcentaje': porcentaje_comision * 100,  # Para mostrar como porcentaje
                'total_ventas_pagadas': total_ventas_pagadas,
                'comision_ganada': comision_ganada,
                'ingreso_total_estimado': ingreso_total,
                'es_usuario_actual': (vendedor.pk == self.request.user.pk),
                'ejecutivo': ejecutivo,
                'tipo_vendedor': tipo_vendedor,
            })

        context['lista_comisiones'] = lista_comisiones
        context['titulo_reporte'] = "Reporte de Comisiones de Ventas"
        context['user_rol'] = user_rol
        
        return context

    def _generar_username_unico(self, nombre_base):
        base_slug = slugify(nombre_base).replace('-', '')
        base_slug = base_slug or 'ejecutivo'
        base_slug = base_slug[:20]
        username = base_slug
        contador = 1
        while User.objects.filter(username=username).exists():
            sufijo = str(contador)
            username = f"{base_slug[:20-len(sufijo)]}{sufijo}"
            contador += 1
        return username

    def _split_nombre(self, nombre):
        partes = (nombre or '').strip().split()
        if not partes:
            return '', ''
        first = partes[0]
        last = ' '.join(partes[1:]) if len(partes) > 1 else ''
        return first, last

    def _crear_o_actualizar_usuario(self, ejecutivo, tipo_usuario='VENDEDOR', forzar_password=False):
        password_plano = None
        first_name, last_name = self._split_nombre(ejecutivo.nombre_completo)

        if not ejecutivo.usuario:
            username = self._generar_username_unico(ejecutivo.nombre_completo)
            password_plano = secrets.token_urlsafe(10)
            user = User.objects.create_user(
                username=username,
                password=password_plano,
                email=ejecutivo.email or '',
                first_name=first_name,
                last_name=last_name
            )
            ejecutivo.usuario = user
            ejecutivo.ultima_contrasena = password_plano
            ejecutivo.save(update_fields=['usuario', 'ultima_contrasena'])
        else:
            user = ejecutivo.usuario
            user.email = ejecutivo.email or ''
            user.first_name = first_name
            user.last_name = last_name
            if forzar_password:
                password_plano = secrets.token_urlsafe(10)
                user.set_password(password_plano)
            user.save()
            if password_plano:
                Ejecutivo.objects.filter(pk=ejecutivo.pk).update(ultima_contrasena=password_plano)

        # Asegurar el rol seleccionado (VENDEDOR o CONTADOR)
        perfil = getattr(user, 'perfil', None)
        if perfil:
            # Asegurar que el rol sea válido
            rol_final = tipo_usuario if tipo_usuario in ['VENDEDOR', 'CONTADOR'] else 'VENDEDOR'
            if perfil.rol != rol_final:
                perfil.rol = rol_final
            perfil.save(update_fields=['rol'])

        return user, password_plano



class GestionRolesView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Vista para gestionar roles y usuarios del sistema.
    Solo accesible para JEFE.
    Migrada desde ComisionesVendedoresView - Sección de Equipo de Ejecutivos.
    """
    template_name = 'ventas/gestion_roles.html'
    
    def test_func(self):
        """Solo JEFE puede gestionar roles."""
        user_rol = get_user_role(self.request.user)
        return user_rol == 'JEFE'
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para acceder a la gestión de roles. Solo el JEFE puede acceder.")
        return redirect('dashboard')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ejecutivos'] = Ejecutivo.objects.all().select_related('usuario', 'usuario__perfil', 'oficina')
        context['ejecutivo_form'] = kwargs.get('ejecutivo_form') or EjecutivoForm()
        context['mostrar_modal_ejecutivo'] = kwargs.get('mostrar_modal_ejecutivo', False)
        context['oficinas'] = Oficina.objects.all().order_by('nombre')
        context['oficina_form'] = kwargs.get('oficina_form') or OficinaForm()
        context['mostrar_modal_oficina'] = kwargs.get('mostrar_modal_oficina', False)
        return context
    
    def _generar_username_unico(self, nombre_base):
        """Genera un username único basado en el nombre."""
        base_slug = slugify(nombre_base).replace('-', '')
        base_slug = base_slug or 'ejecutivo'
        base_slug = base_slug[:20]
        username = base_slug
        contador = 1
        while User.objects.filter(username=username).exists():
            sufijo = str(contador)
            username = f"{base_slug[:20-len(sufijo)]}{sufijo}"
            contador += 1
        return username
    
    def _split_nombre(self, nombre):
        """Divide el nombre completo en first_name y last_name."""
        partes = (nombre or '').strip().split()
        if not partes:
            return '', ''
        first = partes[0]
        last = ' '.join(partes[1:]) if len(partes) > 1 else ''
        return first, last
    
    def _crear_o_actualizar_usuario(self, ejecutivo, tipo_usuario='VENDEDOR', forzar_password=False, nueva_password=None):
        """Crea o actualiza el usuario asociado al ejecutivo."""
        password_plano = None
        first_name, last_name = self._split_nombre(ejecutivo.nombre_completo)
        
        try:
            if not ejecutivo.usuario:
                # Si no hay usuario, crear uno nuevo
                # Verificar que haya email para crear el usuario (email es necesario para crear credenciales)
                if not ejecutivo.email:
                    logger.error(f"No se puede crear usuario para ejecutivo {ejecutivo.pk} sin email")
                    raise ValueError("El correo electrónico es obligatorio para crear el usuario.")
                
                # Verificar que el email no esté en uso por otro usuario
                if User.objects.filter(email__iexact=ejecutivo.email).exists():
                    logger.error(f"El email {ejecutivo.email} ya está en uso por otro usuario")
                    raise ValueError(f"El correo electrónico '{ejecutivo.email}' ya está registrado por otro usuario en el sistema.")
                
                username = self._generar_username_unico(ejecutivo.nombre_completo)
                
                # Verificar que el username no exista (aunque _generar_username_unico debería generar uno único)
                if User.objects.filter(username=username).exists():
                    # Si el username ya existe, generar uno nuevo con contador
                    base_username = username
                    contador = 1
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username[:20-len(str(contador))]}{contador}"
                        contador += 1
                
                password_plano = secrets.token_urlsafe(10)
                try:
                    user = User.objects.create_user(
                        username=username,
                        password=password_plano,
                        email=ejecutivo.email,
                        first_name=first_name,
                        last_name=last_name
                    )
                except Exception as e:
                    error_msg = str(e)
                    # Capturar errores específicos de base de datos
                    if "unique constraint" in error_msg.lower() or "duplicate" in error_msg.lower():
                        if "username" in error_msg.lower():
                            raise ValueError("El nombre de usuario generado ya existe. Intenta nuevamente.")
                        elif "email" in error_msg.lower():
                            raise ValueError(f"El correo electrónico '{ejecutivo.email}' ya está registrado por otro usuario en el sistema.")
                    logger.error(f"Error al crear usuario para ejecutivo {ejecutivo.pk}: {error_msg}", exc_info=True)
                    raise ValueError(f"Error al crear el usuario: {error_msg}")
                
                # Refrescar el usuario desde la base de datos para asegurar que la señal se haya ejecutado
                user.refresh_from_db()
                ejecutivo.usuario = user
                ejecutivo.ultima_contrasena = password_plano
                ejecutivo.save(update_fields=['usuario', 'ultima_contrasena'])
            else:
                # Si ya existe usuario, actualizarlo
                user = ejecutivo.usuario
                if not user:
                    logger.error(f"Ejecutivo {ejecutivo.pk} tiene referencia a usuario pero el usuario es None")
                    return None, None
                
                # Actualizar email solo si se proporciona y es diferente
                if ejecutivo.email and user.email != ejecutivo.email:
                    user.email = ejecutivo.email
                
                user.first_name = first_name
                user.last_name = last_name
                if forzar_password:
                    # Si se proporciona una nueva contraseña, usarla; si no, generar una aleatoria
                    password_plano = nueva_password if nueva_password else secrets.token_urlsafe(10)
                    user.set_password(password_plano)
                
                try:
                    user.save()
                except Exception as e:
                    logger.error(f"Error al guardar usuario {user.pk}: {str(e)}", exc_info=True)
                    raise
                
                if password_plano:
                    Ejecutivo.objects.filter(pk=ejecutivo.pk).update(ultima_contrasena=password_plano)
            
            # Verificar que user no sea None antes de continuar
            if not user:
                logger.error(f"Error: user es None después de crear/actualizar para ejecutivo {ejecutivo.pk}")
                return None, None
            
            # Asegurar que el Perfil exista (puede no haberse creado por la señal si hubo algún problema)
            try:
                perfil = user.perfil
            except Perfil.DoesNotExist:
                # Si no existe, crearlo manualmente
                perfil = Perfil.objects.create(user=user, rol='VENDEDOR')
            
            # Asegurar el rol seleccionado
            roles_validos = ['JEFE', 'DIRECTOR_GENERAL', 'DIRECTOR_VENTAS', 'DIRECTOR_ADMINISTRATIVO', 'GERENTE', 'CONTADOR', 'VENDEDOR']
            rol_final = tipo_usuario if tipo_usuario in roles_validos else 'VENDEDOR'
            if perfil.rol != rol_final:
                perfil.rol = rol_final
                perfil.save(update_fields=['rol'])
            
            return user, password_plano
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error al crear/actualizar usuario para ejecutivo {ejecutivo.pk}: {error_msg}", exc_info=True)
            # Re-raise la excepción para que el código que llama pueda manejarla mejor
            raise
    
    def post(self, request, *args, **kwargs):
        """Maneja las acciones de crear, editar y eliminar ejecutivos y oficinas."""
        # Verificar si es una acción de oficina
        if 'oficina_action' in request.POST:
            return self._handle_oficina_action(request)
        
        # Acción de ejecutivo
        action = request.POST.get('ejecutivo_action', 'crear')
        ejecutivo_id = request.POST.get('ejecutivo_id')
        
        if action == 'eliminar':
            if not ejecutivo_id:
                messages.error(request, "No se pudo identificar al ejecutivo a eliminar.")
                return redirect('gestion_roles')
            ejecutivo = get_object_or_404(Ejecutivo, pk=ejecutivo_id)
            usuario_rel = ejecutivo.usuario
            nombre = ejecutivo.nombre_completo
            ejecutivo.delete()
            if usuario_rel:
                usuario_rel.delete()
            messages.success(request, f"Ejecutivo '{nombre}' eliminado correctamente.")
            return redirect('gestion_roles')
        
        instance = None
        if action == 'editar':
            if not ejecutivo_id:
                messages.error(request, "No se pudo identificar al ejecutivo a editar.")
                return redirect('gestion_roles')
            instance = get_object_or_404(Ejecutivo, pk=ejecutivo_id)
        
        form = EjecutivoForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            try:
                # INICIO DEL BLOQUE DE SEGURIDAD - Transacción atómica
                with transaction.atomic():
                    ejecutivo = form.save()  # Ahora esto es provisional dentro de la transacción
                    tipo_usuario = form.cleaned_data.get('tipo_usuario', 'VENDEDOR')
                    
                    # Manejar cambio de contraseña
                    nueva_contrasena = request.POST.get('nueva_contrasena', '').strip()
                    regenerar_password = False
                    if action == 'editar':
                        # En edición, solo regenerar si se proporciona una nueva contraseña
                        regenerar_password = bool(nueva_contrasena)
                    else:
                        # En creación, siempre generar nueva contraseña
                        regenerar_password = True
                    
                    # Intentar crear usuario
                    user, password = self._crear_o_actualizar_usuario(
                        ejecutivo,
                        tipo_usuario=tipo_usuario,
                        forzar_password=regenerar_password,
                        nueva_password=nueva_contrasena if nueva_contrasena else None
                    )
                    
                    # Verificar que el usuario se creó correctamente
                    # Si no se creó, esto forzará el rollback automático del ejecutivo guardado arriba
                    if not user:
                        error_msg = "Error al crear/actualizar el usuario. Por favor, verifica que el correo electrónico sea válido y único."
                        raise ValueError(error_msg)
                # FIN DEL BLOQUE - Si llegamos aquí, todo se confirma (commit)
                
                # Refrescar el ejecutivo desde la base de datos para asegurar que las relaciones estén cargadas
                ejecutivo.refresh_from_db()
                
                if password:
                    if action == 'editar':
                        messages.success(
                            request,
                            (
                                f"Ejecutivo '{ejecutivo.nombre_completo}' actualizado correctamente. "
                                f"Nueva contraseña: {password}"
                            )
                        )
                    else:
                        messages.success(
                            request,
                            f"Ejecutivo '{ejecutivo.nombre_completo}' agregado."
                        )
                else:
                    messages.success(request, f"Ejecutivo '{ejecutivo.nombre_completo}' actualizado correctamente.")
                return redirect('gestion_roles')
                
            except Exception as e:
                # Si ocurre CUALQUIER error dentro del 'with transaction.atomic', 
                # Django deshace automáticamente el form.save() inicial.
                # La BD queda limpia como si nada hubiera pasado.
                
                error_msg = str(e)
                # Simplificar el mensaje si no es un mensaje específico ya formateado
                if "Error al guardar el ejecutivo" not in error_msg and not any(keyword in error_msg.lower() for keyword in ["correo", "email", "usuario", "username"]):
                    error_msg = f"Error al guardar el ejecutivo: {str(e)}"
                
                messages.error(request, error_msg)
                import traceback
                logger.error(f"Error al crear ejecutivo: {traceback.format_exc()}")
                
                # Mantener el formulario con errores para que se muestren
                # El formulario original tiene los datos del POST, así que se mantendrán
                context = self.get_context_data()
                context['ejecutivo_form'] = form  # El formulario ya tiene los datos del POST
                context['mostrar_modal_ejecutivo'] = True
                # Pasar el ejecutivo_id para que el modal se abra en modo edición (si es edición)
                if action == 'editar' and ejecutivo_id:
                    context['ejecutivo_id_editar'] = ejecutivo_id
                return self.render_to_response(context)
        else:
            # Si el formulario no es válido, mostrar los errores
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"{field}: {error}")
            if error_messages:
                messages.error(request, "Por favor, corrige los siguientes errores: " + " | ".join(error_messages))
        
        # Al renderizar el formulario con errores, asegurarse de que se pasa con los datos del POST
        # para que el usuario no tenga que volver a llenar los campos
        context = self.get_context_data(ejecutivo_form=form, mostrar_modal_ejecutivo=True)
        # Si estamos creando un ejecutivo que ya se guardó pero falló el usuario, pasar su ID para editarlo
        if action == 'crear' and 'ejecutivo' in locals() and ejecutivo.pk:
            context['ejecutivo_id_editar'] = ejecutivo.pk
        elif action == 'editar' and ejecutivo_id:
            context['ejecutivo_id_editar'] = ejecutivo_id
        return self.render_to_response(context)
    
    def _handle_oficina_action(self, request):
        """Maneja las acciones de crear, editar, deshabilitar y habilitar oficinas."""
        action = request.POST.get('oficina_action', 'crear')
        oficina_id = request.POST.get('oficina_id')
        
        if action == 'deshabilitar':
            if not oficina_id:
                messages.error(request, "No se pudo identificar la oficina a deshabilitar.")
                return redirect('gestion_roles')
            oficina = get_object_or_404(Oficina, pk=oficina_id)
            nombre = oficina.nombre
            oficina.activa = False
            oficina.save()
            messages.warning(request, f"Oficina '{nombre}' deshabilitada correctamente.")
            return redirect('gestion_roles')
        
        if action == 'habilitar':
            if not oficina_id:
                messages.error(request, "No se pudo identificar la oficina a habilitar.")
                return redirect('gestion_roles')
            oficina = get_object_or_404(Oficina, pk=oficina_id)
            nombre = oficina.nombre
            oficina.activa = True
            oficina.save()
            messages.success(request, f"Oficina '{nombre}' habilitada correctamente.")
            return redirect('gestion_roles')
        
        instance = None
        if action == 'editar':
            if not oficina_id:
                messages.error(request, "No se pudo identificar la oficina a editar.")
                return redirect('gestion_roles')
            instance = get_object_or_404(Oficina, pk=oficina_id)
        
        form = OficinaForm(request.POST, instance=instance)
        if form.is_valid():
            try:
                oficina = form.save()
                if action == 'editar':
                    messages.success(request, f"Oficina '{oficina.nombre}' actualizada correctamente.")
                else:
                    messages.success(request, f"Oficina '{oficina.nombre}' creada correctamente.")
                return redirect('gestion_roles')
            except Exception as e:
                messages.error(request, f"Error al guardar la oficina: {str(e)}")
        else:
            messages.error(request, "Por favor, corrige los errores en el formulario.")
            # Retornar con el formulario con errores
            context = self.get_context_data()
            context['oficina_form'] = form
            context['mostrar_modal_oficina'] = True
            return self.render_to_response(context)
        
        return redirect('gestion_roles')


class EjecutivoDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    Vista para ver los detalles completos de un ejecutivo.
    Solo accesible para JEFE.
    """
    model = Ejecutivo
    template_name = 'ventas/ejecutivo_detail.html'
    context_object_name = 'ejecutivo'
    
    def test_func(self):
        """Solo JEFE puede ver detalles de ejecutivos."""
        user_rol = get_user_role(self.request.user)
        return user_rol == 'JEFE'
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para ver los detalles del ejecutivo. Solo el JEFE puede acceder.")
        return redirect('gestion_roles')
    
    def post(self, request, *args, **kwargs):
        """Maneja las acciones desde la vista de detalle: eliminar, cambiar contraseña, cambiar sueldo, desactivar/activar."""
        ejecutivo = self.get_object()
        action = request.POST.get('action')
        
        if action == 'cambiar_contrasena':
            nueva_contrasena = request.POST.get('nueva_contrasena', '').strip()
            if nueva_contrasena and ejecutivo.usuario:
                ejecutivo.usuario.set_password(nueva_contrasena)
                ejecutivo.usuario.save()
                ejecutivo.ultima_contrasena = nueva_contrasena
                ejecutivo.save(update_fields=['ultima_contrasena'])
                messages.success(request, f"Contraseña actualizada correctamente. Nueva contraseña: {nueva_contrasena}")
                return redirect(reverse('ejecutivo_detail', kwargs={'pk': ejecutivo.pk}) + '?contrasena_actualizada=1')
            else:
                messages.error(request, "No se pudo actualizar la contraseña. Verifica que el ejecutivo tenga un usuario asociado.")
            return redirect('ejecutivo_detail', pk=ejecutivo.pk)
        
        elif action == 'desactivar' or action == 'activar':
            # Desactivar o activar el usuario
            if not ejecutivo.usuario:
                messages.error(request, "El ejecutivo no tiene un usuario asociado.")
                return redirect('ejecutivo_detail', pk=ejecutivo.pk)
            
            if action == 'desactivar':
                ejecutivo.usuario.is_active = False
                ejecutivo.usuario.save()
                messages.warning(request, f"Usuario '{ejecutivo.usuario.username}' desactivado correctamente. No podrá iniciar sesión hasta que sea reactivado.")
            else:  # activar
                ejecutivo.usuario.is_active = True
                ejecutivo.usuario.save()
                messages.success(request, f"Usuario '{ejecutivo.usuario.username}' activado correctamente. Ya puede iniciar sesión.")
            
            return redirect('ejecutivo_detail', pk=ejecutivo.pk)
        
        elif action == 'eliminar' or not action:
            # Eliminación del ejecutivo
            usuario_rel = ejecutivo.usuario
            nombre = ejecutivo.nombre_completo
            ejecutivo.delete()
            if usuario_rel:
                usuario_rel.delete()
            messages.success(request, f"Ejecutivo '{nombre}' eliminado correctamente.")
            return redirect('gestion_roles')
        
        return redirect('ejecutivo_detail', pk=ejecutivo.pk)


class ProveedorListCreateView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Gestiona el catálogo de proveedores: listado agrupado y creación desde un solo lugar.
    """
    template_name = 'ventas/proveedores.html'

    def test_func(self):
        """Solo JEFE puede gestionar proveedores. CONTADOR solo lectura en otras secciones."""
        rol = get_user_role(self.request.user).upper()
        return 'JEFE' in rol or self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para gestionar proveedores.")
        return redirect('dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        proveedores = Proveedor.objects.all()
        proveedores_por_servicio = {clave: [] for clave, _ in Proveedor.SERVICIO_CHOICES}

        # ✅ Agrupar proveedores por cada servicio que ofrecen (pueden estar en múltiples grupos)
        for proveedor in proveedores:
            if proveedor.servicios:
                servicios_list = [s.strip() for s in proveedor.servicios.split(',') if s.strip()]
                for servicio_codigo in servicios_list:
                    if servicio_codigo in proveedores_por_servicio:
                        proveedores_por_servicio[servicio_codigo].append(proveedor)
            # Si no tiene servicios definidos, no se agrupa

        grupos_proveedores = [
            {
                'clave': clave,
                'label': label,
                'proveedores': sorted(
                    proveedores_por_servicio.get(clave, []),
                    key=lambda p: p.nombre.lower()
                ),
            }
            for clave, label in Proveedor.SERVICIO_CHOICES
        ]

        context['grupos_proveedores'] = grupos_proveedores
        context['total_proveedores'] = len(proveedores)  # Total único de proveedores
        context['form'] = kwargs.get('form') or ProveedorForm()
        context['servicio_choices'] = Proveedor.SERVICIO_CHOICES
        return context

    def post(self, request, *args, **kwargs):
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            messages.success(request, f"Proveedor '{proveedor.nombre}' agregado correctamente.")
            return redirect('proveedores')
        
        # Si el formulario no es válido, mostrar errores
        messages.error(request, "Por favor, corrige los errores en el formulario.")
        context = self.get_context_data(form=form)
        context['form'] = form
        return self.render_to_response(context)

# ------------------- VISTAS PARA NOTIFICACIONES -------------------

class ConfirmarPagoView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Vista para que el CONTADOR confirme pagos pendientes."""
    
    def test_func(self):
        """Solo CONTADOR puede confirmar pagos."""
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol == 'CONTADOR'
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para confirmar pagos.")
        return redirect('dashboard')
    
    def post(self, request, notificacion_id):
        from django.utils import timezone
        
        try:
            notificacion = Notificacion.objects.get(
                pk=notificacion_id,
                usuario=request.user,
                tipo='PAGO_PENDIENTE',
                confirmado=False
            )
            
            venta = notificacion.venta
            abono = notificacion.abono
            
            # Confirmar el abono (si existe)
            if abono:
                abono.confirmado = True
                abono.confirmado_por = request.user
                abono.confirmado_en = timezone.now()
                abono.save(update_fields=['confirmado', 'confirmado_por', 'confirmado_en'])
            
            # Actualizar estado de la venta
            # Refrescar la venta desde la BD para obtener los datos actualizados
            venta.refresh_from_db()
            
            if abono:
                # Verificar si la venta está completada (liquidada)
                # Ahora total_pagado incluirá el abono confirmado
                # IMPORTANTE: Usar costo_total_con_modificacion, no solo costo_venta_final
                nuevo_total = venta.total_pagado
                venta_liquidada = nuevo_total >= venta.costo_total_con_modificacion
                if venta_liquidada:
                    venta.estado_confirmacion = 'COMPLETADO'
                    # Crear notificación de liquidación para el VENDEDOR
                    if venta.vendedor:
                        mensaje_liquidacion = f"¡Venta #{venta.pk} completamente liquidada! - Cliente: {venta.cliente.nombre_completo_display} - Total: ${venta.costo_venta_final:,.2f}"
                        Notificacion.objects.create(
                            usuario=venta.vendedor,
                            tipo='LIQUIDACION',
                            mensaje=mensaje_liquidacion,
                            venta=venta,
                            confirmado=False
                        )
                else:
                    venta.estado_confirmacion = 'PENDIENTE'
            else:
                # Si no hay abono, es una apertura - confirmarla
                # Cuando se confirma la apertura, se establece estado_confirmacion a COMPLETADO
                # Esto hará que total_pagado cuente la cantidad_apertura (según la lógica del modelo)
                venta.estado_confirmacion = 'COMPLETADO'
                # Refrescar desde BD para asegurar que tenemos los valores actualizados
                venta.refresh_from_db()
                
                # Verificar si la venta está completamente pagada después de confirmar la apertura
                venta_liquidada = venta.total_pagado >= venta.costo_total_con_modificacion
                if venta_liquidada:
                    # Si ya está pagada completamente, mantener COMPLETADO
                    # Crear notificación de liquidación para el VENDEDOR
                    if venta.vendedor:
                        mensaje_liquidacion = f"¡Venta #{venta.pk} completamente liquidada! - Cliente: {venta.cliente.nombre_completo_display} - Total: ${venta.costo_venta_final:,.2f}"
                        Notificacion.objects.create(
                            usuario=venta.vendedor,
                            tipo='LIQUIDACION',
                            mensaje=mensaje_liquidacion,
                            venta=venta,
                            confirmado=False
                        )
                else:
                    # Si aún falta pagar, cambiar a PENDIENTE para permitir más abonos
                    venta.estado_confirmacion = 'PENDIENTE'
            
            venta.save(update_fields=['estado_confirmacion'])
            
            # Actualizar notificación del CONTADOR: cambiar de PAGO_PENDIENTE a PAGO_CONFIRMADO
            notificacion.tipo = 'PAGO_CONFIRMADO'
            mensaje_contador_actualizado = f"✅ Pago confirmado: ${abono.monto if abono else venta.cantidad_apertura:,.2f} - Venta #{venta.pk}"
            notificacion.mensaje = mensaje_contador_actualizado
            notificacion.confirmado = True
            notificacion.confirmado_por = request.user
            notificacion.confirmado_en = timezone.now()
            notificacion.marcar_como_vista()
            notificacion.save(update_fields=['tipo', 'mensaje', 'confirmado', 'confirmado_por', 'confirmado_en', 'vista', 'fecha_vista'])
            
            # Crear notificación para el VENDEDOR (solo si NO es JEFE para evitar duplicados)
            if venta.vendedor:
                # Verificar si el vendedor es JEFE
                vendedor_es_jefe = venta.vendedor.perfil.rol == 'JEFE' if hasattr(venta.vendedor, 'perfil') else False
                
                if not vendedor_es_jefe:
                    # Solo crear notificación para vendedor si NO es JEFE
                    mensaje_vendedor = f"✅ Tu pago ha sido confirmado por el contador. Puedes proceder con la venta #{venta.pk}"
                    Notificacion.objects.create(
                        usuario=venta.vendedor,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_vendedor,
                        venta=venta,
                        abono=abono,
                        confirmado=True
                    )
            
            # Actualizar notificaciones existentes del JEFE en lugar de crear nuevas
            jefes = User.objects.filter(perfil__rol='JEFE')
            mensaje_jefe_actualizado = f"✅ Pago confirmado por el contador: ${abono.monto if abono else venta.cantidad_apertura:,.2f} - Venta #{venta.pk}"
            
            for jefe in jefes:
                # Buscar la notificación pendiente existente
                notificacion_jefe = Notificacion.objects.filter(
                    usuario=jefe,
                    venta=venta,
                    tipo='PAGO_PENDIENTE',
                    confirmado=False
                ).first()
                
                if notificacion_jefe and abono:
                    # Si existe una notificación pendiente del mismo abono, actualizarla
                    notificacion_jefe_abono = Notificacion.objects.filter(
                        usuario=jefe,
                        venta=venta,
                        abono=abono,
                        tipo='PAGO_PENDIENTE',
                        confirmado=False
                    ).first()
                    
                    if notificacion_jefe_abono:
                        # Actualizar la notificación existente
                        notificacion_jefe_abono.tipo = 'PAGO_CONFIRMADO'
                        notificacion_jefe_abono.mensaje = mensaje_jefe_actualizado
                        notificacion_jefe_abono.confirmado = True
                        notificacion_jefe_abono.confirmado_por = request.user
                        notificacion_jefe_abono.confirmado_en = timezone.now()
                        notificacion_jefe_abono.save(update_fields=['tipo', 'mensaje', 'confirmado', 'confirmado_por', 'confirmado_en'])
                    elif notificacion_jefe:
                        # Si no hay una específica del abono, actualizar la genérica
                        notificacion_jefe.tipo = 'PAGO_CONFIRMADO'
                        notificacion_jefe.mensaje = mensaje_jefe_actualizado
                        notificacion_jefe.confirmado = True
                        notificacion_jefe.confirmado_por = request.user
                        notificacion_jefe.confirmado_en = timezone.now()
                        notificacion_jefe.save(update_fields=['tipo', 'mensaje', 'confirmado', 'confirmado_por', 'confirmado_en'])
                    else:
                        # Si no existe ninguna, crear una nueva (caso especial)
                        Notificacion.objects.create(
                            usuario=jefe,
                            tipo='PAGO_CONFIRMADO',
                            mensaje=mensaje_jefe_actualizado,
                            venta=venta,
                            abono=abono,
                            confirmado=True
                        )
                elif notificacion_jefe:
                    # Si existe una notificación pero no hay abono específico (apertura)
                    notificacion_jefe.tipo = 'PAGO_CONFIRMADO'
                    notificacion_jefe.mensaje = mensaje_jefe_actualizado
                    notificacion_jefe.confirmado = True
                    notificacion_jefe.confirmado_por = request.user
                    notificacion_jefe.confirmado_en = timezone.now()
                    notificacion_jefe.save(update_fields=['tipo', 'mensaje', 'confirmado', 'confirmado_por', 'confirmado_en'])
                else:
                    # Si no existe ninguna notificación previa, crear una nueva (caso raro)
                    Notificacion.objects.create(
                        usuario=jefe,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_jefe_actualizado,
                        venta=venta,
                        abono=abono,
                        confirmado=True
                    )
            
            messages.success(request, "Pago confirmado exitosamente. ✅")
            # Redirigir al detalle de la venta en la pestaña de abonos para que el contador vea el pago confirmado
            return redirect(reverse('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=abonos')
            
        except Notificacion.DoesNotExist:
            messages.error(request, "No se encontró la notificación o ya fue confirmada.")
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f"Error al confirmar el pago: {str(e)}")
            # Intentar redirigir a la venta si está disponible en el contexto
            try:
                if 'venta' in locals() and venta:
                    return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
            except:
                pass
            return redirect('dashboard')


class ConfirmarAbonoView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Vista para que el CONTADOR confirme abonos pendientes directamente desde el detalle de venta."""
    
    def test_func(self):
        """Solo CONTADOR puede confirmar abonos."""
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol == 'CONTADOR'
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para confirmar abonos.")
        return redirect('dashboard')
    
    def post(self, request, abono_id):
        from django.utils import timezone
        
        try:
            abono = get_object_or_404(AbonoPago, pk=abono_id)
            
            # Verificar que el abono está pendiente de confirmación
            if abono.confirmado:
                messages.warning(request, "Este abono ya fue confirmado anteriormente.")
                return redirect(reverse('detalle_venta', kwargs={'pk': abono.venta.pk, 'slug': abono.venta.slug_safe}) + '?tab=abonos')
            
            # Verificar que el abono es de tipo Transferencia/Tarjeta/Depósito (requiere confirmación)
            if abono.forma_pago not in ['TRN', 'TAR', 'DEP']:
                messages.warning(request, "Solo se pueden confirmar abonos de Transferencia, Tarjeta o Depósito.")
                return redirect(reverse('detalle_venta', kwargs={'pk': abono.venta.pk, 'slug': abono.venta.slug_safe}) + '?tab=abonos')
            
            venta = abono.venta
            
            # Confirmar el abono
            abono.confirmado = True
            abono.confirmado_por = request.user
            abono.confirmado_en = timezone.now()
            abono.save(update_fields=['confirmado', 'confirmado_por', 'confirmado_en'])
            
            # Actualizar estado de la venta
            venta.refresh_from_db()
            nuevo_total = venta.total_pagado
            if nuevo_total >= venta.costo_venta_final:
                venta.estado_confirmacion = 'COMPLETADO'
            else:
                venta.estado_confirmacion = 'PENDIENTE'
            venta.save(update_fields=['estado_confirmacion'])
            
            # Actualizar SOLO las notificaciones relacionadas con ESTE abono específico del CONTADOR
            # IMPORTANTE: Solo actualizar notificaciones que están relacionadas con este abono específico
            notificaciones_contador = Notificacion.objects.filter(
                usuario=request.user,
                abono=abono,
                tipo='PAGO_PENDIENTE',
                confirmado=False
            )
            mensaje_contador_actualizado = f"✅ Abono confirmado: ${abono.monto:,.2f} ({abono.get_forma_pago_display()}) - Venta #{venta.pk}"
            for notificacion in notificaciones_contador:
                notificacion.tipo = 'PAGO_CONFIRMADO'
                notificacion.mensaje = mensaje_contador_actualizado
                notificacion.confirmado = True
                notificacion.confirmado_por = request.user
                notificacion.confirmado_en = timezone.now()
                notificacion.marcar_como_vista()
                notificacion.save(update_fields=['tipo', 'mensaje', 'confirmado', 'confirmado_por', 'confirmado_en', 'vista', 'fecha_vista'])
            
            # Crear notificación para el VENDEDOR (solo si NO es JEFE para evitar duplicados)
            if venta.vendedor:
                # Verificar si el vendedor es JEFE
                vendedor_es_jefe = venta.vendedor.perfil.rol == 'JEFE' if hasattr(venta.vendedor, 'perfil') else False
                
                if not vendedor_es_jefe:
                    # Solo crear notificación para vendedor si NO es JEFE
                    mensaje_vendedor = f"✅ Tu abono de ${abono.monto:,.2f} ha sido confirmado por el contador. Venta #{venta.pk}"
                    Notificacion.objects.create(
                        usuario=venta.vendedor,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_vendedor,
                        venta=venta,
                        abono=abono,
                        confirmado=True
                    )
            
            # Actualizar notificaciones existentes del JEFE en lugar de crear nuevas
            jefes = User.objects.filter(perfil__rol='JEFE')
            mensaje_jefe_actualizado = f"✅ Abono confirmado por el contador: ${abono.monto:,.2f} ({abono.get_forma_pago_display()}) - Venta #{venta.pk}"
            
            for jefe in jefes:
                # Buscar la notificación pendiente existente del mismo abono
                notificacion_jefe_abono = Notificacion.objects.filter(
                    usuario=jefe,
                    venta=venta,
                    abono=abono,
                    tipo='PAGO_PENDIENTE',
                    confirmado=False
                ).first()
                
                if notificacion_jefe_abono:
                    # Actualizar la notificación existente
                    notificacion_jefe_abono.tipo = 'PAGO_CONFIRMADO'
                    notificacion_jefe_abono.mensaje = mensaje_jefe_actualizado
                    notificacion_jefe_abono.confirmado = True
                    notificacion_jefe_abono.confirmado_por = request.user
                    notificacion_jefe_abono.confirmado_en = timezone.now()
                    notificacion_jefe_abono.save(update_fields=['tipo', 'mensaje', 'confirmado', 'confirmado_por', 'confirmado_en'])
                else:
                    # Si no existe, crear una nueva (caso raro donde no se creó la inicial)
                    Notificacion.objects.create(
                        usuario=jefe,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_jefe_actualizado,
                        venta=venta,
                        abono=abono,
                        confirmado=True
                    )
            
            messages.success(request, f"✅ Abono de ${abono.monto:,.2f} confirmado exitosamente.")
            return redirect(reverse('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=abonos')
            
        except AbonoPago.DoesNotExist:
            messages.error(request, "El abono no existe.")
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f"Error al confirmar el abono: {str(e)}")
            return redirect('dashboard')


class MarcarNotificacionVistaView(LoginRequiredMixin, View):
    """Vista AJAX para marcar una notificación como vista."""
    
    def post(self, request, pk):
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Intentando marcar notificación {pk} como vista para usuario {request.user.username}")
            
            # Obtener la notificación sin restricción de usuario
            # Cualquier usuario autenticado puede marcar cualquier notificación como vista
            notificacion = Notificacion.objects.get(pk=pk)
            logger.info(f"Notificación encontrada: {notificacion.pk}, usuario original: {notificacion.usuario.username}, vista: {notificacion.vista}")
            
            # Marcar como vista
            notificacion.marcar_como_vista()
            logger.info(f"Notificación {pk} marcada como vista exitosamente por usuario {request.user.username}")
            
            return JsonResponse({'success': True, 'message': 'Notificación marcada como vista'})
        except Notificacion.DoesNotExist:
            logger.warning(f"Notificación {pk} no existe en la base de datos")
            return JsonResponse({
                'success': False, 
                'message': 'Notificación no encontrada. Puede que ya haya sido eliminada.'
            }, status=404)
        except Exception as e:
            logger.error(f"Error al marcar notificación {pk} como vista: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'message': f'Error del servidor: {str(e)}'}, status=500)


class EliminarNotificacionView(LoginRequiredMixin, View):
    """Vista AJAX para eliminar una notificación."""
    
    def post(self, request, pk):
        try:
            notificacion = Notificacion.objects.get(pk=pk, usuario=request.user)
            notificacion.delete()
            return JsonResponse({'success': True, 'message': 'Notificación eliminada'})
        except Notificacion.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Notificación no encontrada'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


class IncrementarCotizacionClienteView(LoginRequiredMixin, View):
    """Incrementa el contador de cotizaciones generadas por un cliente asociado a una venta."""

    def post(self, request, slug, pk, *args, **kwargs):
        try:
            venta = get_object_or_404(VentaViaje, slug=slug, pk=pk)
            cliente = venta.cliente
            Cliente.objects.filter(pk=cliente.pk).update(
                cotizaciones_generadas=F('cotizaciones_generadas') + 1
            )
            cliente.refresh_from_db(fields=['cotizaciones_generadas'])
            return JsonResponse({'success': True, 'total': cliente.cotizaciones_generadas})
        except VentaViaje.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Venta no encontrada'}, status=404)
        except Exception as exc:
            logger.exception("Error incrementando cotizaciones para la venta %s", pk)
            return JsonResponse({'success': False, 'message': str(exc)}, status=500)


class GenerarCotizacionDocxView(LoginRequiredMixin, View):
    """Genera una cotización en formato DOCX usando la plantilla con membrete."""

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'message': 'Formato JSON inválido.'}, status=400)

        cotizacion = payload.get('cotizacion') or {}
        general = cotizacion.get('general') or {}
        tipo = cotizacion.get('tipo')

        if not tipo:
            return JsonResponse({'success': False, 'message': 'El tipo de cotización es obligatorio.'}, status=400)

        venta = None
        cliente_nombre = general.get('cliente') or ''
        venta_id = payload.get('venta_id')

        if venta_id:
            venta = VentaViaje.objects.filter(pk=venta_id).select_related('cliente').first()
            if venta:
                cliente_nombre = cliente_nombre or venta.cliente.nombre_completo_display
                Cliente.objects.filter(pk=venta.cliente.pk).update(
                    cotizaciones_generadas=F('cotizaciones_generadas') + 1
                )

        general['cliente'] = cliente_nombre

        template_path = os.path.join(settings.BASE_DIR, 'static', 'docx', 'membrete.docx')
        if not os.path.exists(template_path):
            return JsonResponse({'success': False, 'message': 'La plantilla DOCX no fue encontrada en static/docx/membrete.docx.'}, status=500)

        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Inches
            from docx.oxml.ns import qn
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError:
            return JsonResponse({'success': False, 'message': 'python-docx no está instalado en el entorno.'}, status=500)

        def format_date(value):
            if not value:
                return '-'
            try:
                if isinstance(value, datetime.date):
                    parsed = value
                else:
                    parsed = datetime.date.fromisoformat(str(value))
                return parsed.strftime('%d/%m/%Y')
            except Exception:
                return str(value)

        def format_currency(value):
            if value in (None, '', 0):
                return '0.00'
            try:
                number = Decimal(str(value).replace(',', ''))
            except Exception:
                return str(value)
            return f"{number:,.2f}"

        doc = Document(template_path)

        section = doc.sections[0]

        MOVUMS_BLUE = RGBColor(15, 92, 192)
        MOVUMS_LIGHT_BLUE = RGBColor(92, 141, 214)
        TEXT_COLOR = RGBColor(20, 20, 20)

        style = doc.styles['Normal']
        style.font.name = 'Arial'
        style.font.size = Pt(12)
        style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')

        def set_run_font(run, size=12, bold=False, color=TEXT_COLOR):
            run.font.name = 'Arial'
            run.font.size = Pt(size)
            run.bold = bold
            run.font.color.rgb = color

        def add_paragraph(doc_obj, text='', size=12, bold=False, color=TEXT_COLOR, space_before=0, space_after=0):
            paragraph = doc_obj.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(space_before)
            paragraph.paragraph_format.space_after = Pt(space_after)
            run = paragraph.add_run(text)
            set_run_font(run, size=size, bold=bold, color=color)
            return paragraph

        # Respetar el membretado existente de la plantilla desplazando el contenido hacia abajo
        # sin párrafos extra: respetamos el margen del membrete pero iniciamos lo antes posible

        fecha_paragraph = doc.add_paragraph()
        fecha_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        fecha_paragraph.paragraph_format.space_after = Pt(6)
        fecha_run = fecha_paragraph.add_run(f"Fecha de Cotización: {format_date(general.get('fechaCotizacion'))}")
        set_run_font(fecha_run, size=14, bold=True, color=MOVUMS_BLUE)

        info_table = doc.add_table(rows=4, cols=3)
        info_data = [
            ("Origen / Destino", general.get('origen') or '-', general.get('destino') or '-'),
            ("Inicio / Fin", format_date(general.get('fechaInicio')), format_date(general.get('fechaFin'))),
            ("Pasajeros", general.get('pasajeros') or '1', f"{general.get('adultos') or 0} Adultos / {general.get('menores') or 0} Menores"),
            ("Viaje", f"{general.get('dias') or '-'} días", f"{general.get('noches') or '-'} noches"),
        ]
        for row_idx, (label, v1, v2) in enumerate(info_data):
            row = info_table.rows[row_idx].cells
            label_run = row[0].paragraphs[0].add_run(label)
            set_run_font(label_run, size=14, bold=True, color=MOVUMS_BLUE)
            val1_run = row[1].paragraphs[0].add_run(v1)
            set_run_font(val1_run, size=12)
            val2_run = row[2].paragraphs[0].add_run(v2)
            set_run_font(val2_run, size=12)

        add_paragraph(doc, "", space_after=6)
        
        # Salto de línea entre la información general y el contenido de la cotización
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)

        # Funciones helper para el nuevo formato (similar a confirmaciones)
        MOVUMS_BLUE_CORP = RGBColor(0, 74, 142)  # Color corporativo #004a8e
        
        def agregar_subtitulo_con_vineta(texto):
            """Agrega un subtítulo con viñeta azul."""
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            bullet_run = p.add_run('• ')
            set_run_font(bullet_run, size=14, bold=True, color=MOVUMS_BLUE_CORP)
            texto_run = p.add_run(texto)
            set_run_font(texto_run, size=14, bold=True, color=MOVUMS_BLUE_CORP)
            spacer = doc.add_paragraph()
            spacer.paragraph_format.space_after = Pt(2)
            return p
        
        def agregar_info_line(etiqueta, valor):
            """Agrega una línea de información."""
            if not valor:
                return
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            label_run = p.add_run(f'{etiqueta}: ')
            set_run_font(label_run, size=12, bold=True)
            value_run = p.add_run(str(valor))
            set_run_font(value_run, size=12)
            return p
        
        def agregar_info_inline(*pares_etiqueta_valor, separador=' | '):
            """Agrega múltiples campos en una sola línea."""
            if not pares_etiqueta_valor:
                return
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            for idx, (etiqueta, valor) in enumerate(pares_etiqueta_valor):
                if not valor:
                    continue
                if idx > 0:
                    sep_run = p.add_run(separador)
                    set_run_font(sep_run, size=12)
                label_run = p.add_run(f'{etiqueta}: ')
                set_run_font(label_run, size=12, bold=True)
                value_run = p.add_run(str(valor))
                set_run_font(value_run, size=12)
            return p
        
        def agregar_salto_entre_secciones():
            """Agrega un salto de línea entre secciones."""
            spacer = doc.add_paragraph()
            spacer.paragraph_format.space_after = Pt(6)
            return spacer
        
        def agregar_titulo_principal(texto):
            """Agrega un título principal (tamaño 18)."""
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(10)
            run = p.add_run(texto)
            set_run_font(run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
            return p

        def render_vuelos(vuelos):
            """Renderiza cotización de vuelos con el nuevo formato."""
            for vuelo in vuelos:
                agregar_titulo_principal("VUELO")
                
                agregar_subtitulo_con_vineta('Información del Vuelo')
                agregar_info_inline(
                    ('Aerolínea', vuelo.get('aerolinea') or '-'),
                    ('Salida', vuelo.get('salida') or '-'),
                    ('Regreso', vuelo.get('regreso') or '-')
                )
                agregar_info_line('Incluye', vuelo.get('incluye') or '-')
                
                # Forma de pago si está presente
                if vuelo.get('forma_pago'):
                    agregar_info_line('Forma de Pago', vuelo.get('forma_pago'))
                
                # Total sin viñeta, tamaño 18 y subrayado (sin salto antes)
                total_p = doc.add_paragraph()
                total_p.paragraph_format.space_before = Pt(0)
                total_p.paragraph_format.space_after = Pt(6)
                total_run = total_p.add_run(f"Total MXN {format_currency(vuelo.get('total'))} Pesos")
                set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
                total_run.font.underline = True
                
                agregar_salto_entre_secciones()

        def render_hospedaje(hoteles):
            """Renderiza cotización de hospedaje con el nuevo formato."""
            for hotel in hoteles:
                agregar_titulo_principal("HOSPEDAJE")
                
                agregar_subtitulo_con_vineta('Información del Alojamiento')
                
                # Crear tabla de 2 columnas para la información (como muestra la imagen)
                info_table = doc.add_table(rows=4, cols=2)
                info_table.autofit = False
                
                # Configurar ancho de columnas (50% cada una)
                for col in info_table.columns:
                    for cell in col.cells:
                        cell.width = Inches(3.25)
                
                # Columna izquierda: Nombre, Habitación, Dirección
                # Nombre (fila 0, columna 0)
                nombre_cell = info_table.rows[0].cells[0]
                nombre_label = nombre_cell.paragraphs[0].add_run('Nombre: ')
                set_run_font(nombre_label, size=12, bold=True)
                nombre_val = nombre_cell.paragraphs[0].add_run(hotel.get('nombre') or 'Hotel propuesto')
                set_run_font(nombre_val, size=12)
                
                # Habitación (fila 1, columna 0)
                habitacion_cell = info_table.rows[1].cells[0]
                habitacion_label = habitacion_cell.paragraphs[0].add_run('Habitación: ')
                set_run_font(habitacion_label, size=12, bold=True)
                habitacion_val = habitacion_cell.paragraphs[0].add_run(hotel.get('habitacion') or '-')
                set_run_font(habitacion_val, size=12)
                
                # Dirección (fila 2, columna 0)
                direccion_cell = info_table.rows[2].cells[0]
                direccion_label = direccion_cell.paragraphs[0].add_run('Dirección: ')
                set_run_font(direccion_label, size=12, bold=True)
                direccion_val = direccion_cell.paragraphs[0].add_run(hotel.get('direccion') or '-')
                set_run_font(direccion_val, size=12)
                
                # Columna derecha: Plan de Alimentos (fila 0, columna 1)
                plan_cell = info_table.rows[0].cells[1]
                plan_label = plan_cell.paragraphs[0].add_run('Plan de Alimentos: ')
                set_run_font(plan_label, size=12, bold=True)
                plan_val = plan_cell.paragraphs[0].add_run(hotel.get('plan') or '-')
                set_run_font(plan_val, size=12)
                
                # Forma de Pago (en la segunda columna, segunda fila) si está presente
                if hotel.get('forma_pago'):
                    forma_pago_cell = info_table.rows[1].cells[1]
                    forma_pago_label = forma_pago_cell.paragraphs[0].add_run('Forma de Pago: ')
                    set_run_font(forma_pago_label, size=12, bold=True)
                    forma_pago_val = forma_pago_cell.paragraphs[0].add_run(hotel.get('forma_pago'))
                    set_run_font(forma_pago_val, size=12)
                
                # Total sin viñeta, tamaño 18 y subrayado (sin salto antes)
                total_p = doc.add_paragraph()
                total_p.paragraph_format.space_before = Pt(0)
                total_p.paragraph_format.space_after = Pt(6)
                total_run = total_p.add_run(f"Total MXN {format_currency(hotel.get('total'))} Pesos")
                set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
                total_run.font.underline = True
                
                agregar_salto_entre_secciones()

        def render_tours(tours_data):
            """Renderiza cotización de tours con el nuevo formato."""
            agregar_titulo_principal("TOUR")
            
            agregar_subtitulo_con_vineta('Información del Tour')
            agregar_info_line('Número de Reserva', tours_data.get('numero_reserva') or '-')
            agregar_info_line('Nombre del Tour', tours_data.get('nombre') or '-')
            
            if tours_data.get('especificaciones'):
                agregar_salto_entre_secciones()
                agregar_subtitulo_con_vineta('Especificaciones')
                especificaciones = tours_data.get('especificaciones', '').strip()
                if especificaciones:
                    lineas = especificaciones.split('\n')
                    for linea in lineas:
                        if linea.strip():
                            p = doc.add_paragraph()
                            p.paragraph_format.space_after = Pt(4)
                            run = p.add_run(linea.strip())
                            set_run_font(run, size=12)
            
            if tours_data.get('forma_pago'):
                agregar_salto_entre_secciones()
                agregar_subtitulo_con_vineta('Forma de Pago')
                agregar_info_line('Forma de Pago', tours_data.get('forma_pago'))
            
            agregar_salto_entre_secciones()

        def render_paquete(paquete):
            """Renderiza cotización de paquete con el nuevo formato."""
            vuelo = paquete.get('vuelo') or {}
            hotel = paquete.get('hotel') or {}
            
            agregar_titulo_principal("PAQUETE")
            
            agregar_subtitulo_con_vineta('Vuelo')
            agregar_info_inline(
                ('Aerolínea', vuelo.get('aerolinea') or '-'),
                ('Salida', vuelo.get('salida') or '-'),
                ('Regreso', vuelo.get('regreso') or '-')
            )
            agregar_info_line('Incluye', vuelo.get('incluye') or '-')
            
            # Total y Forma de pago del vuelo si están presentes
            if vuelo.get('total'):
                agregar_info_line('Total MXN', format_currency(vuelo.get('total')))
            if vuelo.get('forma_pago'):
                agregar_info_line('Forma de Pago', vuelo.get('forma_pago'))
            
            agregar_salto_entre_secciones()
            
            agregar_subtitulo_con_vineta('Hospedaje')
            
            # Crear tabla de 2 columnas para la información del hospedaje
            # Aumentar filas para incluir todos los campos
            num_filas = 5  # Nombre, Habitación, Dirección, Plan, Notas
            hospedaje_table = doc.add_table(rows=num_filas, cols=2)
            hospedaje_table.autofit = False
            
            # Configurar ancho de columnas (50% cada una)
            for col in hospedaje_table.columns:
                for cell in col.cells:
                    cell.width = Inches(3.25)
            
            # Nombre
            nombre_cell = hospedaje_table.rows[0].cells[0]
            nombre_label = nombre_cell.paragraphs[0].add_run('Nombre: ')
            set_run_font(nombre_label, size=12, bold=True)
            nombre_val = nombre_cell.paragraphs[0].add_run(hotel.get('nombre') or 'Hotel incluido')
            set_run_font(nombre_val, size=12)
            
            # Habitación
            habitacion_cell = hospedaje_table.rows[1].cells[0]
            habitacion_label = habitacion_cell.paragraphs[0].add_run('Habitación: ')
            set_run_font(habitacion_label, size=12, bold=True)
            habitacion_val = habitacion_cell.paragraphs[0].add_run(hotel.get('habitacion') or '-')
            set_run_font(habitacion_val, size=12)
            
            # Dirección
            direccion_cell = hospedaje_table.rows[2].cells[0]
            direccion_label = direccion_cell.paragraphs[0].add_run('Dirección: ')
            set_run_font(direccion_label, size=12, bold=True)
            direccion_val = direccion_cell.paragraphs[0].add_run(hotel.get('direccion') or '-')
            set_run_font(direccion_val, size=12)
            
            # Plan de alimentos
            plan_cell = hospedaje_table.rows[3].cells[0]
            plan_label = plan_cell.paragraphs[0].add_run('Plan de alimentos: ')
            set_run_font(plan_label, size=12, bold=True)
            plan_val = plan_cell.paragraphs[0].add_run(hotel.get('plan') or '-')
            set_run_font(plan_val, size=12)
            
            # Notas
            notas_cell = hospedaje_table.rows[4].cells[0]
            notas_label = notas_cell.paragraphs[0].add_run('Notas: ')
            set_run_font(notas_label, size=12, bold=True)
            notas_val = notas_cell.paragraphs[0].add_run(hotel.get('notas') or '-')
            set_run_font(notas_val, size=12)
            
            # Total y Forma de pago del hotel si están presentes
            if hotel.get('total'):
                agregar_info_line('Total MXN', format_currency(hotel.get('total')))
            if hotel.get('forma_pago'):
                agregar_info_line('Forma de Pago', hotel.get('forma_pago'))
            
            # Forma de pago del paquete si está presente
            if paquete.get('forma_pago'):
                agregar_info_line('Forma de Pago del Paquete', paquete.get('forma_pago'))
            
            # Total sin viñeta, tamaño 18 y subrayado (sin salto antes)
            total_p = doc.add_paragraph()
            total_p.paragraph_format.space_before = Pt(0)
            total_p.paragraph_format.space_after = Pt(6)
            total_run = total_p.add_run(f"Total MXN {format_currency(paquete.get('total'))} Pesos")
            set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
            total_run.font.underline = True
            
            agregar_salto_entre_secciones()
            
            agregar_subtitulo_con_vineta('Términos y Condiciones')
            terms = [
                "Los boletos de avión no son reembolsables.",
                "Una vez emitido el boleto no puede ser asignado a otra persona o aerolínea.",
                "Los cambios pueden generar cargos extra y están sujetos a disponibilidad y políticas de cada aerolínea.",
                "Para vuelos nacionales presentarse 2 horas antes; para internacionales 3 horas antes.",
                "Las tarifas están sujetas a cambios y disponibilidad mientras no se reserve.",
            ]
            for term in terms:
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(4)
                bullet_run = p.add_run('• ')
                set_run_font(bullet_run, size=12)
                term_run = p.add_run(term)
                set_run_font(term_run, size=12)
            
            agregar_salto_entre_secciones()

        if tipo == 'vuelos':
            render_vuelos(cotizacion.get('vuelos') or [])
        elif tipo == 'hospedaje':
            render_hospedaje(cotizacion.get('hoteles') or [])
        elif tipo == 'tours':
            render_tours(cotizacion.get('tours') or {})
        elif tipo == 'paquete':
            render_paquete(cotizacion.get('paquete') or {})

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        filename_cliente = slugify(general.get('cliente') or 'movums')
        filename = f"cotizacion_{filename_cliente}_{timezone.now().strftime('%Y%m%d%H%M%S')}.docx"
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

# ------------------- PLANTILLAS DE CONFIRMACIÓN -------------------

class ListarConfirmacionesView(LoginRequiredMixin, DetailView):
    """
    Vista para listar todas las plantillas de confirmación de una venta.
    """
    model = VentaViaje
    template_name = 'ventas/listar_confirmaciones.html'
    context_object_name = 'venta'
    
    def get_object(self, queryset=None):
        pk = self.kwargs.get('pk')
        slug = self.kwargs.get('slug')
        return get_object_or_404(VentaViaje, pk=pk, slug=slug)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        venta = context['venta']
        context['plantillas'] = PlantillaConfirmacion.objects.filter(venta=venta).order_by('tipo', '-fecha_creacion')
        
        # Obtener los servicios contratados para filtrar qué plantillas mostrar
        servicios_contratados = []
        if venta.servicios_seleccionados:
            servicios_contratados = [s.strip() for s in venta.servicios_seleccionados.split(',')]
        
        # Determinar qué plantillas mostrar según los servicios contratados
        plantillas_disponibles = {
            'mostrar_vuelo_unico': 'VUE' in servicios_contratados,
            'mostrar_vuelo_redondo': 'VUE' in servicios_contratados,
            'mostrar_hospedaje': 'HOS' in servicios_contratados,
            'mostrar_traslado': 'TRA' in servicios_contratados,
            'mostrar_generica': True,  # La genérica siempre está disponible
        }
        
        context.update(plantillas_disponibles)
        return context


class CrearPlantillaConfirmacionView(LoginRequiredMixin, View):
    """
    Vista base para crear una plantilla de confirmación.
    Las vistas específicas heredan de esta y definen el tipo.
    """
    tipo_plantilla = None
    template_name = None
    
    def dispatch(self, request, *args, **kwargs):
        if not self.tipo_plantilla or not self.template_name:
            raise ValueError("Las vistas hijas deben definir 'tipo_plantilla' y 'template_name'")
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, pk, slug):
        venta = get_object_or_404(VentaViaje, pk=pk, slug=slug)
        # Si ya existe una plantilla de este tipo, la editamos en lugar de crear una nueva
        plantilla = PlantillaConfirmacion.objects.filter(venta=venta, tipo=self.tipo_plantilla).first()
        
        # Datos por defecto según el tipo
        datos_default = self.get_datos_default()
        
        if plantilla:
            # Si existe, usamos sus datos existentes, sino los defaults
            datos = plantilla.datos if plantilla.datos else datos_default
        else:
            datos = datos_default
        
        # Asegurar que escalas existe y es una lista
        if 'escalas' not in datos:
            datos['escalas'] = []
        elif not isinstance(datos['escalas'], list):
            datos['escalas'] = []
        
        # Convertir escalas a JSON para el template
        escalas_json = json.dumps(datos.get('escalas', []))
        
        # Para hospedaje, construir la URL completa de la imagen si existe
        if self.tipo_plantilla == 'HOSPEDAJE' and datos.get('imagen_hospedaje_url'):
            from django.conf import settings
            # Si la URL ya es absoluta, usarla tal cual, sino construirla
            if datos['imagen_hospedaje_url'].startswith('http'):
                datos['imagen_hospedaje_url'] = datos['imagen_hospedaje_url']
            else:
                # Asegurar que la URL empiece con /media/
                if not datos['imagen_hospedaje_url'].startswith('/'):
                    datos['imagen_hospedaje_url'] = f"/{datos['imagen_hospedaje_url']}"
        
        # Para traslados, preparar la lista de traslados
        traslados_json = "[]"
        if self.tipo_plantilla == 'TRASLADO':
            if 'traslados' in datos and isinstance(datos['traslados'], list) and len(datos['traslados']) > 0:
                traslados_json = json.dumps(datos['traslados'])
            else:
                # Si no hay traslados, crear uno con datos por defecto
                traslados_json = json.dumps([self.get_datos_default().get('TRASLADO', {})])
        
        # Para vuelo redondo, preparar escalas de ida y regreso
        escalas_ida_json = "[]"
        escalas_regreso_json = "[]"
        if self.tipo_plantilla == 'VUELO_REDONDO':
            if 'escalas_ida' not in datos:
                datos['escalas_ida'] = []
            if 'escalas_regreso' not in datos:
                datos['escalas_regreso'] = []
            escalas_ida_json = json.dumps(datos.get('escalas_ida', []))
            escalas_regreso_json = json.dumps(datos.get('escalas_regreso', []))
        
        context = {
            'venta': venta,
            'tipo_plantilla': self.tipo_plantilla,
            'datos': datos,
            'plantilla': plantilla,
            'escalas_json': escalas_json,
            'traslados_json': traslados_json,
            'escalas_ida_json': escalas_ida_json,
            'escalas_regreso_json': escalas_regreso_json,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, pk, slug):
        venta = get_object_or_404(VentaViaje, pk=pk, slug=slug)
        
        # Recopilar todos los datos del POST
        datos = {}
        escalas = []
        
        # Procesar escalas si existen (formato: escalas[0][ciudad], escalas[0][aeropuerto], etc.)
        import re
        escalas_dict = {}
        
        for key, value in request.POST.items():
            if key.startswith('escalas[') and not key.startswith('escalas_ida[') and not key.startswith('escalas_regreso['):
                # Extraer el índice y el campo de la escala (para vuelo único)
                match = re.match(r'escalas\[(\d+)\]\[(\w+)\]', key)
                if match:
                    escala_index = int(match.group(1))
                    campo = match.group(2)
                    if escala_index not in escalas_dict:
                        escalas_dict[escala_index] = {}
                    escalas_dict[escala_index][campo] = value
            elif key.startswith('escalas_ida[') or key.startswith('escalas_regreso[') or key.startswith('traslados['):
                # Estos se procesan por separado más abajo
                continue
            elif key not in ['csrfmiddlewaretoken']:
                datos[key] = value
        
        # Convertir escalas_dict a lista ordenada
        if escalas_dict:
            for i in sorted(escalas_dict.keys()):
                escalas.append(escalas_dict[i])
            datos['escalas'] = escalas
        elif self.tipo_plantilla == 'VUELO_UNICO':
            datos['escalas'] = []
        
        # Procesar escalas de ida y regreso para vuelo redondo
        if self.tipo_plantilla == 'VUELO_REDONDO':
            # Escalas de Ida
            escalas_ida_dict = {}
            for key, value in request.POST.items():
                if key.startswith('escalas_ida['):
                    match = re.match(r'escalas_ida\[(\d+)\]\[(.*?)\]', key)
                    if match:
                        idx = int(match.group(1))
                        campo = match.group(2)
                        if idx not in escalas_ida_dict:
                            escalas_ida_dict[idx] = {}
                        escalas_ida_dict[idx][campo] = value
            
            if escalas_ida_dict:
                escalas_ida = []
                for i in sorted(escalas_ida_dict.keys()):
                    escalas_ida.append(escalas_ida_dict[i])
                datos['escalas_ida'] = escalas_ida
            else:
                datos['escalas_ida'] = []
            
            # Escalas de Regreso
            escalas_regreso_dict = {}
            for key, value in request.POST.items():
                if key.startswith('escalas_regreso['):
                    match = re.match(r'escalas_regreso\[(\d+)\]\[(.*?)\]', key)
                    if match:
                        idx = int(match.group(1))
                        campo = match.group(2)
                        if idx not in escalas_regreso_dict:
                            escalas_regreso_dict[idx] = {}
                        escalas_regreso_dict[idx][campo] = value
            
            if escalas_regreso_dict:
                escalas_regreso = []
                for i in sorted(escalas_regreso_dict.keys()):
                    escalas_regreso.append(escalas_regreso_dict[i])
                datos['escalas_regreso'] = escalas_regreso
            else:
                datos['escalas_regreso'] = []
        
        # Procesar múltiples traslados si existe
        if self.tipo_plantilla == 'TRASLADO':
            traslados = []
            traslados_count = int(request.POST.get('traslados_count', 0))
            traslados_dict = {}
            
            # Recopilar todos los campos de traslados
            for key, value in request.POST.items():
                if key.startswith('traslados['):
                    match = re.match(r'traslados\[(\d+)\]\[(\w+)\]', key)
                    if match:
                        idx = int(match.group(1))
                        campo = match.group(2)
                        if idx not in traslados_dict:
                            traslados_dict[idx] = {}
                        traslados_dict[idx][campo] = value
            
            # Convertir a lista ordenada
            if traslados_dict:
                for i in sorted(traslados_dict.keys()):
                    traslados.append(traslados_dict[i])
            
            if traslados:
                datos['traslados'] = traslados
            else:
                # Si no hay traslados en POST, crear uno vacío
                datos['traslados'] = []
        
        # Buscar si ya existe una plantilla de este tipo
        plantilla, created = PlantillaConfirmacion.objects.get_or_create(
            venta=venta,
            tipo=self.tipo_plantilla,
            defaults={
                'datos': datos,
                'creado_por': request.user
            }
        )
        
        # Manejar imagen en base64 para plantilla de hospedaje
        if self.tipo_plantilla == 'HOSPEDAJE' and datos.get('imagen_hospedaje_base64'):
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile
            import uuid
            import base64
            
            try:
                # Decodificar base64
                base64_data = datos['imagen_hospedaje_base64']
                # Remover el prefijo data:image/...;base64, si existe
                extension = 'png'  # Por defecto
                if ',' in base64_data:
                    header, base64_data = base64_data.split(',', 1)
                    # Intentar obtener extensión del header MIME
                    if 'image/png' in header:
                        extension = 'png'
                    elif 'image/jpeg' in header or 'image/jpg' in header:
                        extension = 'jpg'
                    elif 'image/gif' in header:
                        extension = 'gif'
                    elif 'image/webp' in header:
                        extension = 'webp'
                
                imagen_data = base64.b64decode(base64_data)
                
                # Generar nombre único para la imagen
                nombre_archivo = f"hospedaje_{venta.pk}_{uuid.uuid4().hex[:8]}.{extension}"
                ruta = default_storage.save(
                    f'plantillas_confirmacion/{nombre_archivo}',
                    ContentFile(imagen_data)
                )
                # Guardar la URL
                url_completa = default_storage.url(ruta)
                datos['imagen_hospedaje_url'] = url_completa
                # Remover el base64 de los datos (no queremos guardarlo)
                datos.pop('imagen_hospedaje_base64', None)
            except Exception as e:
                # Si hay error, no guardar la imagen pero continuar
                logger.error(f"Error al procesar imagen base64: {e}", exc_info=True)
                datos.pop('imagen_hospedaje_base64', None)
        
        # Si no se subió nueva imagen pero ya existe una, preservarla
        if not created and self.tipo_plantilla == 'HOSPEDAJE':
            if 'imagen_hospedaje_url' not in datos and plantilla.datos.get('imagen_hospedaje_url'):
                datos['imagen_hospedaje_url'] = plantilla.datos.get('imagen_hospedaje_url')
        
        if not created:
            # Actualizar la existente
            plantilla.datos = datos
            if not plantilla.creado_por:
                plantilla.creado_por = request.user
            plantilla.save()
        
        messages.success(request, f"Plantilla {self.get_tipo_display()} guardada correctamente.")
        return redirect('listar_confirmaciones', pk=venta.pk, slug=venta.slug_safe)
    
    def get_datos_default(self):
        """Retorna los datos por defecto según el tipo de plantilla."""
        defaults = {
            'VUELO_UNICO': {
                'clave_reserva': '',
                'numero_vuelo': '',
                'aerolinea': '',
                'fecha': '',
                'hora_salida': '',
                'hora_llegada': '',
                'origen_terminal': '',
                'destino_terminal': '',
                'tipo_vuelo': '',
                'escalas': [],
                'equipaje': '',
                'pasajeros': '',
                'vuelo': '',
            },
            'VUELO_REDONDO': {
                'clave_reserva': '',
                'numero_vuelo_ida': '',
                'aerolinea_ida': '',
                'fecha_salida_ida': '',
                'hora_salida_ida': '',
                'hora_llegada_ida': '',
                'origen_ida': '',
                'destino_ida': '',
                'numero_vuelo_regreso': '',
                'aerolinea_regreso': '',
                'fecha_salida_regreso': '',
                'hora_salida_regreso': '',
                'hora_llegada_regreso': '',
                'origen_regreso': '',
                'destino_regreso': '',
                'pasajeros': '',
                'equipaje': '',
            },
            'HOSPEDAJE': {
                'nombre_alojamiento': '',
                'numero_referencia': '',
                'fecha_checkin': '',
                'fecha_checkout': '',
                'tipo_habitacion': '',
                'adultos': '1',
                'ninos': '0',
                'regimen': '',
                'viajero_principal': '',
                'observaciones': '',
                'imagen_hospedaje_url': '',
            },
            'TRASLADO': {
                'compania': '',
                'codigo_reserva': '',
                'tipo_servicio': '',
                'horario_inicio': '',
                'desde': '',
                'hasta': '',
                'adultos': '1',
                'ninos': '0',
                'informacion_adicional': '',
            },
            'GENERICA': {
                'titulo': '',
                'contenido': '',
            },
        }
        return defaults.get(self.tipo_plantilla, {})
    
    def get_tipo_display(self):
        """Retorna el nombre legible del tipo de plantilla."""
        return dict(PlantillaConfirmacion.TIPO_CHOICES).get(self.tipo_plantilla, self.tipo_plantilla)


# Vistas específicas para cada tipo de plantilla
class CrearVueloUnicoView(CrearPlantillaConfirmacionView):
    tipo_plantilla = 'VUELO_UNICO'
    template_name = 'ventas/plantillas/vuelo_unico.html'


class CrearVueloRedondoView(CrearPlantillaConfirmacionView):
    tipo_plantilla = 'VUELO_REDONDO'
    template_name = 'ventas/plantillas/vuelo_redondo.html'


class CrearHospedajeView(CrearPlantillaConfirmacionView):
    tipo_plantilla = 'HOSPEDAJE'
    template_name = 'ventas/plantillas/hospedaje.html'


class CrearTrasladoView(CrearPlantillaConfirmacionView):
    tipo_plantilla = 'TRASLADO'
    template_name = 'ventas/plantillas/traslado.html'


class CrearGenericaView(CrearPlantillaConfirmacionView):
    tipo_plantilla = 'GENERICA'
    template_name = 'ventas/plantillas/generica.html'


class EliminarPlantillaConfirmacionView(LoginRequiredMixin, View):
    """Vista para eliminar una plantilla de confirmación."""
    
    def post(self, request, pk, slug, plantilla_pk):
        venta = get_object_or_404(VentaViaje, pk=pk, slug=slug)
        plantilla = get_object_or_404(PlantillaConfirmacion, pk=plantilla_pk, venta=venta)
        
        tipo_nombre = plantilla.get_tipo_display()
        plantilla.delete()
        
        messages.success(request, f'Plantilla "{tipo_nombre}" eliminada correctamente.')
        return redirect('listar_confirmaciones', pk=pk, slug=slug)


class GenerarDocumentoConfirmacionView(LoginRequiredMixin, DetailView):
    def _asegurar_estilo_heading(self, doc, style_name, size_pt):
        """Garantiza que exista un estilo de encabezado con nombre dado."""
        from docx.enum.style import WD_STYLE_TYPE
        from docx.shared import Pt

        styles = doc.styles
        try:
            styles[style_name]
        except KeyError:
            normal = styles['Normal']
            nuevo = styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
            nuevo.base_style = normal
            font = nuevo.font
            font.name = 'Arial'
            font.size = Pt(size_pt)

    """
    Vista para generar un documento .docx combinando todas las plantillas de confirmación de una venta.
    """
    model = VentaViaje
    
    def _normalizar_texto(self, texto):
        """
        Normaliza un texto limpiando espacios y saltos de línea excesivos.
        Convierte múltiples saltos de línea en uno solo y elimina espacios extras.
        """
        if not texto:
            return texto
        
        import re
        texto = str(texto)
        # Reemplazar múltiples saltos de línea consecutivos por uno solo o espacio
        texto = re.sub(r'\n\s*\n+', '\n', texto)
        # Reemplazar múltiples espacios o tabs por uno solo
        texto = re.sub(r'[ \t]+', ' ', texto)
        # Eliminar saltos de línea solitarios entre palabras (convertirlos a espacio)
        texto = re.sub(r'(?<!\n)\n(?!\n)', ' ', texto)
        # Eliminar espacios al inicio y final
        texto = texto.strip()
        # Limpiar espacios múltiples nuevamente después de convertir saltos de línea
        texto = re.sub(r'[ \t]+', ' ', texto)
        return texto
    
    def _capitalizar_nombre_propio(self, texto):
        """
        Capitaliza nombres propios correctamente según reglas del español.
        Primera letra mayúscula, resto minúsculas.
        Maneja nombres compuestos y artículos/preposiciones.
        """
        if not texto:
            return texto
        
        import re
        texto = str(texto).strip()
        if not texto:
            return texto
        
        # Palabras que deben mantenerse en minúsculas cuando están en medio de un nombre
        # (artículos, preposiciones)
        palabras_minusculas = {
            'de', 'del', 'la', 'las', 'el', 'los', 'y', 'e', 'o', 'u',
            'a', 'al', 'con', 'en', 'por', 'para', 'sin', 'sobre', 'entre',
            'da', 'das', 'do', 'dos', 'von', 'van', 'le', 'les'
        }
        
        # Palabras que siempre deben ir en mayúscula (apellidos comunes, títulos)
        palabras_mayusculas = {'iii', 'ii', 'iv', 'sr', 'sra', 'srta', 'dr', 'dra', 'mtro', 'mtra'}
        
        # Convertir todo a minúsculas primero (preservando estructura)
        texto_lower = texto.lower()
        
        # Dividir por espacios para procesar palabra por palabra
        palabras = texto_lower.split()
        palabras_capitalizadas = []
        
        for i, palabra_orig in enumerate(palabras):
            # Limpiar la palabra de separadores al inicio/final pero preservar estructura
            palabra = palabra_orig.strip()
            
            if not palabra:
                continue
            
            # Manejar palabras con guiones o apóstrofes
            tiene_guion = '-' in palabra
            tiene_apostrofe = "'" in palabra
            
            if tiene_guion or tiene_apostrofe:
                # Dividir por guiones/apóstrofes y capitalizar cada parte
                partes = re.split(r'([\-\']+)', palabra)
                partes_cap = []
                for j, parte in enumerate(partes):
                    if parte in ['-', "'"]:
                        partes_cap.append(parte)
                    elif parte.strip():
                        if j == 0 or (j > 0 and partes[j-1] in ['-', "'"]):
                            # Capitalizar después de guion/apóstrofe
                            partes_cap.append(parte[0].upper() + parte[1:] if len(parte) > 1 else parte.upper())
                        else:
                            partes_cap.append(parte)
                palabra_final = ''.join(partes_cap)
            else:
                # Procesar palabra normal
                if i == 0:
                    # Primera palabra siempre capitalizada
                    palabra_final = palabra[0].upper() + palabra[1:] if len(palabra) > 1 else palabra.upper()
                elif palabra in palabras_mayusculas:
                    # Títulos y números romanos en mayúsculas
                    palabra_final = palabra.upper()
                elif palabra in palabras_minusculas:
                    # Artículos/preposiciones en minúsculas (excepto si es la última palabra)
                    palabra_final = palabra if i < len(palabras) - 1 else palabra[0].upper() + palabra[1:] if len(palabra) > 1 else palabra.upper()
                else:
                    # Capitalizar normalmente
                    palabra_final = palabra[0].upper() + palabra[1:] if len(palabra) > 1 else palabra.upper()
            
            palabras_capitalizadas.append(palabra_final)
        
        # Reconstruir el texto con espacios
        texto_final = ' '.join(palabras_capitalizadas)
        # Limpiar espacios múltiples
        texto_final = re.sub(r'[ \t]+', ' ', texto_final).strip()
        
        return texto_final
    
    def _normalizar_valor_campo(self, valor, es_nombre_propio=False, limpiar_saltos_linea=True):
        """
        Normaliza un valor de campo aplicando las transformaciones necesarias.
        
        Args:
            valor: El valor a normalizar
            es_nombre_propio: Si es True, aplica capitalización de nombre propio
            limpiar_saltos_linea: Si es True, limpia saltos de línea excesivos
        """
        if not valor:
            return valor
        
        texto = str(valor).strip()
        if not texto:
            return valor
        
        # Limpiar saltos de línea si es necesario
        if limpiar_saltos_linea:
            texto = self._normalizar_texto(texto)
        
        # Capitalizar si es nombre propio
        if es_nombre_propio:
            texto = self._capitalizar_nombre_propio(texto)
        
        return texto
    
    def get_object(self, queryset=None):
        pk = self.kwargs.get('pk')
        slug = self.kwargs.get('slug')
        return get_object_or_404(VentaViaje, pk=pk, slug=slug)
    
    def get(self, request, *args, **kwargs):
        try:
            from docx import Document
            from docx.shared import Inches
        except ImportError:
            messages.error(request, "Error: python-docx no está instalado. Ejecuta: pip install python-docx")
            return redirect('listar_confirmaciones', pk=self.get_object().pk, slug=self.get_object().slug_safe)
        
        venta = self.get_object()
        plantillas = PlantillaConfirmacion.objects.filter(venta=venta).order_by('tipo', '-fecha_creacion')
        
        if not plantillas.exists():
            messages.warning(request, "No hay plantillas de confirmación para generar el documento.")
            return redirect('listar_confirmaciones', pk=venta.pk, slug=venta.slug_safe)
        
        # Crear documento Word usando la plantilla con membrete si está disponible
        template_path = os.path.join(settings.BASE_DIR, 'static', 'docx', 'membrete.docx')
        if os.path.exists(template_path):
            doc = Document(template_path)
        else:
            doc = Document()
        
        # Configurar fuente predeterminada Arial 12
        from docx.shared import Pt
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        
        # Establecer Arial como fuente predeterminada
        styles = doc.styles
        style = styles['Normal']
        font = style.font
        font.name = 'Arial'
        font.size = Pt(12)
        
        # Ajustar márgenes solo si estamos usando un documento en blanco
        if not os.path.exists(template_path):
            sections = doc.sections
            for section in sections:
                section.top_margin = Inches(0.75)
                section.bottom_margin = Inches(1)
                section.left_margin = Inches(0.75)
                section.right_margin = Inches(0.75)
        
        # Agregar título principal del documento
        self._agregar_encabezado_documento(doc, venta)
        
        # Agregar cada plantilla como una sección en una nueva página
        from docx.shared import Pt, RGBColor
        
        for idx, plantilla in enumerate(plantillas):
            # Cada servicio comienza en una nueva página (excepto el primero)
            if idx > 0:
                doc.add_page_break()
                # Agregar título en cada nueva página
                self._agregar_encabezado_documento(doc, venta)
            self._agregar_plantilla_al_documento(doc, plantilla)
        
        # Preparar respuesta HTTP
        from io import BytesIO
        
        # Guardar el documento en memoria (sin protección de solo lectura)
        buffer = BytesIO()
        
        # Asegurar que el documento no tenga protección de escritura
        # Remover cualquier protección de documento si existe
        try:
            from docx.oxml.ns import qn
            # Buscar y eliminar cualquier elemento de protección
            for element in doc.element.iter():
                if element.tag.endswith('documentProtection'):
                    doc.element.remove(element)
        except:
            pass  # Si no hay protección, continuar normalmente
        
        doc.save(buffer)
        buffer.seek(0)
        
        # Crear respuesta HTTP con el documento
        nombre_cliente_safe = venta.cliente.nombre_completo_display.replace(' ', '_').replace('/', '_')
        filename = f"Confirmaciones_Venta_{venta.pk}_{nombre_cliente_safe}.docx"
        
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(len(buffer.getvalue()))
        
        # Agregar headers para asegurar que el navegador no marque el archivo como de solo lectura
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        buffer.close()
        return response
    
    def _agregar_encabezado_documento(self, doc, venta):
        """Agrega título e información de la venta respetando el membrete de la plantilla."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor
        from datetime import datetime
        
        # Asegurar estilos básicos
        self._asegurar_estilo_heading(doc, 'Heading 1', 18)
        self._asegurar_estilo_heading(doc, 'Heading 2', 16)
        self._asegurar_estilo_heading(doc, 'Heading 4', 12)

        # Pequeño espacio para no invadir el membrete
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(4)
        
        titulo_principal = doc.add_heading('CONFIRMACIONES DE VIAJE', level=1)
        titulo_principal.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in titulo_principal.runs:
            run.font.name = 'Arial'
            run.font.color.rgb = RGBColor(0, 74, 142)
            run.font.size = Pt(18)
            run.font.bold = True
        
        info_p = doc.add_paragraph()
        info_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        info_p.paragraph_format.space_after = Pt(6)
        
        cliente_run = info_p.add_run(f'Cliente: {venta.cliente.nombre_completo_display}')
        cliente_run.font.name = 'Arial'
        cliente_run.font.size = Pt(12)
        cliente_run.font.color.rgb = RGBColor(0, 0, 0)
        
        fecha_run = info_p.add_run(f' | Fecha de generación: {datetime.now().strftime("%d de %B de %Y")}')
        fecha_run.font.name = 'Arial'
        fecha_run.font.size = Pt(12)
        fecha_run.font.color.rgb = RGBColor(0, 0, 0)
    
    def _agregar_plantilla_al_documento(self, doc, plantilla):
        """Agrega el contenido de una plantilla al documento Word con estilo profesional."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor, Inches
        
        # Salto de línea entre la información del cliente y el título de la plantilla
        self._agregar_salto_entre_secciones(doc)
        
        # Agregar título principal (tamaño 18, Arial)
        self._asegurar_estilo_heading(doc, 'Heading 2', 18)
        titulo = doc.add_heading(plantilla.get_tipo_display().upper(), level=2)
        titulo.alignment = WD_ALIGN_PARAGRAPH.LEFT
        titulo.paragraph_format.space_before = Pt(12)
        titulo.paragraph_format.space_after = Pt(10)
        for run in titulo.runs:
            run.font.name = 'Arial'
            run.font.color.rgb = RGBColor(0, 74, 142)  # Azul similar al PDF
            run.font.size = Pt(18)
            run.font.bold = True
        
        # Agregar datos según el tipo
        datos = plantilla.datos or {}
        
        if plantilla.tipo == 'VUELO_UNICO':
            self._agregar_vuelo_unico(doc, datos)
        elif plantilla.tipo == 'VUELO_REDONDO':
            self._agregar_vuelo_redondo(doc, datos)
        elif plantilla.tipo == 'HOSPEDAJE':
            self._agregar_hospedaje(doc, datos)
        elif plantilla.tipo == 'TRASLADO':
            # Para traslados, puede haber múltiples traslados
            if 'traslados' in datos and isinstance(datos['traslados'], list):
                for idx, traslado in enumerate(datos['traslados'], 1):
                    if idx > 1:
                        self._agregar_subtitulo_con_vineta(doc, f'Traslado {idx}')
                    self._agregar_traslado(doc, traslado)
            else:
                # Compatibilidad con formato antiguo
                self._agregar_traslado(doc, datos)
        elif plantilla.tipo == 'GENERICA':
            self._agregar_generica(doc, datos)
    
    def _agregar_info_line(self, doc, etiqueta, valor, mostrar_si_vacio=False, es_nombre_propio=False, separar_con_comas=False):
        """Helper para agregar una línea de información formateada (ultra compacta)."""
        from docx.shared import Pt, RGBColor
        
        if not valor and not mostrar_si_vacio:
            return
        
        # Si separar_con_comas, convertir saltos de línea en comas
        if separar_con_comas and valor:
            # Reemplazar saltos de línea por comas
            valor = ', '.join([v.strip() for v in str(valor).replace('\r\n', '\n').split('\n') if v.strip()])
        
        # Normalizar el valor
        valor_normalizado = self._normalizar_valor_campo(
            valor, 
            es_nombre_propio=es_nombre_propio, 
            limpiar_saltos_linea=True
        )
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)  # Espaciado entre líneas de información
        p.paragraph_format.line_spacing = 1.15  # Interlineado
        
        # Etiqueta en negrita
        label_run = p.add_run(f'{etiqueta}: ')
        label_run.font.name = 'Arial'
        label_run.bold = True
        label_run.font.size = Pt(12)
        
        # Valor normalizado
        value_run = p.add_run(valor_normalizado if valor_normalizado else 'No especificado')
        value_run.font.name = 'Arial'
        value_run.font.size = Pt(12)
        
        return p
    
    def _agregar_info_inline(self, doc, *pares_etiqueta_valor, separador=' | ', es_nombre_propio=False):
        """Helper para agregar múltiples campos en una sola línea (ultra compacto)."""
        from docx.shared import Pt, RGBColor
        
        if not pares_etiqueta_valor:
            return
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        
        for idx, (etiqueta, valor) in enumerate(pares_etiqueta_valor):
            if not valor:
                continue
            
            # Normalizar el valor
            valor_normalizado = self._normalizar_valor_campo(
                valor,
                es_nombre_propio=es_nombre_propio,
                limpiar_saltos_linea=True
            )
            
            if idx > 0:
                sep_run = p.add_run(separador)
                sep_run.font.name = 'Arial'
                sep_run.font.size = Pt(12)
                sep_run.font.color.rgb = RGBColor(150, 150, 150)
            
            label_run = p.add_run(f'{etiqueta}: ')
            label_run.font.name = 'Arial'
            label_run.bold = True
            label_run.font.size = Pt(12)
            
            value_run = p.add_run(str(valor_normalizado))
            value_run.font.name = 'Arial'
            value_run.font.size = Pt(12)
        
        return p
    
    def _agregar_subtitulo_con_vineta(self, doc, texto):
        """Agrega un subtítulo con viñeta azul como en la imagen."""
        from docx.shared import Pt, RGBColor
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Pt(0)
        
        # Agregar viñeta manualmente (carácter bullet)
        bullet_run = p.add_run('• ')
        bullet_run.font.name = 'Arial'
        bullet_run.font.size = Pt(16)
        bullet_run.font.color.rgb = RGBColor(0, 74, 142)
        bullet_run.font.bold = True
        
        # Agregar texto del subtítulo (tamaño 16 para títulos azules)
        texto_run = p.add_run(texto)
        texto_run.font.name = 'Arial'
        texto_run.font.size = Pt(16)
        texto_run.font.color.rgb = RGBColor(0, 74, 142)
        texto_run.font.bold = True
        
        return p
    
    def _agregar_salto_entre_secciones(self, doc):
        """Agrega un salto de línea entre secciones para separar títulos con viñeta."""
        from docx.shared import Pt
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)
        return spacer
    
    def _agregar_vuelo_unico(self, doc, datos):
        """Agrega contenido de vuelo único al documento con formato profesional."""
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        # Información de Reserva (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información de Reserva')
        
        # Agrupar información de reserva en líneas compactas
        self._agregar_info_inline(doc,
            ('Clave de Reserva', datos.get('clave_reserva', '')),
            ('Aerolínea', datos.get('aerolinea', '')),
            ('Vuelo', datos.get('numero_vuelo', ''))
        )
        
        # Salto de línea entre secciones
        self._agregar_salto_entre_secciones(doc)
        
        # Detalles del Vuelo (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Detalles del Vuelo')
        
        # Agrupar campos relacionados en la misma línea
        self._agregar_info_inline(doc, 
            ('Fecha', datos.get('fecha', '')),
            ('Hora Salida', datos.get('hora_salida', '')),
            ('Hora Llegada', datos.get('hora_llegada', ''))
        )
        self._agregar_info_inline(doc,
            ('Origen', datos.get('origen_terminal', '')),
            ('Destino', datos.get('destino_terminal', ''))
        )
        self._agregar_info_line(doc, 'Tipo de Vuelo', datos.get('tipo_vuelo', ''))
        
        # Escalas si aplica (compacto)
        if datos.get('tipo_vuelo') == 'Escalas' and datos.get('escalas'):
            self._asegurar_estilo_heading(doc, 'Heading 4', 12)
            escalas_titulo = doc.add_heading('Detalles de Escalas', level=4)
            escalas_titulo.paragraph_format.space_before = Pt(4)
            escalas_titulo.paragraph_format.space_after = Pt(6)
            escalas_titulo.runs[0].font.size = Pt(10)
            for i, escala in enumerate(datos['escalas'], 1):
                escala_p = doc.add_paragraph()
                escala_p.paragraph_format.space_after = Pt(6)
                escala_run = escala_p.add_run(f'Escala {i}: ')
                escala_run.font.name = 'Arial'
                escala_run.font.size = Pt(12)
                escala_run.bold = True
                escala_val_run = escala_p.add_run(f"{escala.get('ciudad', '')} - {escala.get('aeropuerto', '')}")
                escala_val_run.font.name = 'Arial'
                escala_val_run.font.size = Pt(12)
                
                escala_info = doc.add_paragraph()
                escala_info.paragraph_format.left_indent = Inches(0.3)
                escala_info.paragraph_format.space_after = Pt(6)
                for part in [
                    (f"Hora Llegada: {escala.get('hora_llegada', '')}", True),
                    (" | ", False),
                    (f"Hora Salida: {escala.get('hora_salida', '')}", True),
                    (" | ", False),
                    (f"Vuelo: {escala.get('numero_vuelo', '')}", True),
                    (" | ", False),
                    (f"Duración: {escala.get('duracion', '')}", False)
                ]:
                    run = escala_info.add_run(part[0])
                    run.font.name = 'Arial'
                    run.font.size = Pt(12)
                    if part[1]:
                        run.bold = True
        
        # Salto de línea entre secciones
        self._agregar_salto_entre_secciones(doc)
        
        # Información de Pasajeros (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información de Pasajeros')
        
        self._agregar_info_line(doc, 'Pasajeros', datos.get('pasajeros', ''), separar_con_comas=True)
        self._agregar_info_line(doc, 'Equipaje', datos.get('equipaje', ''))
        
        if datos.get('informacion_adicional'):
            info_normalizada = self._normalizar_valor_campo(datos.get('informacion_adicional', ''), limpiar_saltos_linea=True)
            info_p = doc.add_paragraph()
            info_p.paragraph_format.space_after = Pt(6)
            info_label = info_p.add_run('Información Adicional: ')
            info_label.font.name = 'Arial'
            info_label.font.size = Pt(12)
            info_label.bold = True
            info_val = info_p.add_run(info_normalizada)
            info_val.font.name = 'Arial'
            info_val.font.size = Pt(12)
        
        # Información Completa del Vuelo (campo "vuelo") - en hoja aparte
        if datos.get('vuelo'):
            from docx.enum.text import WD_BREAK
            # Agregar salto de página
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            self._agregar_subtitulo_con_vineta(doc, 'Información Completa del Vuelo')
            vuelo_info = self._normalizar_valor_campo(datos.get('vuelo', ''), limpiar_saltos_linea=False)
            vuelo_p = doc.add_paragraph()
            vuelo_p.paragraph_format.space_after = Pt(6)
            vuelo_val = vuelo_p.add_run(vuelo_info)
            vuelo_val.font.name = 'Arial'
            vuelo_val.font.size = Pt(12)
    
    def _agregar_vuelo_redondo(self, doc, datos):
        """Agrega contenido de vuelo redondo al documento con formato compacto."""
        from docx.shared import Pt, Inches
        from docx.shared import RGBColor
        
        # Información de Reserva (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información de Reserva')
        
        self._agregar_info_line(doc, 'Clave de Reserva', datos.get('clave_reserva', ''))
        
        # Salto de línea entre secciones
        self._agregar_salto_entre_secciones(doc)
        
        # Vuelo de Ida (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Vuelo de Ida')
        
        # Agrupar campos relacionados en líneas compactas
        self._agregar_info_inline(doc,
            ('Aerolínea', datos.get('aerolinea_ida', '')),
            ('Vuelo', datos.get('numero_vuelo_ida', ''))
        )
        self._agregar_info_inline(doc,
            ('Fecha Salida', datos.get('fecha_salida_ida', '')),
            ('Hora Salida', datos.get('hora_salida_ida', '')),
            ('Hora Llegada', datos.get('hora_llegada_ida', ''))
        )
        self._agregar_info_inline(doc,
            ('Origen', datos.get('origen_ida', '')),
            ('Destino', datos.get('destino_ida', ''))
        )
        self._agregar_info_line(doc, 'Tipo de Vuelo', datos.get('tipo_vuelo_ida', ''))
        
        # Escalas de Ida si aplica
        escalas_ida = datos.get('escalas_ida', [])
        if escalas_ida and isinstance(escalas_ida, list) and len(escalas_ida) > 0:
                p_titulo = doc.add_paragraph()
                p_titulo.paragraph_format.space_before = Pt(8)
                p_titulo.paragraph_format.space_after = Pt(4)
                titulo_run = p_titulo.add_run('Escalas del Vuelo de Ida:')
                titulo_run.font.name = 'Arial'
                titulo_run.font.size = Pt(12)
                titulo_run.font.bold = True
                titulo_run.font.color.rgb = RGBColor(0, 74, 142)
                
                for i, escala in enumerate(escalas_ida, 1):
                    escala_p = doc.add_paragraph()
                    escala_p.paragraph_format.space_after = Pt(4)
                    escala_p.paragraph_format.left_indent = Inches(0.2)
                    
                    escala_run = escala_p.add_run(f'Escala {i}: ')
                    escala_run.font.name = 'Arial'
                    escala_run.font.size = Pt(12)
                    escala_run.bold = True
                    
                    ciudad = escala.get('ciudad', '')
                    aeropuerto = escala.get('aeropuerto', '')
                    escala_val = escala_p.add_run(f"{ciudad} - {aeropuerto}")
                    escala_val.font.name = 'Arial'
                    escala_val.font.size = Pt(12)
                    
                    # Detalles de la escala
                    detalle_p = doc.add_paragraph()
                    detalle_p.paragraph_format.space_after = Pt(6)
                    detalle_p.paragraph_format.left_indent = Inches(0.4)
                    
                    detalles = []
                    if escala.get('hora_llegada'):
                        detalles.append(f"Llegada: {escala.get('hora_llegada')}")
                    if escala.get('hora_salida'):
                        detalles.append(f"Salida: {escala.get('hora_salida')}")
                    if escala.get('numero_vuelo'):
                        detalles.append(f"Vuelo: {escala.get('numero_vuelo')}")
                    if escala.get('duracion'):
                        detalles.append(f"Duración: {escala.get('duracion')}")
                    
                    detalle_run = detalle_p.add_run(' | '.join(detalles))
                    detalle_run.font.name = 'Arial'
                    detalle_run.font.size = Pt(11)
        
        # Salto de página antes del Vuelo de Regreso
        doc.add_page_break()
        
        # Vuelo de Regreso (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Vuelo de Regreso')
        
        # Agrupar campos relacionados en líneas compactas
        self._agregar_info_inline(doc,
            ('Aerolínea', datos.get('aerolinea_regreso', '')),
            ('Vuelo', datos.get('numero_vuelo_regreso', ''))
        )
        self._agregar_info_inline(doc,
            ('Fecha Salida', datos.get('fecha_salida_regreso', '')),
            ('Hora Salida', datos.get('hora_salida_regreso', '')),
            ('Hora Llegada', datos.get('hora_llegada_regreso', ''))
        )
        self._agregar_info_inline(doc,
            ('Origen', datos.get('origen_regreso', '')),
            ('Destino', datos.get('destino_regreso', ''))
        )
        self._agregar_info_line(doc, 'Tipo de Vuelo', datos.get('tipo_vuelo_regreso', ''))
        
        # Escalas de Regreso si aplica
        escalas_regreso = datos.get('escalas_regreso', [])
        if escalas_regreso and isinstance(escalas_regreso, list) and len(escalas_regreso) > 0:
                p_titulo = doc.add_paragraph()
                p_titulo.paragraph_format.space_before = Pt(8)
                p_titulo.paragraph_format.space_after = Pt(4)
                titulo_run = p_titulo.add_run('Escalas del Vuelo de Regreso:')
                titulo_run.font.name = 'Arial'
                titulo_run.font.size = Pt(12)
                titulo_run.font.bold = True
                titulo_run.font.color.rgb = RGBColor(0, 74, 142)
                
                for i, escala in enumerate(escalas_regreso, 1):
                    escala_p = doc.add_paragraph()
                    escala_p.paragraph_format.space_after = Pt(4)
                    escala_p.paragraph_format.left_indent = Inches(0.2)
                    
                    escala_run = escala_p.add_run(f'Escala {i}: ')
                    escala_run.font.name = 'Arial'
                    escala_run.font.size = Pt(12)
                    escala_run.bold = True
                    
                    ciudad = escala.get('ciudad', '')
                    aeropuerto = escala.get('aeropuerto', '')
                    escala_val = escala_p.add_run(f"{ciudad} - {aeropuerto}")
                    escala_val.font.name = 'Arial'
                    escala_val.font.size = Pt(12)
                    
                    # Detalles de la escala
                    detalle_p = doc.add_paragraph()
                    detalle_p.paragraph_format.space_after = Pt(6)
                    detalle_p.paragraph_format.left_indent = Inches(0.4)
                    
                    detalles = []
                    if escala.get('hora_llegada'):
                        detalles.append(f"Llegada: {escala.get('hora_llegada')}")
                    if escala.get('hora_salida'):
                        detalles.append(f"Salida: {escala.get('hora_salida')}")
                    if escala.get('numero_vuelo'):
                        detalles.append(f"Vuelo: {escala.get('numero_vuelo')}")
                    if escala.get('duracion'):
                        detalles.append(f"Duración: {escala.get('duracion')}")
                    
                    detalle_run = detalle_p.add_run(' | '.join(detalles))
                    detalle_run.font.name = 'Arial'
                    detalle_run.font.size = Pt(11)
        
        # Salto de línea entre secciones
        self._agregar_salto_entre_secciones(doc)
        
        # Información General (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información General')
        
        self._agregar_info_line(doc, 'Pasajeros', datos.get('pasajeros', ''), es_nombre_propio=True, separar_con_comas=True)
        self._agregar_info_line(doc, 'Equipaje', datos.get('equipaje', ''))
        
        if datos.get('informacion_adicional'):
            info_normalizada = self._normalizar_valor_campo(datos.get('informacion_adicional', ''), limpiar_saltos_linea=True)
            info_p = doc.add_paragraph()
            info_p.paragraph_format.space_after = Pt(6)
            info_label = info_p.add_run('Información Adicional: ')
            info_label.font.name = 'Arial'
            info_label.font.size = Pt(12)
            info_label.bold = True
            info_val = info_p.add_run(info_normalizada)
            info_val.font.name = 'Arial'
            info_val.font.size = Pt(12)
    
    def _agregar_hospedaje(self, doc, datos):
        """Agrega contenido de hospedaje al documento con formato compacto."""
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import RGBColor
        
        # Información del Alojamiento (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información del Alojamiento')
        
        # Agrupar información del alojamiento (normalizada)
        nombre_alojamiento = self._normalizar_valor_campo(datos.get('nombre_alojamiento', ''), limpiar_saltos_linea=True)
        referencia = self._normalizar_valor_campo(datos.get('numero_referencia', ''), limpiar_saltos_linea=True)
        viajero_principal = self._normalizar_valor_campo(datos.get('viajero_principal', ''), es_nombre_propio=True)
        tipo_habitacion = self._normalizar_valor_campo(datos.get('tipo_habitacion', ''), limpiar_saltos_linea=True)
        
        # Crear línea con viajero principal subrayado
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        
        # Alojamiento
        aloj_run = p.add_run('Alojamiento: ')
        aloj_run.font.name = 'Arial'
        aloj_run.font.size = Pt(12)
        aloj_run.font.bold = True
        aloj_val_run = p.add_run(f'{nombre_alojamiento} | ')
        aloj_val_run.font.name = 'Arial'
        aloj_val_run.font.size = Pt(12)
        
        # Referencia
        ref_run = p.add_run('Referencia: ')
        ref_run.font.name = 'Arial'
        ref_run.font.size = Pt(12)
        ref_run.font.bold = True
        ref_val_run = p.add_run(f'{referencia} | ')
        ref_val_run.font.name = 'Arial'
        ref_val_run.font.size = Pt(12)
        
        # Viajero Principal (subrayado y normalizado)
        viaj_run = p.add_run('Viajero Principal: ')
        viaj_run.font.name = 'Arial'
        viaj_run.font.size = Pt(12)
        viaj_run.font.bold = True
        viaj_val_run = p.add_run(viajero_principal if viajero_principal else '')
        viaj_val_run.font.name = 'Arial'
        viaj_val_run.font.size = Pt(12)
        viaj_val_run.font.underline = True  # Subrayado
        viaj_sep_run = p.add_run(' | ')
        viaj_sep_run.font.name = 'Arial'
        viaj_sep_run.font.size = Pt(12)
        
        # Tipo Habitación
        tipo_run = p.add_run('Tipo Habitación: ')
        tipo_run.font.name = 'Arial'
        tipo_run.font.size = Pt(12)
        tipo_run.font.bold = True
        tipo_val_run = p.add_run(tipo_habitacion if tipo_habitacion else '')
        tipo_val_run.font.name = 'Arial'
        tipo_val_run.font.size = Pt(12)
        
        # Salto de línea entre secciones
        self._agregar_salto_entre_secciones(doc)
        
        # Fechas y Estancia (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Fechas y Estancia')
        
        # Agrupar fechas y horas en una sola línea
        hora_checkin = datos.get('hora_checkin', '')
        hora_checkout = datos.get('hora_checkout', '')
        fecha_checkin = datos.get('fecha_checkin', '')
        fecha_checkout = datos.get('fecha_checkout', '')
        
        checkin_str = f"{fecha_checkin}" + (f" {hora_checkin}" if hora_checkin else "")
        checkout_str = f"{fecha_checkout}" + (f" {hora_checkout}" if hora_checkout else "")
        
        self._agregar_info_inline(doc,
            ('Check-in', checkin_str),
            ('Check-out', checkout_str)
        )
        
        # Salto de línea entre secciones
        self._agregar_salto_entre_secciones(doc)
        
        # Información de Huéspedes (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información de Huéspedes')
        
        adultos = datos.get('adultos', '0')
        ninos = datos.get('ninos', '0')
        ocupacion_str = f"{adultos} Adulto(s)"
        if int(ninos) > 0:
            ocupacion_str += f", {ninos} Niño(s)"
        
        # Agrupar ocupación y régimen en una línea
        self._agregar_info_inline(doc,
            ('Ocupación', ocupacion_str),
            ('Régimen', datos.get('regimen', ''))
        )
        
        if datos.get('observaciones'):
            obs_normalizada = self._normalizar_valor_campo(datos.get('observaciones', ''), limpiar_saltos_linea=True)
            obs_p = doc.add_paragraph()
            obs_p.paragraph_format.space_after = Pt(6)
            obs_label = obs_p.add_run('Observaciones: ')
            obs_label.font.name = 'Arial'
            obs_label.font.size = Pt(12)
            obs_label.bold = True
            obs_val = obs_p.add_run(obs_normalizada)
            obs_val.font.name = 'Arial'
            obs_val.font.size = Pt(12)
        
        # Imagen de hospedaje (si existe)
        if datos.get('imagen_hospedaje_url'):
            try:
                # Intentar importar requests (opcional, puede no estar instalado)
                # type: ignore para evitar advertencia del linter si requests no está instalado
                import requests  # type: ignore[reportMissingModuleSource]
                from io import BytesIO
                image_url = datos['imagen_hospedaje_url']
                if image_url.startswith('/media/'):
                    image_url = self.request.build_absolute_uri(image_url)
                response = requests.get(image_url, timeout=5)
                response.raise_for_status()
                image_stream = BytesIO(response.content)
                doc.add_picture(image_stream, width=Inches(4.5))
            except ImportError:
                # Si requests no está disponible, solo agregar una nota
                img_note = doc.add_paragraph()
                img_note.paragraph_format.space_after = Pt(3)
                img_note.add_run('Nota: ').bold = True
                img_note.add_run('Imagen de confirmación disponible en el sistema (requests no disponible).')
            except Exception as e:
                img_note = doc.add_paragraph()
                img_note.paragraph_format.space_after = Pt(3)
                img_note.add_run('Nota: ').bold = True
                img_note.add_run('Imagen de confirmación disponible en el sistema.')
    
    def _agregar_traslado(self, doc, datos):
        """Agrega contenido de traslado al documento con formato compacto."""
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import RGBColor
        
        # Información de la Compañía (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información de la Compañía')
        
        # Agrupar información de compañía
        self._agregar_info_inline(doc,
            ('Compañía', datos.get('compania', '')),
            ('Código Reserva', datos.get('codigo_reserva', ''))
        )
        
        # Salto de línea entre secciones
        self._agregar_salto_entre_secciones(doc)
        
        # Detalles del Traslado (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Detalles del Traslado')
        
        self._agregar_info_line(doc, 'Horario de Inicio de Viaje', datos.get('horario_inicio', ''))
        self._agregar_info_line(doc, 'Tipo de Servicio', datos.get('tipo_servicio', ''))
        self._agregar_info_line(doc, 'Desde', datos.get('desde', ''))
        self._agregar_info_line(doc, 'Hasta', datos.get('hasta', ''))
        
        # Información de Pasajeros (compacto)
        adultos = datos.get('adultos', '0')
        ninos = datos.get('ninos', '0')
        pasajeros_p = doc.add_paragraph()
        pasajeros_p.paragraph_format.space_after = Pt(3)
        pasajeros_p.add_run('Pasajeros: ').bold = True
        pasajeros_p.add_run(f'{adultos} Adulto(s)')
        if int(ninos) > 0:
            pasajeros_p.add_run(f', {ninos} Niño(s)')
        
        if datos.get('informacion_adicional'):
            info_normalizada = self._normalizar_valor_campo(datos.get('informacion_adicional', ''), limpiar_saltos_linea=True)
            info_p = doc.add_paragraph()
            info_p.paragraph_format.space_after = Pt(6)
            info_label = info_p.add_run('Información Adicional: ')
            info_label.font.name = 'Arial'
            info_label.font.size = Pt(12)
            info_label.bold = True
            info_val = info_p.add_run(info_normalizada)
            info_val.font.name = 'Arial'
            info_val.font.size = Pt(12)
    
    def _agregar_generica(self, doc, datos):
        """Agrega contenido genérico al documento con formato compacto."""
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import RGBColor
        
        titulo = datos.get('titulo', 'Información Adicional')
        if titulo:
            self._agregar_subtitulo_con_vineta(doc, titulo)
        
        contenido = datos.get('contenido', '')
        if contenido:
            # Normalizar el contenido (limpiar saltos de línea excesivos)
            contenido_normalizado = self._normalizar_valor_campo(contenido, limpiar_saltos_linea=True)
            # Dividir por líneas para mejor formato (compacto)
            for linea in contenido_normalizado.split('\n'):
                if linea.strip():
                    p = doc.add_paragraph(linea.strip())
                    p.paragraph_format.space_after = Pt(6)
                    p.paragraph_format.line_spacing = 1.1
                    for run in p.runs:
                        run.font.name = 'Arial'
                        run.font.size = Pt(12)


# ------------------- API: Previsualización de promociones -------------------
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from ventas.services.promociones import PromocionesService


@login_required
@require_POST
def preview_promociones(request):
    """
    Devuelve las promociones aplicables en tiempo real para el formulario de venta.
    Espera: cliente_id, tipo_viaje, costo_venta_final (opcional), costo_modificacion (opcional).
    """
    try:
        cliente_id_str = request.POST.get('cliente_id', '').strip()
        tipo_viaje = request.POST.get('tipo_viaje', '').strip()
        costo_venta_final_str = request.POST.get('costo_venta_final', '0').strip()
        costo_mod_str = request.POST.get('costo_modificacion', '0').strip()
        
        logger.info(f"preview_promociones recibido - cliente_id: '{cliente_id_str}', tipo_viaje: '{tipo_viaje}', costo_venta_final: '{costo_venta_final_str}', costo_mod: '{costo_mod_str}'")
        
        if not cliente_id_str or not tipo_viaje:
            logger.warning(f"Parámetros faltantes - cliente_id: '{cliente_id_str}', tipo_viaje: '{tipo_viaje}'")
            return JsonResponse({'ok': True, 'promos': []})
        
        cliente_id = int(cliente_id_str)
        costo_venta_final = Decimal(costo_venta_final_str or '0')
        costo_mod = Decimal(costo_mod_str or '0')
        
    except (ValueError, InvalidOperation) as e:
        logger.error(f"Error al parsear parámetros: {str(e)}")
        return JsonResponse({'ok': False, 'error': f'Parámetros inválidos: {str(e)}'}, status=400)
    except Exception as e:
        logger.error(f"Error inesperado al procesar parámetros: {str(e)}")
        return JsonResponse({'ok': False, 'error': 'Error al procesar parámetros'}, status=400)

    try:
        cliente = Cliente.objects.get(pk=cliente_id)
        logger.info(f"Cliente encontrado: {cliente.nombre_completo_display} (ID: {cliente_id})")
    except Cliente.DoesNotExist:
        logger.warning(f"Cliente no encontrado con ID: {cliente_id}")
        return JsonResponse({'ok': True, 'promos': []})
    except Exception as e:
        logger.error(f"Error al buscar cliente: {str(e)}")
        return JsonResponse({'ok': False, 'error': 'Error al buscar cliente'}, status=500)

    total_base = costo_venta_final + costo_mod
    logger.info(f"Buscando promociones - cliente: {cliente_id}, tipo_viaje: {tipo_viaje}, total_base: {total_base}")
    
    promos = PromocionesService.obtener_promos_aplicables(
        cliente=cliente,
        tipo_viaje=tipo_viaje,
        total_base_mxn=total_base
    )
    
    logger.info(f"Promociones encontradas: {len(promos)}")
    for p in promos:
        logger.info(f"  - {p['promo'].nombre} (tipo: {p['promo'].tipo}, alcance: {p['promo'].alcance}, monto: {p.get('monto_descuento', 0)})")
    promos_serialized = []
    for p in promos:
        promo = p['promo']
        promos_serialized.append({
            'id': promo.id,
            'nombre': promo.nombre,
            'tipo': promo.tipo,
            'porcentaje': str(p.get('porcentaje') or '0'),
            'monto_descuento': str(p.get('monto_descuento') or '0'),
            'km_bono': str(p.get('km_bono') or '0'),
            'requiere_confirmacion': p.get('requiere_confirmacion', False),
            'condicion': promo.get_condicion_display(),
            'alcance': promo.alcance,  # Agregar alcance para validación frontend
        })

    return JsonResponse({'ok': True, 'promos': promos_serialized})


# ------------------- VISTAS DE DETALLE Y EXPORTACIÓN DE COMISIONES -------------------

class DetalleComisionesView(LoginRequiredMixin, TemplateView):
    """
    Vista detallada de comisiones de un vendedor específico.
    Muestra desglose por venta.
    """
    template_name = 'ventas/detalle_comisiones.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        vendedor_id = kwargs.get('pk')
        
        try:
            vendedor = User.objects.get(pk=vendedor_id, perfil__rol='VENDEDOR')
        except User.DoesNotExist:
            from django.http import Http404
            raise Http404("Vendedor no encontrado")
        
        # Verificar permisos: solo puede ver su propio detalle o ser JEFE/CONTADOR
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        if user_rol == 'VENDEDOR' and self.request.user.pk != vendedor_id:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("No tienes permiso para ver este detalle")
        
        # Obtener ventas del vendedor
        ventas_base = VentaViaje.objects.filter(vendedor=vendedor)
        
        # Filtrar ventas pagadas al 100%
        ventas_pagadas = [
            venta for venta in ventas_base 
            if venta.total_pagado >= venta.costo_total_con_modificacion
        ]
        
        # Calcular comisiones
        ejecutivo = getattr(vendedor, 'ejecutivo_asociado', None)
        tipo_vendedor = ejecutivo.tipo_vendedor if ejecutivo else 'OFICINA'
        
        total_ventas_pagadas = sum(
            venta.costo_venta_final for venta in ventas_pagadas
        ) or Decimal('0.00')
        
        porcentaje_comision, comision_total = calcular_comision_por_tipo(
            total_ventas_pagadas, 
            tipo_vendedor
        )
        
        sueldo_base = ejecutivo.sueldo_base if ejecutivo and ejecutivo.sueldo_base else Decimal('10000.00')
        ingreso_total = sueldo_base + comision_total
        
        context.update({
            'vendedor': vendedor,
            'ejecutivo': ejecutivo,
            'tipo_vendedor': tipo_vendedor,
            'ventas_pagadas': ventas_pagadas,
            'user_rol': user_rol,
            'sueldo_base': sueldo_base,
            'total_ventas_pagadas': total_ventas_pagadas,
            'porcentaje_comision': porcentaje_comision * 100,
            'comision_total': comision_total,
            'ingreso_total': ingreso_total,
        })
        
        return context


class ExportarComisionesExcelView(LoginRequiredMixin, View):
    """
    Exporta las comisiones de un vendedor a Excel.
    """
    def get(self, request, pk):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        except ImportError:
            messages.error(request, "La librería openpyxl no está instalada. Instálala con: pip install openpyxl")
            return redirect('reporte_comisiones')
        
        from django.http import HttpResponse
        
        try:
            vendedor = User.objects.get(pk=pk, perfil__rol='VENDEDOR')
        except User.DoesNotExist:
            from django.http import Http404
            raise Http404("Vendedor no encontrado")
        
        # Verificar permisos
        user_rol = request.user.perfil.rol if hasattr(request.user, 'perfil') else 'INVITADO'
        if user_rol == 'VENDEDOR' and request.user.pk != pk:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("No tienes permiso para exportar este detalle")
        
        # Obtener ventas
        ventas_base = VentaViaje.objects.filter(vendedor=vendedor)
        
        ventas_pagadas = [
            venta for venta in ventas_base 
            if venta.total_pagado >= venta.costo_total_con_modificacion
        ]
        
        # Calcular comisiones
        ejecutivo = getattr(vendedor, 'ejecutivo_asociado', None)
        tipo_vendedor = ejecutivo.tipo_vendedor if ejecutivo else 'OFICINA'
        
        total_ventas_pagadas = sum(
            venta.costo_venta_final for venta in ventas_pagadas
        ) or Decimal('0.00')
        
        porcentaje_comision, comision_total = calcular_comision_por_tipo(
            total_ventas_pagadas, 
            tipo_vendedor
        )
        
        sueldo_base = ejecutivo.sueldo_base if ejecutivo and ejecutivo.sueldo_base else Decimal('10000.00')
        ingreso_total = sueldo_base + comision_total
        
        # Crear workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Comisiones"
        
        # Estilos
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=12)
        title_font = Font(bold=True, size=14)
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # Título
        ws['A1'] = f"Reporte de Comisiones - {vendedor.get_full_name() or vendedor.username}"
        ws['A1'].font = title_font
        ws.merge_cells('A1:F1')
        
        row = 3
        
        # Resumen general
        ws[f'A{row}'] = "RESUMEN GENERAL"
        ws[f'A{row}'].font = title_font
        row += 1
        
        ws[f'A{row}'] = "Concepto"
        ws[f'B{row}'] = "Monto"
        for cell in [ws[f'A{row}'], ws[f'B{row}']]:
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
        row += 1
        
        ws[f'A{row}'] = "Sueldo Base"
        ws[f'B{row}'] = float(sueldo_base)
        row += 1
        
        ws[f'A{row}'] = "Comisión"
        ws[f'B{row}'] = float(comision_total)
        row += 1
        
        ws[f'A{row}'] = "TOTAL"
        ws[f'B{row}'] = float(ingreso_total)
        ws[f'A{row}'].font = Font(bold=True)
        ws[f'B{row}'].font = Font(bold=True)
        row += 2
        
        # Detalle de ventas
        ws[f'A{row}'] = "VENTAS"
        ws[f'A{row}'].font = title_font
        ws.merge_cells(f'A{row}:F{row}')
        row += 1
        
        headers = ['Venta ID', 'Cliente', 'Total Venta', 'Pagado', 'Comisión']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
        row += 1
        
        for venta in ventas_pagadas:
            comision_venta = venta.costo_venta_final * porcentaje_comision
            ws.cell(row=row, column=1, value=venta.pk)
            ws.cell(row=row, column=2, value=str(venta.cliente))
            ws.cell(row=row, column=3, value=float(venta.costo_venta_final))
            ws.cell(row=row, column=4, value=float(venta.total_pagado))
            ws.cell(row=row, column=5, value=float(comision_venta))
            row += 1
        
        # Ajustar ancho de columnas
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Preparar respuesta
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"comisiones_{vendedor.username}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        wb.save(response)
        return response


# ------------------- VISTAS PARA PROVEEDORES -------------------

class ProveedorUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """
    Vista para editar un proveedor existente.
    """
    model = Proveedor
    form_class = ProveedorForm
    template_name = 'ventas/proveedores.html'
    
    def test_func(self):
        """Solo JEFE puede editar proveedores."""
        rol = get_user_role(self.request.user).upper()
        return 'JEFE' in rol or self.request.user.is_superuser
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para editar proveedores.")
        return redirect('proveedores')
    
    def get_success_url(self):
        messages.success(self.request, "Proveedor actualizado correctamente.")
        return reverse('proveedores')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Incluir el contexto de la vista de lista
        proveedores = Proveedor.objects.all()
        proveedores_por_servicio = {clave: [] for clave, _ in Proveedor.SERVICIO_CHOICES}

        # ✅ Agrupar proveedores por cada servicio que ofrecen (pueden estar en múltiples grupos)
        for proveedor in proveedores:
            if proveedor.servicios:
                servicios_list = [s.strip() for s in proveedor.servicios.split(',') if s.strip()]
                for servicio_codigo in servicios_list:
                    if servicio_codigo in proveedores_por_servicio:
                        proveedores_por_servicio[servicio_codigo].append(proveedor)
        
        grupos_proveedores = [
            {
                'clave': clave,
                'label': label,
                'proveedores': sorted(
                    proveedores_por_servicio.get(clave, []),
                    key=lambda p: p.nombre.lower()
                ),
            }
            for clave, label in Proveedor.SERVICIO_CHOICES
        ]
        
        context['grupos_proveedores'] = grupos_proveedores
        context['total_proveedores'] = sum(len(grupo['proveedores']) for grupo in grupos_proveedores)
        context['servicio_choices'] = Proveedor.SERVICIO_CHOICES
        context['proveedor_editando'] = self.object
        context['form'] = self.get_form()
        return context


class ProveedorDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Vista para eliminar un proveedor. Solo disponible para JEFE.
    """
    model = Proveedor
    template_name = 'ventas/proveedor_confirm_delete.html'
    
    def test_func(self):
        """Solo JEFE puede eliminar proveedores."""
        rol = get_user_role(self.request.user).upper()
        return 'JEFE' in rol or self.request.user.is_superuser
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para eliminar proveedores.")
        return redirect('proveedores')
    
    def get_success_url(self):
        messages.success(self.request, "Proveedor eliminado correctamente.")
        return reverse('proveedores')


# ------------------- VISTAS PARA GESTIÓN DE COMPROBANTES Y PAGOS POR CONFIRMAR -------------------

class SubirComprobanteAbonoView(LoginRequiredMixin, View):
    """Vista para subir el comprobante de un abono."""
    
    def post(self, request, pk):
        abono = get_object_or_404(AbonoPago, pk=pk)
        
        # Verificar que el usuario tenga permiso (vendedor de la venta, JEFE o CONTADOR)
        user_rol = get_user_role(request.user)
        puede_subir = (
            user_rol in ['JEFE', 'CONTADOR'] or
            (abono.venta.vendedor == request.user)
        )
        
        if not puede_subir:
            messages.error(request, "No tienes permiso para subir comprobantes.")
            return redirect(reverse('detalle_venta', kwargs={'pk': abono.venta.pk, 'slug': abono.venta.slug_safe}) + '?tab=abonos')
        
        # Verificar que el abono requiera comprobante (TRN, TAR, DEP)
        if abono.forma_pago not in ['TRN', 'TAR', 'DEP']:
            messages.error(request, "Este tipo de pago no requiere comprobante.")
            return redirect(reverse('detalle_venta', kwargs={'pk': abono.venta.pk, 'slug': abono.venta.slug_safe}) + '?tab=abonos')
        
        # Obtener la imagen del request
        imagen = request.FILES.get('comprobante_imagen')
        if not imagen:
            messages.error(request, "Debes seleccionar una imagen del comprobante.")
            return redirect(reverse('detalle_venta', kwargs={'pk': abono.venta.pk, 'slug': abono.venta.slug_safe}) + '?tab=abonos')
        
        # Guardar el comprobante
        abono.comprobante_imagen = imagen
        abono.comprobante_subido = True
        abono.comprobante_subido_en = timezone.now()
        abono.comprobante_subido_por = request.user
        abono.save()
        
        # Crear notificaciones para CONTADOR
        contadores = User.objects.filter(perfil__rol='CONTADOR')
        forma_pago_display = dict(AbonoPago.FORMA_PAGO_CHOICES).get(abono.forma_pago, abono.forma_pago)
        mensaje_contador = f"Abono pendiente de confirmación: ${abono.monto:,.2f} ({forma_pago_display}) - Venta #{abono.venta.pk} - Cliente: {abono.venta.cliente.nombre_completo_display}"
        
        for contador in contadores:
            # Eliminar notificaciones previas del mismo abono para evitar duplicados
            Notificacion.objects.filter(
                usuario=contador,
                venta=abono.venta,
                abono=abono,
                tipo='PAGO_PENDIENTE',
                confirmado=False
            ).delete()
            
            Notificacion.objects.create(
                usuario=contador,
                tipo='PAGO_PENDIENTE',
                mensaje=mensaje_contador,
                venta=abono.venta,
                abono=abono,
                confirmado=False
            )
        
        # Crear notificaciones para JEFE (información)
        jefes = User.objects.filter(perfil__rol='JEFE')
        mensaje_jefe = f"Abono pendiente de confirmación: ${abono.monto:,.2f} ({forma_pago_display}) - Venta #{abono.venta.pk} - Cliente: {abono.venta.cliente.nombre_completo_display}"
        for jefe in jefes:
            # Eliminar notificaciones previas del mismo abono
            Notificacion.objects.filter(
                usuario=jefe,
                venta=abono.venta,
                abono=abono,
                tipo='PAGO_PENDIENTE',
                confirmado=False
            ).delete()
            
            Notificacion.objects.create(
                usuario=jefe,
                tipo='PAGO_PENDIENTE',
                mensaje=mensaje_jefe,
                venta=abono.venta,
                abono=abono,
                confirmado=False
            )
        
        messages.success(request, "Comprobante subido exitosamente. El contador ha sido notificado.")
        return redirect(reverse('detalle_venta', kwargs={'pk': abono.venta.pk, 'slug': abono.venta.slug_safe}) + '?tab=abonos')


class SubirComprobanteAperturaView(LoginRequiredMixin, View):
    """Vista para subir el comprobante de un pago de apertura."""
    
    def post(self, request, pk):
        venta = get_object_or_404(VentaViaje, pk=pk)
        
        # Verificar que el usuario tenga permiso
        user_rol = get_user_role(request.user)
        puede_subir = (
            user_rol in ['JEFE', 'CONTADOR'] or
            (venta.vendedor == request.user)
        )
        
        if not puede_subir:
            messages.error(request, "No tienes permiso para subir comprobantes.")
            return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
        
        # Verificar que la venta tenga apertura y requiera comprobante (no aplica para crédito)
        if venta.modo_pago_apertura == 'CRE':
            messages.error(request, "El crédito no requiere comprobante. El contador validará el crédito directamente.")
            return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
        
        if not venta.cantidad_apertura or venta.cantidad_apertura <= 0:
            messages.error(request, "Esta venta no tiene pago de apertura.")
            return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
        
        if venta.modo_pago_apertura not in ['TRN', 'TAR', 'DEP']:
            messages.error(request, "Este tipo de pago no requiere comprobante.")
            return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
        
        # Obtener la imagen del request
        imagen = request.FILES.get('comprobante_apertura')
        if not imagen:
            messages.error(request, "Debes seleccionar una imagen del comprobante.")
            return redirect('detalle_venta', pk=venta.pk, slug=venta.slug_safe)
        
        # Guardar el comprobante
        venta.comprobante_apertura = imagen
        venta.comprobante_apertura_subido = True
        venta.comprobante_apertura_subido_en = timezone.now()
        venta.comprobante_apertura_subido_por = request.user
        venta.save()
        
        # Crear notificaciones para CONTADOR
        contadores = User.objects.filter(perfil__rol='CONTADOR')
        modo_pago_display = dict(VentaViaje.MODO_PAGO_CHOICES).get(venta.modo_pago_apertura, venta.modo_pago_apertura)
        mensaje_contador = f"Pago de apertura pendiente de confirmación: ${venta.cantidad_apertura:,.2f} ({modo_pago_display}) - Venta #{venta.pk} - Cliente: {venta.cliente.nombre_completo_display}"
        
        for contador in contadores:
            # Eliminar notificaciones previas de apertura para esta venta
            Notificacion.objects.filter(
                usuario=contador,
                venta=venta,
                abono__isnull=True,  # Notificaciones sin abono son de apertura
                tipo='PAGO_PENDIENTE',
                confirmado=False
            ).delete()
            
            Notificacion.objects.create(
                usuario=contador,
                tipo='PAGO_PENDIENTE',
                mensaje=mensaje_contador,
                venta=venta,
                confirmado=False
            )
        
        # Crear notificaciones para JEFE
        jefes = User.objects.filter(perfil__rol='JEFE')
        mensaje_jefe = f"Pago de apertura pendiente de confirmación: ${venta.cantidad_apertura:,.2f} ({modo_pago_display}) - Venta #{venta.pk}"
        for jefe in jefes:
            # Eliminar notificaciones previas
            Notificacion.objects.filter(
                usuario=jefe,
                venta=venta,
                abono__isnull=True,
                tipo='PAGO_PENDIENTE',
                confirmado=False
            ).delete()
            
            Notificacion.objects.create(
                usuario=jefe,
                tipo='APERTURA',
                mensaje=mensaje_jefe,
                venta=venta,
                confirmado=False
            )
        
        messages.success(request, "Comprobante de apertura subido exitosamente. El contador ha sido notificado.")
        return redirect(reverse('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=abonos')


class PagosPorConfirmarView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Vista para que el contador vea todos los pagos pendientes de confirmar."""
    
    template_name = 'ventas/pagos_por_confirmar.html'
    
    def test_func(self):
        """Solo CONTADOR puede acceder."""
        return get_user_role(self.request.user) == 'CONTADOR'
    
    def handle_no_permission(self):
        messages.error(self.request, "Solo el contador puede acceder a esta sección.")
        return redirect('dashboard')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Obtener pagos pendientes de confirmar
        # Abonos pendientes con comprobante subido
        abonos_pendientes = AbonoPago.objects.filter(
            Q(forma_pago__in=['TRN', 'TAR', 'DEP']) &
            Q(confirmado=False) &
            Q(comprobante_subido=True)
        ).select_related('venta', 'venta__cliente', 'venta__vendedor', 'registrado_por').order_by('-fecha_pago')
        
        # Ventas con apertura pendiente
        # Para TRN/TAR/DEP: requiere comprobante subido
        # Para CRE: no requiere comprobante, solo estar en EN_CONFIRMACION
        # IMPORTANTE: Solo mostrar las que están en 'EN_CONFIRMACION' (no las confirmadas)
        ventas_apertura_pendiente = VentaViaje.objects.filter(
            Q(estado_confirmacion='EN_CONFIRMACION') &  # Solo las que están en confirmación
            (
                # Transferencia, Tarjeta, Depósito: requieren comprobante
                (Q(modo_pago_apertura__in=['TRN', 'TAR', 'DEP']) & Q(cantidad_apertura__gt=0) & Q(comprobante_apertura_subido=True)) |
                # Crédito: no requiere comprobante ni cantidad_apertura > 0
                Q(modo_pago_apertura='CRE')
            )
        ).exclude(
            estado_confirmacion='COMPLETADO'  # Excluir explícitamente las ya confirmadas
        ).select_related('cliente', 'vendedor').order_by('-fecha_creacion')
        
        # Crear un objeto simple para el template que tenga los atributos abonos y aperturas
        class PagosPendientes:
            def __init__(self, abonos, aperturas):
                self.abonos = abonos
                self.aperturas = aperturas
        
        context['object'] = PagosPendientes(abonos_pendientes, ventas_apertura_pendiente)
        context['pagos_pendientes'] = context['object']  # También disponible con este nombre
        
        # Obtener pagos confirmados para el historial
        fecha_filtro = self.request.GET.get('fecha_filtro', 'mes')
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        # Abonos confirmados - Incluir todos los confirmados
        # Primero aplicar filtros de fecha, luego ordenar
        abonos_confirmados = AbonoPago.objects.filter(
            confirmado=True
        ).select_related('venta', 'venta__cliente', 'confirmado_por')
        
        # Ventas con apertura confirmada - SOLO las que tienen modo_pago que requiere confirmación
        # y que fueron confirmadas (estado_confirmacion='COMPLETADO')
        # Para TRN/TAR/DEP: requieren comprobante subido
        # Para CRE: no requiere comprobante, solo que estado no sea EN_CONFIRMACION
        ventas_apertura_confirmada = VentaViaje.objects.filter(
            Q(estado_confirmacion='COMPLETADO') &
            (
                # Transferencia, Tarjeta, Depósito: requieren comprobante subido
                (Q(modo_pago_apertura__in=['TRN', 'TAR', 'DEP']) & Q(cantidad_apertura__gt=0) & Q(comprobante_apertura_subido=True)) |
                # Crédito: no requiere comprobante
                Q(modo_pago_apertura='CRE')
            )
        ).select_related('cliente', 'vendedor')
        
        # Aplicar filtros de fecha a abonos confirmados
        # IMPORTANTE: Solo usar fecha_desde y fecha_hasta si fecha_filtro es 'personalizado'
        if fecha_filtro == 'personalizado' and fecha_desde and fecha_hasta:
            try:
                fecha_desde_obj = datetime.datetime.strptime(fecha_desde, '%Y-%m-%d').date()
                fecha_hasta_obj = datetime.datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
                # Filtrar por confirmado_en si existe, sino por fecha_pago
                abonos_confirmados = abonos_confirmados.filter(
                    Q(confirmado_en__date__range=[fecha_desde_obj, fecha_hasta_obj]) |
                    Q(confirmado_en__isnull=True, fecha_pago__date__range=[fecha_desde_obj, fecha_hasta_obj])
                )
                # También aplicar filtro a aperturas confirmadas por fecha de creación
                ventas_apertura_confirmada = ventas_apertura_confirmada.filter(
                    fecha_creacion__date__range=[fecha_desde_obj, fecha_hasta_obj]
                )
            except ValueError:
                pass
        elif fecha_filtro == 'dia':
            # Filtrar solo los de hoy
            # Usar localdate() para obtener la fecha local de México, no UTC
            hoy = timezone.localdate()
            # Buscar por confirmado_en si existe, sino por fecha_pago
            # IMPORTANTE: Usar Q objects para que funcione correctamente con OR
            abonos_confirmados = abonos_confirmados.filter(
                Q(confirmado_en__date=hoy) | 
                Q(confirmado_en__isnull=True, fecha_pago__date=hoy)
            )
            # Para aperturas, usar fecha_creacion
            ventas_apertura_confirmada = ventas_apertura_confirmada.filter(fecha_creacion__date=hoy)
        elif fecha_filtro == 'semana':
            # Usar localdate() para obtener la fecha local de México, no UTC
            semana_pasada = timezone.localdate() - timedelta(days=7)
            abonos_confirmados = abonos_confirmados.filter(
                Q(confirmado_en__date__gte=semana_pasada) | Q(confirmado_en__isnull=True, fecha_pago__date__gte=semana_pasada)
            )
            ventas_apertura_confirmada = ventas_apertura_confirmada.filter(fecha_creacion__date__gte=semana_pasada)
        elif fecha_filtro == 'mes':
            # Usar localdate() para obtener la fecha local de México, no UTC
            mes_pasado = timezone.localdate() - timedelta(days=30)
            abonos_confirmados = abonos_confirmados.filter(
                Q(confirmado_en__date__gte=mes_pasado) | Q(confirmado_en__isnull=True, fecha_pago__date__gte=mes_pasado)
            )
            ventas_apertura_confirmada = ventas_apertura_confirmada.filter(fecha_creacion__date__gte=mes_pasado)
        
        # Ordenar abonos confirmados por confirmado_en si existe, sino por fecha_pago
        from django.db.models import Case, When, F, DateTimeField
        abonos_confirmados = abonos_confirmados.annotate(
            fecha_orden=Case(
                When(confirmado_en__isnull=False, then=F('confirmado_en')),
                default=F('fecha_pago'),
                output_field=DateTimeField()
            )
        ).order_by('-fecha_orden')
        
        # Ordenar aperturas confirmadas por fecha de creación
        ventas_apertura_confirmada = ventas_apertura_confirmada.order_by('-fecha_creacion')
        
        context['abonos_confirmados'] = abonos_confirmados[:100]  # Limitar a 100 para rendimiento
        context['ventas_apertura_confirmada'] = ventas_apertura_confirmada[:100]
        context['fecha_filtro'] = fecha_filtro
        # Solo pasar fecha_desde y fecha_hasta al contexto si es personalizado
        if fecha_filtro == 'personalizado':
            context['fecha_desde'] = fecha_desde
            context['fecha_hasta'] = fecha_hasta
        else:
            context['fecha_desde'] = None
            context['fecha_hasta'] = None
        
        return context


class ConfirmarPagoDesdeListaView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Vista para confirmar un pago desde la lista de pagos por confirmar."""
    
    def test_func(self):
        """Solo CONTADOR puede confirmar pagos."""
        return get_user_role(self.request.user) == 'CONTADOR'
    
    def handle_no_permission(self):
        messages.error(self.request, "Solo el contador puede confirmar pagos.")
        return redirect('dashboard')
    
    def post(self, request, tipo, pk):
        """
        Confirma un pago. Tipo puede ser 'abono' o 'apertura'.
        """
        if tipo == 'abono':
            abono = get_object_or_404(AbonoPago, pk=pk)
            
            # Verificar que tenga comprobante subido
            if not abono.comprobante_subido:
                messages.error(request, "Este abono no tiene comprobante subido.")
                return redirect('pagos_por_confirmar')
            
            # Confirmar el abono
            abono.confirmado = True
            abono.confirmado_por = request.user
            abono.confirmado_en = timezone.now()
            abono.save()
            
            venta = abono.venta
            
            # Actualizar estado de la venta
            # El método actualizar_estado_financiero() ahora maneja correctamente
            # las aperturas confirmadas y no las cambia de estado
            venta.actualizar_estado_financiero()
            
            # Eliminar notificaciones pendientes del CONTADOR
            Notificacion.objects.filter(
                usuario=request.user,
                venta=venta,
                abono=abono,
                tipo='PAGO_PENDIENTE',
                confirmado=False
            ).delete()
            
            # Crear notificaciones para VENDEDOR y JEFE
            if venta.vendedor and venta.vendedor != request.user:
                vendedor_es_jefe = venta.vendedor.perfil.rol == 'JEFE' if hasattr(venta.vendedor, 'perfil') else False
                if not vendedor_es_jefe:
                    Notificacion.objects.create(
                        usuario=venta.vendedor,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=f"✅ Tu pago ha sido confirmado por el contador. Puedes proceder con la venta #{venta.pk}",
                        venta=venta,
                        abono=abono,
                        confirmado=True
                    )
            
            # Actualizar notificaciones del JEFE
            jefes = User.objects.filter(perfil__rol='JEFE')
            forma_pago_display = dict(AbonoPago.FORMA_PAGO_CHOICES).get(abono.forma_pago, abono.forma_pago)
            mensaje_jefe = f"✅ Pago confirmado por el contador: ${abono.monto:,.2f} ({forma_pago_display}) - Venta #{venta.pk}"
            
            for jefe in jefes:
                # Actualizar notificaciones pendientes
                notificaciones_jefe = Notificacion.objects.filter(
                    usuario=jefe,
                    venta=venta,
                    abono=abono,
                    tipo='PAGO_PENDIENTE',
                    confirmado=False
                )
                if notificaciones_jefe.exists():
                    notificaciones_jefe.update(
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_jefe,
                        confirmado=True,
                        confirmado_por=request.user,
                        confirmado_en=timezone.now()
                    )
                else:
                    Notificacion.objects.create(
                        usuario=jefe,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_jefe,
                        venta=venta,
                        abono=abono,
                        confirmado=True
                    )
            
            messages.success(request, f"Abono de ${abono.monto:,.2f} confirmado exitosamente.")
            
        elif tipo == 'apertura':
            venta = get_object_or_404(VentaViaje, pk=pk)
            
            # Verificar que tenga comprobante subido (solo para TRN/TAR/DEP, no para crédito)
            if venta.modo_pago_apertura in ['TRN', 'TAR', 'DEP'] and not venta.comprobante_apertura_subido:
                messages.error(request, "Este pago de apertura no tiene comprobante subido.")
                return redirect('pagos_por_confirmar')
            
            # Confirmar la apertura (cambiar estado de la venta)
            venta.estado_confirmacion = 'COMPLETADO'
            venta.save(update_fields=['estado_confirmacion'])
            
            # Eliminar notificaciones pendientes del CONTADOR
            Notificacion.objects.filter(
                usuario=request.user,
                venta=venta,
                abono__isnull=True,  # Notificaciones sin abono son de apertura
                tipo='PAGO_PENDIENTE',
                confirmado=False
            ).delete()
            
            # Crear notificaciones para VENDEDOR y JEFE
            if venta.vendedor and venta.vendedor != request.user:
                vendedor_es_jefe = venta.vendedor.perfil.rol == 'JEFE' if hasattr(venta.vendedor, 'perfil') else False
                if not vendedor_es_jefe:
                    Notificacion.objects.create(
                        usuario=venta.vendedor,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=f"✅ Tu pago de apertura ha sido confirmado por el contador. Puedes proceder con la venta #{venta.pk}",
                        venta=venta,
                        confirmado=True
                    )
            
            # Actualizar notificaciones del JEFE
            jefes = User.objects.filter(perfil__rol='JEFE')
            modo_pago_display = dict(VentaViaje.MODO_PAGO_CHOICES).get(venta.modo_pago_apertura, venta.modo_pago_apertura)
            if venta.modo_pago_apertura == 'CRE':
                mensaje_jefe = f"✅ Crédito confirmado por el contador ({modo_pago_display}) - Venta #{venta.pk}"
            else:
                mensaje_jefe = f"✅ Pago de apertura confirmado por el contador: ${venta.cantidad_apertura:,.2f} ({modo_pago_display}) - Venta #{venta.pk}"
            
            for jefe in jefes:
                # Actualizar notificaciones pendientes
                notificaciones_jefe = Notificacion.objects.filter(
                    usuario=jefe,
                    venta=venta,
                    abono__isnull=True,
                    tipo='PAGO_PENDIENTE',
                    confirmado=False
                )
                if notificaciones_jefe.exists():
                    notificaciones_jefe.update(
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_jefe,
                        confirmado=True,
                        confirmado_por=request.user,
                        confirmado_en=timezone.now()
                    )
                else:
                    Notificacion.objects.create(
                        usuario=jefe,
                        tipo='PAGO_CONFIRMADO',
                        mensaje=mensaje_jefe,
                        venta=venta,
                        confirmado=True
                    )
            
            messages.success(request, f"Pago de apertura de ${venta.cantidad_apertura:,.2f} confirmado exitosamente.")
        else:
            messages.error(request, "Tipo de pago inválido.")
            return redirect('pagos_por_confirmar')
        
        return redirect('pagos_por_confirmar')


# ------------------- 9. COTIZACIONES -------------------
class CotizacionListView(LoginRequiredMixin, ListView):
    model = Cotizacion
    template_name = 'ventas/cotizacion_list.html'
    context_object_name = 'cotizaciones'

    def get_queryset(self):
        qs = super().get_queryset().select_related('cliente', 'vendedor')
        cliente_id = self.request.GET.get('cliente')
        estado = self.request.GET.get('estado')
        if cliente_id:
            qs = qs.filter(cliente_id=cliente_id)
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        from datetime import timedelta
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        start_week = today - timedelta(days=today.weekday())
        start_month = today.replace(day=1)

        qs_base = Cotizacion.objects.all()
        user = self.request.user
        usuario_qs = qs_base.filter(vendedor=user) if user.is_authenticated else Cotizacion.objects.none()

        def rangos(qs):
            return {
                'hoy': qs.filter(creada_en__date=today).count(),
                'semana': qs.filter(creada_en__date__gte=start_week).count(),
                'mes': qs.filter(creada_en__date__gte=start_month).count(),
            }

        context['stats_propias'] = rangos(usuario_qs)
        context['stats_globales'] = rangos(qs_base)
        return context


class CotizacionCreateView(LoginRequiredMixin, CreateView):
    model = Cotizacion
    form_class = CotizacionForm
    template_name = 'ventas/cotizacion_form.html'

    def form_valid(self, form):
        form.instance.vendedor = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('cotizacion_detalle', kwargs={'slug': self.object.slug})


class CotizacionUpdateView(LoginRequiredMixin, UpdateView):
    model = Cotizacion
    form_class = CotizacionForm
    template_name = 'ventas/cotizacion_form.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get_success_url(self):
        return reverse('cotizacion_detalle', kwargs={'slug': self.object.slug})


class CotizacionDetailView(LoginRequiredMixin, DetailView):
    model = Cotizacion
    template_name = 'ventas/cotizacion_detail.html'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    context_object_name = 'cotizacion'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if not obj.folio:
            obj.save(update_fields=[])  # trigger folio generation
        return obj


class CotizacionDocxView(LoginRequiredMixin, DetailView):
    model = Cotizacion
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get(self, request, *args, **kwargs):
        try:
            cot = self.get_object()
        except Exception as e:
            logging.error(f"Error obteniendo cotización: {e}")
            return HttpResponse(f"Error: No se pudo obtener la cotización. {str(e)}", status=400)
        
        template_path = os.path.join(settings.BASE_DIR, 'static', 'docx', 'membrete.docx')
        if not os.path.exists(template_path):
            error_msg = f'La plantilla DOCX no fue encontrada en: {template_path}'
            logging.error(error_msg)
            return HttpResponse(error_msg, status=404)

        try:
            from docx import Document
            from docx.shared import Pt, RGBColor, Inches
            from docx.oxml.ns import qn
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError as e:
            error_msg = f'python-docx no está instalado en el entorno: {e}'
            logging.error(error_msg)
            return HttpResponse(error_msg, status=500)

        def format_date(value):
            if not value:
                return '-'
            try:
                if isinstance(value, datetime.date):
                    parsed = value
                else:
                    parsed = datetime.date.fromisoformat(str(value))
                return parsed.strftime('%d/%m/%Y')
            except Exception:
                return str(value)

        def format_currency(value):
            if value in (None, '', 0):
                return '0.00'
            try:
                number = Decimal(str(value).replace(',', ''))
            except Exception:
                return str(value)
            return f"{number:,.2f}"

        doc = Document(template_path)
        section = doc.sections[0]

        MOVUMS_BLUE = RGBColor(15, 92, 192)
        MOVUMS_LIGHT_BLUE = RGBColor(92, 141, 214)
        TEXT_COLOR = RGBColor(20, 20, 20)
        MOVUMS_BLUE_CORP = RGBColor(0, 74, 142)

        style = doc.styles['Normal']
        style.font.name = 'Arial'
        style.font.size = Pt(12)
        style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')

        def set_run_font(run, size=12, bold=False, color=TEXT_COLOR):
            run.font.name = 'Arial'
            run.font.size = Pt(size)
            run.bold = bold
            run.font.color.rgb = color

        def add_paragraph(doc_obj, text='', size=12, bold=False, color=TEXT_COLOR, space_before=0, space_after=0):
            paragraph = doc_obj.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(space_before)
            paragraph.paragraph_format.space_after = Pt(space_after)
            run = paragraph.add_run(text)
            set_run_font(run, size=size, bold=bold, color=color)
            return paragraph

        # Obtener fecha de cotización desde propuestas o usar fecha de creación
        fecha_cotizacion = None
        if isinstance(cot.propuestas, dict) and cot.propuestas.get('fecha_cotizacion'):
            try:
                fecha_cotizacion = datetime.date.fromisoformat(cot.propuestas['fecha_cotizacion'])
            except (ValueError, TypeError):
                fecha_cotizacion = cot.creada_en.date() if cot.creada_en else None
        else:
            fecha_cotizacion = cot.creada_en.date() if cot.creada_en else None
        
        # Título de la cotización
        titulo_paragraph = doc.add_paragraph()
        titulo_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        titulo_paragraph.paragraph_format.space_before = Pt(12)
        titulo_paragraph.paragraph_format.space_after = Pt(6)
        titulo_run = titulo_paragraph.add_run(cot.titulo or 'Cotización de Viaje')
        set_run_font(titulo_run, size=16, bold=True, color=MOVUMS_BLUE_CORP)
        
        # Información del cliente
        cliente_paragraph = doc.add_paragraph()
        cliente_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        cliente_paragraph.paragraph_format.space_after = Pt(6)
        cliente_label_run = cliente_paragraph.add_run('Cliente: ')
        set_run_font(cliente_label_run, size=12, bold=True, color=TEXT_COLOR)
        cliente_value_run = cliente_paragraph.add_run(cot.cliente.nombre_completo_display)
        set_run_font(cliente_value_run, size=12, bold=False, color=TEXT_COLOR)
        
        # Fecha de cotización
        fecha_paragraph = doc.add_paragraph()
        fecha_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        fecha_paragraph.paragraph_format.space_after = Pt(12)
        fecha_run = fecha_paragraph.add_run(f"Fecha de Cotización: {format_date(fecha_cotizacion)}")
        set_run_font(fecha_run, size=14, bold=True, color=MOVUMS_BLUE)

        propuestas = cot.propuestas if isinstance(cot.propuestas, dict) else {}
        tipo = propuestas.get('tipo', 'vuelos')  # Default a 'vuelos' si no está en propuestas
        
        # Determinar si es traslados o renta_autos para ajustar la tabla de información
        es_traslados = tipo == 'traslados'
        es_renta_autos = tipo == 'renta_autos'
        
        # Para traslados, usar datos desde propuestas si están disponibles
        if es_traslados and propuestas.get('traslados'):
            traslados_data = propuestas.get('traslados', {})
            origen_val = traslados_data.get('desde') or cot.origen or '-'
            destino_val = traslados_data.get('hasta') or cot.destino or '-'
        elif es_renta_autos and propuestas.get('renta_autos'):
            # Para renta_autos, usar punto de origen y punto de regreso desde propuestas
            renta_autos_data = propuestas.get('renta_autos', {})
            origen_val = renta_autos_data.get('punto_origen') or '-'
            destino_val = renta_autos_data.get('punto_regreso') or '-'
        else:
            origen_val = cot.origen or '-'
            destino_val = cot.destino or '-'
        
        # Preparar información de edades de menores
        edades_menores_texto = ''
        if cot.edades_menores and cot.edades_menores.strip():
            edades_menores_texto = f" (Edades: {cot.edades_menores})"
        
        # Construir datos de la tabla según el tipo
        if es_traslados:
            # Para traslados: solo mostrar origen/destino y pasajeros
            pasajeros_texto = f"{cot.adultos or 0} Adultos / {cot.menores or 0} Menores{edades_menores_texto}"
            info_data = [
                ("Desde / Hasta", origen_val, destino_val),
                ("Pasajeros", str(cot.pasajeros) or '1', pasajeros_texto),
            ]
            info_table = doc.add_table(rows=len(info_data), cols=3)
        elif es_renta_autos:
            # Para renta_autos: solo mostrar punto de origen/regreso y pasajeros (sin fechas ni días/noches)
            pasajeros_texto = f"{cot.adultos or 0} Adultos / {cot.menores or 0} Menores{edades_menores_texto}"
            info_data = [
                ("Punto de Origen / Punto de Regreso", origen_val, destino_val),
                ("Pasajeros", str(cot.pasajeros) or '1', pasajeros_texto),
            ]
            info_table = doc.add_table(rows=len(info_data), cols=3)
        else:
            # Para otros tipos: mostrar toda la información
            pasajeros_texto = f"{cot.adultos or 0} Adultos / {cot.menores or 0} Menores{edades_menores_texto}"
            info_data = [
                ("Origen / Destino", origen_val, destino_val),
                ("Inicio / Fin", format_date(cot.fecha_inicio) if cot.fecha_inicio else '-', format_date(cot.fecha_fin) if cot.fecha_fin else '-'),
                ("Pasajeros", str(cot.pasajeros) or '1', pasajeros_texto),
                ("Viaje", f"{cot.dias or '-'} días", f"{cot.noches or '-'} noches"),
            ]
            info_table = doc.add_table(rows=len(info_data), cols=3)
        
        for row_idx, (label, v1, v2) in enumerate(info_data):
            row = info_table.rows[row_idx].cells
            label_run = row[0].paragraphs[0].add_run(label)
            set_run_font(label_run, size=14, bold=True, color=MOVUMS_BLUE)
            val1_run = row[1].paragraphs[0].add_run(v1)
            set_run_font(val1_run, size=12)
            val2_run = row[2].paragraphs[0].add_run(v2)
            set_run_font(val2_run, size=12)

        add_paragraph(doc, "", space_after=6)
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)

        def agregar_subtitulo_con_vineta(texto):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            bullet_run = p.add_run('• ')
            set_run_font(bullet_run, size=14, bold=True, color=MOVUMS_BLUE_CORP)
            texto_run = p.add_run(texto)
            set_run_font(texto_run, size=14, bold=True, color=MOVUMS_BLUE_CORP)
            spacer = doc.add_paragraph()
            spacer.paragraph_format.space_after = Pt(2)
            return p

        def agregar_info_line(etiqueta, valor):
            if not valor:
                return
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            label_run = p.add_run(f'{etiqueta}: ')
            set_run_font(label_run, size=12, bold=True)
            value_run = p.add_run(str(valor))
            set_run_font(value_run, size=12)
            return p

        def agregar_info_inline(*pares_etiqueta_valor, separador=' | '):
            if not pares_etiqueta_valor:
                return
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(4)
            for idx, (etiqueta, valor) in enumerate(pares_etiqueta_valor):
                if not valor:
                    continue
                if idx > 0:
                    sep_run = p.add_run(separador)
                    set_run_font(sep_run, size=12)
                label_run = p.add_run(f'{etiqueta}: ')
                set_run_font(label_run, size=12, bold=True)
                value_run = p.add_run(str(valor))
                set_run_font(value_run, size=12)
            return p

        def agregar_salto_entre_secciones():
            spacer = doc.add_paragraph()
            spacer.paragraph_format.space_after = Pt(6)
            return spacer

        def agregar_titulo_principal(texto):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(10)
            run = p.add_run(texto)
            set_run_font(run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
            return p

        if tipo == 'vuelos' and propuestas.get('vuelos'):
            for vuelo in propuestas.get('vuelos', []):
                agregar_titulo_principal("VUELO")
                agregar_subtitulo_con_vineta('Información del Vuelo')
                agregar_info_inline(
                    ('Aerolínea', vuelo.get('aerolinea') or '-'),
                    ('Salida', vuelo.get('salida') or '-'),
                    ('Regreso', vuelo.get('regreso') or '-')
                )
                agregar_info_line('Incluye', vuelo.get('incluye') or '-')
                if vuelo.get('forma_pago'):
                    agregar_info_line('Forma de Pago', vuelo.get('forma_pago'))
                total_p = doc.add_paragraph()
                total_p.paragraph_format.space_before = Pt(0)
                total_p.paragraph_format.space_after = Pt(6)
                total_run = total_p.add_run(f"Total MXN {format_currency(vuelo.get('total'))} Pesos")
                set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
                total_run.font.underline = True
                agregar_salto_entre_secciones()

        elif tipo == 'hospedaje' and propuestas.get('hoteles'):
            for hotel in propuestas.get('hoteles', []):
                agregar_titulo_principal("HOSPEDAJE")
                agregar_subtitulo_con_vineta('Información del Alojamiento')
                info_table = doc.add_table(rows=4, cols=2)
                info_table.autofit = False
                for col in info_table.columns:
                    for cell in col.cells:
                        cell.width = Inches(3.25)
                nombre_cell = info_table.rows[0].cells[0]
                nombre_label = nombre_cell.paragraphs[0].add_run('Nombre: ')
                set_run_font(nombre_label, size=12, bold=True)
                nombre_val = nombre_cell.paragraphs[0].add_run(hotel.get('nombre') or 'Hotel propuesto')
                set_run_font(nombre_val, size=12)
                habitacion_cell = info_table.rows[1].cells[0]
                habitacion_label = habitacion_cell.paragraphs[0].add_run('Habitación: ')
                set_run_font(habitacion_label, size=12, bold=True)
                habitacion_val = habitacion_cell.paragraphs[0].add_run(hotel.get('habitacion') or '-')
                set_run_font(habitacion_val, size=12)
                direccion_cell = info_table.rows[2].cells[0]
                direccion_label = direccion_cell.paragraphs[0].add_run('Dirección: ')
                set_run_font(direccion_label, size=12, bold=True)
                direccion_val = direccion_cell.paragraphs[0].add_run(hotel.get('direccion') or '-')
                set_run_font(direccion_val, size=12)
                plan_cell = info_table.rows[0].cells[1]
                plan_label = plan_cell.paragraphs[0].add_run('Plan de Alimentos: ')
                set_run_font(plan_label, size=12, bold=True)
                plan_val = plan_cell.paragraphs[0].add_run(hotel.get('plan') or '-')
                set_run_font(plan_val, size=12)
                if hotel.get('forma_pago'):
                    forma_pago_cell = info_table.rows[1].cells[1]
                    forma_pago_label = forma_pago_cell.paragraphs[0].add_run('Forma de Pago: ')
                    set_run_font(forma_pago_label, size=12, bold=True)
                    forma_pago_val = forma_pago_cell.paragraphs[0].add_run(hotel.get('forma_pago'))
                    set_run_font(forma_pago_val, size=12)
                total_p = doc.add_paragraph()
                total_p.paragraph_format.space_before = Pt(0)
                total_p.paragraph_format.space_after = Pt(6)
                total_run = total_p.add_run(f"Total MXN {format_currency(hotel.get('total'))} Pesos")
                set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
                total_run.font.underline = True
                agregar_salto_entre_secciones()

        elif tipo == 'paquete' and propuestas.get('paquete'):
            paquete = propuestas.get('paquete', {})
            vuelo = paquete.get('vuelo') or {}
            hotel = paquete.get('hotel') or {}
            agregar_titulo_principal("PAQUETE")
            agregar_subtitulo_con_vineta('Vuelo')
            agregar_info_inline(
                ('Aerolínea', vuelo.get('aerolinea') or '-'),
                ('Salida', vuelo.get('salida') or '-'),
                ('Regreso', vuelo.get('regreso') or '-')
            )
            agregar_info_line('Incluye', vuelo.get('incluye') or '-')
            if vuelo.get('forma_pago'):
                agregar_info_line('Forma de Pago', vuelo.get('forma_pago'))
            agregar_salto_entre_secciones()
            agregar_subtitulo_con_vineta('Hospedaje')
            hospedaje_table = doc.add_table(rows=3, cols=2)
            hospedaje_table.autofit = False
            for col in hospedaje_table.columns:
                for cell in col.cells:
                    cell.width = Inches(3.25)
            nombre_cell = hospedaje_table.rows[0].cells[0]
            nombre_label = nombre_cell.paragraphs[0].add_run('Nombre: ')
            set_run_font(nombre_label, size=12, bold=True)
            nombre_val = nombre_cell.paragraphs[0].add_run(hotel.get('nombre') or 'Hotel incluido')
            set_run_font(nombre_val, size=12)
            habitacion_cell = hospedaje_table.rows[1].cells[0]
            habitacion_label = habitacion_cell.paragraphs[0].add_run('Habitación / Plan: ')
            set_run_font(habitacion_label, size=12, bold=True)
            habitacion_val = habitacion_cell.paragraphs[0].add_run(hotel.get('habitacion') or '-')
            set_run_font(habitacion_val, size=12)
            notas_cell = hospedaje_table.rows[2].cells[0]
            notas_label = notas_cell.paragraphs[0].add_run('Notas: ')
            set_run_font(notas_label, size=12, bold=True)
            notas_val = notas_cell.paragraphs[0].add_run(hotel.get('notas') or '-')
            set_run_font(notas_val, size=12)
            if paquete.get('forma_pago'):
                agregar_info_line('Forma de Pago', paquete.get('forma_pago'))
            total_p = doc.add_paragraph()
            total_p.paragraph_format.space_before = Pt(0)
            total_p.paragraph_format.space_after = Pt(6)
            total_run = total_p.add_run(f"Total MXN {format_currency(paquete.get('total'))} Pesos")
            set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
            total_run.font.underline = True
            agregar_salto_entre_secciones()
            
            # Tours del Paquete
            if paquete.get('tours') and isinstance(paquete.get('tours'), list) and len(paquete.get('tours')) > 0:
                agregar_subtitulo_con_vineta('Tours del Paquete')
                for idx, tour in enumerate(paquete.get('tours'), 1):
                    if len(paquete.get('tours')) > 1:
                        agregar_info_line('Tour', f'Tour del Paquete {idx}')
                    agregar_info_line('Nombre del Tour', tour.get('nombre') or '-')
                    
                    if tour.get('total'):
                        total_tour_p = doc.add_paragraph()
                        total_tour_p.paragraph_format.space_before = Pt(0)
                        total_tour_p.paragraph_format.space_after = Pt(6)
                        total_tour_run = total_tour_p.add_run(f"Total MXN {format_currency(tour.get('total'))} Pesos")
                        set_run_font(total_tour_run, size=16, bold=True, color=MOVUMS_BLUE_CORP)
                        total_tour_run.font.underline = True
                    
                    if tour.get('especificaciones'):
                        especificaciones = tour.get('especificaciones', '').strip()
                        if especificaciones:
                            agregar_salto_entre_secciones()
                            agregar_subtitulo_con_vineta('Especificaciones')
                            lineas = especificaciones.split('\n')
                            for linea in lineas:
                                if linea.strip():
                                    p = doc.add_paragraph()
                                    p.paragraph_format.space_after = Pt(4)
                                    run = p.add_run(linea.strip())
                                    set_run_font(run, size=12)
                    
                    if tour.get('forma_pago'):
                        agregar_salto_entre_secciones()
                        agregar_subtitulo_con_vineta('Forma de Pago')
                        agregar_info_line('Forma de Pago', tour.get('forma_pago'))
                    
                    # Agregar separador entre tours si hay más de uno
                    if idx < len(paquete.get('tours')):
                        agregar_salto_entre_secciones()
                        agregar_salto_entre_secciones()
                
                agregar_salto_entre_secciones()

        elif tipo == 'tours' and propuestas.get('tours'):
            tours_data = propuestas.get('tours', {})
            
            # Verificar si es un array de tours o un objeto único (compatibilidad)
            tours_list = []
            if isinstance(tours_data, list):
                tours_list = tours_data
            else:
                # Compatibilidad: convertir objeto único a array
                tours_list = [tours_data] if tours_data else []
            
            if tours_list:
                agregar_titulo_principal("TOURS" if len(tours_list) > 1 else "TOUR")
                
                for idx, tour in enumerate(tours_list, 1):
                    if len(tours_list) > 1:
                        agregar_subtitulo_con_vineta(f'Tour {idx}')
                    else:
                        agregar_subtitulo_con_vineta('Información del Tour')
                    
                    agregar_info_line('Nombre del Tour', tour.get('nombre') or '-')
                    
                    if tour.get('total'):
                        total_p = doc.add_paragraph()
                        total_p.paragraph_format.space_before = Pt(0)
                        total_p.paragraph_format.space_after = Pt(6)
                        total_run = total_p.add_run(f"Total MXN {format_currency(tour.get('total'))} Pesos")
                        set_run_font(total_run, size=16, bold=True, color=MOVUMS_BLUE_CORP)
                        total_run.font.underline = True
                    
                    if tour.get('especificaciones'):
                        agregar_salto_entre_secciones()
                        agregar_subtitulo_con_vineta('Especificaciones')
                        especificaciones = tour.get('especificaciones', '').strip()
                        if especificaciones:
                            lineas = especificaciones.split('\n')
                            for linea in lineas:
                                if linea.strip():
                                    p = doc.add_paragraph()
                                    p.paragraph_format.space_after = Pt(4)
                                    run = p.add_run(linea.strip())
                                    set_run_font(run, size=12)
                    
                    if tour.get('forma_pago'):
                        agregar_salto_entre_secciones()
                        agregar_subtitulo_con_vineta('Forma de Pago')
                        agregar_info_line('Forma de Pago', tour.get('forma_pago'))
                    
                    # Agregar separador entre tours si hay más de uno
                    if idx < len(tours_list):
                        agregar_salto_entre_secciones()
                        agregar_salto_entre_secciones()
                
                agregar_salto_entre_secciones()

        elif tipo == 'traslados' and propuestas.get('traslados'):
            traslados_data = propuestas.get('traslados', {})
            agregar_titulo_principal("TRASLADO")
            agregar_subtitulo_con_vineta('Información del Traslado')
            agregar_info_inline(
                ('Tipo', traslados_data.get('tipo') or '-'),
                ('Modalidad', traslados_data.get('modalidad') or '-')
            )
            agregar_info_inline(
                ('Desde', traslados_data.get('desde') or '-'),
                ('Hasta', traslados_data.get('hasta') or '-')
            )
            # Si es traslado redondo, mostrar fechas y horarios
            if traslados_data.get('modalidad') == 'REDONDO':
                if traslados_data.get('fecha_ida') or traslados_data.get('fecha_regreso'):
                    agregar_info_inline(
                        ('Fecha de Ida', format_date(traslados_data.get('fecha_ida'))),
                        ('Fecha de Regreso', format_date(traslados_data.get('fecha_regreso')))
                    )
                if traslados_data.get('hora_ida') or traslados_data.get('hora_regreso'):
                    agregar_info_inline(
                        ('Hora de Ida', traslados_data.get('hora_ida') or '-'),
                        ('Hora de Regreso', traslados_data.get('hora_regreso') or '-')
                    )
            if traslados_data.get('descripcion'):
                agregar_salto_entre_secciones()
                agregar_subtitulo_con_vineta('Descripción')
                descripcion = traslados_data.get('descripcion', '').strip()
                if descripcion:
                    lineas = descripcion.split('\n')
                    for linea in lineas:
                        if linea.strip():
                            p = doc.add_paragraph()
                            p.paragraph_format.space_after = Pt(4)
                            run = p.add_run(linea.strip())
                            set_run_font(run, size=12)
            if traslados_data.get('forma_pago'):
                agregar_salto_entre_secciones()
                agregar_subtitulo_con_vineta('Forma de Pago')
                agregar_info_line('Forma de Pago', traslados_data.get('forma_pago'))
            total_p = doc.add_paragraph()
            total_p.paragraph_format.space_before = Pt(0)
            total_p.paragraph_format.space_after = Pt(6)
            total_run = total_p.add_run(f"Total MXN {format_currency(traslados_data.get('total'))} Pesos")
            set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
            total_run.font.underline = True
            agregar_salto_entre_secciones()

        elif tipo == 'renta_autos' and propuestas.get('renta_autos'):
            renta_autos_data = propuestas.get('renta_autos', {})
            agregar_titulo_principal("RENTA DE AUTOS")
            agregar_subtitulo_con_vineta('Información de la Renta')
            agregar_info_inline(
                ('Arrendadora', renta_autos_data.get('arrendadora') or '-'),
                ('Punto de Origen', renta_autos_data.get('punto_origen') or '-'),
                ('Punto de Regreso', renta_autos_data.get('punto_regreso') or '-')
            )
            if renta_autos_data.get('hora_pickup') or renta_autos_data.get('hora_devolucion'):
                agregar_info_inline(
                    ('Hora de Pickup', renta_autos_data.get('hora_pickup') or '-'),
                    ('Hora de Devolución', renta_autos_data.get('hora_devolucion') or '-')
                )
            if renta_autos_data.get('forma_pago'):
                agregar_salto_entre_secciones()
                agregar_subtitulo_con_vineta('Forma de Pago')
                agregar_info_line('Forma de Pago', renta_autos_data.get('forma_pago'))
            total_p = doc.add_paragraph()
            total_p.paragraph_format.space_before = Pt(0)
            total_p.paragraph_format.space_after = Pt(6)
            total_run = total_p.add_run(f"Total MXN {format_currency(renta_autos_data.get('total'))} Pesos")
            set_run_font(total_run, size=18, bold=True, color=MOVUMS_BLUE_CORP)
            total_run.font.underline = True
            agregar_salto_entre_secciones()

        elif tipo == 'generica' and propuestas.get('generica'):
            generica_data = propuestas.get('generica', {})
            agregar_titulo_principal("COTIZACIÓN GENÉRICA")
            if generica_data.get('contenido'):
                contenido = generica_data.get('contenido', '').strip()
                if contenido:
                    lineas = contenido.split('\n')
                    for linea in lineas:
                        if linea.strip():
                            p = doc.add_paragraph()
                            p.paragraph_format.space_after = Pt(4)
                            run = p.add_run(linea.strip())
                            set_run_font(run, size=12)

        try:
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            if buffer.getvalue() is None or len(buffer.getvalue()) == 0:
                error_msg = 'El documento generado está vacío'
                logging.error(error_msg)
                return HttpResponse(error_msg, status=500)

            filename = f"cotizacion_{cot.slug}_{timezone.now().strftime('%Y%m%d%H%M%S')}.docx"
            response = HttpResponse(
                buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        except Exception as e:
            error_msg = f'Error al generar el documento DOCX: {str(e)}'
            logging.error(error_msg, exc_info=True)
            return HttpResponse(error_msg, status=500)


class CotizacionPDFView(LoginRequiredMixin, DetailView):
    """
    Vista para generar cotizaciones en formato PDF usando WeasyPrint.
    Incluye sistema de cache para mejorar el rendimiento.
    """
    model = Cotizacion
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

    def get(self, request, *args, **kwargs):
        try:
            cot = self.get_object()
        except Exception as e:
            logging.error(f"Error obteniendo cotización: {e}")
            return HttpResponse(f"Error: No se pudo obtener la cotización. {str(e)}", status=400)
        
        # Verificar disponibilidad de WeasyPrint
        if not WEASYPRINT_AVAILABLE:
            return HttpResponse(
                "Error: WeasyPrint no está disponible. Por favor instálalo con: pip install weasyprint", 
                status=500
            )
        
        # Cache deshabilitado temporalmente para forzar regeneración con nuevos estilos
        # TODO: Re-habilitar cache una vez que los estilos estén estabilizados
        # pdf_path = self._get_cache_path(cot)
        # if os.path.exists(pdf_path):
        #     cache_mtime = os.path.getmtime(pdf_path)
        #     cot_mtime = cot.actualizada_en.timestamp() if cot.actualizada_en else 0
        #     if cache_mtime >= cot_mtime:
        #         try:
        #             with open(pdf_path, 'rb') as f:
        #                 pdf_content = f.read()
        #             return self._crear_respuesta_pdf(pdf_content, cot)
        #         except Exception as e:
        #             logging.warning(f"Error leyendo cache, regenerando: {e}")
        
        # Generar nuevo PDF
        try:
            pdf_content = self._generar_pdf(cot)
            
            # Cache deshabilitado temporalmente
            # Guardar en cache
            # try:
            #     pdf_path = self._get_cache_path(cot)
            #     os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            #     with open(pdf_path, 'wb') as f:
            #         f.write(pdf_content)
            # except Exception as e:
            #     logging.warning(f"Error guardando en cache: {e}")
            
            return self._crear_respuesta_pdf(pdf_content, cot)
            
        except Exception as e:
            error_msg = f'Error al generar el documento PDF: {str(e)}'
            logging.error(error_msg, exc_info=True)
            return HttpResponse(error_msg, status=500)
    
    def _get_cache_path(self, cotizacion):
        """Genera la ruta del archivo cacheado."""
        cache_dir = os.path.join(settings.MEDIA_ROOT, 'cache', 'pdfs')
        # Usar slug y timestamp de actualización para invalidar cache automáticamente
        timestamp = int(cotizacion.actualizada_en.timestamp()) if cotizacion.actualizada_en else 0
        filename = f"cotizacion_{cotizacion.slug}_{timestamp}.pdf"
        return os.path.join(cache_dir, filename)
    
    def _preparar_contexto(self, cotizacion):
        """Prepara el contexto para la plantilla."""
        propuestas = cotizacion.propuestas if isinstance(cotizacion.propuestas, dict) else {}
        tipo = propuestas.get('tipo', 'vuelos')
        
        # Determinar template según tipo
        template_map = {
            'vuelos': 'ventas/pdf/cotizacion_vuelos_pdf.html',
            'hospedaje': 'ventas/pdf/cotizacion_hospedaje_pdf.html',
            'paquete': 'ventas/pdf/cotizacion_paquete_pdf.html',
            'tours': 'ventas/pdf/cotizacion_tours_pdf.html',
            'traslados': 'ventas/pdf/cotizacion_traslados_pdf.html',
            'renta_autos': 'ventas/pdf/cotizacion_renta_autos_pdf.html',
            'generica': 'ventas/pdf/cotizacion_generica_pdf.html',
        }
        
        template_name = template_map.get(tipo, 'ventas/pdf/cotizacion_vuelos_pdf.html')
        
        # Preparar ruta absoluta file:// para el membrete (WeasyPrint necesita URL absoluta)
        membrete_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'membrete_movums.jpg')
        membrete_url = None
        if os.path.exists(membrete_path):
            # Crear URL file:// absoluta para WeasyPrint
            membrete_abs_path = os.path.abspath(membrete_path)
            # En Windows, necesitamos ajustar el formato de la ruta
            if os.name == 'nt':
                membrete_url = f"file:///{membrete_abs_path.replace(os.sep, '/')}"
            else:
                membrete_url = f"file://{membrete_abs_path}"
        
        # Obtener información del ejecutivo que realizó la cotización
        ejecutivo = None
        ejecutivo_nombre = None
        ejecutivo_telefono = None
        
        if cotizacion.vendedor:
            try:
                # Intentar obtener el Ejecutivo asociado al usuario
                ejecutivo = Ejecutivo.objects.filter(usuario=cotizacion.vendedor).first()
                
                if ejecutivo:
                    # Si hay ejecutivo, usar su nombre y teléfono
                    ejecutivo_nombre = ejecutivo.nombre_completo
                    if ejecutivo.telefono:
                        # Formatear teléfono a 10 dígitos (eliminar espacios, guiones, paréntesis, etc.)
                        telefono_limpio = re.sub(r'[^\d]', '', ejecutivo.telefono)
                        # Si tiene más de 10 dígitos (puede incluir código de país), tomar los últimos 10
                        if len(telefono_limpio) > 10:
                            ejecutivo_telefono = telefono_limpio[-10:]
                        elif len(telefono_limpio) == 10:
                            ejecutivo_telefono = telefono_limpio
                        else:
                            ejecutivo_telefono = ejecutivo.telefono  # Mantener original si no tiene 10 dígitos
                else:
                    # Si no hay ejecutivo asociado, usar el nombre del usuario como fallback
                    ejecutivo_nombre = f"{cotizacion.vendedor.get_full_name() or cotizacion.vendedor.get_username()}"
                    logger.info(f"Usuario {cotizacion.vendedor.username} no tiene Ejecutivo asociado, usando nombre de usuario")
            except Exception as e:
                logger.warning(f"Error al obtener ejecutivo para cotización {cotizacion.pk}: {e}", exc_info=True)
                # Fallback: usar el nombre del usuario
                if cotizacion.vendedor:
                    ejecutivo_nombre = f"{cotizacion.vendedor.get_full_name() or cotizacion.vendedor.get_username()}"
        
        return {
            'cotizacion': cotizacion,
            'propuestas': propuestas,
            'tipo': tipo,
            'template_name': template_name,
            'STATIC_URL': settings.STATIC_URL,
            'membrete_url': membrete_url,  # URL absoluta file:// para WeasyPrint
            'ejecutivo': ejecutivo,
            'ejecutivo_nombre': ejecutivo_nombre,
            'ejecutivo_telefono': ejecutivo_telefono,
        }
    
    def _generar_pdf(self, cotizacion):
        """
        Genera el PDF usando WeasyPrint para mejor control de diseño y formato con HTML/CSS.
        """
        from django.template.loader import render_to_string
        from weasyprint import HTML
        from io import BytesIO
        
        # Preparar contexto (ya incluye membrete en base64)
        context = self._preparar_contexto(cotizacion)
        
        # Renderizar HTML (el CSS ya está incrustado en base_cotizacion_pdf.html)
        html_string = render_to_string(context['template_name'], context, request=self.request)
        
        # Obtener rutas de archivos estáticos para recursos como imágenes
        static_dir = os.path.join(settings.BASE_DIR, 'static')
        static_dir_abs = os.path.abspath(static_dir)
        base_url = f"file://{static_dir_abs}/"
        
        # Generar PDF (sin CSS externo, ya está en el HTML)
        html = HTML(
            string=html_string, 
            base_url=base_url
        )
        
        pdf_buffer = BytesIO()
        html.write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        
        return pdf_buffer.getvalue()
    
    def _crear_respuesta_pdf(self, pdf_content, cotizacion):
        """Crea la respuesta HTTP con el PDF."""
        filename = f"cotizacion_{cotizacion.slug}_{timezone.now().strftime('%Y%m%d%H%M%S')}.pdf"
        
        response = HttpResponse(
            pdf_content,
            content_type='application/pdf'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(len(pdf_content))
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response


class CotizacionConvertirView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        cot = get_object_or_404(Cotizacion, slug=kwargs.get('slug'))
        
        # Extraer el total de las propuestas según el tipo de cotización
        total_cotizacion = Decimal('0.00')
        propuestas = cot.propuestas if isinstance(cot.propuestas, dict) else {}
        tipo = propuestas.get('tipo', '')
        
        def limpiar_y_convertir_total(valor):
            """Convierte un string de total (puede tener comas) a Decimal"""
            if not valor:
                return Decimal('0.00')
            try:
                # Remover comas y espacios, luego convertir a Decimal
                valor_limpio = str(valor).replace(',', '').replace('$', '').strip()
                return Decimal(valor_limpio)
            except (ValueError, InvalidOperation):
                return Decimal('0.00')
        
        # Obtener índices seleccionados del formulario
        opcion_vuelo_index = request.POST.get('opcion_vuelo_index', '')
        opcion_hotel_index = request.POST.get('opcion_hotel_index', '')
        
        # Guardar los índices en la sesión para que el formulario los use
        if opcion_vuelo_index:
            request.session[f'cotizacion_{cot.slug}_opcion_vuelo'] = opcion_vuelo_index
        if opcion_hotel_index:
            request.session[f'cotizacion_{cot.slug}_opcion_hotel'] = opcion_hotel_index
        
        if tipo == 'vuelos' and propuestas.get('vuelos'):
            # Para vuelos, usar la opción seleccionada o la primera por defecto
            vuelos = propuestas.get('vuelos', [])
            if vuelos and len(vuelos) > 0:
                # Determinar qué índice usar
                try:
                    indice = int(opcion_vuelo_index) if opcion_vuelo_index else 0
                    if indice < 0 or indice >= len(vuelos):
                        indice = 0
                except (ValueError, TypeError):
                    indice = 0
                
                # Tomar el vuelo seleccionado usando el índice correcto
                vuelo_seleccionado = vuelos[indice] if isinstance(vuelos, list) else vuelos.get(f'propuesta_{indice + 1}', {})
                if isinstance(vuelo_seleccionado, dict):
                    total_vuelo = vuelo_seleccionado.get('total')
                    if total_vuelo:
                        total_cotizacion = limpiar_y_convertir_total(total_vuelo)
                        # Log para depuración (puedes removerlo después)
                        logging.debug(f"Total del vuelo seleccionado (índice {indice}): {total_cotizacion}")
                    else:
                        # Si no hay total en el vuelo seleccionado, intentar con el primero
                        if len(vuelos) > 0 and isinstance(vuelos[0], dict) and vuelos[0].get('total'):
                            total_cotizacion = limpiar_y_convertir_total(vuelos[0].get('total'))
                            logging.debug(f"Total del primer vuelo (fallback): {total_cotizacion}")
                else:
                    # Si no se encontró el vuelo seleccionado, usar el primero
                    if len(vuelos) > 0 and isinstance(vuelos[0], dict) and vuelos[0].get('total'):
                        total_cotizacion = limpiar_y_convertir_total(vuelos[0].get('total'))
                        logging.debug(f"Total del primer vuelo (fallback - vuelo no encontrado): {total_cotizacion}")
        
        elif tipo == 'hospedaje' and propuestas.get('hoteles'):
            # Para hospedaje, usar la opción seleccionada o la primera por defecto
            hoteles = propuestas.get('hoteles', [])
            
            # 1. Asegurar índice válido
            indice = 0
            try:
                if opcion_hotel_index:
                    indice = int(opcion_hotel_index)
            except (ValueError, TypeError):
                indice = 0
            
            # 2. Obtener el hotel usando lógica dual (Lista o Diccionario)
            hotel_seleccionado = {}
            if isinstance(hoteles, list):
                if 0 <= indice < len(hoteles):
                    hotel_seleccionado = hoteles[indice]
            else:
                # Si es diccionario, buscar por claves numéricas o string 'propuesta_X'
                hotel_seleccionado = hoteles.get(f'propuesta_{indice+1}') or hoteles.get(str(indice)) or {}
            
            # 3. Extraer total (Blindado)
            if hotel_seleccionado and isinstance(hotel_seleccionado, dict):
                total_str = hotel_seleccionado.get('total')
                if total_str:
                    total_cotizacion = limpiar_y_convertir_total(total_str)
                    logging.debug(f"Total HOTEL blindado (índice {indice}): {total_cotizacion}")
        
        elif tipo == 'paquete' and propuestas.get('paquete'):
            # Para paquete, tomar el total del paquete y sumar los tours
            paquete = propuestas.get('paquete', {})
            if isinstance(paquete, dict) and paquete.get('total'):
                total_cotizacion = limpiar_y_convertir_total(paquete.get('total'))
            
            # Sumar los totales de los tours del paquete
            if isinstance(paquete, dict) and paquete.get('tours') and isinstance(paquete.get('tours'), list):
                for tour in paquete.get('tours', []):
                    if isinstance(tour, dict) and tour.get('total'):
                        total_tour = limpiar_y_convertir_total(tour.get('total'))
                        total_cotizacion += total_tour
        
        elif tipo == 'tours' and propuestas.get('tours'):
            # Para tours, puede ser un array o un objeto único (compatibilidad)
            tours = propuestas.get('tours', {})
            tours_list = []
            if isinstance(tours, list):
                tours_list = tours
            else:
                # Compatibilidad: convertir objeto único a array
                tours_list = [tours] if tours else []
            
            # Sumar todos los totales de los tours
            for tour in tours_list:
                if isinstance(tour, dict) and tour.get('total'):
                    total_tour = limpiar_y_convertir_total(tour.get('total'))
                    total_cotizacion += total_tour
        
        elif tipo == 'traslados' and propuestas.get('traslados'):
            # Para traslados, tomar el total
            traslados = propuestas.get('traslados', {})
            if isinstance(traslados, dict) and traslados.get('total'):
                total_cotizacion = limpiar_y_convertir_total(traslados.get('total'))
        
        elif tipo == 'renta_autos' and propuestas.get('renta_autos'):
            # Para renta_autos, tomar el total
            renta_autos = propuestas.get('renta_autos', {})
            if isinstance(renta_autos, dict) and renta_autos.get('total'):
                total_cotizacion = limpiar_y_convertir_total(renta_autos.get('total'))
        
        # Si no se encontró total en propuestas, usar total_estimado como fallback
        if total_cotizacion == Decimal('0.00'):
            total_cotizacion = cot.total_estimado or Decimal('0.00')
        
        # Determinar servicios según el tipo de cotización
        servicios_mapeo = {
            'vuelos': ['Vuelo'],
            'hospedaje': ['Hospedaje'],
            'tours': ['Tour y Actividades'],
            'traslados': ['Traslado'],
            'renta_autos': ['Renta de Auto'],
        }
        servicios_seleccionados = servicios_mapeo.get(tipo, [])
        
        # Para paquetes, siempre incluir Vuelo y Hospedaje, y Tour solo si hay tours
        if tipo == 'paquete':
            servicios_seleccionados = ['Vuelo', 'Hospedaje']
            # Verificar si hay tours en el paquete
            paquete = propuestas.get('paquete', {})
            if isinstance(paquete, dict) and paquete.get('tours'):
                tours = paquete.get('tours', [])
                # Verificar si hay tours (puede ser lista o objeto único)
                if isinstance(tours, list) and len(tours) > 0:
                    # Verificar que al menos un tour tenga datos
                    tiene_tours = any(
                        isinstance(tour, dict) and (
                            tour.get('nombre') or 
                            tour.get('especificaciones') or 
                            tour.get('total') or 
                            tour.get('forma_pago')
                        ) for tour in tours
                    )
                    if tiene_tours:
                        servicios_seleccionados.append('Tour y Actividades')
                elif isinstance(tours, dict) and (tours.get('nombre') or tours.get('total')):
                    # Compatibilidad: si es un objeto único con datos
                    servicios_seleccionados.append('Tour y Actividades')
        
        # Preparar edades de menores en formato lista (nombre - edad) con saltos de línea
        edades_menores_formato = ''
        if cot.edades_menores and cot.edades_menores.strip():
            # Si las edades están en formato "5, 8, 12", convertirlas a formato lista con saltos de línea
            edades = [e.strip() for e in cot.edades_menores.split(',') if e.strip()]
            if edades:
                # Crear formato con saltos de línea: "Menor 1 - 5\nMenor 2 - 8\nMenor 3 - 12"
                edades_lista = [f"Menor {i+1} - {edad}" for i, edad in enumerate(edades)]
                edades_menores_formato = '\n'.join(edades_lista)
        
        # Guardar información de la cotización en la sesión para pre-llenar el formulario
        # Asegurar que el total se guarde correctamente
        logging.debug(f"Guardando total_cotizacion en sesión: {total_cotizacion} (índice vuelo: {opcion_vuelo_index})")
        request.session['cotizacion_convertir'] = {
            'cotizacion_id': cot.pk,
            'cotizacion_slug': cot.slug,
            'cliente_id': cot.cliente.pk,
            'fecha_inicio': str(cot.fecha_inicio) if cot.fecha_inicio else None,
            'fecha_fin': str(cot.fecha_fin) if cot.fecha_fin else None,
            'total_cotizacion': str(total_cotizacion),
            'opcion_vuelo_index': opcion_vuelo_index if opcion_vuelo_index else None,
            'opcion_hotel_index': opcion_hotel_index if opcion_hotel_index else None,
            'edades_menores': edades_menores_formato,
            'servicios_seleccionados': servicios_seleccionados,
            'tipo_cotizacion': tipo,
        }
        # Forzar guardado de la sesión
        request.session.modified = True
        
        # CAMBIO ANTIGRAVITY: Pasar datos explícitos por URL para garantizar que lleguen
        # Mejorar el redirect para incluir cualquier índice (vuelo u hotel)
        indice_final = opcion_vuelo_index or opcion_hotel_index or '0'
        url_destino = reverse('crear_venta') + f'?cotizacion={cot.slug}&total_b={str(total_cotizacion)}&idx_b={indice_final}'
        return redirect(url_destino)