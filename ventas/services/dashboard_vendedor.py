"""
Servicio de KPIs y alertas para el Dashboard de Vendedores.
Todas las funciones reciben el usuario (vendedor) y retornan dicts listos para el contexto del template.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, Count, Q, F, ExpressionWrapper, DecimalField, Avg
from django.utils import timezone

from ventas.models import VentaViaje, Cotizacion, ComisionVenta, SolicitudCancelacion, AbonoPago, ComisionMensual


def _calcular_comision_por_tipo(total_ventas, tipo_vendedor):
    """
    Copia del cálculo legacy para evitar imports circulares.
    """
    if tipo_vendedor == 'CAMPO' or tipo_vendedor == 'CALLE':
        porcentaje = Decimal('0.04')
        return porcentaje, total_ventas * porcentaje

    if tipo_vendedor in ['MOSTRADOR', 'ISLA', 'OFICINA']:
        if total_ventas < Decimal('100000'):
            porcentaje = Decimal('0.01')
        elif total_ventas < Decimal('200000'):
            porcentaje = Decimal('0.02')
        elif total_ventas < Decimal('300000'):
            porcentaje = Decimal('0.03')
        elif total_ventas < Decimal('400000'):
            porcentaje = Decimal('0.04')
        else:
            porcentaje = Decimal('0.05')
        return porcentaje, total_ventas * porcentaje

    porcentaje = Decimal('0.04')
    return porcentaje, total_ventas * porcentaje


def _calcular_monto_base_comision_int(venta):
    # Import local para evitar problemas de import en arranque
    from ventas.services.comisiones import calcular_monto_base_comision
    monto_base_usd, _ = calcular_monto_base_comision(venta)
    return monto_base_usd

MARGEN_MINIMO = Decimal('0.15')
DIAS_RIESGO_COBRO = 7


def _fechas_periodo(periodo):
    """Devuelve (fecha_inicio, fecha_fin) según el periodo seleccionado."""
    hoy = timezone.localdate()
    if periodo == 'semanal':
        # Lunes a hoy (inicio de semana ISO: lunes = 0)
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        return inicio_semana, hoy
    if periodo == 'mes_anterior':
        primer_dia_mes_actual = hoy.replace(day=1)
        ultimo_dia_anterior = primer_dia_mes_actual - timedelta(days=1)
        primer_dia_anterior = ultimo_dia_anterior.replace(day=1)
        return primer_dia_anterior, ultimo_dia_anterior
    # mensual (mes actual)
    primer_dia = hoy.replace(day=1)
    return primer_dia, hoy


def _venta_mxn(venta):
    """Devuelve el monto de la venta en MXN (INT convertido con tipo_cambio)."""
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        total_usd = getattr(venta, 'costo_venta_final_usd', None) or getattr(venta, 'total_usd', None)
        tc = getattr(venta, 'tipo_cambio', None)
        if total_usd and tc and Decimal(str(tc)) > 0:
            return (Decimal(str(total_usd)) * Decimal(str(tc))).quantize(Decimal('0.01'))
        return Decimal('0.00')
    return venta.costo_venta_final or Decimal('0.00')


def _margen_venta(venta):
    """Devuelve el margen porcentual (0-1) de una venta. None si no se puede calcular."""
    if getattr(venta, 'tipo_viaje', 'NAC') == 'INT':
        costo_neto = getattr(venta, 'costo_neto_usd', None) or Decimal('0.00')
        total = getattr(venta, 'costo_venta_final_usd', None) or getattr(venta, 'total_usd', None) or Decimal('0.00')
    else:
        costo_neto = venta.costo_neto or Decimal('0.00')
        total = venta.costo_venta_final or Decimal('0.00')
    if total <= 0:
        return None
    return (total - costo_neto) / total


# --------------- FASE 1: Embudo y Ventas ---------------

def kpis_embudo(user, fecha_inicio, fecha_fin):
    """KPIs del embudo comercial para el vendedor en el periodo."""
    fecha_fin_dt = fecha_fin + timedelta(days=1)

    cotizaciones_periodo = Cotizacion.objects.filter(
        vendedor=user,
        creada_en__date__gte=fecha_inicio,
        creada_en__date__lte=fecha_fin,
    )
    cotizaciones_generadas = cotizaciones_periodo.count()

    cotizaciones_activas_periodo = cotizaciones_periodo.exclude(estado='CONVERTIDA').count()
    cotizaciones_activas_total = Cotizacion.objects.filter(
        vendedor=user,
    ).exclude(estado='CONVERTIDA').count()

    ventas_periodo = VentaViaje.objects.filter(
        vendedor=user,
        fecha_creacion__gte=fecha_inicio,
        fecha_creacion__lt=fecha_fin_dt,
    ).exclude(estado='CANCELADA')

    ventas_con_cotizacion = ventas_periodo.filter(cotizacion_origen__isnull=False).count()
    pct_conversion = Decimal('0.00')
    if cotizaciones_generadas > 0:
        pct_conversion = (Decimal(ventas_con_cotizacion) / Decimal(cotizaciones_generadas) * 100).quantize(Decimal('0.1'))

    # Tiempo promedio de cierre (días entre cotización y venta)
    ventas_con_cot = ventas_periodo.filter(
        cotizacion_origen__isnull=False,
    ).select_related('cotizacion_origen')
    dias_cierre = []
    for v in ventas_con_cot:
        if v.cotizacion_origen and v.cotizacion_origen.creada_en:
            delta = (v.fecha_creacion.date() if hasattr(v.fecha_creacion, 'date') else v.fecha_creacion) - v.cotizacion_origen.creada_en.date()
            dias_cierre.append(delta.days)
    tiempo_promedio_cierre = round(sum(dias_cierre) / len(dias_cierre), 1) if dias_cierre else 0

    # Ticket promedio
    total_mxn = Decimal('0.00')
    count_ventas = 0
    for v in ventas_periodo.select_related('proveedor'):
        total_mxn += _venta_mxn(v)
        count_ventas += 1
    ticket_promedio = (total_mxn / count_ventas).quantize(Decimal('0.01')) if count_ventas > 0 else Decimal('0.00')

    return {
        'cotizaciones_generadas': cotizaciones_generadas,
        'cotizaciones_activas_periodo': cotizaciones_activas_periodo,
        'cotizaciones_activas_total': cotizaciones_activas_total,
        'pct_conversion': pct_conversion,
        'tiempo_promedio_cierre': tiempo_promedio_cierre,
        'ticket_promedio': ticket_promedio,
    }


def kpis_ventas(user, fecha_inicio, fecha_fin):
    """KPIs de ventas cerradas y desglose por tipo."""
    fecha_fin_dt = fecha_fin + timedelta(days=1)

    ventas_periodo = VentaViaje.objects.filter(
        vendedor=user,
        fecha_creacion__gte=fecha_inicio,
        fecha_creacion__lt=fecha_fin_dt,
    ).exclude(estado='CANCELADA').select_related('proveedor').prefetch_related(
        'abonos',
    )

    total_mxn = Decimal('0.00')
    count_ventas = 0
    por_tipo = {'NAC': Decimal('0.00'), 'INT': Decimal('0.00'), 'INT_MXN': Decimal('0.00')}
    count_por_tipo = {'NAC': 0, 'INT': 0, 'INT_MXN': 0}

    for v in ventas_periodo:
        monto = _venta_mxn(v)
        total_mxn += monto
        count_ventas += 1
        tipo = v.tipo_viaje or 'NAC'
        if tipo in por_tipo:
            por_tipo[tipo] += monto
            count_por_tipo[tipo] += 1

    return {
        'ventas_cerradas_mxn': total_mxn,
        'ventas_cerradas_count': count_ventas,
        'por_tipo': por_tipo,
        'count_por_tipo': count_por_tipo,
    }


# --------------- FASE 2: Cobranza y Comisiones ---------------

def kpis_cobranza(user, fecha_inicio, fecha_fin):
    """KPIs de cobranza del vendedor."""
    fecha_fin_dt = fecha_fin + timedelta(days=1)
    hoy = timezone.localdate()

    ventas_periodo = list(
        VentaViaje.objects.filter(
            vendedor=user,
            fecha_creacion__gte=fecha_inicio,
            fecha_creacion__lt=fecha_fin_dt,
        ).exclude(estado='CANCELADA').prefetch_related(
            'abonos',
        )
    )

    total_ventas = len(ventas_periodo)
    cobradas = 0
    monto_pendiente = Decimal('0.00')
    anticipos = Decimal('0.00')
    clientes_riesgo = []

    for v in ventas_periodo:
        if v.total_pagado >= v.costo_total_con_modificacion:
            cobradas += 1
        else:
            monto_pendiente += v.saldo_restante
        anticipos += v.cantidad_apertura or Decimal('0.00')
        if v.tipo_viaje == 'INT':
            anticipos_usd = getattr(v, 'cantidad_apertura_usd', None)
            if anticipos_usd and v.tipo_cambio:
                anticipos += Decimal(str(anticipos_usd)) * Decimal(str(v.tipo_cambio)) - (v.cantidad_apertura or Decimal('0.00'))

    pct_cobradas = Decimal('0.00')
    if total_ventas > 0:
        pct_cobradas = (Decimal(cobradas) / Decimal(total_ventas) * 100).quantize(Decimal('0.1'))

    # Clientes en riesgo: ventas con fecha_vencimiento_pago dentro de los próximos 7 días o ya vencida, con saldo > 0
    limite_riesgo = hoy + timedelta(days=DIAS_RIESGO_COBRO)
    ventas_riesgo = VentaViaje.objects.filter(
        vendedor=user,
        fecha_vencimiento_pago__isnull=False,
        fecha_vencimiento_pago__lte=limite_riesgo,
    ).exclude(estado='CANCELADA').select_related('cliente').order_by('fecha_vencimiento_pago')

    for v in ventas_riesgo:
        if v.saldo_restante > 0:
            clientes_riesgo.append({
                'venta': v,
                'dias_para_vencer': (v.fecha_vencimiento_pago - hoy).days,
                'saldo': v.saldo_restante,
            })

    return {
        'pct_ventas_cobradas': pct_cobradas,
        'monto_pendiente_cobro': monto_pendiente,
        'anticipos_mxn': anticipos,
        'clientes_riesgo': clientes_riesgo,
        'clientes_riesgo_count': len(clientes_riesgo),
    }


def kpis_comisiones(user, mes, anio):
    """
    Comisiones del mes: total (100%), recibida y pendiente.

    Se calcula desde ventas del mes para que coincida con el detalle, sin depender de `ComisionVenta`.
    """
    res = comisiones_mes_desde_ventas(user, mes, anio)
    return {
        'comision_total': res['comision_total'],
        'comision_recibida': res['comision_recibida'],
        'comision_pendiente': res['comision_pendiente'],
        'ventas_int_count': res.get('ventas_int_count', 0),
        'total_ventas_periodo_usd': res.get('total_ventas_periodo_usd', Decimal('0.00')),
    }


def detalle_comisiones_mes(user, mes, anio, limit=200):
    """Listado por venta del mes (para modal en dashboard)."""
    return comisiones_mes_desde_ventas(user, mes, anio, limit=limit)['detalle']


def comisiones_mes_desde_ventas(user, mes, anio, limit=200):
    from datetime import datetime

    inicio = timezone.make_aware(datetime(anio, mes, 1, 0, 0, 0))
    if mes == 12:
        fin = timezone.make_aware(datetime(anio + 1, 1, 1, 0, 0, 0))
    else:
        fin = timezone.make_aware(datetime(anio, mes + 1, 1, 0, 0, 0))

    ventas_qs = (
        VentaViaje.objects.filter(
            vendedor=user,
            fecha_creacion__gte=inicio,
            fecha_creacion__lt=fin,
        )
        .exclude(estado='CANCELADA')
        .select_related('cliente')
        .prefetch_related(
            'abonos',
        )
        .order_by('-fecha_creacion')
    )

    ejecutivo = getattr(user, 'ejecutivo_asociado', None)
    tipo_vendedor = ejecutivo.tipo_vendedor if ejecutivo else 'MOSTRADOR'

    ventas_base = []
    total_ventas_periodo = Decimal('0.00')
    total_ventas_periodo_usd = Decimal('0.00')
    ventas_int_count = 0

    for venta in ventas_qs:
        es_int = getattr(venta, 'tipo_viaje', 'NAC') == 'INT'
        if es_int:
            # INT: sin conversiones; cálculo de comisión es manual
            monto_base_usd = _calcular_monto_base_comision_int(venta)
            tc = getattr(venta, 'tipo_cambio', None)
            base_comision = (monto_base_usd or Decimal('0.00')).quantize(Decimal('0.01'))
            costo_total = venta.costo_total_con_modificacion_usd or Decimal('0.00')
            total_pagado = venta.total_pagado_usd or Decimal('0.00')
        else:
            base_comision = venta.costo_venta_final or Decimal('0.00')
            costo_total = (venta.costo_venta_final or Decimal('0.00')) + (venta.costo_modificacion or Decimal('0.00'))

            total_abonos = Decimal('0.00')
            for ab in venta.abonos.all():
                if getattr(ab, 'confirmado', False) or getattr(ab, 'forma_pago', None) == 'EFE':
                    total_abonos += ab.monto or Decimal('0.00')
            total_pagado = total_abonos + (venta.cantidad_apertura or Decimal('0.00'))

        if base_comision <= 0:
            continue

        esta_pagada = (costo_total > 0 and total_pagado >= costo_total)

        if es_int:
            ventas_int_count += 1
            total_ventas_periodo_usd += base_comision
            ventas_base.append({
                'venta': venta,
                'base_comision': base_comision,
                'esta_pagada': esta_pagada,
                'es_comision_manual': True,
                'tipo_cambio': tc,
            })
        else:
            total_ventas_periodo += base_comision
            ventas_base.append({
                'venta': venta,
                'base_comision': base_comision,
                'esta_pagada': esta_pagada,
                'es_comision_manual': False,
                'tipo_cambio': None,
            })

    # Porcentaje
    if tipo_vendedor == 'ISLA':
        cm = ComisionMensual.objects.filter(vendedor=user, mes=mes, anio=anio, tipo_vendedor='ISLA').first()
        if cm and cm.porcentaje_ajustado_manual:
            porcentaje_a_usar = (cm.porcentaje_ajustado_manual / Decimal('100'))
        else:
            porcentaje_a_usar = Decimal('0.00')
    else:
        porcentaje_a_usar, _ = _calcular_comision_por_tipo(total_ventas_periodo, tipo_vendedor)

    detalle = []
    comision_recibida = Decimal('0.00')
    comision_pendiente = Decimal('0.00')
    comision_total = Decimal('0.00')

    for item in ventas_base[:limit]:
        base = item['base_comision']
        esta_pagada = item['esta_pagada']
        if item.get('es_comision_manual'):
            detalle.append({
                'venta': item['venta'],
                'estado_pago_venta': 'PAGADA' if esta_pagada else 'PENDIENTE',
                'moneda_base': 'USD',
                'tipo_cambio': item.get('tipo_cambio'),
                'base_comision': base,
                'es_comision_manual': True,
                'comision_total': None,
                'comision_pagada': None,
                'comision_pendiente': None,
            })
            continue

        com_total = (base * porcentaje_a_usar).quantize(Decimal('0.01'))
        if esta_pagada:
            com_pag = com_total
            com_pend = Decimal('0.00')
            estado = 'PAGADA'
        else:
            com_pag = (com_total * Decimal('0.30')).quantize(Decimal('0.01'))
            com_pend = (com_total * Decimal('0.70')).quantize(Decimal('0.01'))
            estado = 'PENDIENTE'

        comision_total += com_total
        comision_recibida += com_pag
        comision_pendiente += com_pend

        detalle.append({
            'venta': item['venta'],
            'estado_pago_venta': estado,
            'moneda_base': 'MXN',
            'tipo_cambio': None,
            'base_comision': base,
            'es_comision_manual': False,
            'comision_total': com_total,
            'comision_pagada': com_pag,
            'comision_pendiente': com_pend,
        })

    return {
        'comision_total': comision_total,
        'comision_recibida': comision_recibida,
        'comision_pendiente': comision_pendiente,
        'detalle': detalle,
        'ventas_int_count': ventas_int_count,
        'total_ventas_periodo_usd': total_ventas_periodo_usd,
    }


# --------------- FASE 3: Kilómetros Movums ---------------

def kpis_kilometros(user, fecha_inicio, fecha_fin):
    """KPIs de fidelidad para el vendedor."""
    from crm.models import Cliente, HistorialKilometros

    # Clientes activos en fidelidad: participan en km y tienen al menos una venta con este vendedor
    clientes_ids = VentaViaje.objects.filter(
        vendedor=user,
    ).values_list('cliente_id', flat=True).distinct()

    clientes_activos = Cliente.objects.filter(
        pk__in=clientes_ids,
        participa_kilometros=True,
    ).count()

    # Kilómetros otorgados por compras en ventas del vendedor (en el periodo)
    fecha_fin_dt = fecha_fin + timedelta(days=1)
    km_otorgados = HistorialKilometros.objects.filter(
        venta__vendedor=user,
        tipo_evento='COMPRA',
        es_redencion=False,
        fecha_registro__date__gte=fecha_inicio,
        fecha_registro__date__lte=fecha_fin,
    ).aggregate(total=Sum('kilometros'))['total'] or Decimal('0.00')

    # Recompras: clientes con 2+ ventas del vendedor (cualquier compra)
    recompras = VentaViaje.objects.filter(
        vendedor=user,
    ).exclude(estado='CANCELADA').values('cliente_id').annotate(
        num_ventas=Count('id'),
    ).filter(num_ventas__gte=2).count()

    return {
        'clientes_activos_fidelidad': clientes_activos,
        'kilometros_otorgados': km_otorgados,
        'recompras_generadas': recompras,
    }


# --------------- FASE 4: Alertas automáticas ---------------

def alertas_vendedor(user):
    """Cuatro tipos de alertas para el vendedor."""
    hoy = timezone.localdate()
    ahora = timezone.now()

    # 1. Cotizaciones sin seguimiento > 48 horas
    limite_48h = ahora - timedelta(hours=48)
    cotizaciones_sin_seguimiento = list(
        Cotizacion.objects.filter(
            vendedor=user,
            actualizada_en__lt=limite_48h,
        ).exclude(
            estado='CONVERTIDA',
        ).select_related('cliente').order_by('actualizada_en')[:20]
    )

    # 2. Clientes con pago vencido o por vencer en 7 días
    limite_riesgo = hoy + timedelta(days=DIAS_RIESGO_COBRO)
    ventas_pago_vencido_qs = VentaViaje.objects.filter(
        vendedor=user,
        fecha_vencimiento_pago__isnull=False,
        fecha_vencimiento_pago__lte=limite_riesgo,
    ).exclude(estado='CANCELADA').select_related('cliente').order_by('fecha_vencimiento_pago')
    ventas_pago_vencido = [v for v in ventas_pago_vencido_qs if v.saldo_restante > 0]

    # 3. Ventas con margen < 15%
    ventas_margen_bajo = []
    mis_ventas = VentaViaje.objects.filter(
        vendedor=user,
    ).exclude(estado='CANCELADA').select_related('cliente')
    for v in mis_ventas:
        margen = _margen_venta(v)
        if margen is not None and margen < MARGEN_MINIMO:
            ventas_margen_bajo.append({
                'venta': v,
                'margen_pct': (margen * 100).quantize(Decimal('0.1')),
            })
    ventas_margen_bajo = ventas_margen_bajo[:20]

    # 4. Cancelaciones solicitadas (pendientes)
    solicitudes_cancelacion = list(
        SolicitudCancelacion.objects.filter(
            venta__vendedor=user,
            estado='PENDIENTE',
        ).select_related('venta', 'venta__cliente').order_by('-fecha_solicitud')[:10]
    )

    return {
        'cotizaciones_sin_seguimiento': cotizaciones_sin_seguimiento,
        'cotizaciones_sin_seguimiento_count': len(cotizaciones_sin_seguimiento),
        'ventas_pago_vencido': ventas_pago_vencido,
        'ventas_pago_vencido_count': len(ventas_pago_vencido),
        'ventas_margen_bajo': ventas_margen_bajo,
        'ventas_margen_bajo_count': len(ventas_margen_bajo),
        'solicitudes_cancelacion': solicitudes_cancelacion,
        'solicitudes_cancelacion_count': len(solicitudes_cancelacion),
    }


# --------------- FASE 5: Competencia interna ---------------

def competencia_interna(user, mes, anio):
    """Top 3 vendedores del mes y posición del usuario. Scope por oficina del vendedor."""
    from usuarios.models import Perfil
    fecha_inicio = date(anio, mes, 1)
    if mes == 12:
        fecha_fin = date(anio + 1, 1, 1)
    else:
        fecha_fin = date(anio, mes + 1, 1)

    # Determinar oficina del vendedor
    ejecutivo = getattr(user, 'ejecutivo_asociado', None)
    oficina_id = getattr(ejecutivo, 'oficina_id', None) if ejecutivo else None

    # Base: vendedores con rol VENDEDOR
    vendedores_qs = Perfil.objects.filter(rol='VENDEDOR').select_related('user')
    if oficina_id:
        from ventas.models import Ejecutivo as EjecutivoModel
        vendedores_ids = EjecutivoModel.objects.filter(oficina_id=oficina_id).values_list('usuario_id', flat=True)
        vendedores_qs = vendedores_qs.filter(user_id__in=vendedores_ids)

    vendedores = [p.user for p in vendedores_qs]

    # Calcular por vendedor
    ranking_ventas = []
    ranking_conversion = []
    ranking_margen = []
    ranking_recompras = []

    for vendedor in vendedores:
        ventas_mes = VentaViaje.objects.filter(
            vendedor=vendedor,
            fecha_creacion__gte=fecha_inicio,
            fecha_creacion__lt=fecha_fin,
        ).exclude(estado='CANCELADA')

        total_mxn = Decimal('0.00')
        margenes = []
        for v in ventas_mes:
            total_mxn += _venta_mxn(v)
            m = _margen_venta(v)
            if m is not None:
                margenes.append(m)

        # Conversión
        cots_generadas = Cotizacion.objects.filter(
            vendedor=vendedor,
            creada_en__date__gte=fecha_inicio,
            creada_en__date__lt=fecha_fin,
        ).count()
        ventas_con_cot = ventas_mes.filter(cotizacion_origen__isnull=False).count()
        pct_conv = (Decimal(ventas_con_cot) / Decimal(cots_generadas) * 100).quantize(Decimal('0.1')) if cots_generadas > 0 else Decimal('0.00')

        margen_prom = (sum(margenes) / len(margenes) * 100).quantize(Decimal('0.1')) if margenes else Decimal('0.00')

        recompras = VentaViaje.objects.filter(
            vendedor=vendedor,
        ).exclude(estado='CANCELADA').values('cliente_id').annotate(
            num=Count('id'),
        ).filter(num__gte=2).count()

        nombre = vendedor.get_full_name() or vendedor.username

        ranking_ventas.append({'nombre': nombre, 'user_id': vendedor.pk, 'valor': total_mxn})
        ranking_conversion.append({'nombre': nombre, 'user_id': vendedor.pk, 'valor': pct_conv})
        ranking_margen.append({'nombre': nombre, 'user_id': vendedor.pk, 'valor': margen_prom})
        ranking_recompras.append({'nombre': nombre, 'user_id': vendedor.pk, 'valor': recompras})

    def _top3_y_posicion(ranking, user_id, reverse=True):
        ranking.sort(key=lambda x: x['valor'], reverse=reverse)
        posicion = next((i + 1 for i, r in enumerate(ranking) if r['user_id'] == user_id), None)
        return ranking[:3], posicion

    top3_ventas, pos_ventas = _top3_y_posicion(ranking_ventas, user.pk)
    top3_conversion, pos_conversion = _top3_y_posicion(ranking_conversion, user.pk)
    top3_margen, pos_margen = _top3_y_posicion(ranking_margen, user.pk)
    top3_recompras, pos_recompras = _top3_y_posicion(ranking_recompras, user.pk)

    return {
        'top3_ventas': top3_ventas,
        'mi_posicion_ventas': pos_ventas,
        'top3_conversion': top3_conversion,
        'mi_posicion_conversion': pos_conversion,
        'top3_margen': top3_margen,
        'mi_posicion_margen': pos_margen,
        'top3_recompras': top3_recompras,
        'mi_posicion_recompras': pos_recompras,
    }
