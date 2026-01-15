from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
import logging

from .models import Cliente, HistorialKilometros

logger = logging.getLogger(__name__)


class KilometrosService:
    """Utilidad centralizada para el programa de fidelidad Kilómetros Movums."""

    KM_POR_PESO = Decimal('0.5')
    VALOR_PESO_POR_KM = Decimal('0.05')
    MAX_PORCENTAJE_REDENCION = Decimal('0.10')
    VIGENCIA_DIAS = 730  # 24 meses aproximados

    BONO_REFERIDO = Decimal('2000')
    BONO_CUMPLE = Decimal('1000')

    @classmethod
    def _to_decimal(cls, value) -> Decimal:
        if value is None:
            return Decimal('0.00')
        return value if isinstance(value, Decimal) else Decimal(str(value))

    @classmethod
    def _vigencia(cls):
        return timezone.now() + timedelta(days=cls.VIGENCIA_DIAS)

    @classmethod
    def _crear_historial(cls, cliente, tipo, kilometros, descripcion='', venta=None,
                         multiplicador=Decimal('1.00'), es_redencion=False):
        kilometros = cls._to_decimal(kilometros)
        if kilometros == 0:
            return None
        valor_equivalente = kilometros * cls.VALOR_PESO_POR_KM
        return HistorialKilometros.objects.create(
            cliente=cliente,
            tipo_evento=tipo,
            descripcion=descripcion or '',
            kilometros=kilometros,
            multiplicador=multiplicador,
            valor_equivalente=valor_equivalente,
            fecha_expiracion=None if es_redencion else cls._vigencia(),
            venta=venta,
            es_redencion=es_redencion,
            expirado=False,
        )

    # ------------------ Acumulación ------------------
    @classmethod
    def acumular_por_compra(cls, cliente: Cliente, monto, venta=None, multiplicador=Decimal('1.0')):
        if not cliente or not cliente.participa_kilometros:
            return None
        monto = cls._to_decimal(monto)
        if monto <= 0:
            return None
        km = monto * cls.KM_POR_PESO * cls._to_decimal(multiplicador)

        with transaction.atomic():
            registro = cls._crear_historial(
                cliente,
                'COMPRA',
                km,
                descripcion="Kilómetros generados por compra",
                venta=venta,
                multiplicador=multiplicador
            )
            cliente.kilometros_acumulados += km
            cliente.kilometros_disponibles += km
            cliente.ultima_fecha_km = timezone.now()
            cliente.save(update_fields=['kilometros_acumulados', 'kilometros_disponibles', 'ultima_fecha_km'])
        return registro

    @classmethod
    def otorgar_referido(cls, cliente: Cliente, descripcion="Bono por cliente referido"):
        if not cliente or not cliente.participa_kilometros:
            return None
        return cls._bono_simple(cliente, cls.BONO_REFERIDO, 'REFERIDO', descripcion)

    @classmethod
    def otorgar_cumple(cls, cliente: Cliente):
        if not cliente or not cliente.participa_kilometros:
            return None
        today = timezone.localdate()
        if cliente.fecha_ultimo_bono_cumple and cliente.fecha_ultimo_bono_cumple.year == today.year:
            return None
        registro = cls._bono_simple(cliente, cls.BONO_CUMPLE, 'CUMPLE', "Bono de cumpleaños")
        if registro:
            cliente.fecha_ultimo_bono_cumple = today
            cliente.save(update_fields=['fecha_ultimo_bono_cumple'])
        return registro

    @classmethod
    def _bono_simple(cls, cliente, kilometros, tipo, descripcion):
        kilometros = cls._to_decimal(kilometros)
        if kilometros <= 0:
            return None
        with transaction.atomic():
            registro = cls._crear_historial(
                cliente,
                tipo,
                kilometros,
                descripcion=descripcion
            )
            cliente.kilometros_acumulados += kilometros
            cliente.kilometros_disponibles += kilometros
            cliente.ultima_fecha_km = timezone.now()
            cliente.save(update_fields=['kilometros_acumulados', 'kilometros_disponibles', 'ultima_fecha_km'])
        return registro

    # ------------------ Redención ------------------
    @classmethod
    def limite_redencion_por_venta(cls, venta_total):
        venta_total = cls._to_decimal(venta_total)
        if venta_total <= 0:
            return Decimal('0.00'), Decimal('0.00')
        max_valor = venta_total * cls.MAX_PORCENTAJE_REDENCION
        max_km = max_valor / cls.VALOR_PESO_POR_KM
        # Usar ROUND_HALF_UP: del 1-4 baja, del 5-9 sube (redondeo estándar)
        return max_km.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), max_valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @classmethod
    def redimir(cls, cliente: Cliente, kilometros, venta=None, descripcion="Redención aplicada a servicio"):
        if not cliente or kilometros <= 0:
            return None
        kilometros = cls._to_decimal(kilometros)
        if kilometros > cliente.kilometros_disponibles:
            kilometros = cliente.kilometros_disponibles
        if kilometros <= 0:
            return None
        with transaction.atomic():
            registro = cls._crear_historial(
                cliente,
                'REDENCION',
                kilometros * -1,
                descripcion=descripcion,
                venta=venta,
                es_redencion=True
            )
            cliente.kilometros_disponibles -= kilometros
            cliente.save(update_fields=['kilometros_disponibles'])
        return registro

    # ------------------ Reportes ------------------
    @classmethod
    def resumen_cliente(cls, cliente: Cliente):
        if not cliente:
            return None
        disponible = cliente.kilometros_disponibles or Decimal('0.00')
        valor = disponible * cls.VALOR_PESO_POR_KM
        historial_qs = cliente.historial_kilometros.all().order_by('-fecha_registro')
        historial_reciente = list(historial_qs[:10])
        proximo_a_vencer = cliente.historial_kilometros.filter(
            fecha_expiracion__isnull=False,
            fecha_expiracion__gt=timezone.now()
        ).order_by('fecha_expiracion').first()
        return {
            'total_acumulado': cliente.kilometros_acumulados or Decimal('0.00'),
            'disponible': disponible,
            'valor_equivalente': valor,
            'participa': cliente.participa_kilometros,
            'ultima_fecha': cliente.ultima_fecha_km,
            'proximo_vencimiento': proximo_a_vencer.fecha_expiracion if proximo_a_vencer else None,
            'historial_reciente': historial_reciente,
        }

    # ------------------ Expiración ------------------
    @classmethod
    def expirar_kilometros(cls):
        """
        Procesa todos los movimientos con fecha de expiración vencida.
        """
        hoy = timezone.now()
        expirables = (
            HistorialKilometros.objects
            .select_related('cliente')
            .filter(
                fecha_expiracion__isnull=False,
                fecha_expiracion__lt=hoy,
                es_redencion=False,
                expirado=False,
                kilometros__gt=0
            )
        )

        procesados = 0
        for movimiento in expirables:
            km = movimiento.kilometros
            cliente = movimiento.cliente
            if not cliente:
                continue
            with transaction.atomic():
                cls._crear_historial(
                    cliente,
                    'EXPIRACION',
                    km * -1,
                    descripcion=f"Expiración automática de movimientos registrados el {movimiento.fecha_registro:%d/%m/%Y}.",
                    venta=movimiento.venta,
                    es_redencion=True
                )
                movimiento.expirado = True
                movimiento.save(update_fields=['expirado'])

                cliente.kilometros_disponibles = max(
                    Decimal('0.00'),
                    (cliente.kilometros_disponibles or Decimal('0.00')) - km
                )
                cliente.save(update_fields=['kilometros_disponibles'])
                procesados += 1

        return procesados

    # ------------------ Bonos de Promociones ------------------
    @classmethod
    def acumular_bono_promocion(cls, cliente: Cliente, kilometros, venta=None, promocion=None, descripcion=''):
        """
        Acumula kilómetros bonificados por una promoción tipo 'KM'.
        
        Args:
            cliente: Cliente que recibe el bono
            kilometros: Cantidad de kilómetros a bonificar
            venta: Venta asociada (opcional)
            promocion: Promoción que otorga el bono (opcional)
            descripcion: Descripción personalizada (opcional)
            
        Returns:
            HistorialKilometros: Registro creado o None si no se pudo crear
        """
        if not cliente or not cliente.participa_kilometros:
            return None
        kilometros = cls._to_decimal(kilometros)
        if kilometros <= 0:
            return None
        
        nombre_promocion = promocion.nombre if promocion else 'Promoción'
        descripcion_final = descripcion or f"Bono de promoción: {nombre_promocion}"
        if venta:
            descripcion_final += f" - Venta #{venta.pk}"
        
        with transaction.atomic():
            registro = cls._crear_historial(
                cliente,
                'BONO_PROMOCION',
                kilometros,
                descripcion=descripcion_final,
                venta=venta
            )
            cliente.kilometros_acumulados += kilometros
            cliente.kilometros_disponibles += kilometros
            cliente.ultima_fecha_km = timezone.now()
            cliente.save(update_fields=['kilometros_acumulados', 'kilometros_disponibles', 'ultima_fecha_km'])
        return registro
    
    @classmethod
    def revertir_bono_promocion(cls, cliente: Cliente, kilometros, venta=None, promocion=None, descripcion=''):
        """
        Revierte kilómetros bonificados por una promoción.
        
        Args:
            cliente: Cliente del cual revertir
            kilometros: Cantidad de kilómetros a revertir
            venta: Venta asociada (opcional)
            promocion: Promoción que otorgó el bono (opcional)
            descripcion: Descripción personalizada (opcional)
            
        Returns:
            HistorialKilometros: Registro de reversión creado o None
        """
        if not cliente or kilometros <= 0:
            return None
        kilometros = cls._to_decimal(kilometros)
        
        nombre_promocion = promocion.nombre if promocion else 'Promoción'
        descripcion_final = descripcion or f"Reversión de bono de promoción: {nombre_promocion}"
        if venta:
            descripcion_final += f" - Venta #{venta.pk}"
        
        with transaction.atomic():
            registro = cls._crear_historial(
                cliente,
                'AJUSTE',
                kilometros * -1,  # Negativo para restar
                descripcion=descripcion_final,
                venta=venta
            )
            cliente.kilometros_acumulados = max(
                Decimal('0.00'),
                (cliente.kilometros_acumulados or Decimal('0.00')) - kilometros
            )
            cliente.kilometros_disponibles = max(
                Decimal('0.00'),
                (cliente.kilometros_disponibles or Decimal('0.00')) - kilometros
            )
            cliente.ultima_fecha_km = timezone.now()
            cliente.save(update_fields=['kilometros_acumulados', 'kilometros_disponibles', 'ultima_fecha_km'])
        return registro

    # ------------------ Reversión por Cancelación ------------------
    @classmethod
    def revertir_por_cancelacion(cls, venta):
        """
        Revierte todos los kilómetros acumulados asociados a una venta cancelada.
        Incluye:
        - Kilómetros acumulados por compra (tipo_evento='COMPRA')
        - Bonos de kilómetros de promociones (tipo_evento='CAMPANIA')
        
        Args:
            venta: Instancia de VentaViaje que fue cancelada
            
        Returns:
            dict: Resumen de la reversión con totales revertidos
        """
        from crm.models import HistorialKilometros
        
        if not venta or not venta.cliente:
            return {'revertidos': 0, 'km_totales': Decimal('0.00')}
        
        cliente = venta.cliente
        if not cliente.participa_kilometros:
            return {'revertidos': 0, 'km_totales': Decimal('0.00')}
        
        # Buscar todos los movimientos de kilómetros asociados a esta venta
        # 1. Acumulaciones (compra, bonos de promociones, etc.)
        movimientos_acumulacion = HistorialKilometros.objects.filter(
            venta=venta,
            kilometros__gt=0,  # Solo acumulaciones positivas
            es_redencion=False,
            expirado=False
        )
        
        # 2. Redenciones (kilómetros redimidos que deben devolverse)
        movimientos_redencion = HistorialKilometros.objects.filter(
            venta=venta,
            kilometros__lt=0,  # Redenciones son negativas
            es_redencion=True,
            expirado=False
        )
        
        total_km_revertidos = Decimal('0.00')
        total_km_devueltos = Decimal('0.00')
        registros_revertidos = 0
        
        with transaction.atomic():
            # Revertir acumulaciones
            for movimiento in movimientos_acumulacion:
                km = movimiento.kilometros
                if km <= 0:
                    continue
                
                # Determinar tipo de reversión según el tipo de evento original
                if movimiento.tipo_evento == 'BONO_PROMOCION':
                    tipo_reversion = 'AJUSTE'  # Mantener AJUSTE para bonos de promociones
                else:
                    tipo_reversion = 'REVERSION_CANCELACION'
                
                descripcion = f"Reversión por cancelación de venta #{venta.pk}: {movimiento.descripcion or 'Kilómetros acumulados'}"
                
                cls._crear_historial(
                    cliente,
                    tipo_reversion,
                    km * -1,  # Negativo para restar
                    descripcion=descripcion,
                    venta=venta,
                    es_redencion=False
                )
                
                # Restar del cliente
                cliente.kilometros_acumulados = max(
                    Decimal('0.00'),
                    (cliente.kilometros_acumulados or Decimal('0.00')) - km
                )
                cliente.kilometros_disponibles = max(
                    Decimal('0.00'),
                    (cliente.kilometros_disponibles or Decimal('0.00')) - km
                )
                
                total_km_revertidos += km
                registros_revertidos += 1
            
            # Devolver redenciones (kilómetros redimidos)
            for movimiento in movimientos_redencion:
                km_redimidos = abs(movimiento.kilometros)  # Convertir a positivo
                if km_redimidos <= 0:
                    continue
                
                descripcion = f"Reversión de redención por cancelación de venta #{venta.pk}: {movimiento.descripcion or 'Kilómetros redimidos'}"
                
                cls._crear_historial(
                    cliente,
                    'REVERSION_REDENCION',
                    km_redimidos,  # Positivo para devolver
                    descripcion=descripcion,
                    venta=venta,
                    es_redencion=False
                )
                
                # Devolver kilómetros al cliente
                cliente.kilometros_disponibles += km_redimidos
                total_km_devueltos += km_redimidos
                registros_revertidos += 1
            
            # Guardar cambios del cliente
            if registros_revertidos > 0:
                cliente.ultima_fecha_km = timezone.now()
                cliente.save(update_fields=['kilometros_acumulados', 'kilometros_disponibles', 'ultima_fecha_km'])
        
        return {
            'revertidos': registros_revertidos,
            'km_totales': total_km_revertidos,
            'km_devueltos': total_km_devueltos
        }

    # ------------------ Validación y Corrección de Consistencia ------------------
    @classmethod
    def validar_consistencia_cliente(cls, cliente: Cliente):
        """
        Valida que los totales del cliente coincidan con el historial.
        
        Returns:
            dict: {
                'consistente': bool,
                'diferencias': {
                    'acumulados': Decimal,  # Diferencia en acumulados
                    'disponibles': Decimal,  # Diferencia en disponibles
                },
                'calculados': {
                    'acumulados': Decimal,  # Total calculado desde historial
                    'disponibles': Decimal,  # Total calculado desde historial
                },
                'actuales': {
                    'acumulados': Decimal,  # Valor actual en cliente
                    'disponibles': Decimal,  # Valor actual en cliente
                }
            }
        """
        if not cliente.participa_kilometros:
            return {
                'consistente': True,
                'diferencias': {'acumulados': Decimal('0.00'), 'disponibles': Decimal('0.00')},
                'calculados': {'acumulados': Decimal('0.00'), 'disponibles': Decimal('0.00')},
                'actuales': {'acumulados': Decimal('0.00'), 'disponibles': Decimal('0.00')}
            }
        
        # Calcular acumulados desde historial (todos los movimientos positivos)
        acumulados_calculados = HistorialKilometros.objects.filter(
            cliente=cliente,
            kilometros__gt=0
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00')
        
        # Calcular disponibles desde historial (todos los movimientos no expirados)
        # Disponibles = acumulaciones positivas - redenciones - expiraciones
        movimientos_positivos = HistorialKilometros.objects.filter(
            cliente=cliente,
            kilometros__gt=0,
            expirado=False
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00')
        
        movimientos_negativos = HistorialKilometros.objects.filter(
            cliente=cliente,
            kilometros__lt=0,
            expirado=False
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00')
        
        disponibles_calculados = movimientos_positivos + movimientos_negativos  # negativos ya son negativos
        
        # Valores actuales del cliente
        acumulados_actuales = cls._to_decimal(cliente.kilometros_acumulados)
        disponibles_actuales = cls._to_decimal(cliente.kilometros_disponibles)
        
        # Calcular diferencias
        diferencia_acumulados = acumulados_calculados - acumulados_actuales
        diferencia_disponibles = disponibles_calculados - disponibles_actuales
        
        # Tolerancia para comparaciones decimales (0.01 km)
        tolerancia = Decimal('0.01')
        consistente = (
            abs(diferencia_acumulados) <= tolerancia and
            abs(diferencia_disponibles) <= tolerancia
        )
        
        return {
            'consistente': consistente,
            'diferencias': {
                'acumulados': diferencia_acumulados,
                'disponibles': diferencia_disponibles,
            },
            'calculados': {
                'acumulados': acumulados_calculados,
                'disponibles': disponibles_calculados,
            },
            'actuales': {
                'acumulados': acumulados_actuales,
                'disponibles': disponibles_actuales,
            }
        }
    
    @classmethod
    def corregir_consistencia_cliente(cls, cliente: Cliente, forzar=False):
        """
        Corrige las inconsistencias en los totales del cliente.
        
        Args:
            cliente: Cliente a corregir
            forzar: Si True, corrige incluso si la diferencia es pequeña
            
        Returns:
            dict: Resultado de la corrección con información de cambios
        """
        validacion = cls.validar_consistencia_cliente(cliente)
        
        if validacion['consistente'] and not forzar:
            return {
                'corregido': False,
                'mensaje': 'El cliente ya está consistente',
                'validacion': validacion
            }
        
        tolerancia = Decimal('0.01')
        necesita_correccion = (
            abs(validacion['diferencias']['acumulados']) > tolerancia or
            abs(validacion['diferencias']['disponibles']) > tolerancia
        )
        
        if not necesita_correccion and not forzar:
            return {
                'corregido': False,
                'mensaje': 'Las diferencias están dentro de la tolerancia',
                'validacion': validacion
            }
        
        with transaction.atomic():
            # Crear registro de ajuste si hay diferencias significativas
            if abs(validacion['diferencias']['acumulados']) > tolerancia:
                descripcion = f"Ajuste de consistencia: Diferencia en acumulados de {validacion['diferencias']['acumulados']:,.2f} km"
                cls._crear_historial(
                    cliente,
                    'AJUSTE',
                    validacion['diferencias']['acumulados'],
                    descripcion=descripcion
                )
                logger.info(f"Ajuste de acumulados para cliente {cliente.pk}: {validacion['diferencias']['acumulados']:,.2f} km")
            
            if abs(validacion['diferencias']['disponibles']) > tolerancia:
                # Solo crear registro si la diferencia de disponibles no se debe solo a la diferencia de acumulados
                diferencia_independiente = validacion['diferencias']['disponibles'] - validacion['diferencias']['acumulados']
                if abs(diferencia_independiente) > tolerancia:
                    descripcion = f"Ajuste de consistencia: Diferencia en disponibles de {validacion['diferencias']['disponibles']:,.2f} km"
                    cls._crear_historial(
                        cliente,
                        'AJUSTE',
                        diferencia_independiente,
                        descripcion=descripcion
                    )
                    logger.info(f"Ajuste de disponibles para cliente {cliente.pk}: {diferencia_independiente:,.2f} km")
            
            # Actualizar valores del cliente
            cliente.kilometros_acumulados = validacion['calculados']['acumulados']
            cliente.kilometros_disponibles = validacion['calculados']['disponibles']
            cliente.ultima_fecha_km = timezone.now()
            cliente.save(update_fields=['kilometros_acumulados', 'kilometros_disponibles', 'ultima_fecha_km'])
        
        return {
            'corregido': True,
            'mensaje': f"Cliente corregido: Acumulados ajustados {validacion['diferencias']['acumulados']:,.2f} km, Disponibles ajustados {validacion['diferencias']['disponibles']:,.2f} km",
            'validacion_antes': validacion,
            'validacion_despues': cls.validar_consistencia_cliente(cliente)
        }
    
    @classmethod
    def validar_todos_clientes(cls):
        """
        Valida la consistencia de todos los clientes que participan en kilómetros.
        
        Returns:
            dict: {
                'total': int,
                'consistentes': int,
                'inconsistentes': int,
                'detalles': list[dict]  # Lista de clientes inconsistentes
            }
        """
        clientes = Cliente.objects.filter(participa_kilometros=True)
        total = clientes.count()
        consistentes = 0
        inconsistentes = 0
        detalles = []
        
        for cliente in clientes:
            validacion = cls.validar_consistencia_cliente(cliente)
            if not validacion['consistente']:
                inconsistentes += 1
                detalles.append({
                    'cliente_id': cliente.pk,
                    'cliente_nombre': str(cliente),
                    'diferencias': validacion['diferencias'],
                    'calculados': validacion['calculados'],
                    'actuales': validacion['actuales']
                })
            else:
                consistentes += 1
        
        return {
            'total': total,
            'consistentes': consistentes,
            'inconsistentes': inconsistentes,
            'detalles': detalles
        }
    
    # ------------------ Métricas y Reportes ------------------
    @classmethod
    def obtener_metricas_sistema(cls):
        """
        Obtiene métricas generales del sistema de Kilómetros Movums.
        
        Returns:
            dict: Métricas del sistema
        """
        from django.db.models import Sum, Count, Avg, Q
        from django.utils import timezone
        from datetime import timedelta
        
        ahora = timezone.now()
        ultimos_30_dias = ahora - timedelta(days=30)
        ultimos_90_dias = ahora - timedelta(days=90)
        
        # Total de clientes participantes
        total_clientes = Cliente.objects.filter(participa_kilometros=True).count()
        
        # Total de kilómetros acumulados en el sistema
        total_km_acumulados = HistorialKilometros.objects.filter(
            kilometros__gt=0
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00')
        
        # Total de kilómetros disponibles
        total_km_disponibles = Cliente.objects.filter(
            participa_kilometros=True
        ).aggregate(
            total=Sum('kilometros_disponibles')
        )['total'] or Decimal('0.00')
        
        # Total de kilómetros redimidos
        total_km_redimidos = abs(HistorialKilometros.objects.filter(
            es_redencion=True,
            kilometros__lt=0
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00'))
        
        # Total de kilómetros expirados
        total_km_expirados = abs(HistorialKilometros.objects.filter(
            expirado=True,
            kilometros__lt=0
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00'))
        
        # Actividad reciente (últimos 30 días)
        movimientos_30_dias = HistorialKilometros.objects.filter(
            fecha_registro__gte=ultimos_30_dias
        ).count()
        
        acumulaciones_30_dias = HistorialKilometros.objects.filter(
            fecha_registro__gte=ultimos_30_dias,
            kilometros__gt=0
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00')
        
        redenciones_30_dias = abs(HistorialKilometros.objects.filter(
            fecha_registro__gte=ultimos_30_dias,
            es_redencion=True,
            kilometros__lt=0
        ).aggregate(
            total=Sum('kilometros')
        )['total'] or Decimal('0.00'))
        
        # Bonos de promociones (últimos 90 días)
        bonos_promociones_90_dias = HistorialKilometros.objects.filter(
            fecha_registro__gte=ultimos_90_dias,
            tipo_evento='BONO_PROMOCION',
            kilometros__gt=0
        ).aggregate(
            total=Sum('kilometros'),
            cantidad=Count('id')
        )
        
        # Promedio de kilómetros por cliente
        promedio_km_por_cliente = (
            total_km_disponibles / total_clientes
            if total_clientes > 0
            else Decimal('0.00')
        )
        
        # Valor total equivalente en pesos
        valor_total_equivalente = total_km_disponibles * cls.VALOR_PESO_POR_KM
        
        return {
            'total_clientes': total_clientes,
            'total_km_acumulados': total_km_acumulados,
            'total_km_disponibles': total_km_disponibles,
            'total_km_redimidos': total_km_redimidos,
            'total_km_expirados': total_km_expirados,
            'promedio_km_por_cliente': promedio_km_por_cliente,
            'valor_total_equivalente': valor_total_equivalente,
            'actividad_30_dias': {
                'movimientos': movimientos_30_dias,
                'acumulaciones': acumulaciones_30_dias,
                'redenciones': redenciones_30_dias,
            },
            'bonos_promociones_90_dias': {
                'total_km': bonos_promociones_90_dias['total'] or Decimal('0.00'),
                'cantidad': bonos_promociones_90_dias['cantidad'] or 0,
            },
            'fecha_consulta': ahora,
        }
