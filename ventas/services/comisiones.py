"""
Servicios para el cálculo de comisiones de vendedores.
Implementa la lógica de cálculo de comisiones para Asesores de Mostrador.
"""
import logging
from decimal import Decimal
from datetime import datetime, date
from django.db.models import Sum, Q
from django.utils import timezone
from django.contrib.auth.models import User

from ventas.models import VentaViaje, ComisionVenta, ComisionMensual
from usuarios.models import Perfil

logger = logging.getLogger(__name__)


def obtener_porcentaje_comision_mostrador(total_ventas_mes):
    """
    Determina el porcentaje de comisión según el total de ventas mensuales.
    
    Escalas:
    - $1 - $99,999: 1%
    - $100,000 - $199,999: 2%
    - $200,000 - $299,999: 3%
    - $300,000 - $399,999: 4%
    - $400,000 en adelante: 5%
    
    Args:
        total_ventas_mes: Decimal - Total de ventas del mes
        
    Returns:
        Decimal: Porcentaje de comisión (ej: 0.01 para 1%)
    """
    total = Decimal(str(total_ventas_mes))
    
    if total < Decimal('100000'):
        return Decimal('0.01')  # 1%
    elif total < Decimal('200000'):
        return Decimal('0.02')  # 2%
    elif total < Decimal('300000'):
        return Decimal('0.03')  # 3%
    elif total < Decimal('400000'):
        return Decimal('0.04')  # 4%
    else:
        return Decimal('0.05')  # 5%


def calcular_bono_extra_mostrador(total_ventas_mes):
    """
    Calcula el bono extra del 1% si el total de ventas supera $500,000.
    
    Args:
        total_ventas_mes: Decimal - Total de ventas del mes
        
    Returns:
        Decimal: Bono extra (1% del total si supera $500,000, 0 en caso contrario)
    """
    total = Decimal(str(total_ventas_mes))
    
    if total >= Decimal('500000'):
        return total * Decimal('0.01')  # 1% del total
    return Decimal('0.00')


def es_vuelo_solitario(venta):
    """
    Determina si una venta es un vuelo solitario (solo VUE, sin otros servicios).
    
    Args:
        venta: VentaViaje
        
    Returns:
        bool: True si es vuelo solitario, False en caso contrario
    """
    if not venta.servicios_seleccionados:
        return False
    
    servicios = [s.strip() for s in venta.servicios_seleccionados.split(',')]
    # Es vuelo solitario si solo tiene VUE y ningún otro servicio
    return len(servicios) == 1 and servicios[0] == 'VUE'


def calcular_monto_base_comision(venta):
    """
    Calcula el monto base sobre el que se calculará la comisión.
    
    Reglas:
    - Vuelos solitarios: $100 fijos (no se usa monto base, se maneja aparte)
    - Ventas internacionales: tarifa_base + suplementos + tours (excluye impuestos)
    - Ventas nacionales: costo_venta_final
    
    Args:
        venta: VentaViaje
        
    Returns:
        tuple: (monto_base, detalles_dict)
            monto_base: Decimal - Monto base para comisión
            detalles_dict: dict - Desglose detallado
    """
    detalles = {
        'tipo_venta': venta.tipo_viaje,
        'costo_venta_final': float(venta.costo_venta_final),
    }
    
    # Vuelo solitario: $100 fijos (no se calcula sobre monto)
    if es_vuelo_solitario(venta):
        detalles['tipo_calculo'] = 'VUELO_SOLITARIO'
        detalles['monto_vuelo'] = 100.00
        return Decimal('100.00'), detalles
    
    # Venta internacional: desglose
    if venta.tipo_viaje == 'INT':
        detalles['tipo_calculo'] = 'INTERNACIONAL_DESGLOSADO'
        
        # Convertir USD a MXN usando tipo_cambio
        tipo_cambio = venta.tipo_cambio if venta.tipo_cambio and venta.tipo_cambio > 0 else Decimal('1.0')
        
        tarifa_base_mxn = (venta.tarifa_base_usd or Decimal('0.00')) * tipo_cambio
        suplementos_mxn = (venta.suplementos_usd or Decimal('0.00')) * tipo_cambio
        tours_mxn = (venta.tours_usd or Decimal('0.00')) * tipo_cambio
        impuestos_mxn = (venta.impuestos_usd or Decimal('0.00')) * tipo_cambio
        
        detalles['tarifa_base_usd'] = float(venta.tarifa_base_usd or Decimal('0.00'))
        detalles['suplementos_usd'] = float(venta.suplementos_usd or Decimal('0.00'))
        detalles['tours_usd'] = float(venta.tours_usd or Decimal('0.00'))
        detalles['impuestos_usd'] = float(venta.impuestos_usd or Decimal('0.00'))
        detalles['tipo_cambio'] = float(tipo_cambio)
        
        detalles['tarifa_base_mxn'] = float(tarifa_base_mxn)
        detalles['suplementos_mxn'] = float(suplementos_mxn)
        detalles['tours_mxn'] = float(tours_mxn)
        detalles['impuestos_mxn'] = float(impuestos_mxn)
        detalles['impuestos_excluidos'] = True
        
        # Monto base = tarifa_base + suplementos + tours (excluye impuestos)
        monto_base = tarifa_base_mxn + suplementos_mxn + tours_mxn
        detalles['monto_base_calculado'] = float(monto_base)
        
        return monto_base, detalles
    
    # Venta nacional: costo_venta_final
    detalles['tipo_calculo'] = 'NACIONAL'
    detalles['monto_base_calculado'] = float(venta.costo_venta_final)
    return venta.costo_venta_final, detalles


def calcular_comision_venta_mostrador(venta, porcentaje_comision, mes, anio):
    """
    Calcula la comisión de una venta individual para Asesor de Mostrador.
    
    Args:
        venta: VentaViaje
        porcentaje_comision: Decimal - Porcentaje a aplicar según total mensual
        mes: int - Mes del cálculo
        anio: int - Año del cálculo
        
    Returns:
        ComisionVenta: Objeto creado o actualizado
    """
    # Determinar tipo de venta
    if es_vuelo_solitario(venta):
        tipo_venta = 'VUELO'
        # Vuelos solitarios: $100 fijos
        monto_base = Decimal('100.00')
        comision_calculada = Decimal('100.00')
        porcentaje_aplicado = Decimal('0.00')  # No aplica porcentaje
        detalles = {
            'tipo_calculo': 'VUELO_SOLITARIO',
            'comision_fija': 100.00,
        }
    else:
        if venta.tipo_viaje == 'INT':
            tipo_venta = 'INTERNACIONAL'
        else:
            tipo_venta = 'NACIONAL'
        
        # Calcular monto base
        monto_base, detalles = calcular_monto_base_comision(venta)
        
        # Calcular comisión
        if tipo_venta == 'INTERNACIONAL':
            # Para internacionales, aplicar porcentaje sobre el monto base (sin impuestos)
            comision_calculada = monto_base * porcentaje_comision
            porcentaje_aplicado = porcentaje_comision * Decimal('100')  # Convertir a porcentaje
        else:
            # Para nacionales, aplicar porcentaje sobre costo_venta_final
            comision_calculada = monto_base * porcentaje_comision
            porcentaje_aplicado = porcentaje_comision * Decimal('100')
        
        detalles['porcentaje_aplicado'] = float(porcentaje_aplicado)
        detalles['comision_calculada'] = float(comision_calculada)
    
    # Determinar estado de pago
    total_pagado = venta.total_pagado
    costo_total = venta.costo_total_con_modificacion
    
    if total_pagado >= costo_total:
        estado_pago = 'PAGADA'
        comision_pagada = comision_calculada  # 100% de la comisión
        comision_pendiente = Decimal('0.00')
    else:
        estado_pago = 'PENDIENTE'
        comision_pagada = comision_calculada * Decimal('0.30')  # 30% de la comisión
        comision_pendiente = comision_calculada * Decimal('0.70')  # 70% pendiente
    
    detalles['estado_pago'] = estado_pago
    detalles['total_pagado'] = float(total_pagado)
    detalles['costo_total'] = float(costo_total)
    detalles['porcentaje_pagado'] = float((total_pagado / costo_total * 100) if costo_total > 0 else 0)
    
    # Crear o actualizar ComisionVenta
    comision_venta, created = ComisionVenta.objects.update_or_create(
        venta=venta,
        mes=mes,
        anio=anio,
        defaults={
            'vendedor': venta.vendedor,
            'tipo_venta': tipo_venta,
            'monto_base_comision': monto_base,
            'porcentaje_aplicado': porcentaje_aplicado,
            'comision_calculada': comision_calculada,
            'comision_pagada': comision_pagada,
            'comision_pendiente': comision_pendiente,
            'estado_pago_venta': estado_pago,
            'detalles': detalles,
        }
    )
    
    return comision_venta


def calcular_comisiones_mensuales_mostrador(vendedor, mes, anio):
    """
    Calcula las comisiones mensuales para un Asesor de Mostrador.
    
    Args:
        vendedor: User - Vendedor
        mes: int - Mes (1-12)
        anio: int - Año
        
    Returns:
        ComisionMensual: Objeto creado o actualizado
    """
    # Obtener todas las ventas del mes del vendedor
    fecha_inicio = date(anio, mes, 1)
    if mes == 12:
        fecha_fin = date(anio + 1, 1, 1)
    else:
        fecha_fin = date(anio, mes + 1, 1)
    
    ventas_mes = VentaViaje.objects.filter(
        vendedor=vendedor,
        fecha_creacion__gte=fecha_inicio,
        fecha_creacion__lt=fecha_fin
    )
    
    # Calcular total de ventas del mes (para determinar porcentaje)
    total_ventas_mes = sum(venta.costo_venta_final for venta in ventas_mes) or Decimal('0.00')
    
    # Determinar porcentaje según escala
    porcentaje_comision = obtener_porcentaje_comision_mostrador(total_ventas_mes)
    
    # Calcular bono extra si supera $500,000
    bono_extra = calcular_bono_extra_mostrador(total_ventas_mes)
    
    # Calcular comisión por cada venta
    comisiones_ventas = []
    comision_total_pagada = Decimal('0.00')
    comision_total_pendiente = Decimal('0.00')
    
    for venta in ventas_mes:
        comision_venta = calcular_comision_venta_mostrador(venta, porcentaje_comision, mes, anio)
        comisiones_ventas.append(comision_venta)
        
        comision_total_pagada += comision_venta.comision_pagada
        comision_total_pendiente += comision_venta.comision_pendiente
    
    # Total de comisión = pagada + pendiente + bono
    comision_total = comision_total_pagada + comision_total_pendiente + bono_extra
    
    # Crear o actualizar ComisionMensual
    comision_mensual, created = ComisionMensual.objects.update_or_create(
        vendedor=vendedor,
        mes=mes,
        anio=anio,
        tipo_vendedor='MOSTRADOR',
        defaults={
            'total_ventas_mes': total_ventas_mes,
            'porcentaje_comision': porcentaje_comision * Decimal('100'),  # Convertir a porcentaje
            'bono_extra': bono_extra,
            'comision_total_pagada': comision_total_pagada,
            'comision_total_pendiente': comision_total_pendiente,
            'comision_total': comision_total,
        }
    )
    
    return comision_mensual


def recalcular_comision_venta_si_pagada(venta):
    """
    Recalcula la comisión de una venta si cambió su estado de pago.
    Se llama cuando una venta se marca como pagada completamente.
    
    Args:
        venta: VentaViaje
    """
    # Obtener todas las comisiones de esta venta
    comisiones = ComisionVenta.objects.filter(venta=venta)
    
    for comision in comisiones:
        # Verificar si la venta está pagada
        total_pagado = venta.total_pagado
        costo_total = venta.costo_total_con_modificacion
        
        if total_pagado >= costo_total:
            # Actualizar a 100% de la comisión
            comision.estado_pago_venta = 'PAGADA'
            comision.comision_pagada = comision.comision_calculada
            comision.comision_pendiente = Decimal('0.00')
            comision.save()
            
            # Actualizar el resumen mensual
            actualizar_comision_mensual(comision.vendedor, comision.mes, comision.anio)


def actualizar_comision_mensual(vendedor, mes, anio):
    """
    Actualiza el resumen mensual de comisiones después de recalcular una venta.
    
    Args:
        vendedor: User
        mes: int
        anio: int
    """
    comision_mensual = ComisionMensual.objects.filter(
        vendedor=vendedor,
        mes=mes,
        anio=anio,
        tipo_vendedor='MOSTRADOR'
    ).first()
    
    if not comision_mensual:
        return
    
    # Recalcular totales desde las comisiones de ventas
    comisiones_ventas = ComisionVenta.objects.filter(
        vendedor=vendedor,
        mes=mes,
        anio=anio
    )
    
    comision_total_pagada = sum(c.comision_pagada for c in comisiones_ventas) or Decimal('0.00')
    comision_total_pendiente = sum(c.comision_pendiente for c in comisiones_ventas) or Decimal('0.00')
    
    # Mantener el bono extra
    bono_extra = comision_mensual.bono_extra
    
    # Actualizar totales
    comision_mensual.comision_total_pagada = comision_total_pagada
    comision_mensual.comision_total_pendiente = comision_total_pendiente
    comision_mensual.comision_total = comision_total_pagada + comision_total_pendiente + bono_extra
    comision_mensual.save()
