"""
Servicio para el calendario visual de check-in/check-out de viajes.
Devuelve eventos para FullCalendar según el alcance del usuario (rol).
Excluye siempre las ventas canceladas.
"""
import calendar
from datetime import date

from django.urls import reverse


def ventas_para_calendario(queryset_base, anio, mes):
    """
    Obtiene ventas con check-in en el mes/año indicado para el calendario.
    Solo muestra check-in (fecha_inicio_viaje). Excluye CANCELADA.

    Args:
        queryset_base: QuerySet de VentaViaje ya filtrado por rol (perm.get_ventas_queryset_base)
        anio: año (int)
        mes: mes (int, 1-12)

    Returns:
        Lista de dicts para FullCalendar:
        [{"title": str, "start": "YYYY-MM-DD", "url": str}, ...]
    """
    try:
        ultimo_dia = calendar.monthrange(anio, mes)[1]
        fecha_desde = date(anio, mes, 1)
        fecha_hasta = date(anio, mes, ultimo_dia)
    except (ValueError, TypeError):
        return []

    ventas = (
        queryset_base.exclude(estado='CANCELADA')
        .filter(
            fecha_inicio_viaje__gte=fecha_desde,
            fecha_inicio_viaje__lte=fecha_hasta
        )
        .select_related('cliente', 'vendedor')
        .order_by('fecha_inicio_viaje', 'id')
    )

    eventos = []
    for v in ventas:
        cliente_nombre = (v.cliente.nombre_completo_display if v.cliente else 'Sin cliente')
        folio = v.folio or f'#{v.pk}'
        titulo = f"Check-in: {cliente_nombre} — {folio}"
        try:
            url = reverse('detalle_venta', kwargs={'pk': v.pk, 'slug': v.slug_safe})
        except Exception:
            url = ''
        eventos.append({
            'title': titulo,
            'start': v.fecha_inicio_viaje.isoformat(),
            'url': url,
            'extendedProps': {
                'venta_id': v.pk,
                'folio': folio,
            }
        })

    return eventos
