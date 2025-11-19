from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q, Max 
from django.views.decorators.http import require_POST
from .models import Cliente 
from .forms import ClienteForm 
# Importa tu VentaViaje si no está en este mismo módulo
# from ventas.models import VentaViaje 

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
        return context


# ------------------- 3. CREACIÓN DE CLIENTE (CLAVE) -------------------

class ClienteCreateView(LoginRequiredMixin, CreateView):
    """Permite crear un nuevo cliente usando el formulario con validación condicional."""
    model = Cliente
    template_name = 'crm/crear_cliente.html' 
    form_class = ClienteForm
    
    def form_valid(self, form):
        messages.success(self.request, f"Cliente '{form.instance}' creado exitosamente.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('detalle_cliente', kwargs={'pk': self.object.pk})


# ------------------- 4. EDICIÓN DE CLIENTE -------------------
class ClienteUpdateView(LoginRequiredMixin, UpdateView):
    """Permite editar los datos de un cliente existente."""
    model = Cliente
    template_name = 'crm/crear_cliente.html' 
    form_class = ClienteForm
    
    def form_valid(self, form):
        messages.success(self.request, f"Cliente '{form.instance}' actualizado exitosamente.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('detalle_cliente', kwargs={'pk': self.object.pk})


# ------------------- 5. ELIMINACIÓN DE CLIENTE -------------------

@require_POST
def eliminar_cliente(request, pk):
    """
    Vista que maneja la eliminación de un cliente específico.
    Solo accesible mediante método POST (formulario).
    """
    try:
        cliente = get_object_or_404(Cliente, pk=pk)
        cliente_nombre = str(cliente) 
        
        cliente.delete()
        
        messages.success(request, f'El cliente "{cliente_nombre}" y sus datos asociados han sido eliminados exitosamente.')
        
        return redirect('lista_clientes') 
    
    except Exception as e:
        messages.error(request, f'Error al intentar eliminar el cliente: No se pudo completar la operación. Detalles: {e}')
        return redirect('detalle_cliente', pk=pk)