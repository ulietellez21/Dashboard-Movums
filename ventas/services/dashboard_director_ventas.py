"""
Servicio de KPIs para el Dashboard del Director de Ventas.
Scope: toda la red (todas las ventas/cotizaciones del sistema).
Objetivo: escalar ingresos nacionales y dominar el mercado.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q
from django.utils import timezone

from ventas.models import VentaViaje, Cotizacion


# ===================== helpers =====================

def _fechas_periodo(periodo):
    """Devuelve (fecha_inicio, fecha_fin) según periodo."""
    hoy = timezone.localdate()
    if periodo == 'semanal':
        return hoy - timedelta(days=hoy.weekday()), hoy
    if periodo == 'mes_anterior':
        primer_dia_mes = hoy.replace(day=1)
        ultimo_anterior = primer_dia_mes - timedelta(days=1)
        return ultimo_anterior.replace(day=1), ultimo_anterior
    return hoy.replace(day=1), hoy


def _ventas_red(fecha_inicio=None, fecha_fin=None, exclude_canceladas=True):
    """QuerySet de todas las ventas de la red, opcionalmente acotado."""
    qs = VentaViaje.objects.all()
    if exclude_canceladas:
        qs = qs.exclude(estado='CANCELADA')
    if fecha_inicio and fecha_fin:
        qs = qs.filter(
            fecha_creacion__gte=fecha_inicio,
            fecha_creacion__lt=fecha_fin + timedelta(days=1),
        )
    return qs


def _venta_mxn(venta):
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        total_usd = getattr(venta, 'costo_venta_final_usd', None) or getattr(venta, 'total_usd', None)
        tc = getattr(venta, 'tipo_cambio', None)
        if total_usd and tc and Decimal(str(tc)) > 0:
            return (Decimal(str(total_usd)) * Decimal(str(tc))).quantize(Decimal('0.01'))
        return Decimal('0.00')
    return venta.costo_venta_final or Decimal('0.00')


def _utilidad_venta(venta):
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        total_usd = getattr(venta, 'costo_venta_final_usd', None) or Decimal('0.00')
        neto_usd = getattr(venta, 'costo_neto_usd', None) or Decimal('0.00')
        tc = getattr(venta, 'tipo_cambio', None) or Decimal('0.00')
        if Decimal(str(tc)) > 0:
            return ((Decimal(str(total_usd)) - Decimal(str(neto_usd))) * Decimal(str(tc))).quantize(Decimal('0.01'))
        return Decimal('0.00')
    return (venta.costo_venta_final or Decimal('0.00')) - (venta.costo_neto or Decimal('0.00'))


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


def _es_corporativo(venta):
    """Determina si la venta es corporativa (cliente tipo EMPRESA o asociado a empresa)."""
    cliente = venta.cliente
    if not cliente:
        return False
    return (
        getattr(cliente, 'tipo_cliente', '') == 'EMPRESA'
        or getattr(cliente, 'empresa_asociada_id', None) is not None
    )


def _canal_venta(venta):
    """Clasifica la venta en canal: CORPORATIVO, NAC, INT o INT_MXN."""
    if _es_corporativo(venta):
        return 'CORPORATIVO'
    return venta.tipo_viaje or 'NAC'


def _calcular_totales(ventas_iter):
    """Calcula total_mxn, utilidad, margenes y count a partir de un iterable de ventas."""
    total_mxn = Decimal('0.00')
    utilidad = Decimal('0.00')
    margenes = []
    count = 0
    for v in ventas_iter:
        total_mxn += _venta_mxn(v)
        utilidad += _utilidad_venta(v)
        m = _margen_venta(v)
        if m is not None:
            margenes.append(m)
        count += 1
    margen_prom = (
        (sum(margenes) / len(margenes) * 100).quantize(Decimal('0.1'))
        if margenes else Decimal('0.00')
    )
    return total_mxn, utilidad, margen_prom, count


# ===================== MACROKPIS =====================

def macrokpis(fecha_inicio, fecha_fin):
    """
    Ventas totales red, utilidad, margen consolidado,
    crecimiento MoM (mes calendario), YoY, forecast 30-60-90.
    """
    ventas = list(
        _ventas_red(fecha_inicio, fecha_fin)
        .select_related('cliente', 'proveedor')
    )
    total_mxn, utilidad, margen, count = _calcular_totales(ventas)

    # --- Crecimiento vs mes anterior (meses calendario completos) ---
    mes_actual = fecha_inicio.month
    anio_actual = fecha_inicio.year
    if mes_actual == 1:
        mes_prev, anio_prev = 12, anio_actual - 1
    else:
        mes_prev, anio_prev = mes_actual - 1, anio_actual

    inicio_prev = date(anio_prev, mes_prev, 1)
    if mes_prev == 12:
        fin_prev = date(anio_prev + 1, 1, 1) - timedelta(days=1)
    else:
        fin_prev = date(anio_prev, mes_prev + 1, 1) - timedelta(days=1)

    ventas_prev = list(
        _ventas_red(inicio_prev, fin_prev).select_related('cliente', 'proveedor')
    )
    total_prev, _, _, count_prev = _calcular_totales(ventas_prev)

    if total_prev > 0:
        crecimiento_mom = ((total_mxn - total_prev) / total_prev * 100).quantize(Decimal('0.1'))
    else:
        crecimiento_mom = Decimal('0.0') if total_mxn == 0 else Decimal('100.0')

    # --- Crecimiento YoY (mismo mes, año anterior — mes calendario completo) ---
    anio_yoy = anio_actual - 1
    inicio_yoy = date(anio_yoy, mes_actual, 1)
    if mes_actual == 12:
        fin_yoy = date(anio_yoy + 1, 1, 1) - timedelta(days=1)
    else:
        fin_yoy = date(anio_yoy, mes_actual + 1, 1) - timedelta(days=1)

    ventas_yoy = list(
        _ventas_red(inicio_yoy, fin_yoy).select_related('cliente', 'proveedor')
    )
    total_yoy, _, _, _ = _calcular_totales(ventas_yoy)

    if total_yoy > 0:
        crecimiento_yoy = ((total_mxn - total_yoy) / total_yoy * 100).quantize(Decimal('0.1'))
    else:
        crecimiento_yoy = Decimal('0.0') if total_mxn == 0 else Decimal('100.0')

    # --- Forecast 30-60-90 (run-rate basado en días transcurridos del periodo) ---
    hoy = timezone.localdate()
    dias_transcurridos = (min(hoy, fecha_fin) - fecha_inicio).days + 1
    if dias_transcurridos > 0:
        rate_diario = total_mxn / dias_transcurridos
    else:
        rate_diario = Decimal('0.00')

    forecast_30 = (rate_diario * 30).quantize(Decimal('0.01'))
    forecast_60 = (rate_diario * 60).quantize(Decimal('0.01'))
    forecast_90 = (rate_diario * 90).quantize(Decimal('0.01'))

    return {
        'ventas_total_mxn': total_mxn,
        'ventas_count': count,
        'utilidad_total': utilidad,
        'margen_consolidado': margen,
        'total_prev': total_prev,
        'count_prev': count_prev,
        'crecimiento_mom': crecimiento_mom,
        'total_yoy': total_yoy,
        'crecimiento_yoy': crecimiento_yoy,
        'forecast_30': forecast_30,
        'forecast_60': forecast_60,
        'forecast_90': forecast_90,
        'rate_diario': rate_diario.quantize(Decimal('0.01')),
        'dias_transcurridos': dias_transcurridos,
    }


# ===================== EMBUDO NACIONAL =====================

def embudo_nacional(fecha_inicio, fecha_fin):
    """
    Embudo solo para tipo_viaje=NAC:
    cotizaciones, conversión, tiempo cierre.
    """
    fecha_fin_dt = fecha_fin + timedelta(days=1)

    cotizaciones = Cotizacion.objects.filter(
        creada_en__date__gte=fecha_inicio,
        creada_en__date__lte=fecha_fin,
    )
    total_cotizaciones = cotizaciones.count()

    ventas_nac = VentaViaje.objects.filter(
        tipo_viaje='NAC',
        fecha_creacion__gte=fecha_inicio,
        fecha_creacion__lt=fecha_fin_dt,
    ).exclude(estado='CANCELADA')

    ventas_con_cot = ventas_nac.filter(cotizacion_origen__isnull=False).count()
    pct_conversion = (
        (Decimal(ventas_con_cot) / Decimal(total_cotizaciones) * 100).quantize(Decimal('0.1'))
        if total_cotizaciones else Decimal('0.00')
    )

    # Tiempo promedio de cierre
    ventas_cot = ventas_nac.filter(
        cotizacion_origen__isnull=False,
    ).select_related('cotizacion_origen')
    dias_cierre = []
    for v in ventas_cot:
        if v.cotizacion_origen and v.cotizacion_origen.creada_en:
            fc = v.fecha_creacion.date() if hasattr(v.fecha_creacion, 'date') else v.fecha_creacion
            delta = (fc - v.cotizacion_origen.creada_en.date()).days
            dias_cierre.append(delta)
    tiempo_promedio = round(sum(dias_cierre) / len(dias_cierre), 1) if dias_cierre else 0

    return {
        'total_cotizaciones': total_cotizaciones,
        'ventas_nac_con_cot': ventas_con_cot,
        'pct_conversion': pct_conversion,
        'tiempo_promedio_cierre': tiempo_promedio,
    }


# ===================== VENTAS POR CANAL =====================

def ventas_por_canal(fecha_inicio, fecha_fin):
    """
    Desglose de ventas por canal: NAC, INT, INT_MXN, CORPORATIVO.
    Corporativo = cliente EMPRESA o con empresa_asociada.
    """
    ventas = list(
        _ventas_red(fecha_inicio, fecha_fin)
        .select_related('cliente', 'proveedor')
    )

    canales = {
        'NAC': {'ventas': [], 'label': 'Nacional'},
        'INT': {'ventas': [], 'label': 'Internacional'},
        'INT_MXN': {'ventas': [], 'label': 'Internacional MXN'},
        'CORPORATIVO': {'ventas': [], 'label': 'Corporativo'},
    }

    for v in ventas:
        canal = _canal_venta(v)
        if canal not in canales:
            canal = 'NAC'
        canales[canal]['ventas'].append(v)

    total_general = Decimal('0.00')
    resultado = {}
    for key, data in canales.items():
        t_mxn, util, margen_prom, cnt = _calcular_totales(data['ventas'])
        total_general += t_mxn
        resultado[key] = {
            'label': data['label'],
            'ventas_count': cnt,
            'ventas_mxn': t_mxn,
            'utilidad': util,
            'margen_promedio': margen_prom,
        }

    # Calcular % de participación
    for key in resultado:
        if total_general > 0:
            resultado[key]['pct_participacion'] = (
                resultado[key]['ventas_mxn'] / total_general * 100
            ).quantize(Decimal('0.1'))
        else:
            resultado[key]['pct_participacion'] = Decimal('0.0')

    return resultado, total_general
