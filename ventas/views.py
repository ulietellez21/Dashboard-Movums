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
from decimal import Decimal # Importar Decimal para asegurar precisión en cálculos financieros

# Intento cargar WeasyPrint; si falla (por dependencias GTK), defino placeholders.
try:
    from weasyprint import HTML, CSS 
    WEASYPRINT_AVAILABLE = True
except ImportError:
    print("ADVERTENCIA: WeasyPrint no está disponible. La generación de PDF fallará.")
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
    PlantillaConfirmacion,
)
from crm.models import Cliente
from crm.services import KilometrosService
from .forms import (
    VentaViajeForm,
    LogisticaForm,
    LogisticaServicioFormSet,
    AbonoPagoForm,
    ProveedorForm,
    ConfirmacionVentaForm,
    EjecutivoForm,
)
from .utils import numero_a_texto
from .services.logistica import (
    build_financial_summary,
    build_service_rows,
    build_logistica_card,
)
logger = logging.getLogger(__name__)

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
            context['alertas_logistica_count'] = VentaViaje.objects.filter(
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
                ).select_related('venta', 'venta__cliente', 'abono', 'abono__confirmado_por').order_by('-fecha_creacion')
                
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

        # 2. Aplicar filtro por fecha de viaje si se proporciona (soporta fecha única o rango)
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
        
        # Agregar filtros de fecha al contexto para mantenerlos en el formulario
        context['fecha_filtro'] = self.request.GET.get('fecha_filtro', '')
        context['fecha_desde'] = self.request.GET.get('fecha_desde', '')
        context['fecha_hasta'] = self.request.GET.get('fecha_hasta', '')
        
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

            servicios_qs = self.object.servicios_logisticos.all().order_by('orden', 'pk')
            formset = LogisticaServicioFormSet(
                request.POST,
                queryset=servicios_qs,
                prefix='servicios'
            )

            if formset.is_valid():
                total_pagado = self.object.total_pagado
                total_marcado_pagado = Decimal('0.00')
                for form in formset.forms:
                    cleaned = form.cleaned_data
                    if not cleaned:
                        continue
                    if cleaned.get('pagado'):
                        total_marcado_pagado += cleaned.get('monto_planeado') or Decimal('0.00')

                if total_marcado_pagado > total_pagado + Decimal('0.01'):
                    formset._non_form_errors = formset.error_class([
                        f"No puedes marcar como pagados ${total_marcado_pagado:,.2f} cuando solo hay ${total_pagado:,.2f} registrados en abonos y apertura."
                    ])
                else:
                    originales = {serv.pk: serv for serv in servicios_qs}
                    for form in formset.forms:
                        servicio = form.save(commit=False)
                        original = originales.get(servicio.pk)
                        if not original:
                            continue
                        servicio.venta = self.object
                        servicio.codigo_servicio = original.codigo_servicio
                        servicio.nombre_servicio = original.nombre_servicio
                        servicio.orden = original.orden

                        marcado_pagado = form.cleaned_data.get('pagado')
                        if marcado_pagado and not original.pagado:
                            servicio.fecha_pagado = timezone.now()
                        elif not marcado_pagado and original.pagado:
                            servicio.fecha_pagado = None
                        else:
                            servicio.fecha_pagado = original.fecha_pagado

                        servicio.save(update_fields=['monto_planeado', 'pagado', 'fecha_pagado', 'notas', 'orden', 'codigo_servicio', 'nombre_servicio'])

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
                    
                    # 1. Cambiar estado de venta a "En confirmación"
                    self.object.estado_confirmacion = 'EN_CONFIRMACION'
                    self.object.save(update_fields=['estado_confirmacion'])
                    
                    # 2. Crear notificaciones para CONTADOR
                    # Notificacion ya está importada al inicio del archivo
                    contadores = User.objects.filter(perfil__rol='CONTADOR')
                    forma_pago_display = dict(AbonoPago.FORMA_PAGO_CHOICES).get(forma_pago, forma_pago)
                    mensaje_contador = f"Abono pendiente de confirmación: ${abono.monto:,.2f} ({forma_pago_display}) - Venta #{self.object.pk} - Cliente: {self.object.cliente.nombre_completo_display}"
                    
                    for contador in contadores:
                        Notificacion.objects.create(
                            usuario=contador,
                            tipo='PAGO_PENDIENTE',
                            mensaje=mensaje_contador,
                            venta=self.object,
                            abono=abono,  # Vincular la notificación con el abono específico
                            confirmado=False
                        )
                    
                    # 3. Crear notificaciones para JEFE también (información)
                    jefes = User.objects.filter(perfil__rol='JEFE')
                    mensaje_jefe = f"Abono pendiente de confirmación: ${abono.monto:,.2f} ({forma_pago_display}) - Venta #{self.object.pk} - Cliente: {self.object.cliente.nombre_completo_display}"
                    for jefe in jefes:
                        Notificacion.objects.create(
                            usuario=jefe,
                            tipo='PAGO_PENDIENTE',
                            mensaje=mensaje_jefe,
                            venta=self.object,
                            abono=abono,
                            confirmado=False
                        )
                    
                    # 4. Crear notificación para el VENDEDOR de la venta (si existe y no es quien registra el abono)
                    if self.object.vendedor and self.object.vendedor != request.user:
                        mensaje_vendedor = f"Abono registrado en tu venta: ${abono.monto:,.2f} ({forma_pago_display}) - Venta #{self.object.pk} - Cliente: {self.object.cliente.nombre_completo_display} - Pendiente de confirmación"
                        Notificacion.objects.create(
                            usuario=self.object.vendedor,
                            tipo='ABONO',
                            mensaje=mensaje_vendedor,
                            venta=self.object,
                            abono=abono,
                            confirmado=False
                        )
                    
                    messages.success(request, f"Abono de ${abono.monto:,.2f} ({forma_pago_display}) registrado exitosamente. ⏳ Pendiente de confirmación del contador.")
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

        for idx, code in enumerate(servicios_codes):
            nombre = choices.get(code)
            if not nombre:
                continue
            if code not in existentes:
                LogisticaServicio.objects.create(
                    venta=venta,
                    codigo_servicio=code,
                    nombre_servicio=nombre,
                    orden=idx
                )
            else:
                serv = existentes[code]
                if serv.orden != idx:
                    serv.orden = idx
                    serv.save(update_fields=['orden'])

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

        if not context.get('puede_editar_servicios_financieros'):
            for form in formset.forms:
                for field in form.fields.values():
                    field.widget.attrs['disabled'] = 'disabled'

        resumen = build_financial_summary(venta, servicios_qs)
        filas = build_service_rows(servicios_qs, resumen, list(formset.forms))

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

        # 3. ¡IMPORTANTE! Eliminamos la lógica manual de generación de slug de aquí.
        # El modelo VentaViaje se encarga de generar y asegurar el slug único 
        # dentro de su método save() una vez que la PK ha sido asignada.
        
        # 4. Guarda la instancia, lo que dispara el método save() del modelo
        self.object = instance # Establece self.object para que get_success_url funcione
        self.object.save() 
        
        # 5. Llama a save_m2m (necesario si hay campos ManyToMany en VentaViajeForm)
        form.save_m2m() 
        try:
            KilometrosService.acumular_por_compra(self.object.cliente, self.object.costo_venta_final, venta=self.object)
        except Exception:
            logger.exception("No se pudieron acumular kilómetros para la venta %s", self.object.pk)
    
        # 5.1. Lógica de notificaciones para apertura con Transferencia/Tarjeta
        modo_pago = form.cleaned_data.get('modo_pago_apertura', 'EFE')
        cantidad_apertura = form.cleaned_data.get('cantidad_apertura', Decimal('0.00'))
        
        if cantidad_apertura > 0 and modo_pago in ['TRN', 'TAR']:
            # Cambiar estado a "En confirmación"
            self.object.estado_confirmacion = 'EN_CONFIRMACION'
            self.object.save(update_fields=['estado_confirmacion'])
            
            # Crear notificación para CONTADOR
            contadores = User.objects.filter(perfil__rol='CONTADOR')
            modo_pago_display = dict(VentaViaje.MODO_PAGO_CHOICES).get(modo_pago, modo_pago)
            mensaje = f"Pago de apertura pendiente de confirmación: ${cantidad_apertura:,.2f} ({modo_pago_display}) - Venta #{self.object.pk} - Cliente: {self.object.cliente}"
            
            for contador in contadores:
                Notificacion.objects.create(
                    usuario=contador,
                    tipo='PAGO_PENDIENTE',
                    mensaje=mensaje,
                    venta=self.object,
                    confirmado=False
                )
            
            # Crear notificación para JEFE
            jefes = User.objects.filter(perfil__rol='JEFE')
            for jefe in jefes:
                Notificacion.objects.create(
                    usuario=jefe,
                    tipo='APERTURA',
                    mensaje=f"Pago de apertura pendiente de confirmación: ${cantidad_apertura:,.2f} ({modo_pago_display}) - Venta #{self.object.pk}",
                    venta=self.object,
                    confirmado=False
                )
            
            # Crear notificación para el VENDEDOR (si existe)
            if self.object.vendedor:
                mensaje_vendedor_apertura = f"Apertura registrada en tu venta #{self.object.pk}: ${cantidad_apertura:,.2f} ({modo_pago_display}) - Cliente: {self.object.cliente.nombre_completo_display} - Pendiente de confirmación del contador"
                Notificacion.objects.create(
                    usuario=self.object.vendedor,
                    tipo='APERTURA',
                    mensaje=mensaje_vendedor_apertura,
                    venta=self.object,
                    confirmado=False
                )
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
        cliente = get_object_or_404(Cliente, pk=cliente_id)
        resumen = KilometrosService.resumen_cliente(cliente)

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
        # Obtener el costo de modificación del formulario
        costo_modificacion = form.cleaned_data.get('costo_modificacion', Decimal('0.00')) or Decimal('0.00')
        previo_modificacion = form.instance.costo_modificacion or Decimal('0.00')
        
        # Guardar la instancia
        self.object = form.save()
        
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
        venta.estado = 'CANCELADA'
        venta.save(update_fields=['estado'])
        
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
        
        messages.success(request, f"La venta #{venta.pk} ha sido cancelada exitosamente.")
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
        
        # Obtener el contexto para la plantilla HTML
        context = {
            'venta': venta,
            'now': datetime.datetime.now(),
            'total_pagado': total_pagado,
            'saldo_restante': saldo_restante,
            # Incluir TODOS los abonos para el detalle en el PDF (mostrar todos, incluso pendientes)
            'abonos': venta.abonos.all().order_by('fecha_pago') 
        }

        # 1. Renderizar la plantilla HTML
        # Se usa request.build_absolute_uri() para manejar las rutas absolutas de CSS/Imágenes
        html_string = render_to_string('ventas/comprobante_abonos_pdf.html', context, request=request)
        
        # 2. Generar el PDF con WeasyPrint
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
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
    Vista para generar el Contrato de Venta en formato PDF.
    Utiliza el modelo VentaViaje y la plantilla 'ventas/contrato_pdf.html'.
    """
    model = VentaViaje
    
    def get(self, request, *args, **kwargs):
        if not WEASYPRINT_AVAILABLE:
             # Si WeasyPrint no está cargado, devuelve un error 503
             return HttpResponse("Error en la generación de PDF. Faltan dependencias (GTK3).", status=503)

        self.object = self.get_object() 
        venta = self.object
        cliente = venta.cliente
        
        # Intentar obtener el contrato generado si existe (para el contenido HTML)
        contenido_html_sustituido = ''
        try:
            contrato_generado = ContratoGenerado.objects.get(venta=venta)
            contenido_html_sustituido = contrato_generado.contenido_final
        except ContratoGenerado.DoesNotExist:
            # Si no existe contrato generado, usar contenido vacío o por defecto
            contenido_html_sustituido = '<p>Contrato en proceso de generación.</p>'
        
        # Calcular la dirección completa del cliente
        cliente_direccion_completa = (
            cliente.direccion_fiscal if cliente.tipo_cliente == 'EMPRESA' and cliente.direccion_fiscal
            else f"{cliente.nombre_completo_display} - {cliente.telefono or 'Sin teléfono'}"
        )
        
        # Calcular saldo pendiente (asegurarse de que no sea negativo)
        from decimal import Decimal
        saldo_pendiente = max(Decimal('0.00'), venta.costo_venta_final - venta.cantidad_apertura)
        
        # Convertir montos a texto
        monto_apertura_texto = numero_a_texto(venta.cantidad_apertura)
        saldo_pendiente_texto = numero_a_texto(saldo_pendiente)
        
        # Contexto completo para el contrato
        context = {
            'venta': venta,
            'cliente': cliente,
            'fecha_generacion': formats.date_format(datetime.datetime.now(), r"j \d\e F \d\e Y"),
            'cliente_direccion_completa': cliente_direccion_completa,
            'contenido_html_sustituido': contenido_html_sustituido,
            'monto_apertura_texto': monto_apertura_texto,
            'saldo_pendiente': saldo_pendiente,
            'saldo_pendiente_texto': saldo_pendiente_texto,
        }

        # 1. Renderizar la plantilla HTML específica para el CONTRATO
        # Asegúrate de que tienes un archivo llamado 'ventas/contrato_pdf.html'
        html_string = render_to_string('ventas/contrato_pdf.html', context, request=request)
        
        # 2. Generar el PDF con WeasyPrint
        # Es crucial usar base_url para que WeasyPrint pueda cargar CSS e imágenes
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf_file = html.write_pdf(stylesheets=[])
        
        # 3. Preparar la respuesta HTTP para el Contrato
        response = HttpResponse(pdf_file, content_type='application/pdf')
        # Nombre más descriptivo para el contrato
        nombre_cliente_safe = venta.cliente.nombre_completo_display.replace(' ', '_').replace('/', '_')
        filename = f"Contrato_Venta_{venta.pk}_{nombre_cliente_safe}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"' 
        
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
        context['ejecutivos'] = Ejecutivo.objects.all()
        context['ejecutivo_form'] = kwargs.get('ejecutivo_form') or EjecutivoForm()
        context['mostrar_modal_ejecutivo'] = kwargs.get('mostrar_modal_ejecutivo', False)
        
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

    def post(self, request, *args, **kwargs):
        user_rol = get_user_role(request.user)
        if user_rol != 'JEFE':
            messages.error(request, "Solo el rol JEFE puede gestionar ejecutivos.")
            return redirect('reporte_comisiones')

        action = request.POST.get('ejecutivo_action', 'crear')
        ejecutivo_id = request.POST.get('ejecutivo_id')

        if action == 'eliminar':
            if not ejecutivo_id:
                messages.error(request, "No se pudo identificar al ejecutivo a eliminar.")
                return redirect('reporte_comisiones')
            ejecutivo = get_object_or_404(Ejecutivo, pk=ejecutivo_id)
            usuario_rel = ejecutivo.usuario
            nombre = ejecutivo.nombre_completo
            ejecutivo.delete()
            if usuario_rel:
                usuario_rel.delete()
            messages.success(request, f"Ejecutivo '{ejecutivo.nombre_completo}' eliminado correctamente.")
            return redirect('reporte_comisiones')

        instance = None
        if action == 'editar':
            if not ejecutivo_id:
                messages.error(request, "No se pudo identificar al ejecutivo a editar.")
                return redirect('reporte_comisiones')
            instance = get_object_or_404(Ejecutivo, pk=ejecutivo_id)

        form = EjecutivoForm(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            ejecutivo = form.save()
            # Obtener el tipo de usuario seleccionado del formulario
            tipo_usuario = form.cleaned_data.get('tipo_usuario', 'VENDEDOR')
            regenerar_password = (action != 'editar')
            user, password = self._crear_o_actualizar_usuario(
                ejecutivo,
                tipo_usuario=tipo_usuario,
                forzar_password=regenerar_password and ejecutivo.usuario is not None
            )

            if password:
                messages.success(
                    request,
                    (
                        f"Ejecutivo '{ejecutivo.nombre_completo}' agregado. "
                        f"Credenciales -> Usuario: {user.username} / Contraseña: {password}"
                    )
                )
            else:
                messages.success(request, f"Ejecutivo '{ejecutivo.nombre_completo}' actualizado correctamente.")
            return redirect('reporte_comisiones')

        context = self.get_context_data(ejecutivo_form=form, mostrar_modal_ejecutivo=True)
        return self.render_to_response(context)


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

        for proveedor in proveedores:
            proveedores_por_servicio.setdefault(proveedor.servicio, []).append(proveedor)

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
        context['form'] = kwargs.get('form') or ProveedorForm()
        context['servicio_choices'] = Proveedor.SERVICIO_CHOICES
        return context

    def post(self, request, *args, **kwargs):
        form = ProveedorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Proveedor agregado correctamente.")
            return redirect('proveedores')

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
        fecha_run = fecha_paragraph.add_run(f"Fecha de Cotización: {format_date(general.get('fechaCotizacion'))}")
        set_run_font(fecha_run, size=14, bold=True, color=MOVUMS_BLUE)

        add_paragraph(doc, "", space_after=4)

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
            set_run_font(label_run, size=12, bold=True, color=MOVUMS_BLUE)
            val1_run = row[1].paragraphs[0].add_run(v1)
            set_run_font(val1_run, size=12)
            val2_run = row[2].paragraphs[0].add_run(v2)
            set_run_font(val2_run, size=12)

        add_paragraph(doc, "", space_after=6)

        def render_block(title, subtitle, details, total_text=None):
            add_paragraph(doc, title, size=18, bold=True, color=MOVUMS_BLUE, space_before=4, space_after=2)
            if subtitle:
                add_paragraph(doc, subtitle, size=18, bold=True, color=TEXT_COLOR, space_after=2)
            for label, value in details:
                paragraph = doc.add_paragraph()
                paragraph.paragraph_format.space_after = Pt(2)
                run_title = paragraph.add_run(f"{label} ")
                set_run_font(run_title, size=12, bold=True)
                run_value = paragraph.add_run(value)
                set_run_font(run_value, size=12)
            if total_text:
                add_paragraph(doc, total_text, size=16, bold=True, color=MOVUMS_BLUE, space_before=4, space_after=4)
            add_paragraph(doc, "", space_after=4)

        def render_hospedaje(hoteles):
            for hotel in hoteles:
                render_block(
                    "Hospedaje",
                    hotel.get('nombre') or 'Hotel propuesto',
                    [
                        ("Habitación:", hotel.get('habitacion') or '-'),
                        ("Dirección:", hotel.get('direccion') or '-'),
                        ("Plan de Alimentos:", hotel.get('plan') or '-'),
                    ],
                    f"Total MXN {format_currency(hotel.get('total'))} Pesos"
                )

        def render_vuelos(vuelos):
            for vuelo in vuelos:
                render_block(
                    "Vuelo",
                    vuelo.get('aerolinea') or 'Aerolínea propuesta',
                    [
                        ("Salida:", vuelo.get('salida') or '-'),
                        ("Regreso:", vuelo.get('regreso') or '-'),
                        ("Incluye:", vuelo.get('incluye') or '-'),
                    ],
                    f"Total MXN {format_currency(vuelo.get('total'))} Pesos"
                )

        def render_paquete(paquete):
            vuelo = paquete.get('vuelo') or {}
            hotel = paquete.get('hotel') or {}
            render_block(
                "Vuelo",
                vuelo.get('aerolinea') or 'Vuelo incluido',
                [
                    ("Salida:", vuelo.get('salida') or '-'),
                    ("Regreso:", vuelo.get('regreso') or '-'),
                    ("Incluye:", vuelo.get('incluye') or '-'),
                ]
            )
            render_block(
                "Hospedaje",
                hotel.get('nombre') or 'Hotel incluido',
                [
                    ("Habitación / Plan:", hotel.get('habitacion') or '-'),
                    ("Notas:", hotel.get('notas') or '-'),
                ],
                f"Total MXN {format_currency(paquete.get('total'))} Pesos"
            )

            add_paragraph(doc, "Términos y condiciones", size=14, bold=True, color=MOVUMS_BLUE, space_before=6, space_after=2)
            terms = [
                "Los boletos de avión no son reembolsables.",
                "Una vez emitido el boleto no puede ser asignado a otra persona o aerolínea.",
                "Los cambios pueden generar cargos extra y están sujetos a disponibilidad y políticas de cada aerolínea.",
                "Para vuelos nacionales presentarse 2 horas antes; para internacionales 3 horas antes.",
                "Las tarifas están sujetas a cambios y disponibilidad mientras no se reserve.",
            ]
            for term in terms:
                paragraph = doc.add_paragraph(f"• {term}")
                paragraph.paragraph_format.left_indent = Pt(18)
                paragraph.paragraph_format.space_after = Pt(0)
                set_run_font(paragraph.runs[0], size=12)

        if tipo == 'vuelos':
            render_vuelos(cotizacion.get('vuelos') or [])
        elif tipo == 'hospedaje':
            render_hospedaje(cotizacion.get('hoteles') or [])
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
        
        context = {
            'venta': venta,
            'tipo_plantilla': self.tipo_plantilla,
            'datos': datos,
            'plantilla': plantilla,
            'escalas_json': escalas_json,
            'traslados_json': traslados_json,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, pk, slug):
        venta = get_object_or_404(VentaViaje, pk=pk, slug=slug)
        
        # Recopilar todos los datos del POST
        datos = {}
        escalas = []
        
        # Procesar escalas si existen (formato: escalas[0][ciudad], escalas[0][aeropuerto], etc.)
        escalas_dict = {}
        for key, value in request.POST.items():
            if key.startswith('escalas['):
                # Extraer el índice y el campo de la escala
                import re
                match = re.match(r'escalas\[(\d+)\]\[(\w+)\]', key)
                if match:
                    escala_index = int(match.group(1))
                    campo = match.group(2)
                    if escala_index not in escalas_dict:
                        escalas_dict[escala_index] = {}
                    escalas_dict[escala_index][campo] = value
            elif key not in ['csrfmiddlewaretoken']:
                datos[key] = value
        
        # Convertir escalas_dict a lista ordenada
        if escalas_dict:
            for i in sorted(escalas_dict.keys()):
                escalas.append(escalas_dict[i])
            datos['escalas'] = escalas
        elif self.tipo_plantilla == 'VUELO_UNICO':
            datos['escalas'] = []
        
        # Procesar múltiples traslados si existe
        if self.tipo_plantilla == 'TRASLADO':
            import re
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
                print(f"Error al procesar imagen base64: {e}")
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
        
        fecha_run = info_p.add_run(f' | Fecha de generación: {datetime.now().strftime("%d de %B de %Y, %H:%M")}')
        fecha_run.font.name = 'Arial'
        fecha_run.font.size = Pt(12)
        fecha_run.font.color.rgb = RGBColor(0, 0, 0)
    
    def _agregar_plantilla_al_documento(self, doc, plantilla):
        """Agrega el contenido de una plantilla al documento Word con estilo profesional."""
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt, RGBColor, Inches
        
        # Agregar título principal (tamaño 18, Arial)
        self._asegurar_estilo_heading(doc, 'Heading 2', 16)
        titulo = doc.add_heading(plantilla.get_tipo_display().upper(), level=2)
        titulo.alignment = WD_ALIGN_PARAGRAPH.LEFT
        titulo.paragraph_format.space_before = Pt(12)
        titulo.paragraph_format.space_after = Pt(6)
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
    
    def _agregar_info_line(self, doc, etiqueta, valor, mostrar_si_vacio=False, es_nombre_propio=False):
        """Helper para agregar una línea de información formateada (ultra compacta)."""
        from docx.shared import Pt, RGBColor
        
        if not valor and not mostrar_si_vacio:
            return
        
        # Normalizar el valor
        valor_normalizado = self._normalizar_valor_campo(
            valor, 
            es_nombre_propio=es_nombre_propio, 
            limpiar_saltos_linea=True
        )
        
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)  # Espaciado ultra compacto
        p.paragraph_format.line_spacing = 1.1  # Interlineado mínimo
        
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
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.1
        
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
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Pt(0)
        
        # Agregar viñeta manualmente (carácter bullet)
        bullet_run = p.add_run('• ')
        bullet_run.font.name = 'Arial'
        bullet_run.font.size = Pt(12)
        bullet_run.font.color.rgb = RGBColor(0, 74, 142)
        bullet_run.font.bold = True
        
        # Agregar texto del subtítulo
        texto_run = p.add_run(texto)
        texto_run.font.name = 'Arial'
        texto_run.font.size = Pt(12)
        texto_run.font.color.rgb = RGBColor(0, 74, 142)
        texto_run.font.bold = True
        
        return p
    
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
            escalas_titulo.paragraph_format.space_after = Pt(2)
            escalas_titulo.runs[0].font.size = Pt(10)
            for i, escala in enumerate(datos['escalas'], 1):
                escala_p = doc.add_paragraph()
                escala_p.paragraph_format.space_after = Pt(2)
                escala_run = escala_p.add_run(f'Escala {i}: ')
                escala_run.font.name = 'Arial'
                escala_run.font.size = Pt(12)
                escala_run.bold = True
                escala_val_run = escala_p.add_run(f"{escala.get('ciudad', '')} - {escala.get('aeropuerto', '')}")
                escala_val_run.font.name = 'Arial'
                escala_val_run.font.size = Pt(12)
                
                escala_info = doc.add_paragraph()
                escala_info.paragraph_format.left_indent = Inches(0.3)
                escala_info.paragraph_format.space_after = Pt(2)
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
        
        # Información de Pasajeros (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información de Pasajeros')
        
        self._agregar_info_line(doc, 'Pasajeros', datos.get('pasajeros', ''))
        self._agregar_info_line(doc, 'Equipaje', datos.get('equipaje', ''))
        
        if datos.get('informacion_adicional'):
            info_normalizada = self._normalizar_valor_campo(datos.get('informacion_adicional', ''), limpiar_saltos_linea=True)
            info_p = doc.add_paragraph()
            info_p.paragraph_format.space_after = Pt(2)
            info_label = info_p.add_run('Información Adicional: ')
            info_label.font.name = 'Arial'
            info_label.font.size = Pt(12)
            info_label.bold = True
            info_val = info_p.add_run(info_normalizada)
            info_val.font.name = 'Arial'
            info_val.font.size = Pt(12)
    
    def _agregar_vuelo_redondo(self, doc, datos):
        """Agrega contenido de vuelo redondo al documento con formato compacto."""
        from docx.shared import Pt
        
        # Información de Reserva (con viñeta)
        from docx.shared import RGBColor
        self._agregar_subtitulo_con_vineta(doc, 'Información de Reserva')
        
        self._agregar_info_line(doc, 'Clave de Reserva', datos.get('clave_reserva', ''))
        
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
        
        # Información General (con viñeta)
        self._agregar_subtitulo_con_vineta(doc, 'Información General')
        
        self._agregar_info_line(doc, 'Pasajeros', datos.get('pasajeros', ''), es_nombre_propio=True)
        self._agregar_info_line(doc, 'Equipaje', datos.get('equipaje', ''))
        
        if datos.get('informacion_adicional'):
            info_normalizada = self._normalizar_valor_campo(datos.get('informacion_adicional', ''), limpiar_saltos_linea=True)
            info_p = doc.add_paragraph()
            info_p.paragraph_format.space_after = Pt(2)
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
        p.paragraph_format.space_after = Pt(2)
        
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
            obs_p.paragraph_format.space_after = Pt(2)
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
            info_p.paragraph_format.space_after = Pt(2)
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
                    p.paragraph_format.space_after = Pt(2)
                    p.paragraph_format.line_spacing = 1.1
                    for run in p.runs:
                        run.font.name = 'Arial'
                        run.font.size = Pt(12)