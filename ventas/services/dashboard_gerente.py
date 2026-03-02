"""
Servicio de KPIs para el Dashboard de Gerente (Dueño de Franquicia).
Todas las funciones reciben oficina_id y retornan dicts listos para el contexto del template.
Scope: solo ventas cuyos vendedores pertenecen a la oficina del gerente.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone

from ventas.models import (
    VentaViaje, Cotizacion, ComisionVenta, SolicitudCancelacion,
    AbonoPago, Ejecutivo,
)

MARGEN_MINIMO = Decimal('0.15')
DIAS_RIESGO_COBRO = 7


# ===================== helpers =====================

def _fechas_periodo(periodo):
    """Devuelve (fecha_inicio, fecha_fin) según periodo seleccionado."""
    hoy = timezone.localdate()
    if periodo == 'semanal':
        return hoy - timedelta(days=hoy.weekday()), hoy
    if periodo == 'mes_anterior':
        primer_dia_mes = hoy.replace(day=1)
        ultimo_anterior = primer_dia_mes - timedelta(days=1)
        return ultimo_anterior.replace(day=1), ultimo_anterior
    # mensual (default)
    return hoy.replace(day=1), hoy


def _vendedores_oficina(oficina_id):
    """User IDs de vendedores que pertenecen a la oficina."""
    return list(
        Ejecutivo.objects.filter(
            oficina_id=oficina_id,
            usuario__isnull=False,
        ).values_list('usuario_id', flat=True)
    )


def _ventas_oficina(oficina_id, fecha_inicio=None, fecha_fin=None, exclude_canceladas=True):
    """QuerySet base de ventas de la oficina, opcionalmente acotado a un periodo."""
    qs = VentaViaje.objects.filter(
        vendedor__ejecutivo_asociado__oficina_id=oficina_id,
    )
    if exclude_canceladas:
        qs = qs.exclude(estado='CANCELADA')
    if fecha_inicio and fecha_fin:
        fecha_fin_dt = fecha_fin + timedelta(days=1)
        qs = qs.filter(fecha_creacion__gte=fecha_inicio, fecha_creacion__lt=fecha_fin_dt)
    return qs


def _venta_mxn(venta):
    """Monto de la venta en MXN."""
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        total_usd = getattr(venta, 'costo_venta_final_usd', None) or getattr(venta, 'total_usd', None)
        tc = getattr(venta, 'tipo_cambio', None)
        if total_usd and tc and Decimal(str(tc)) > 0:
            return (Decimal(str(total_usd)) * Decimal(str(tc))).quantize(Decimal('0.01'))
        return Decimal('0.00')
    return venta.costo_venta_final or Decimal('0.00')


def _utilidad_venta(venta):
    """Utilidad (venta_final - costo_neto) en MXN."""
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        total_usd = getattr(venta, 'costo_venta_final_usd', None) or Decimal('0.00')
        neto_usd = getattr(venta, 'costo_neto_usd', None) or Decimal('0.00')
        tc = getattr(venta, 'tipo_cambio', None) or Decimal('0.00')
        if Decimal(str(tc)) > 0:
            return ((Decimal(str(total_usd)) - Decimal(str(neto_usd))) * Decimal(str(tc))).quantize(Decimal('0.01'))
        return Decimal('0.00')
    total = venta.costo_venta_final or Decimal('0.00')
    neto = venta.costo_neto or Decimal('0.00')
    return total - neto


def _margen_venta(venta):
    """Margen porcentual (0-1). None si no se puede calcular."""
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        neto = getattr(venta, 'costo_neto_usd', None) or Decimal('0.00')
        total = getattr(venta, 'costo_venta_final_usd', None) or Decimal('0.00')
    else:
        neto = venta.costo_neto or Decimal('0.00')
        total = venta.costo_venta_final or Decimal('0.00')
    if total <= 0:
        return None
    return (total - neto) / total


# ===================== FASE 1: KPIs clave =====================

def kpis_clave(oficina_id, fecha_inicio, fecha_fin):
    """
    Ventas totales oficina, Utilidad, Margen promedio,
    Ticket promedio, % Conversión global.
    """
    ventas = list(
        _ventas_oficina(oficina_id, fecha_inicio, fecha_fin)
        .select_related('proveedor')
    )

    total_mxn = Decimal('0.00')
    utilidad_total = Decimal('0.00')
    margenes = []

    for v in ventas:
        monto = _venta_mxn(v)
        total_mxn += monto
        utilidad_total += _utilidad_venta(v)
        m = _margen_venta(v)
        if m is not None:
            margenes.append(m)

    count = len(ventas)
    ticket_promedio = (total_mxn / count).quantize(Decimal('0.01')) if count else Decimal('0.00')
    margen_promedio = (
        (sum(margenes) / len(margenes) * 100).quantize(Decimal('0.1'))
        if margenes else Decimal('0.00')
    )

    # Conversión global oficina
    vendedor_ids = _vendedores_oficina(oficina_id)
    fecha_fin_dt = fecha_fin + timedelta(days=1)
    cotizaciones_periodo = Cotizacion.objects.filter(
        vendedor_id__in=vendedor_ids,
        creada_en__date__gte=fecha_inicio,
        creada_en__date__lte=fecha_fin,
    ).count()
    ventas_con_cot = _ventas_oficina(oficina_id, fecha_inicio, fecha_fin).filter(
        cotizacion_origen__isnull=False,
    ).count()
    pct_conversion = (
        (Decimal(ventas_con_cot) / Decimal(cotizaciones_periodo) * 100).quantize(Decimal('0.1'))
        if cotizaciones_periodo else Decimal('0.00')
    )

    return {
        'ventas_total_mxn': total_mxn,
        'ventas_count': count,
        'utilidad_total': utilidad_total,
        'margen_promedio': margen_promedio,
        'ticket_promedio': ticket_promedio,
        'pct_conversion': pct_conversion,
        'cotizaciones_periodo': cotizaciones_periodo,
    }


def ventas_por_vendedor(oficina_id, fecha_inicio, fecha_fin):
    """Desglose de ventas y utilidad por cada vendedor de la oficina."""
    vendedor_ids = _vendedores_oficina(oficina_id)
    fecha_fin_dt = fecha_fin + timedelta(days=1)

    from django.contrib.auth.models import User
    vendedores = User.objects.filter(pk__in=vendedor_ids).select_related('ejecutivo_asociado')

    resultado = []
    for vendedor in vendedores:
        ventas_v = VentaViaje.objects.filter(
            vendedor=vendedor,
            fecha_creacion__gte=fecha_inicio,
            fecha_creacion__lt=fecha_fin_dt,
        ).exclude(estado='CANCELADA').select_related('proveedor')

        total_mxn = Decimal('0.00')
        utilidad = Decimal('0.00')
        count = 0
        for v in ventas_v:
            total_mxn += _venta_mxn(v)
            utilidad += _utilidad_venta(v)
            count += 1

        nombre = vendedor.get_full_name() or vendedor.username
        tipo = getattr(vendedor.ejecutivo_asociado, 'tipo_vendedor', '—') if hasattr(vendedor, 'ejecutivo_asociado') else '—'

        resultado.append({
            'nombre': nombre,
            'tipo': tipo,
            'ventas_count': count,
            'ventas_mxn': total_mxn,
            'utilidad': utilidad,
        })

    resultado.sort(key=lambda x: x['ventas_mxn'], reverse=True)
    return resultado


def kpis_comisiones(oficina_id, mes, anio):
    """Comisiones generadas (calculadas) vs pagadas, totalizadas por oficina."""
    vendedor_ids = _vendedores_oficina(oficina_id)
    comisiones = ComisionVenta.objects.filter(
        vendedor_id__in=vendedor_ids,
        mes=mes,
        anio=anio,
        cancelada=False,
    )
    generadas = comisiones.aggregate(t=Sum('comision_calculada'))['t'] or Decimal('0.00')
    pagadas = comisiones.aggregate(t=Sum('comision_pagada'))['t'] or Decimal('0.00')
    return {
        'comisiones_generadas': generadas,
        'comisiones_pagadas': pagadas,
    }


# ===================== FASE 2: Productividad =====================

def kpis_productividad(oficina_id, fecha_inicio, fecha_fin):
    """Ventas por empleado (vendedores activos de la oficina)."""
    vendedor_ids = _vendedores_oficina(oficina_id)
    num_vendedores = len(vendedor_ids) or 1

    ventas = list(
        _ventas_oficina(oficina_id, fecha_inicio, fecha_fin)
        .select_related('proveedor')
    )

    total_mxn = Decimal('0.00')
    for v in ventas:
        total_mxn += _venta_mxn(v)

    count = len(ventas)
    ventas_por_empleado = round(count / num_vendedores, 1)
    mxn_por_empleado = (total_mxn / num_vendedores).quantize(Decimal('0.01'))

    return {
        'num_vendedores': num_vendedores,
        'ventas_por_empleado': ventas_por_empleado,
        'mxn_por_empleado': mxn_por_empleado,
        'total_ventas_count': count,
        'total_ventas_mxn': total_mxn,
    }


# ===================== FASE 3: Cartera =====================

def kpis_cartera(oficina_id, fecha_inicio, fecha_fin):
    """
    Cuentas por cobrar, ventas con riesgo (vencimiento <= 7 días),
    cancelaciones del mes (por fecha_cancelacion_definitiva).
    """
    hoy = timezone.localdate()

    # --- Cuentas por cobrar: ventas del periodo con saldo > 0 ---
    ventas_periodo = list(
        _ventas_oficina(oficina_id, fecha_inicio, fecha_fin)
        .prefetch_related('abonos')
    )
    cuentas_por_cobrar = Decimal('0.00')
    ventas_con_saldo = 0
    for v in ventas_periodo:
        saldo = v.saldo_restante
        if saldo and saldo > 0:
            cuentas_por_cobrar += saldo
            ventas_con_saldo += 1

    # --- Ventas con riesgo: vencimiento <= 7 días con saldo pendiente ---
    limite_riesgo = hoy + timedelta(days=DIAS_RIESGO_COBRO)
    ventas_riesgo_qs = VentaViaje.objects.filter(
        vendedor__ejecutivo_asociado__oficina_id=oficina_id,
        fecha_vencimiento_pago__isnull=False,
        fecha_vencimiento_pago__lte=limite_riesgo,
    ).exclude(estado='CANCELADA').select_related('cliente', 'vendedor').order_by('fecha_vencimiento_pago')

    ventas_riesgo = []
    for v in ventas_riesgo_qs:
        if v.saldo_restante > 0:
            ventas_riesgo.append({
                'venta': v,
                'dias_para_vencer': (v.fecha_vencimiento_pago - hoy).days,
                'saldo': v.saldo_restante,
                'vendedor_nombre': v.vendedor.get_full_name() or v.vendedor.username,
            })

    # --- Cancelaciones del mes (por fecha_cancelacion_definitiva en SolicitudCancelacion) ---
    vendedor_ids = _vendedores_oficina(oficina_id)
    cancelaciones = SolicitudCancelacion.objects.filter(
        venta__vendedor_id__in=vendedor_ids,
        estado='APROBADA',
        fecha_cancelacion_definitiva__date__gte=fecha_inicio,
        fecha_cancelacion_definitiva__date__lte=fecha_fin,
    ).select_related('venta', 'venta__cliente', 'venta__vendedor').order_by('-fecha_cancelacion_definitiva')

    return {
        'cuentas_por_cobrar': cuentas_por_cobrar,
        'ventas_con_saldo': ventas_con_saldo,
        'ventas_riesgo': ventas_riesgo,
        'ventas_riesgo_count': len(ventas_riesgo),
        'cancelaciones': list(cancelaciones),
        'cancelaciones_count': cancelaciones.count(),
    }


# ===================== FASE 4: Inteligencia =====================

def ranking_vendedores_oficina(oficina_id, fecha_inicio, fecha_fin):
    """
    Ranking de vendedores de la oficina: ventas MXN, utilidad, margen.
    Solo nombres reales, scope oficina.
    """
    vendedor_ids = _vendedores_oficina(oficina_id)
    fecha_fin_dt = fecha_fin + timedelta(days=1)

    from django.contrib.auth.models import User
    vendedores = User.objects.filter(pk__in=vendedor_ids).select_related('ejecutivo_asociado')

    ranking = []
    for vendedor in vendedores:
        ventas_v = VentaViaje.objects.filter(
            vendedor=vendedor,
            fecha_creacion__gte=fecha_inicio,
            fecha_creacion__lt=fecha_fin_dt,
        ).exclude(estado='CANCELADA').select_related('proveedor')

        total_mxn = Decimal('0.00')
        utilidad = Decimal('0.00')
        margenes = []
        count = 0
        for v in ventas_v:
            total_mxn += _venta_mxn(v)
            utilidad += _utilidad_venta(v)
            m = _margen_venta(v)
            if m is not None:
                margenes.append(m)
            count += 1

        margen_prom = (sum(margenes) / len(margenes) * 100).quantize(Decimal('0.1')) if margenes else Decimal('0.00')
        nombre = vendedor.get_full_name() or vendedor.username

        ranking.append({
            'nombre': nombre,
            'ventas_count': count,
            'ventas_mxn': total_mxn,
            'utilidad': utilidad,
            'margen_promedio': margen_prom,
        })

    ranking.sort(key=lambda x: x['ventas_mxn'], reverse=True)
    return ranking


def rentabilidad_por_tipo(oficina_id, fecha_inicio, fecha_fin):
    """Rentabilidad desglosada por tipo de viaje: NAC, INT, INT_MXN."""
    ventas = list(
        _ventas_oficina(oficina_id, fecha_inicio, fecha_fin)
        .select_related('proveedor')
    )

    por_tipo = {}
    for tipo_key in ('NAC', 'INT', 'INT_MXN'):
        por_tipo[tipo_key] = {
            'ventas_count': 0,
            'ventas_mxn': Decimal('0.00'),
            'utilidad': Decimal('0.00'),
            'margenes': [],
        }

    for v in ventas:
        tipo = v.tipo_viaje or 'NAC'
        if tipo not in por_tipo:
            tipo = 'NAC'
        por_tipo[tipo]['ventas_count'] += 1
        por_tipo[tipo]['ventas_mxn'] += _venta_mxn(v)
        por_tipo[tipo]['utilidad'] += _utilidad_venta(v)
        m = _margen_venta(v)
        if m is not None:
            por_tipo[tipo]['margenes'].append(m)

    for tipo_key, data in por_tipo.items():
        ms = data.pop('margenes')
        data['margen_promedio'] = (
            (sum(ms) / len(ms) * 100).quantize(Decimal('0.1'))
            if ms else Decimal('0.00')
        )

    return por_tipo
