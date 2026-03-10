"""
Servicio para el calendario visual de check-in/check-out de viajes.
Devuelve eventos para FullCalendar según el alcance del usuario (rol).
Excluye siempre las ventas canceladas.
"""
import calendar
from datetime import date

from django.db.models import Q
from django.urls import reverse


def ventas_para_calendario(queryset_base, anio, mes):
    """
    Obtiene ventas con check-in o check-out en el mes/año indicado para el calendario.
    Muestra tanto check-in (fecha_inicio_viaje) como check-out (fecha_fin_viaje) cuando exista.
    Excluye CANCELADA.

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

    # Incluir ventas cuyo check-in O check-out caiga en el mes
    ventas = (
        queryset_base.exclude(estado='CANCELADA')
        .filter(
            Q(
                Q(fecha_inicio_viaje__gte=fecha_desde, fecha_inicio_viaje__lte=fecha_hasta) |
                Q(fecha_fin_viaje__gte=fecha_desde, fecha_fin_viaje__lte=fecha_hasta)
            )
        )
        .select_related('cliente', 'vendedor')
        .order_by('fecha_inicio_viaje', 'id')
    )

    eventos = []
    for v in ventas:
        cliente_nombre = (v.cliente.nombre_completo_display if v.cliente else 'Sin cliente')
        folio = v.folio or f'#{v.pk}'
        try:
            url = reverse('detalle_venta', kwargs={'pk': v.pk, 'slug': v.slug_safe})
        except Exception:
            url = ''

        # Evento check-in (si cae en el mes)
        if fecha_desde <= v.fecha_inicio_viaje <= fecha_hasta:
            eventos.append({
                'title': f"Check-in: {cliente_nombre} — {folio}",
                'start': v.fecha_inicio_viaje.isoformat(),
                'url': url,
                'extendedProps': {'venta_id': v.pk, 'folio': folio, 'tipo': 'checkin'},
                'backgroundColor': '#0d6efd',
            })

        # Evento check-out (si existe y cae en el mes)
        if v.fecha_fin_viaje and fecha_desde <= v.fecha_fin_viaje <= fecha_hasta:
            eventos.append({
                'title': f"Check-out: {cliente_nombre} — {folio}",
                'start': v.fecha_fin_viaje.isoformat(),
                'url': url,
                'extendedProps': {'venta_id': v.pk, 'folio': folio, 'tipo': 'checkout'},
                'backgroundColor': '#198754',
            })

    return eventos
