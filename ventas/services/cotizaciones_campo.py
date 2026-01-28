"""
Servicio para calcular ajustes de cotización para Asesores de Campo.

Implementa la lógica de ajustes según la forma de pago y tipo de servicio
para cotizaciones creadas por asesores de campo.
"""
import logging
from decimal import Decimal
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


# Tabla de ajustes para asesores de campo (Transferencia o Efectivo)
AJUSTES_CAMPO = {
    'PAQ': {  # Paquete
        'tipo': 'porcentaje',
        'valor': Decimal('0.03'),  # 3%
    },
    'HOS': {  # Hotel/Hospedaje
        'tipo': 'porcentaje',
        'valor': Decimal('0.04'),  # 4%
    },
    'VUE': {  # Vuelo
        'tipo': 'fijo',
        'valor': Decimal('100.00'),  # $100.00 MXN
    },
    'CIR': {  # Circuito Internacional
        'tipo': 'fijo_usd',
        'valor': Decimal('35.00'),  # 35 USD (antes de impuestos)
    },
    'TOU': {  # Tours
        'tipo': 'porcentaje',
        'valor': Decimal('0.05'),  # 5%
    },
}


def es_asesor_campo(vendedor):
    """
    Verifica si el vendedor es un asesor de campo.
    
    Args:
        vendedor: User - Usuario vendedor
        
    Returns:
        bool: True si es asesor de campo, False en caso contrario
    """
    if not vendedor:
        return False
    
    try:
        perfil = vendedor.perfil
        return perfil.tipo_vendedor == 'CAMPO'
    except AttributeError:
        # Si no tiene perfil o no tiene tipo_vendedor, no es campo
        return False


def obtener_tipo_servicio_cotizacion(propuestas):
    """
    Determina el tipo de servicio principal de la cotización basándose en las propuestas.
    
    Args:
        propuestas: dict - Diccionario con las propuestas de la cotización
        
    Returns:
        str: Código del tipo de servicio ('PAQ', 'HOS', 'VUE', 'CIR', 'TOU', etc.)
    """
    if not isinstance(propuestas, dict):
        return None
    
    tipo = propuestas.get('tipo', '')
    
    # Mapeo de tipos de cotización a códigos de servicio
    tipo_mapping = {
        'paquete': 'PAQ',
        'hospedaje': 'HOS',
        'vuelos': 'VUE',
        'tours': 'TOU',
        'traslados': 'TRA',
        'renta_autos': 'REN',
    }
    
    codigo_servicio = tipo_mapping.get(tipo)
    
    # Caso especial: Circuitos Internacionales
    # Verificar si hay un campo explícito que indique que es circuito internacional
    if propuestas.get('es_circuito_internacional') or propuestas.get('circuito_internacional'):
        return 'CIR'
    
    # Si el tipo es 'paquete' o 'hospedaje', verificar si es circuito internacional
    if tipo == 'paquete':
        paquete = propuestas.get('paquete', {})
        if isinstance(paquete, dict):
            # Verificar campo explícito en el paquete
            if paquete.get('es_circuito_internacional') or paquete.get('circuito_internacional'):
                return 'CIR'
            
            # Buscar en descripciones si menciona "circuito internacional"
            vuelo = paquete.get('vuelo', {})
            hotel = paquete.get('hotel', {})
            tours = paquete.get('tours', [])
            
            # Verificar en descripciones
            descripciones = [
                str(vuelo.get('incluye', '')).lower(),
                str(vuelo.get('aerolinea', '')).lower(),
                str(hotel.get('nombre', '')).lower(),
                str(hotel.get('notas', '')).lower(),
                str(paquete.get('total', '')).lower(),
            ]
            
            # Agregar descripciones de tours
            if isinstance(tours, list):
                for tour in tours:
                    if isinstance(tour, dict):
                        descripciones.append(str(tour.get('nombre', '')).lower())
                        descripciones.append(str(tour.get('especificaciones', '')).lower())
            elif isinstance(tours, dict):
                descripciones.append(str(tours.get('nombre', '')).lower())
                descripciones.append(str(tours.get('especificaciones', '')).lower())
            
            # Si alguna descripción menciona "circuito internacional" o variaciones
            texto_completo = ' '.join(descripciones)
            keywords_circuito = ['circuito internacional', 'circuito int', 'circuito intl', 'circuito inter']
            if any(keyword in texto_completo for keyword in keywords_circuito):
                return 'CIR'
    
    elif tipo == 'hospedaje':
        # Para hospedaje, verificar si es circuito internacional
        hoteles = propuestas.get('hoteles', [])
        if hoteles and len(hoteles) > 0:
            hotel = hoteles[0] if isinstance(hoteles, list) else hoteles
            if isinstance(hotel, dict):
                # Verificar campo explícito
                if hotel.get('es_circuito_internacional') or hotel.get('circuito_internacional'):
                    return 'CIR'
                
                # Verificar en descripciones
                descripciones = [
                    str(hotel.get('nombre', '')).lower(),
                    str(hotel.get('notas', '')).lower(),
                    str(hotel.get('direccion', '')).lower(),
                ]
                texto_completo = ' '.join(descripciones)
                keywords_circuito = ['circuito internacional', 'circuito int', 'circuito intl', 'circuito inter']
                if any(keyword in texto_completo for keyword in keywords_circuito):
                    return 'CIR'
    
    return codigo_servicio


def calcular_ajuste_campo(total_base, tipo_servicio, forma_pago=None, tipo_cambio=None):
    """
    Calcula el ajuste a aplicar para una cotización de asesor de campo.
    
    IMPORTANTE: Los ajustes SIEMPRE se aplican para asesores de campo,
    independientemente de la forma de pago.
    
    Args:
        total_base: Decimal - Total base de la cotización (antes de ajustes)
        tipo_servicio: str - Código del tipo de servicio ('PAQ', 'HOS', 'VUE', 'CIR', 'TOU')
        forma_pago: str - Forma de pago (opcional, para referencia futura)
        tipo_cambio: Decimal - Tipo de cambio USD a MXN (necesario para ajustes en USD)
        
    Returns:
        dict: {
            'ajuste': Decimal - Monto del ajuste a aplicar,
            'total_final': Decimal - Total después del ajuste,
            'tipo_ajuste': str - 'porcentaje', 'fijo', o 'fijo_usd',
            'valor_ajuste': Decimal - Valor del ajuste aplicado
        }
    """
    if not tipo_servicio or tipo_servicio not in AJUSTES_CAMPO:
        return {
            'ajuste': Decimal('0.00'),
            'total_final': total_base,
            'tipo_ajuste': None,
            'valor_ajuste': Decimal('0.00')
        }
    
    config_ajuste = AJUSTES_CAMPO[tipo_servicio]
    tipo_ajuste = config_ajuste['tipo']
    valor_ajuste = config_ajuste['valor']
    
    ajuste = Decimal('0.00')
    
    if tipo_ajuste == 'porcentaje':
        # Aplicar porcentaje sobre el total base
        ajuste = total_base * valor_ajuste
    elif tipo_ajuste == 'fijo':
        # Monto fijo en MXN
        ajuste = valor_ajuste
    elif tipo_ajuste == 'fijo_usd':
        # Monto fijo en USD, convertir a MXN
        if tipo_cambio and tipo_cambio > 0:
            ajuste = valor_ajuste * tipo_cambio
        else:
            # Si no hay tipo de cambio, usar un valor por defecto o lanzar error
            logger.warning(f"No se proporcionó tipo de cambio para ajuste USD. Usando tipo de cambio por defecto.")
            # Usar tipo de cambio por defecto (ej: 20 MXN por USD)
            tipo_cambio_default = Decimal('20.00')
            ajuste = valor_ajuste * tipo_cambio_default
    
    total_final = total_base + ajuste
    
    return {
        'ajuste': ajuste,
        'total_final': total_final,
        'tipo_ajuste': tipo_ajuste,
        'valor_ajuste': valor_ajuste
    }


def aplicar_ajustes_cotizacion_campo(cotizacion, tipo_cambio=None):
    """
    Aplica los ajustes de asesor de campo a una cotización completa.
    
    Esta función procesa todas las propuestas de la cotización y aplica
    los ajustes correspondientes según el tipo de servicio.
    
    Args:
        cotizacion: Cotizacion - Instancia de la cotización
        tipo_cambio: Decimal - Tipo de cambio USD a MXN (opcional)
        
    Returns:
        dict: {
            'ajustes_aplicados': list - Lista de ajustes aplicados,
            'total_ajustes': Decimal - Suma total de ajustes,
            'total_final': Decimal - Total final después de ajustes
        }
    """
    if not es_asesor_campo(cotizacion.vendedor):
        return {
            'ajustes_aplicados': [],
            'total_ajustes': Decimal('0.00'),
            'total_final': cotizacion.total_estimado
        }
    
    propuestas = cotizacion.propuestas if isinstance(cotizacion.propuestas, dict) else {}
    tipo_servicio = obtener_tipo_servicio_cotizacion(propuestas)
    
    if not tipo_servicio:
        return {
            'ajustes_aplicados': [],
            'total_ajustes': Decimal('0.00'),
            'total_final': cotizacion.total_estimado
        }
    
    total_base = cotizacion.total_estimado or Decimal('0.00')
    forma_pago = None
    
    # Intentar obtener forma de pago de las propuestas
    tipo_cotizacion = propuestas.get('tipo', '')
    if tipo_cotizacion == 'paquete':
        paquete = propuestas.get('paquete', {})
        forma_pago = paquete.get('forma_pago')
    elif tipo_cotizacion == 'hospedaje':
        hoteles = propuestas.get('hoteles', [])
        if hoteles and len(hoteles) > 0:
            forma_pago = hoteles[0].get('forma_pago')
    elif tipo_cotizacion == 'vuelos':
        vuelos = propuestas.get('vuelos', [])
        if vuelos and len(vuelos) > 0:
            forma_pago = vuelos[0].get('forma_pago')
    elif tipo_cotizacion == 'tours':
        tours = propuestas.get('tours', [])
        if tours and len(tours) > 0:
            # Si es lista, tomar el primero
            tour = tours[0] if isinstance(tours, list) else tours
            if isinstance(tour, dict):
                forma_pago = tour.get('forma_pago')
    
    resultado = calcular_ajuste_campo(
        total_base=total_base,
        tipo_servicio=tipo_servicio,
        forma_pago=forma_pago,
        tipo_cambio=tipo_cambio
    )
    
    ajuste_info = {
        'tipo_servicio': tipo_servicio,
        'tipo_ajuste': resultado['tipo_ajuste'],
        'valor_ajuste': resultado['valor_ajuste'],
        'ajuste_aplicado': resultado['ajuste'],
        'total_base': total_base,
        'total_final': resultado['total_final']
    }
    
    return {
        'ajustes_aplicados': [ajuste_info],
        'total_ajustes': resultado['ajuste'],
        'total_final': resultado['total_final']
    }
