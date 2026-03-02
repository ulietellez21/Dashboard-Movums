"""
Servicio de KPIs para el Dashboard del Director Administrativo.
Scope: toda la red. Objetivo: control total del dinero y riesgo financiero.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Q
from django.utils import timezone

from ventas.models import (
    VentaViaje, AbonoPago, AbonoProveedor, ComisionVenta,
    SolicitudCancelacion,
)

MARGEN_MINIMO = Decimal('0.15')


# ===================== helpers =====================

def _fechas_periodo(periodo):
    hoy = timezone.localdate()
    if periodo == 'semanal':
        return hoy - timedelta(days=hoy.weekday()), hoy
    if periodo == 'mes_anterior':
        primer_dia_mes = hoy.replace(day=1)
        ultimo_anterior = primer_dia_mes - timedelta(days=1)
        return ultimo_anterior.replace(day=1), ultimo_anterior
    return hoy.replace(day=1), hoy


def _ventas_periodo(fecha_inicio, fecha_fin, exclude_canceladas=True):
    qs = VentaViaje.objects.filter(
        fecha_creacion__gte=fecha_inicio,
        fecha_creacion__lt=fecha_fin + timedelta(days=1),
    )
    if exclude_canceladas:
        qs = qs.exclude(estado='CANCELADA')
    return qs


def _venta_mxn(venta):
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        total_usd = getattr(venta, 'costo_venta_final_usd', None) or getattr(venta, 'total_usd', None)
        tc = getattr(venta, 'tipo_cambio', None)
        if total_usd and tc and Decimal(str(tc)) > 0:
            return (Decimal(str(total_usd)) * Decimal(str(tc))).quantize(Decimal('0.01'))
        return Decimal('0.00')
    return venta.costo_venta_final or Decimal('0.00')


def _margen_venta(venta):
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        neto = getattr(venta, 'costo_neto_usd', None) or Decimal('0.00')
        total = getattr(venta, 'costo_venta_final_usd', None) or Decimal('0.00')
    else:
        neto = venta.costo_neto or Decimal('0.00')
        total = venta.costo_venta_final or Decimal('0.00')
    if total <= 0:
        return None
    return (total - neto) / total


# ===================== FASE 1: Flujo de efectivo =====================

def flujo_efectivo(fecha_inicio, fecha_fin):
    """
    Ingresos cobrados reales, por cobrar, pagos a proveedores pendientes,
    anticipos retenidos, flujo proyectado 30-60-90 (por vencimientos).
    """
    hoy = timezone.localdate()
    ventas = list(
        _ventas_periodo(fecha_inicio, fecha_fin)
        .prefetch_related('abonos')
    )

    ingresos_cobrados = Decimal('0.00')
    ingresos_por_cobrar = Decimal('0.00')

    for v in ventas:
        pagado = v.total_pagado or Decimal('0.00')
        ingresos_cobrados += pagado
        saldo = v.saldo_restante
        if saldo and saldo > 0:
            ingresos_por_cobrar += saldo

    # Pagos a proveedores pendientes (PENDIENTE + APROBADO = aún no completados)
    proveedores_pendientes = AbonoProveedor.objects.filter(
        estado__in=['PENDIENTE', 'APROBADO'],
    ).aggregate(total=Sum('monto'))['total'] or Decimal('0.00')

    # Anticipos retenidos: aperturas de ventas en estado_confirmacion='EN_CONFIRMACION'
    ventas_en_confirmacion = VentaViaje.objects.filter(
        estado_confirmacion='EN_CONFIRMACION',
    ).exclude(estado='CANCELADA')
    anticipos_retenidos = Decimal('0.00')
    for v in ventas_en_confirmacion:
        anticipos_retenidos += v.cantidad_apertura or Decimal('0.00')

    # Flujo proyectado 30-60-90 por vencimientos de pago
    todas_activas_con_saldo = VentaViaje.objects.filter(
        fecha_vencimiento_pago__isnull=False,
    ).exclude(estado='CANCELADA')

    flujo_30 = Decimal('0.00')
    flujo_60 = Decimal('0.00')
    flujo_90 = Decimal('0.00')
    limite_30 = hoy + timedelta(days=30)
    limite_60 = hoy + timedelta(days=60)
    limite_90 = hoy + timedelta(days=90)

    for v in todas_activas_con_saldo:
        saldo = v.saldo_restante
        if not saldo or saldo <= 0:
            continue
        fv = v.fecha_vencimiento_pago
        if fv <= limite_30:
            flujo_30 += saldo
        if fv <= limite_60:
            flujo_60 += saldo
        if fv <= limite_90:
            flujo_90 += saldo

    return {
        'ingresos_cobrados': ingresos_cobrados,
        'ingresos_por_cobrar': ingresos_por_cobrar,
        'proveedores_pendientes': proveedores_pendientes,
        'anticipos_retenidos': anticipos_retenidos,
        'anticipos_retenidos_count': ventas_en_confirmacion.count(),
        'flujo_30': flujo_30,
        'flujo_60': flujo_60,
        'flujo_90': flujo_90,
    }


# ===================== FASE 2: Riesgo financiero =====================

def riesgo_financiero(fecha_inicio, fecha_fin):
    """
    Cancelaciones en proceso, margen comprometido (<15%).
    """
    # Cancelaciones pendientes (global, no por periodo)
    cancelaciones = list(
        SolicitudCancelacion.objects.filter(
            estado='PENDIENTE',
        ).select_related('venta', 'venta__cliente', 'venta__vendedor', 'solicitado_por')
        .order_by('-fecha_solicitud')[:20]
    )

    monto_cancelaciones = Decimal('0.00')
    for sc in cancelaciones:
        monto_cancelaciones += _venta_mxn(sc.venta)

    # Margen comprometido: ventas del periodo con margen < 15%
    ventas = list(
        _ventas_periodo(fecha_inicio, fecha_fin)
        .select_related('cliente', 'vendedor', 'proveedor')
    )
    ventas_margen_bajo = []
    for v in ventas:
        m = _margen_venta(v)
        if m is not None and m < MARGEN_MINIMO:
            ventas_margen_bajo.append({
                'venta': v,
                'margen_pct': (m * 100).quantize(Decimal('0.1')),
                'monto_mxn': _venta_mxn(v),
            })
    ventas_margen_bajo.sort(key=lambda x: x['margen_pct'])

    return {
        'cancelaciones': cancelaciones,
        'cancelaciones_count': len(cancelaciones),
        'monto_cancelaciones': monto_cancelaciones,
        'ventas_margen_bajo': ventas_margen_bajo[:20],
        'ventas_margen_bajo_count': len(ventas_margen_bajo),
    }


# ===================== FASE 3: Control interno =====================

def control_interno(fecha_inicio, fecha_fin):
    """
    Comisiones devengadas vs pagadas, diferencias contables,
    ventas sin soporte documental (>24h sin comprobante en confirmaciones).
    """
    hoy = timezone.localdate()
    ahora = timezone.now()

    # --- Comisiones devengadas vs pagadas (mes actual) ---
    comisiones = ComisionVenta.objects.filter(
        mes=hoy.month,
        anio=hoy.year,
        cancelada=False,
    )
    comisiones_devengadas = comisiones.aggregate(
        t=Sum('comision_calculada')
    )['t'] or Decimal('0.00')
    comisiones_pagadas = comisiones.aggregate(
        t=Sum('comision_pagada')
    )['t'] or Decimal('0.00')
    comisiones_diferencia = comisiones_devengadas - comisiones_pagadas

    # --- Diferencias contables ---
    # Ventas donde total_pagado (abonos+apertura) difiere del esperado
    # (saldo_restante negativo indica sobre-pago; descuadre > $1 se reporta)
    ventas_periodo = list(
        _ventas_periodo(fecha_inicio, fecha_fin)
        .prefetch_related('abonos')
    )
    diferencias = []
    for v in ventas_periodo:
        saldo = v.saldo_restante
        if saldo is not None and saldo < Decimal('-1.00'):
            diferencias.append({
                'venta': v,
                'saldo': saldo,
                'tipo': 'SOBREPAGO',
            })

    # --- Ventas sin soporte documental (>24h desde creación) ---
    # Regla: ventas con >24h de creadas y estado_confirmacion='PENDIENTE'
    # (no han subido comprobante de apertura ni iniciado confirmación)
    limite_24h = ahora - timedelta(hours=24)
    ventas_sin_docs = list(
        VentaViaje.objects.filter(
            fecha_creacion__lt=limite_24h,
            estado_confirmacion='PENDIENTE',
        ).exclude(
            estado='CANCELADA',
        ).select_related('cliente', 'vendedor')
        .order_by('fecha_creacion')[:30]
    )

    return {
        'comisiones_devengadas': comisiones_devengadas,
        'comisiones_pagadas': comisiones_pagadas,
        'comisiones_diferencia': comisiones_diferencia,
        'diferencias_contables': diferencias,
        'diferencias_contables_count': len(diferencias),
        'ventas_sin_docs': ventas_sin_docs,
        'ventas_sin_docs_count': len(ventas_sin_docs),
    }
