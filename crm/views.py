from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.db.models import Q, Max 
from django.db import IntegrityError
from django.views.decorators.http import require_POST
from decimal import Decimal
from .models import Cliente, HistorialKilometros, PromocionKilometros
from ventas.models import VentaViaje
from .services import KilometrosService
from .forms import ClienteForm, PromocionKilometrosForm
from usuarios import permissions as perm

# ------------------- 1. LISTADO DE CLIENTES (OPTIMIZADO) -------------------

class ClienteListView(LoginRequiredMixin, ListView):
    """Muestra una lista de clientes con soporte para búsqueda y paginación."""
    model = Cliente
    template_name = 'crm/cliente_list.html'
    context_object_name = 'object_list' 
    paginate_by = 20
    ordering = ['-fecha_registro'] 

    def get_queryset(self):
        qs = super().get_queryset()
        
        # 1. Optimización: Anotar la PK de la última venta para un enlace rápido
        qs = qs.prefetch_related('ventas_asociadas').annotate(
             ultima_venta_pk=Max('ventas_asociadas__pk')
        )
        
        # 2. Lógica de Búsqueda 
        query = self.request.GET.get('q')
        if query:
            # CORRECCIÓN DE INDENTACIÓN Y SINTAXIS PARA EVITAR EL ERROR
            qs = qs.filter(
                Q(nombre__icontains=query) |
                Q(apellido__icontains=query) |
                Q(nombre_empresa__icontains=query) | 
                Q(rfc__icontains=query) | 
                Q(email__icontains=query) |
                Q(telefono__icontains=query)
            ).distinct() 
            
        return qs

# ------------------- 2. DETALLE DE CLIENTE -------------------

class ClienteDetailView(LoginRequiredMixin, DetailView):
    """Muestra el detalle de un cliente y sus ventas asociadas."""
    model = Cliente
    template_name = 'crm/cliente_detail.html'
    context_object_name = 'cliente'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['ventas_cliente'] = self.object.ventas_asociadas.all().order_by('-fecha_inicio_viaje')
        context['kilometros'] = KilometrosService.resumen_cliente(self.object)
        return context


# ------------------- 3. CREACIÓN DE CLIENTE (CLAVE) -------------------

class ClienteCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Permite crear un nuevo cliente usando el formulario con validación condicional."""
    model = Cliente
    template_name = 'crm/crear_cliente.html' 
    form_class = ClienteForm
    
    def test_func(self):
        """Solo JEFE y VENDEDOR pueden crear clientes. CONTADOR solo lectura."""
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol in ['JEFE', 'VENDEDOR']
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para crear clientes. Solo puedes visualizarlos.")
        return redirect('lista_clientes')
    
    def form_valid(self, form):
        try:
            messages.success(self.request, f"Cliente '{form.instance}' creado exitosamente.")
            return super().form_valid(form)
        except IntegrityError as e:
            # Capturar errores de integridad (campos únicos duplicados)
            error_str = str(e).lower()
            if 'telefono' in error_str or 'unique constraint' in error_str and 'telefono' in error_str:
                form.add_error('telefono', 'Este número de teléfono ya está registrado. Por favor, usa otro número.')
            elif 'rfc' in error_str or 'unique constraint' in error_str and 'rfc' in error_str:
                form.add_error('rfc', 'Este RFC ya está registrado. Por favor, verifica el RFC.')
            elif 'documento_identificacion' in error_str or 'unique constraint' in error_str and 'documento_identificacion' in error_str:
                form.add_error('documento_identificacion', 'Este documento de identificación ya está registrado.')
            else:
                messages.error(self.request, 'Error al guardar el cliente: Ya existe un cliente con estos datos. Por favor, verifica la información.')
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f'Error al guardar el cliente: {str(e)}')
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        """Manejar errores de validación y mostrarlos correctamente."""
        # Agregar mensaje de error general si hay errores
        if form.errors:
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"{field}: {error}")
            if error_messages:
                messages.error(self.request, f"Por favor, corrige los siguientes errores: {'; '.join(error_messages[:3])}")
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse_lazy('detalle_cliente', kwargs={'pk': self.object.pk})


# ------------------- 4. EDICIÓN DE CLIENTE -------------------
class ClienteUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Permite editar los datos de un cliente existente."""
    model = Cliente
    template_name = 'crm/crear_cliente.html' 
    form_class = ClienteForm
    
    def test_func(self):
        """Solo JEFE y VENDEDOR pueden editar clientes. CONTADOR solo lectura."""
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol in ['JEFE', 'VENDEDOR']
    
    def handle_no_permission(self):
        cliente = self.get_object()
        messages.error(self.request, "No tienes permiso para editar clientes. Solo puedes visualizarlos.")
        return redirect('detalle_cliente', pk=cliente.pk)
    
    def form_valid(self, form):
        try:
            messages.success(self.request, f"Cliente '{form.instance}' actualizado exitosamente.")
            return super().form_valid(form)
        except IntegrityError as e:
            # Capturar errores de integridad (campos únicos duplicados)
            error_str = str(e).lower()
            if 'telefono' in error_str or 'unique constraint' in error_str and 'telefono' in error_str:
                form.add_error('telefono', 'Este número de teléfono ya está registrado. Por favor, usa otro número.')
            elif 'rfc' in error_str or 'unique constraint' in error_str and 'rfc' in error_str:
                form.add_error('rfc', 'Este RFC ya está registrado. Por favor, verifica el RFC.')
            elif 'documento_identificacion' in error_str or 'unique constraint' in error_str and 'documento_identificacion' in error_str:
                form.add_error('documento_identificacion', 'Este documento de identificación ya está registrado.')
            else:
                messages.error(self.request, 'Error al actualizar el cliente: Ya existe un cliente con estos datos. Por favor, verifica la información.')
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f'Error al actualizar el cliente: {str(e)}')
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        """Manejar errores de validación y mostrarlos correctamente."""
        # Agregar mensaje de error general si hay errores
        if form.errors:
            error_messages = []
            for field, errors in form.errors.items():
                for error in errors:
                    error_messages.append(f"{field}: {error}")
            if error_messages:
                messages.error(self.request, f"Por favor, corrige los siguientes errores: {'; '.join(error_messages[:3])}")
        return super().form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('detalle_cliente', kwargs={'pk': self.object.pk})


# ------------------- 5. ELIMINACIÓN DE CLIENTE -------------------

@require_POST
def eliminar_cliente(request, pk):
    """
    Vista que maneja la eliminación de un cliente específico.
    Solo accesible mediante método POST (formulario).
    Solo JEFE puede eliminar.
    """
    # Verificar permisos - SOLO JEFE
    user_rol = request.user.perfil.rol if hasattr(request.user, 'perfil') else 'INVITADO'
    if user_rol != 'JEFE':
        messages.error(request, "No tienes permiso para eliminar clientes. Solo el JEFE puede realizar esta acción.")
        return redirect('detalle_cliente', pk=pk)
    
    try:
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente_nombre = str(cliente) 
        
        cliente.delete()
        
        messages.success(request, f'El cliente "{cliente_nombre}" y sus datos asociados han sido eliminados exitosamente.')
        
        return redirect('lista_clientes') 
    
    except Exception as e:
        messages.error(request, f'Error al intentar eliminar el cliente: No se pudo completar la operación. Detalles: {e}')
        return redirect('detalle_cliente', pk=pk)


# ------------------- 6. Dashboard Kilómetros Movums -------------------

class KilometrosDashboardView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Dashboard centralizado para promociones, KPIs y movimientos de Kilómetros Movums.
    Vendedores solo consulta (no pueden editar).
    """
    model = HistorialKilometros
    template_name = 'crm/kilometros_dashboard.html'
    context_object_name = 'movimientos'
    paginate_by = 20

    def test_func(self):
        return perm.can_view_km_movums(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para ver el programa de Kilómetros Movums.")
        return redirect('lista_clientes')

    def get_queryset(self):
        return HistorialKilometros.objects.select_related('cliente').order_by('-fecha_registro')

    def get_context_data(self, **kwargs):
        from django.db import models as dj_models
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['can_edit_km_movums'] = perm.can_edit_km_movums(user)
        socios = Cliente.objects.filter(participa_kilometros=True)
        total_km_acumulados = socios.aggregate(total=dj_models.Sum('kilometros_acumulados'))['total'] or 0
        total_km_disponibles = socios.aggregate(total=dj_models.Sum('kilometros_disponibles'))['total'] or 0
        total_km_canjeados = HistorialKilometros.objects.filter(es_redencion=True).aggregate(total=dj_models.Sum('kilometros'))['total'] or 0
        total_km_expirados = HistorialKilometros.objects.filter(expirado=True).aggregate(total=dj_models.Sum('kilometros'))['total'] or 0
        context.update({
            'total_km_acumulados': total_km_acumulados,
            'total_km_disponibles': total_km_disponibles,
            'total_km_canjeados': total_km_canjeados,
            'total_km_expirados': total_km_expirados,
            'socios_count': socios.count(),
        })
        context['promociones'] = PromocionKilometros.objects.all().order_by('-creada_en')
        context['promocion_form'] = kwargs.get('promocion_form') or PromocionKilometrosForm()
        socios_list = list(socios.order_by('-kilometros_disponibles')[:20])
        for socio in socios_list:
            socio.valor_disponible_mxn = (socio.kilometros_disponibles or Decimal('0.00')) * Decimal('0.05')
        context['socios'] = socios_list
        context['ventas_con_promos'] = (
            VentaViaje.objects.filter(descuento_promociones_mxn__gt=0)
            .select_related('cliente', 'vendedor')
            .order_by('-fecha_creacion')[:50]
        )
        return context

    def post(self, request, *args, **kwargs):
        if not perm.can_edit_km_movums(request.user):
            messages.error(request, "No tienes permiso para crear o editar promociones en Kilómetros Movums (solo consulta).")
            return redirect('kilometros_dashboard')
        form = PromocionKilometrosForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Promoción guardada correctamente.")
            return redirect('kilometros_dashboard')
        messages.error(request, "Revisa los errores en la promoción.")
        context = self.get_context_data(promocion_form=form)
        return self.render_to_response(context)


class PromocionKilometrosUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = PromocionKilometros
    form_class = PromocionKilometrosForm
    template_name = 'crm/promocion_form.html'
    context_object_name = 'promocion'

    def test_func(self):
        return perm.can_edit_km_movums(self.request.user)

    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para editar promociones en Kilómetros Movums.")
        return redirect('kilometros_dashboard')

    def get_success_url(self):
        messages.success(self.request, "Promoción actualizada correctamente.")
        return reverse_lazy('kilometros_dashboard')


# ------------------- VISTAS PARA ACTIVAR/DESACTIVAR/ELIMINAR PROMOCIONES -------------------

class PromocionKilometrosActivarView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Vista para activar una promoción."""
    
    def test_func(self):
        return perm.can_edit_km_movums(self.request.user)
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para activar promociones en Kilómetros Movums.")
        return redirect('kilometros_dashboard')
    
    def post(self, request, *args, **kwargs):
        promocion = get_object_or_404(PromocionKilometros, pk=kwargs['pk'])
        promocion.activa = True
        promocion.save()
        messages.success(request, f"Promoción '{promocion.nombre}' activada correctamente.")
        return redirect('kilometros_dashboard')
    
    def get(self, request, *args, **kwargs):
        # Permitir GET también para facilitar el uso desde enlaces
        return self.post(request, *args, **kwargs)


class PromocionKilometrosDesactivarView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Vista para desactivar una promoción."""
    
    def test_func(self):
        return perm.can_edit_km_movums(self.request.user)
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para desactivar promociones en Kilómetros Movums.")
        return redirect('kilometros_dashboard')
    
    def post(self, request, *args, **kwargs):
        promocion = get_object_or_404(PromocionKilometros, pk=kwargs['pk'])
        promocion.activa = False
        promocion.save()
        messages.success(request, f"Promoción '{promocion.nombre}' desactivada correctamente.")
        return redirect('kilometros_dashboard')
    
    def get(self, request, *args, **kwargs):
        # Permitir GET también para facilitar el uso desde enlaces
        return self.post(request, *args, **kwargs)


class PromocionKilometrosDeleteView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Vista para eliminar una promoción."""
    
    def test_func(self):
        return perm.can_edit_km_movums(self.request.user)
    
    def handle_no_permission(self):
        messages.error(self.request, "No tienes permiso para eliminar promociones en Kilómetros Movums.")
        return redirect('kilometros_dashboard')
    
    def post(self, request, *args, **kwargs):
        promocion = get_object_or_404(PromocionKilometros, pk=kwargs['pk'])
        nombre_promocion = promocion.nombre
        promocion.delete()
        messages.success(request, f"Promoción '{nombre_promocion}' eliminada correctamente.")
        return redirect('kilometros_dashboard')
    
    def get(self, request, *args, **kwargs):
        # Permitir GET también para facilitar el uso desde enlaces
        return self.post(request, *args, **kwargs)