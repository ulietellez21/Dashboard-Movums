"""
Servicio de KPIs para el Dashboard del Director General.
Scope: toda la red. Objetivo: decidir expansión y dominar mercado.
Minimalista pero brutalmente claro.
"""
from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict

from django.db.models import Sum, Count
from django.utils import timezone

from ventas.models import VentaViaje, AbonoProveedor, Ejecutivo, Oficina


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


def _ventas_red(fecha_inicio=None, fecha_fin=None, exclude_canceladas=True):
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
    cliente = venta.cliente
    if not cliente:
        return False
    return (
        getattr(cliente, 'tipo_cliente', '') == 'EMPRESA'
        or getattr(cliente, 'empresa_asociada_id', None) is not None
    )


def _canal_venta(venta):
    if _es_corporativo(venta):
        return 'CORPORATIVO'
    return venta.tipo_viaje or 'NAC'


# ===================== 12 KPIs MAESTROS =====================

def kpis_maestros(fecha_inicio, fecha_fin):
    """
    12 KPIs: ventas totales, utilidad neta, margen consolidado,
    crecimiento MoM, YoY, ventas por oficina, ventas por canal,
    recompra clientes, ticket promedio, cancelaciones %, flujo disponible.
    (ROI marketing omitido)
    """
    hoy = timezone.localdate()
    ventas = list(
        _ventas_red(fecha_inicio, fecha_fin)
        .select_related('cliente', 'proveedor', 'vendedor')
        .prefetch_related('abonos')
    )

    total_mxn = Decimal('0.00')
    utilidad = Decimal('0.00')
    margenes = []
    for v in ventas:
        total_mxn += _venta_mxn(v)
        utilidad += _utilidad_venta(v)
        m = _margen_venta(v)
        if m is not None:
            margenes.append(m)

    count = len(ventas)
    margen_consolidado = (
        (sum(margenes) / len(margenes) * 100).quantize(Decimal('0.1'))
        if margenes else Decimal('0.00')
    )
    ticket_promedio = (total_mxn / count).quantize(Decimal('0.01')) if count else Decimal('0.00')

    # Crecimiento MoM
    mes = fecha_inicio.month
    anio = fecha_inicio.year
    if mes == 1:
        mes_prev, anio_prev = 12, anio - 1
    else:
        mes_prev, anio_prev = mes - 1, anio
    inicio_prev = date(anio_prev, mes_prev, 1)
    fin_prev = (date(anio_prev, mes_prev + 1, 1) if mes_prev < 12 else date(anio_prev + 1, 1, 1)) - timedelta(days=1)
    ventas_prev = list(_ventas_red(inicio_prev, fin_prev).select_related('proveedor'))
    total_prev = sum(_venta_mxn(v) for v in ventas_prev)
    crecimiento_mom = ((total_mxn - total_prev) / total_prev * 100).quantize(Decimal('0.1')) if total_prev else (Decimal('0') if total_mxn == 0 else Decimal('100'))

    # Crecimiento YoY
    inicio_yoy = date(anio - 1, mes, 1)
    fin_yoy = (date(anio - 1, mes + 1, 1) if mes < 12 else date(anio, 1, 1)) - timedelta(days=1)
    ventas_yoy = list(_ventas_red(inicio_yoy, fin_yoy).select_related('proveedor'))
    total_yoy = sum(_venta_mxn(v) for v in ventas_yoy)
    crecimiento_yoy = ((total_mxn - total_yoy) / total_yoy * 100).quantize(Decimal('0.1')) if total_yoy else (Decimal('0') if total_mxn == 0 else Decimal('100'))

    # Cancelaciones %
    total_mas_canceladas = VentaViaje.objects.filter(
        fecha_creacion__gte=fecha_inicio,
        fecha_creacion__lt=fecha_fin + timedelta(days=1),
    )
    total_todas = total_mas_canceladas.count()
    canceladas = total_mas_canceladas.filter(estado='CANCELADA').count()
    pct_cancelaciones = (Decimal(canceladas) / Decimal(total_todas) * 100).quantize(Decimal('0.1')) if total_todas else Decimal('0')

    # Flujo disponible: ingresos cobrados - pagos proveedores pendientes
    ingresos_cobrados = sum((v.total_pagado or Decimal('0')) for v in ventas)
    proveedores_pendientes = AbonoProveedor.objects.filter(
        estado__in=['PENDIENTE', 'APROBADO'],
    ).aggregate(t=Sum('monto'))['t'] or Decimal('0.00')
    flujo_disponible = ingresos_cobrados - proveedores_pendientes

    # Recompra clientes
    clientes_ids = [v.cliente_id for v in ventas if v.cliente_id]
    ventas_por_cliente = defaultdict(int)
    for vid in clientes_ids:
        ventas_por_cliente[vid] += 1
    recompras = sum(1 for c in ventas_por_cliente.values() if c >= 2)
    pct_recompra = (Decimal(recompras) / Decimal(len(ventas_por_cliente)) * 100).quantize(Decimal('0.1')) if ventas_por_cliente else Decimal('0')

    # Ventas por oficina
    oficina_totales = defaultdict(lambda: {'mxn': Decimal('0'), 'count': 0})
    for v in ventas:
        ejec = getattr(v.vendedor, 'ejecutivo_asociado', None) if v.vendedor else None
        of_id = getattr(ejec, 'oficina_id', None) if ejec else None
        key = of_id or 0
        oficina_totales[key]['mxn'] += _venta_mxn(v)
        oficina_totales[key]['count'] += 1

    oficinas_nombres = {}
    for of in Oficina.objects.filter(pk__in=[k for k in oficina_totales if k != 0]):
        oficinas_nombres[of.pk] = of.nombre
    oficinas_nombres[0] = 'Sin oficina'

    ventas_por_oficina = [
        {'nombre': oficinas_nombres.get(k, f'Oficina {k}'), 'mxn': data['mxn'], 'count': data['count']}
        for k, data in sorted(oficina_totales.items(), key=lambda x: x[1]['mxn'], reverse=True)
    ]

    # Ventas por canal
    canales = defaultdict(lambda: {'mxn': Decimal('0'), 'count': 0})
    for v in ventas:
        c = _canal_venta(v)
        canales[c]['mxn'] += _venta_mxn(v)
        canales[c]['count'] += 1

    labels = {'NAC': 'Nacional', 'INT': 'Internacional', 'INT_MXN': 'Int. MXN', 'CORPORATIVO': 'Corporativo'}
    ventas_por_canal = [
        {'canal': k, 'label': labels.get(k, k), 'mxn': data['mxn'], 'count': data['count'],
         'pct': (data['mxn'] / total_mxn * 100).quantize(Decimal('0.1')) if total_mxn else Decimal('0')}
        for k, data in sorted(canales.items(), key=lambda x: x[1]['mxn'], reverse=True)
    ]

    return {
        'ventas_totales': total_mxn,
        'utilidad_neta': utilidad,
        'margen_consolidado': margen_consolidado,
        'crecimiento_mom': crecimiento_mom,
        'crecimiento_yoy': crecimiento_yoy,
        'ventas_por_oficina': ventas_por_oficina,
        'ventas_por_canal': ventas_por_canal,
        'recompra_clientes_count': recompras,
        'recompra_clientes_pct': pct_recompra,
        'ticket_promedio': ticket_promedio,
        'pct_cancelaciones': pct_cancelaciones,
        'flujo_disponible': flujo_disponible,
        'ventas_count': count,
    }


# ===================== EXPANSIÓN =====================

def rentabilidad_por_oficina(fecha_inicio, fecha_fin):
    """Utilidad y margen por oficina."""
    ventas = list(
        _ventas_red(fecha_inicio, fecha_fin)
        .select_related('cliente', 'proveedor', 'vendedor')
    )

    por_oficina = defaultdict(lambda: {'mxn': Decimal('0'), 'utilidad': Decimal('0'), 'margenes': []})
    for v in ventas:
        ejec = getattr(v.vendedor, 'ejecutivo_asociado', None) if v.vendedor else None
        of_id = getattr(ejec, 'oficina_id', None) if ejec else None
        key = of_id or 0
        por_oficina[key]['mxn'] += _venta_mxn(v)
        por_oficina[key]['utilidad'] += _utilidad_venta(v)
        m = _margen_venta(v)
        if m is not None:
            por_oficina[key]['margenes'].append(m)

    oficinas = {o.pk: o.nombre for o in Oficina.objects.all()}
    oficinas[0] = 'Sin oficina'

    resultado = []
    for k, data in por_oficina.items():
        margen = (sum(data['margenes']) / len(data['margenes']) * 100).quantize(Decimal('0.1')) if data['margenes'] else Decimal('0')
        resultado.append({
            'nombre': oficinas.get(k, f'Oficina {k}'),
            'ventas_mxn': data['mxn'],
            'utilidad': data['utilidad'],
            'margen': margen,
        })
    resultado.sort(key=lambda x: x['ventas_mxn'], reverse=True)
    return resultado


def penetracion_segmento(fecha_inicio, fecha_fin):
    """% de ventas por segmento (NAC, INT, INT_MXN, Corporativo)."""
    ventas = list(_ventas_red(fecha_inicio, fecha_fin).select_related('cliente'))
    total = Decimal('0.00')
    por_segmento = defaultdict(Decimal)
    for v in ventas:
        m = _venta_mxn(v)
        total += m
        por_segmento[_canal_venta(v)] += m

    labels = {'NAC': 'Nacional', 'INT': 'Internacional', 'INT_MXN': 'Int. MXN', 'CORPORATIVO': 'Corporativo'}
    return [
        {'segmento': k, 'label': labels.get(k, k), 'mxn': mxn, 'pct': (mxn / total * 100).quantize(Decimal('0.1')) if total else Decimal('0')}
        for k, mxn in sorted(por_segmento.items(), key=lambda x: x[1], reverse=True)
    ]


# ===================== INTELIGENCIA ESTRATÉGICA =====================

def dependencia_proveedores(fecha_inicio, fecha_fin, top=5):
    """% de ventas por proveedor (concentración)."""
    ventas = list(_ventas_red(fecha_inicio, fecha_fin).select_related('proveedor'))
    total = Decimal('0.00')
    por_prov = defaultdict(Decimal)
    for v in ventas:
        m = _venta_mxn(v)
        total += m
        nombre = v.proveedor.nombre if v.proveedor else 'Sin proveedor'
        por_prov[nombre] += m

    lista = [{'proveedor': k, 'mxn': mxn, 'pct': (mxn / total * 100).quantize(Decimal('0.1')) if total else Decimal('0')}
             for k, mxn in sorted(por_prov.items(), key=lambda x: x[1], reverse=True)[:top]]
    top3_pct = sum(x['pct'] for x in lista[:3])
    return lista, top3_pct


def concentracion_ingresos(fecha_inicio, fecha_fin):
    """Top vendedores, oficinas y canales por % de ingresos."""
    ventas = list(_ventas_red(fecha_inicio, fecha_fin).select_related('vendedor'))
    total = sum(_venta_mxn(v) for v in ventas)
    if total <= 0:
        return {'vendedores': [], 'oficinas': [], 'canales': []}

    oficinas_map = {o.pk: o.nombre for o in Oficina.objects.all()}

    por_vend = defaultdict(Decimal)
    por_oficina = defaultdict(Decimal)
    por_canal = defaultdict(Decimal)
    for v in ventas:
        m = _venta_mxn(v)
        nom = (v.vendedor.get_full_name() or v.vendedor.username) if v.vendedor else '—'
        por_vend[nom] += m
        ejec = getattr(v.vendedor, 'ejecutivo_asociado', None) if v.vendedor else None
        of_id = getattr(ejec, 'oficina_id', None) if ejec else None
        nombre_of = oficinas_map.get(of_id, 'Sin oficina') if of_id else 'Sin oficina'
        por_oficina[nombre_of] += m
        por_canal[_canal_venta(v)] += m

    labels = {'NAC': 'Nacional', 'INT': 'Internacional', 'INT_MXN': 'Int. MXN', 'CORPORATIVO': 'Corporativo'}
    return {
        'vendedores': [{'nombre': k, 'mxn': mxn, 'pct': (mxn / total * 100).quantize(Decimal('0.1'))}
                      for k, mxn in sorted(por_vend.items(), key=lambda x: x[1], reverse=True)[:10]],
        'oficinas': [{'nombre': k, 'mxn': mxn, 'pct': (mxn / total * 100).quantize(Decimal('0.1'))}
                     for k, mxn in sorted(por_oficina.items(), key=lambda x: x[1], reverse=True)[:10]],
        'canales': [{'canal': k, 'label': labels.get(k, k), 'mxn': mxn, 'pct': (mxn / total * 100).quantize(Decimal('0.1'))}
                    for k, mxn in sorted(por_canal.items(), key=lambda x: x[1], reverse=True)],
    }


def temporadas_pico_valle(meses=12):
    """Ventas por mes últimos 12 meses (pico vs valle)."""
    hoy = timezone.localdate()
    inicio = hoy.replace(day=1) - timedelta(days=365)
    ventas = list(
        _ventas_red(inicio, hoy)
        .select_related('proveedor')
    )

    por_mes = defaultdict(lambda: {'mxn': Decimal('0'), 'count': 0})
    for v in ventas:
        fc = v.fecha_creacion.date() if hasattr(v.fecha_creacion, 'date') else v.fecha_creacion
        key = (fc.year, fc.month)
        por_mes[key]['mxn'] += _venta_mxn(v)
        por_mes[key]['count'] += 1

    meses_orden = []
    d = inicio.replace(day=1)
    while d <= hoy:
        key = (d.year, d.month)
        data = por_mes.get(key, {'mxn': Decimal('0'), 'count': 0})
        meses_orden.append({
            'anio': d.year,
            'mes': d.month,
            'label': d.strftime('%b %y'),
            'mxn': data['mxn'],
            'count': data['count'],
        })
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1)
        else:
            d = d.replace(month=d.month + 1)

    max_mxn = Decimal('1')
    if meses_orden:
        max_mxn = max((m['mxn'] for m in meses_orden), default=Decimal('1'))
        if max_mxn <= 0:
            max_mxn = Decimal('1')
        min_mxn = min((m['mxn'] for m in meses_orden), default=Decimal('0'))
        for m in meses_orden:
            m['es_pico'] = m['mxn'] == max_mxn and max_mxn > 0
            m['es_valle'] = m['mxn'] == min_mxn and len(meses_orden) > 1
            m['altura_pct'] = int(float(m['mxn'] / max_mxn * 60)) if max_mxn > 0 else 0

    return meses_orden[-12:], max_mxn


def elasticidad_precios():
    """Ticket promedio histórico (12 meses) vs ticket mes actual."""
    hoy = timezone.localdate()
    mes_actual_inicio = hoy.replace(day=1)
    historico_inicio = mes_actual_inicio - timedelta(days=365)

    ventas_historico = list(_ventas_red(historico_inicio, hoy).select_related('proveedor'))
    ventas_mes = list(_ventas_red(mes_actual_inicio, hoy).select_related('proveedor'))

    total_h = sum(_venta_mxn(v) for v in ventas_historico)
    count_h = len(ventas_historico)
    ticket_historico = (total_h / count_h).quantize(Decimal('0.01')) if count_h else Decimal('0')

    total_m = sum(_venta_mxn(v) for v in ventas_mes)
    count_m = len(ventas_mes)
    ticket_actual = (total_m / count_m).quantize(Decimal('0.01')) if count_m else Decimal('0')

    variacion = Decimal('0')
    if ticket_historico > 0:
        variacion = ((ticket_actual - ticket_historico) / ticket_historico * 100).quantize(Decimal('0.1'))

    return {
        'ticket_historico': ticket_historico,
        'ticket_actual': ticket_actual,
        'variacion_pct': variacion,
        'count_historico': count_h,
        'count_actual': count_m,
    }
