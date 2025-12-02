from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, View, DeleteView, TemplateView
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User 
from django.template.loader import render_to_string
from django.urls import reverse_lazy, reverse
from django.db.models.functions import Coalesce
from django.db.models import Sum, Count, F, Q, Value, IntegerField
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone 
from django.utils import formats  # Para formatear fechas en el PDF
# IMPORTACIÓN CLAVE: Necesaria para generar slugs automáticamente
from django.utils.text import slugify 
from datetime import timedelta 
import math, re, logging
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
    ContratoGenerado,
    Notificacion,
    Proveedor,
    ConfirmacionVenta,
)
from crm.models import Cliente
from .forms import (
    VentaViajeForm,
    LogisticaForm,
    AbonoPagoForm,
    ProveedorForm,
    ConfirmacionVentaForm,
)
from .utils import numero_a_texto
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
            # ¡ATENCIÓN! REVISA ESTE MENSAJE EN TU TERMINAL
            print(f"DEBUG: Rol detectado para usuario {user.username}: {role}")
            return role
        except AttributeError:
            # ¡ATENCIÓN! REVISA ESTE MENSAJE EN TU TERMINAL
            print(f"DEBUG: Usuario {user.username} NO tiene perfil o rol definido. Rol: INVITADO")
            return 'INVITADO'


    def get_queryset(self):
        user = self.request.user
        user_rol = self.get_user_role(user)

        # Lógica de filtrado
        if user_rol in ['JEFE', 'CONTADOR']:
            queryset = VentaViaje.objects.all().order_by('-fecha_creacion')
            print(f"DEBUG: Rol {user_rol}. Se están cargando TODAS las ventas.")
        elif user_rol == 'VENDEDOR':
            # Filtro CRÍTICO: Si el vendedor es un User, esto debería funcionar.
            queryset = VentaViaje.objects.filter(vendedor=user).order_by('-fecha_creacion')
            print(f"DEBUG: Rol VENDEDOR. Intentando filtrar ventas para {user.username} (ID: {user.id})")
        else:
            queryset = VentaViaje.objects.none()
            print(f"DEBUG: Rol {user_rol}. Queryset: NINGUNA venta.")

        # ¡ATENCIÓN! REVISA ESTE MENSAJE EN TU TERMINAL
        print(f"DEBUG: Ventas encontradas por get_queryset (Count): {queryset.count()}")
        
        return queryset.select_related('cliente', 'vendedor', 'proveedor')


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        user_rol = self.get_user_role(user)
        context['user_rol'] = user_rol

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
                Q(logistica__seguro_emitido=False) |
                Q(logistica__documentos_enviados=False)
            ).count()
            
            # INNOVACIÓN 2: Ranking de Vendedores
            context['ranking_ventas'] = VentaViaje.objects.filter(
                vendedor__isnull=False,
            ).values('vendedor__username').annotate(
                num_ventas=Count('id'),
                total_vendido=Sum('costo_venta_final')
            ).order_by('-num_ventas', '-total_vendido')[:5]
            
            # INNOVACIÓN 3: Notificaciones (solo para JEFE)
            if user_rol == 'JEFE':
                context['notificaciones'] = Notificacion.objects.filter(
                    usuario=user,
                    vista=False
                ).select_related('venta', 'venta__cliente')[:20]  # Últimas 20 no vistas
                context['notificaciones_count'] = Notificacion.objects.filter(
                    usuario=user,
                    vista=False
                ).count()
            
        # --- Lógica de KPIs (se mantiene para vendedores) ---
        elif user_rol == 'VENDEDOR':
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

        # 2. Anotar el QuerySet para calcular el total pagado, manejando NULL y usando un nombre NUEVO.
        # 'monto_abonado' es el nuevo nombre para evitar el conflicto con la propiedad 'total_pagado' del modelo.
        queryset = base_query.annotate(
            monto_abonado=Coalesce(  # <-- ¡NOMBRE DE CAMPO CORREGIDO!
                Sum('abonos__monto'), 
                Value(0), 
                output_field=IntegerField()
            ) 
        ).order_by('-fecha_creacion')
        
        # DEBUG: Mensaje para verificar en la consola del servidor
        print(f"DEBUG (VentaViajeListView): Rol {user_rol}. Ventas cargadas: {queryset.count()}")
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_queryset = context['object_list'] # QuerySet ahora tiene 'monto_abonado'

        # Criterio para CERRADA/LIQUIDADA: monto_abonado >= costo_venta_final

        # VENTAS CERRADAS (LIQUIDADA): 
        ventas_cerradas_qs = base_queryset.filter(
            monto_abonado__gte=F('costo_venta_final') # <-- ¡NOMBRE DE CAMPO CORREGIDO!
        )

        # VENTAS ACTIVAS: No cumplen la condición de cerradas 
        ventas_activas_qs = base_queryset.exclude(
            monto_abonado__gte=F('costo_venta_final') # <-- ¡NOMBRE DE CAMPO CORREGIDO!
        )
        
        # --- DEBUG FINAL (CRÍTICO) ---
        print("--------------------------------------------------")
        print(f"DEBUG FINAL (Contexto): Usuario {self.request.user.username}")
        print(f"   Ventas Activas (enviadas al HTML): {ventas_activas_qs.count()}")
        print(f"   Ventas Cerradas (enviadas al HTML): {ventas_cerradas_qs.count()}")
        print("--------------------------------------------------")
        # --- FIN DEL DEBUG CRÍTICO ---
        
        context['ventas_activas'] = ventas_activas_qs
        context['ventas_cerradas'] = ventas_cerradas_qs
        context['user_rol'] = get_user_role(self.request.user)
        
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
        
        # Inicialización del Formulario de Abono
        context['abono_form'] = AbonoPagoForm(initial={'venta': venta.pk}) 
        # Abonos existentes, ordenados por fecha
        context['abonos'] = venta.abonos.all().order_by('-fecha_pago')

        # LÓGICA: Inyección del Formulario de Logística (GET)
        try:
            logistica_instance = venta.logistica
        except Logistica.DoesNotExist:
            # Crea la instancia si el signal falló
            logistica_instance = Logistica.objects.create(venta=venta)
            
        # El template necesita 'logistica_form' cargado con los datos existentes
        context['logistica_form'] = LogisticaForm(instance=logistica_instance)
        context['confirmaciones'] = venta.confirmaciones.select_related('subido_por').all()
        context.setdefault('confirmacion_form', ConfirmacionVentaForm())
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
        
        # 1. Manejo del Formulario de Logística
        if 'actualizar_logistica' in request.POST:
            # Es importante asegurarse de que el usuario tenga el permiso para modificar la logística
            user_rol = request.user.perfil.rol if hasattr(request.user, 'perfil') else 'INVITADO'
            if user_rol in ['JEFE', 'CONTADOR'] or self.object.vendedor == request.user:
                logistica_instance = self.object.logistica
                logistica_form = LogisticaForm(request.POST, instance=logistica_instance)
                
                if logistica_form.is_valid():
                    logistica_form.save()
                    messages.success(request, "Checklist de Logística actualizado correctamente. ✅")
                    # Redirige a la misma URL para evitar el doble POST y mantener la pestaña Logística activa
                    # ******************************************************************
                    # IMPORTANTE: Se actualiza la redirección para usar SLUG y PK (YA ESTABA BIEN AQUÍ)
                    # ******************************************************************
                    return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=logistica')
                else:
                    messages.error(request, "Error al guardar la logística. Por favor, revisa los campos. ❌")
                    context['logistica_form'] = logistica_form # Muestra el formulario con errores
            else:
                messages.error(request, "No tienes permiso para actualizar la logística de esta venta.")
        
        # 2. Manejo del Formulario de Abono
        elif 'registrar_abono' in request.POST:
            abono_form = AbonoPagoForm(request.POST)
            if abono_form.is_valid():
                abono = abono_form.save(commit=False)
                abono.venta = self.object
                abono.registrado_por = request.user
                abono.save()
                messages.success(request, f"Abono de ${abono.monto} registrado exitosamente. 💰")
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

            confirmacion_form = ConfirmacionVentaForm(request.POST, request.FILES)
            if confirmacion_form.is_valid():
                archivos = request.FILES.getlist('archivos')
                nota = confirmacion_form.cleaned_data.get('nota', '')

                if not archivos:
                    messages.error(request, "Debes seleccionar al menos un archivo.")
                else:
                    creadas = 0
                    for archivo in archivos:
                        ConfirmacionVenta.objects.create(
                            venta=self.object,
                            archivo=archivo,
                            nota=nota,
                            subido_por=request.user if request.user.is_authenticated else None
                        )
                        creadas += 1

                    messages.success(request, f"Se cargaron {creadas} archivo(s) de confirmación correctamente.")
                    return redirect(reverse('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe}) + '?tab=confirmaciones')
            else:
                messages.error(request, "Hubo un error al cargar los archivos. Revisa el formulario.")

            context['confirmacion_form'] = confirmacion_form

        # Si no hubo redirección exitosa, re-renderiza la respuesta con el contexto actualizado
        return self.render_to_response(context)

    def _puede_subir_confirmaciones(self, user, venta):
        if not user.is_authenticated:
            return False
        if user.is_superuser or user == venta.vendedor:
            return True
        rol = get_user_role(user).upper()
        return 'JEFE' in rol or 'CONTADOR' in rol


# ------------------- 4. CREACIÓN Y EDICIÓN DE VENTA -------------------

class VentaViajeCreateView(LoginRequiredMixin, CreateView):
    model = VentaViaje
    form_class = VentaViajeForm
    template_name = 'ventas/venta_form.html'
    
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
    
        messages.success(self.request, "Venta creada exitosamente. ¡No olvides gestionar la logística!")
    
    # 6. Retorna la respuesta de redirección usando la URL de éxito
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        # Redirección correcta a la vista de detalle (AHORA CON SLUG)
        return reverse_lazy('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe})

class VentaViajeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = VentaViaje
    form_class = VentaViajeForm
    template_name = 'ventas/venta_form.html' # Usar el template de formulario si es UpdateView

    def test_func(self):
        # Solo el vendedor que creó la venta o el JEFE pueden editarla
        venta = self.get_object()
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return venta.vendedor == self.request.user or user_rol == 'JEFE'

    def handle_no_permission(self):
        venta = self.get_object()
        messages.error(self.request, "No tienes permiso para editar esta venta.")
        # Se asegura de usar 'detalle_venta' para la redirección de error (AHORA CON SLUG)
        return HttpResponseRedirect(reverse_lazy('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}))

    def get_success_url(self):
        messages.success(self.request, "Venta actualizada correctamente.")
        # Se asegura de usar 'detalle_venta' para la redirección de éxito (AHORA CON SLUG)
        return reverse_lazy('detalle_venta', kwargs={'pk': self.object.pk, 'slug': self.object.slug_safe})


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
        # Solo JEFES, CONTADORES o el VENDEDOR de la venta pueden acceder
        venta = self.get_object().venta
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        
        return user_rol in ['JEFE', 'CONTADOR'] or venta.vendedor == self.request.user

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
    context_object_name = 'lista_ventas'

    def dispatch(self, request, *args, **kwargs):
        """ Control de acceso directo: Solo Jefes y Contadores. """
        user = request.user
        
        # 1. Prioridad 1: Acceso Inmediato por Username o Flags (A prueba de fallos)
        if user.username == 'jefe_usuario' or user.is_superuser or user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        
        # 2. Prioridad 2: Acceso por Rol
        rol_valido = False
        
        if user.is_authenticated and hasattr(user, 'perfil') and user.perfil is not None:
            rol_completo = getattr(user.perfil, 'rol', None)
            
            if rol_completo and isinstance(rol_completo, str):
                rol_sanitizado = re.sub(r'[^A-Z]', '', rol_completo.upper())
                is_jefe = 'JEFE' in rol_sanitizado
                is_contador = 'CONTADOR' in rol_sanitizado
                rol_valido = is_jefe or is_contador
        
        if rol_valido:
            # Si el rol es válido, conceder acceso
            return super().dispatch(request, *args, **kwargs)
        
        # REDIRECCIÓN DE ACCESO DENEGADO 
        messages.error(request, "No tienes permiso para acceder al reporte de Logística Pendiente.")
        return redirect(reverse('dashboard'))

    # MÉTODO AGREGADO PARA INYECTAR LA VARIABLE user_rol AL TEMPLATE 
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        user_rol = '' # Valor predeterminado
        
        # Lógica para extraer el rol y pasarlo al template
        if user.is_authenticated and hasattr(user, 'perfil') and user.perfil is not None:
            rol_completo = getattr(user.perfil, 'rol', '').upper()
            
            # Sanitización (usando 're' importado globalmente)
            rol_sanitizado = re.sub(r'[^A-Z]', '', rol_completo)
            
            if 'JEFE' in rol_sanitizado:
                user_rol = 'JEFE'
            elif 'CONTADOR' in rol_sanitizado:
                user_rol = 'CONTADOR'
                
        context['user_rol'] = user_rol 
        return context

    def get_queryset(self):
        """ Filtra todas las ventas activas que tienen al menos una tarea de logística pendiente. """
        
        ventas_activas_con_pendientes = self.model.objects.filter(
            # Condición de Tipo de Viaje (NAC o INT son los valores válidos)
            tipo_viaje__in=['NAC', 'INT'] 
        ).exclude(
            # Excluye todas las ventas que NO tienen un registro de Logistica.
            logistica__isnull=True 
        ).filter(
            # Condición de Logística Pendiente (OR Lógico)
            Q(logistica__vuelo_confirmado=False) |
            Q(logistica__hospedaje_reservado=False) |
            Q(logistica__seguro_emitido=False) |
            Q(logistica__documentos_enviados=False)
        ).order_by('fecha_inicio_viaje').distinct()

        hoy = timezone.now().date()
        
        for venta in ventas_activas_con_pendientes:
            try:
                # El cálculo de días restantes y alerta de proximidad es correcto.
                dias_restantes = venta.fecha_inicio_viaje - hoy
                venta.dias_restantes = dias_restantes

                if dias_restantes.days <= 15:
                    venta.alerta_proximidad = 'CRITICA'
                elif dias_restantes.days <= 45:
                    venta.alerta_proximidad = 'URGENTE'
                else:
                    venta.alerta_proximidad = 'NORMAL'
            except (TypeError, AttributeError): # Capturar si fecha_inicio_viaje es None
                venta.dias_restantes = None
                venta.alerta_proximidad = 'SIN_FECHA'
        
        return ventas_activas_con_pendientes

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
        
        # Calcular totales para el PDF (incluyendo el saldo restante)
        total_pagado = venta.abonos.aggregate(Sum('monto'))['monto__sum'] or 0
        saldo_restante = venta.costo_venta_final - total_pagado
        
        # Obtener el contexto para la plantilla HTML
        context = {
            'venta': venta,
            'now': datetime.datetime.now(),
            'total_pagado': total_pagado,
            'saldo_restante': saldo_restante,
            # Incluir la lista de abonos para el detalle en el PDF
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
            'fecha_generacion': formats.date_format(datetime.datetime.now(), "j \d\e F \d\e Y"),
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
    Solo accesible para roles 'JEFE' o 'CONTADOR'.
    """
    model = VentaViaje
    template_name = 'ventas/venta_confirm_delete.html' 
    success_url = reverse_lazy('lista_ventas')

    def test_func(self):
        # Solo permite eliminar a Jefes y Contadores
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol in ['JEFE', 'CONTADOR']

    def handle_no_permission(self):
        # Redirige al dashboard si no tiene permiso
        messages.error(self.request, "No tienes permiso para eliminar ventas.")
        return redirect('dashboard')
    
# ------------------- 12. REPORTE DE COMISIONES POR VENDEDOR -------------------

class ComisionesVendedoresView(LoginRequiredMixin, TemplateView):
    """
    Muestra un reporte de sueldo fijo y comisiones calculadas.
    - JEFE: Ve a todos los vendedores de la agencia.
    - VENDEDOR: Solo ve su propia información.
    """
    template_name = 'ventas/comisiones_vendedores.html'
    
    # SUELDO FIJO Y COMISIÓN: Puedes ajustar estos valores.
    SUELDO_BASE = Decimal('10000.00') 
    COMISION_PORCENTAJE = Decimal('0.025') 

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
        elif user_rol == 'JEFE':
            # Si es jefe, ve a todos los vendedores
            vendedores_a_mostrar = vendedores_query
        else:
            # Otros roles (Contador, etc.) no deberían acceder si no son Jefe/Vendedor, 
            # pero por si acaso, se ven a sí mismos si tienen un perfil.
            vendedores_a_mostrar = User.objects.none() 

        # 2. Obtener todas las ventas pagadas (donde Costo Final <= Total Pagado)
        ventas_pagadas_base = self.get_queryset_base().filter(
            total_abonos__gte=F('costo_venta_final')
        )

        lista_comisiones = []
        
        for vendedor in vendedores_a_mostrar:
            # Filtra las ventas pagadas solo por el vendedor actual
            ventas_pagadas_vendedor = ventas_pagadas_base.filter(vendedor=vendedor)
            
            # Suma el costo final de las ventas pagadas (base para la comisión)
            total_ventas_pagadas = ventas_pagadas_vendedor.aggregate(
                total_suma_ventas=Sum('costo_venta_final')
            )['total_suma_ventas'] or Decimal('0.00')
            
            # CÁLCULO DE COMISIÓN
            comision_ganada = total_ventas_pagadas * self.COMISION_PORCENTAJE
            ingreso_total = self.SUELDO_BASE + comision_ganada

            lista_comisiones.append({
                'vendedor': vendedor,
                'sueldo_base': self.SUELDO_BASE,
                'comision_porcentaje': self.COMISION_PORCENTAJE * 100, # Para mostrar 2.5%
                'total_ventas_pagadas': total_ventas_pagadas,
                'comision_ganada': comision_ganada,
                'ingreso_total_estimado': ingreso_total,
                'es_usuario_actual': (vendedor.pk == self.request.user.pk)
            })

        context['lista_comisiones'] = lista_comisiones
        context['titulo_reporte'] = "Reporte de Comisiones de Ventas"
        context['user_rol'] = user_rol
        
        return context


class ProveedorListCreateView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Gestiona el catálogo de proveedores: listado agrupado y creación desde un solo lugar.
    """
    template_name = 'ventas/proveedores.html'

    def test_func(self):
        rol = get_user_role(self.request.user).upper()
        return 'JEFE' in rol or 'CONTADOR' in rol or self.request.user.is_superuser

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

class MarcarNotificacionVistaView(LoginRequiredMixin, View):
    """Vista AJAX para marcar una notificación como vista."""
    
    def post(self, request, pk):
        try:
            notificacion = Notificacion.objects.get(pk=pk, usuario=request.user)
            notificacion.marcar_como_vista()
            return JsonResponse({'success': True, 'message': 'Notificación marcada como vista'})
        except Notificacion.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Notificación no encontrada'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)


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

class EliminarConfirmacionView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """
    Vista para eliminar una confirmación de venta (archivo adjunto).
    """
    model = ConfirmacionVenta
    template_name = 'ventas/confirmacion_confirm_delete.html' 

    def get_success_url(self):
        venta = self.object.venta
        return reverse_lazy('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=confirmaciones'

    def test_func(self):
        confirmacion = self.get_object()
        user = self.request.user
        # Permitir si es superusuario, el que subió el archivo, o JEFE/CONTADOR
        if user.is_superuser: return True
        if confirmacion.subido_por == user: return True
        
        rol = get_user_role(user).upper()
        return 'JEFE' in rol or 'CONTADOR' in rol

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para eliminar esta confirmación.")
        venta = self.get_object().venta
        return redirect(reverse('detalle_venta', kwargs={'pk': venta.pk, 'slug': venta.slug_safe}) + '?tab=confirmaciones')