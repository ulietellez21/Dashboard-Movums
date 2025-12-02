from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from .models import Cliente, HistorialKilometros


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
        return max_km.quantize(Decimal('0.01')), max_valor.quantize(Decimal('0.01'))

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

