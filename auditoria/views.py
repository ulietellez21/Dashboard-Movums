from django.views.generic import ListView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta

from .models import HistorialMovimiento
from ventas.models import VentaViaje, Cotizacion, AbonoPago
from ventas.validators import safe_int
from crm.models import Cliente


class HistorialMovimientosView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Vista para mostrar el historial completo de movimientos del sistema.
    Solo accesible para JEFE y CONTADOR.
    """
    model = HistorialMovimiento
    template_name = 'auditoria/historial_list.html'
    context_object_name = 'movimientos'
    paginate_by = 50
    
    def test_func(self):
        """Solo JEFE y CONTADOR pueden ver el historial."""
        if not self.request.user.is_authenticated:
            return False
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol in ['JEFE', 'CONTADOR']
    
    def get_queryset(self):
        """Filtra el queryset según los parámetros de búsqueda."""
        queryset = HistorialMovimiento.objects.select_related('usuario', 'content_type').order_by('-fecha_hora')
        
        # Filtro por tipo de evento
        tipo_evento = self.request.GET.get('tipo_evento')
        if tipo_evento:
            queryset = queryset.filter(tipo_evento=tipo_evento)
        
        # Filtro por nivel
        nivel = self.request.GET.get('nivel')
        if nivel:
            queryset = queryset.filter(nivel=nivel)
        
        # Filtro por usuario
        usuario_id = self.request.GET.get('usuario')
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)
        
        # Filtro por búsqueda de texto
        busqueda = self.request.GET.get('busqueda')
        if busqueda:
            queryset = queryset.filter(
                Q(descripcion__icontains=busqueda) |
                Q(usuario__username__icontains=busqueda)
            )
        
        # Filtro por rango de fechas
        fecha_desde = self.request.GET.get('fecha_desde')
        fecha_hasta = self.request.GET.get('fecha_hasta')
        
        if fecha_desde:
            try:
                fecha_desde_obj = timezone.datetime.strptime(fecha_desde, '%Y-%m-%d').date()
                queryset = queryset.filter(fecha_hora__date__gte=fecha_desde_obj)
            except ValueError:
                pass
        
        if fecha_hasta:
            try:
                fecha_hasta_obj = timezone.datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
                # Agregar 1 día para incluir todo el día
                fecha_hasta_obj = fecha_hasta_obj + timedelta(days=1)
                queryset = queryset.filter(fecha_hora__date__lt=fecha_hasta_obj)
            except ValueError:
                pass
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Agregar opciones para los filtros
        context['tipos_evento'] = HistorialMovimiento.TIPO_EVENTO_CHOICES
        context['niveles'] = HistorialMovimiento.NIVEL_CHOICES
        
        # ✅ PERFORMANCE: Optimizar estadísticas con una sola query usando aggregate
        from django.db.models import Count, Q
        stats = HistorialMovimiento.objects.aggregate(
            total=Count('id'),
            hoy=Count('id', filter=Q(fecha_hora__date=timezone.now().date())),
            semana=Count('id', filter=Q(fecha_hora__gte=timezone.now() - timedelta(days=7)))
        )
        context['total_movimientos'] = stats['total']
        context['movimientos_hoy'] = stats['hoy']
        context['movimientos_ultima_semana'] = stats['semana']
        
        # Valores de filtros actuales
        context['filtro_tipo'] = self.request.GET.get('tipo_evento', '')
        context['filtro_nivel'] = self.request.GET.get('nivel', '')
        context['filtro_usuario'] = self.request.GET.get('usuario', '')
        context['filtro_busqueda'] = self.request.GET.get('busqueda', '')
        context['filtro_fecha_desde'] = self.request.GET.get('fecha_desde', '')
        context['filtro_fecha_hasta'] = self.request.GET.get('fecha_hasta', '')
        
        return context


class HistorialMovimientosAjaxView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Vista AJAX para obtener movimientos filtrados para el modal del reporte financiero.
    Solo accesible para JEFE y CONTADOR.
    """
    
    def test_func(self):
        """Solo JEFE y CONTADOR pueden ver el historial."""
        if not self.request.user.is_authenticated:
            return False
        user_rol = self.request.user.perfil.rol if hasattr(self.request.user, 'perfil') else 'INVITADO'
        return user_rol in ['JEFE', 'CONTADOR']
    
    def get(self, request, *args, **kwargs):
        """Retorna los movimientos filtrados en formato JSON."""
        from django.db.models import Q
        from django.http import JsonResponse
        from django.contrib.contenttypes.models import ContentType
        
        queryset = HistorialMovimiento.objects.select_related('usuario', 'content_type').order_by('-fecha_hora')
        
        # Filtros
        tipo_evento = request.GET.get('tipo_evento')
        if tipo_evento:
            queryset = queryset.filter(tipo_evento=tipo_evento)
        
        usuario_id = request.GET.get('usuario')
        if usuario_id:
            queryset = queryset.filter(usuario_id=usuario_id)
        
        busqueda = request.GET.get('busqueda')
        if busqueda:
            queryset = queryset.filter(
                Q(descripcion__icontains=busqueda) |
                Q(usuario__username__icontains=busqueda)
            )
        
        fecha_desde = request.GET.get('fecha_desde')
        fecha_hasta = request.GET.get('fecha_hasta')
        
        if fecha_desde:
            try:
                fecha_desde_obj = timezone.datetime.strptime(fecha_desde, '%Y-%m-%d').date()
                queryset = queryset.filter(fecha_hora__date__gte=fecha_desde_obj)
            except ValueError:
                pass
        
        if fecha_hasta:
            try:
                fecha_hasta_obj = timezone.datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
                fecha_hasta_obj = fecha_hasta_obj + timedelta(days=1)
                queryset = queryset.filter(fecha_hora__date__lt=fecha_hasta_obj)
            except ValueError:
                pass
        
        # Paginación (safe_int previene errores 500 si el usuario manipula el parámetro)
        page = safe_int(request.GET.get('page'), default=1)
        if page < 1:
            page = 1
        per_page = 35
        start = (page - 1) * per_page
        end = start + per_page
        
        total = queryset.count()
        movimientos = queryset[start:end]
        
        # Preparar datos para JSON
        movimientos_data = []
        for mov in movimientos:
            # Determinar URL de enlace si aplica
            enlace_url = None
            enlace_texto = None
            
            if mov.content_type and mov.object_id:
                try:
                    obj = mov.content_type.get_object_for_this_type(pk=mov.object_id)
                    # Si el objeto es un AbonoPago, obtener la venta relacionada
                    if isinstance(obj, AbonoPago):
                        venta = obj.venta
                        enlace_url = f"/ventas/{venta.slug_safe}-{venta.pk}/?tab=abonos"
                        enlace_texto = f"Ver Venta #{venta.pk}"
                    elif isinstance(obj, VentaViaje):
                        enlace_url = f"/ventas/{obj.slug_safe}-{obj.pk}/"
                        # Si es un movimiento de abono, agregar parámetro para ir directo a la pestaña de abonos
                        if mov.tipo_evento in ['ABONO_REGISTRADO', 'ABONO_CONFIRMADO', 'ABONO_ELIMINADO']:
                            enlace_url += '?tab=abonos'
                        enlace_texto = f"Ver Venta #{obj.pk}"
                    elif isinstance(obj, Cotizacion):
                        enlace_url = f"/ventas/cotizaciones/{obj.slug}/"
                        enlace_texto = f"Ver Cotización"
                    elif isinstance(obj, Cliente):
                        enlace_url = f"/crm/clientes/{obj.pk}/"
                        enlace_texto = f"Ver Cliente"
                except Exception as e:
                    # Log del error para debugging si es necesario
                    pass
            
            movimientos_data.append({
                'id': mov.pk,
                'fecha_hora': mov.fecha_hora.strftime('%d/%m/%Y %H:%M:%S'),
                'usuario': mov.usuario.username if mov.usuario else 'Sistema',
                'tipo_evento': mov.get_tipo_evento_display(),
                'descripcion': mov.descripcion,
                'nivel': mov.nivel,
                'enlace_url': enlace_url,
                'enlace_texto': enlace_texto,
            })
        
        return JsonResponse({
            'success': True,
            'movimientos': movimientos_data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
        })










