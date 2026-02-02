from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone


def build_financial_summary(venta, servicios_qs):
    # Calcular total_venta incluyendo modificaciones y restando ambos descuentos
    costo_base = venta.costo_venta_final or Decimal('0.00')
    modificaciones = venta.costo_modificacion or Decimal('0.00')
    descuento_km = venta.descuento_kilometros_mxn or Decimal('0.00')
    descuento_promo = venta.descuento_promociones_mxn or Decimal('0.00')
    total_venta = costo_base + modificaciones - descuento_km - descuento_promo
    total_venta = max(Decimal('0.00'), total_venta)  # Asegurar que no sea negativo
    
    total_neto = venta.costo_neto or Decimal('0.00')
    total_pagado = venta.total_pagado or Decimal('0.00')

    # Servicios planificados = costo neto de la venta (asignado al crear la venta)
    total_servicios_planeados = venta.costo_neto or Decimal('0.00')
    # Suma real de los montos planificados asignados en la tabla (debe coincidir con costo_neto)
    suma_montos_planeados = servicios_qs.aggregate(
        total=Coalesce(Sum('monto_planeado'), Decimal('0.00'))
    )['total']
    pagado_servicios = servicios_qs.filter(pagado=True).aggregate(
        total=Coalesce(Sum('monto_planeado'), Decimal('0.00'))
    )['total']

    # Saldo disponible para servicios = Servicios planificados - Servicios pagados
    saldo_disponible = max(Decimal('0.00'), total_servicios_planeados - pagado_servicios)
    ganancia_estimada = max(Decimal('0.00'), total_venta - total_servicios_planeados)
    ganancia_en_mano = max(Decimal('0.00'), total_pagado - total_servicios_planeados)
    ganancia_pendiente = max(Decimal('0.00'), ganancia_estimada - ganancia_en_mano)

    # Cuadre: la suma de montos planificados debe ser igual al costo neto (tolerancia 0.01)
    montos_cuadran = abs(suma_montos_planeados - total_servicios_planeados) < Decimal('0.01')

    return {
        'total_venta': total_venta,
        'total_neto': total_neto,
        'total_pagado': total_pagado,
        'total_servicios_planeados': total_servicios_planeados,
        'suma_montos_planeados': suma_montos_planeados,
        'montos_cuadran': montos_cuadran,
        'monto_pagado_servicios': pagado_servicios,
        'saldo_disponible_servicios': saldo_disponible,
        'ganancia_estimada': ganancia_estimada,
        'ganancia_cobrada': ganancia_en_mano,
        'ganancia_pendiente': ganancia_pendiente,
        'servicios_totales': servicios_qs.count(),
        'modificaciones': modificaciones,
    }


def build_service_rows(servicios_qs, summary, formset_forms=None, venta=None):
    saldo_disponible = summary['saldo_disponible_servicios']
    badge_map = {
        'paid': ('success', 'Pagado'),
        'ready': ('warning text-dark', 'Listo para pagar'),
        'pending': ('danger', 'Pendiente'),
    }

    filas = []
    forms = formset_forms or []
    use_forms = len(forms) == len(servicios_qs)
    for idx, servicio in enumerate(servicios_qs):
        monto = servicio.monto_planeado or Decimal('0.00')
        if servicio.pagado:
            status = 'paid'
            hint = servicio.fecha_pagado.strftime('%d/%m/%Y %H:%M') if servicio.fecha_pagado else 'Pagado'
        elif monto > 0 and saldo_disponible >= monto:
            status = 'ready'
            hint = "Fondos disponibles para cubrir este servicio."
        else:
            status = 'pending'
            faltante = max(Decimal('0.00'), monto - saldo_disponible)
            hint = f"Faltan ${faltante:,.2f} para cubrir este servicio."

        badge_class, status_label = badge_map[status]
        
        filas.append({
            'form': forms[idx] if use_forms else None,
            'servicio': servicio,
            'status': status,
            'badge_class': badge_class,
            'status_label': status_label,
            'status_hint': hint,
        })

    return filas


def build_logistica_card(venta):
    servicios = list(venta.servicios_logisticos.all().order_by('orden', 'pk'))
    summary = build_financial_summary(venta, venta.servicios_logisticos.all())
    saldo_disponible = summary['saldo_disponible_servicios']

    STATUS_META = {
        'pending': ('danger', 'Pendiente'),
        'ready': ('warning text-dark', 'Fondos listos'),
        'paid': ('success', 'Pagado'),
    }
    ESTADO_META = {
        'pendiente': ('danger', 'Servicios pendientes'),
        'ready': ('warning text-dark', 'Servicios listos para pagar'),
        'completo': ('success', 'Servicios cubiertos'),
        'sin_servicios': ('secondary', 'Sin servicios planificados'),
    }

    servicios_info = []
    ready_found = False
    pending_found = False

    for serv in servicios:
        monto = serv.monto_planeado or Decimal('0.00')
        if serv.pagado:
            status = 'paid'
            hint = f"Pagado el {serv.fecha_pagado.strftime('%d/%m/%Y %H:%M')}" if serv.fecha_pagado else "Pagado"
        elif monto > 0 and saldo_disponible >= monto:
            status = 'ready'
            ready_found = True
            hint = "Fondos disponibles para cubrir este servicio."
        else:
            status = 'pending'
            pending_found = True
            faltante = max(Decimal('0.00'), monto - saldo_disponible)
            hint = f"Faltan ${faltante:,.2f} para cubrir este servicio."

        servicios_info.append({
            'obj': serv,
            'nombre': serv.nombre_servicio,
            'monto': monto,
            'status': status,
            'badge_class': STATUS_META[status][0],
            'status_label': STATUS_META[status][1],
            'status_hint': hint,
        })

    if servicios and all(s['status'] == 'paid' for s in servicios_info):
        estado = 'completo'
    elif ready_found:
        estado = 'ready'
    elif pending_found:
        estado = 'pendiente'
    else:
        estado = 'sin_servicios'

    estado_badge, estado_label = ESTADO_META[estado]
    estado_border = estado_badge.split()[0]

    today = timezone.localdate()
    dias_restantes = None
    if venta.fecha_inicio_viaje:
        dias_restantes = (venta.fecha_inicio_viaje - today).days

    total_planeado = summary['total_servicios_planeados']
    pagado_servicios = summary['monto_pagado_servicios']
    progreso_neto = 0
    if total_planeado > 0:
        progreso_neto = min(100, max(0, round(float(pagado_servicios / total_planeado * 100), 2)))

    summary_extended = summary.copy()
    summary_extended['progreso_neto'] = progreso_neto

    return {
        'venta': venta,
        'servicios': servicios_info,
        'estado': estado,
        'estado_badge': estado_badge,
        'estado_border': estado_border,
        'estado_label': estado_label,
        'dias_restantes': dias_restantes,
        'resumen': summary_extended,
    }
