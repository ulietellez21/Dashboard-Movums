from decimal import Decimal
from datetime import date

from crm.models import PromocionKilometros


class PromocionesService:
    """
    Servicio para evaluar y calcular promociones aplicables a una venta.
    """

    @classmethod
    def _fecha_hoy(cls):
        return date.today()

    @classmethod
    def _condicion_cumple(cls, cliente, fecha_ref, valor_condicion=None):
        if not cliente or not getattr(cliente, 'fecha_nacimiento', None):
            return False
        fn = cliente.fecha_nacimiento
        return fn.month == fecha_ref.month and fn.day == fecha_ref.day

    @classmethod
    def _condicion_mes(cls, fecha_ref, valor_condicion):
        try:
            mes = int(valor_condicion)
        except (TypeError, ValueError):
            return False
        return fecha_ref.month == mes

    @classmethod
    def _en_rango_fecha(cls, promo, fecha_ref):
        if promo.fecha_inicio and fecha_ref < promo.fecha_inicio:
            return False
        if promo.fecha_fin and fecha_ref > promo.fecha_fin:
            return False
        return True

    @classmethod
    def obtener_promos_aplicables(cls, cliente, tipo_viaje, total_base_mxn, fecha_ref=None):
        """
        Devuelve una lista de dicts con promociones aplicables:
        [
          {
            'promo': promo,
            'monto_descuento': Decimal,
            'porcentaje': Decimal,
            'requiere_confirmacion': bool,
            'km_bono': Decimal,
          },
          ...
        ]
        """
        fecha_ref = fecha_ref or cls._fecha_hoy()
        total_base_mxn = Decimal(total_base_mxn or 0)

        qs = PromocionKilometros.objects.filter(activa=True)

        candidatas = []
        for promo in qs:
            if not cls._en_rango_fecha(promo, fecha_ref):
                continue
            
            # Validar alcance de la promoción
            if promo.alcance == 'NAC' and tipo_viaje != 'NAC':
                continue
            if promo.alcance == 'INT' and tipo_viaje != 'INT':
                continue
            if promo.alcance == 'CLIENTE_ESPECIFICO':
                # Si es promoción personal, solo aplicar si el cliente está en la lista
                if not cliente:
                    continue
                # Verificar si el cliente está en la lista de clientes específicos de la promoción
                clientes_especificos = promo.clientes.all()
                if not clientes_especificos.exists():
                    # Si la promoción es CLIENTE_ESPECIFICO pero no tiene clientes asignados, no aplica
                    continue
                if not clientes_especificos.filter(pk=cliente.pk).exists():
                    # El cliente no está en la lista de clientes específicos
                    continue

            aplica = False
            if promo.condicion == 'SIEMPRE':
                aplica = True
            elif promo.condicion == 'CUMPLE':
                aplica = cls._condicion_cumple(cliente, fecha_ref, promo.valor_condicion)
            elif promo.condicion == 'MES':
                aplica = cls._condicion_mes(fecha_ref, promo.valor_condicion)
            elif promo.condicion == 'RANGO':
                # Ya se validó el rango por fechas inicio/fin
                aplica = True

            if not aplica:
                continue

            if promo.tipo == 'DESCUENTO':
                porcentaje = Decimal(promo.porcentaje_descuento or 0)
                if porcentaje <= 0:
                    continue
                monto = (total_base_mxn * porcentaje / Decimal('100')).quantize(Decimal('0.01'))
                if promo.monto_tope_mxn and promo.monto_tope_mxn > 0:
                    monto = min(monto, promo.monto_tope_mxn)
                if monto <= 0:
                    continue
                candidatas.append({
                    'promo': promo,
                    'monto_descuento': monto,
                    'porcentaje': porcentaje,
                    'requiere_confirmacion': promo.requiere_confirmacion,
                    'km_bono': Decimal('0.00'),
                })
            elif promo.tipo == 'KM':
                km_bono = Decimal(promo.kilometros_bono or 0)
                if km_bono <= 0:
                    continue
                candidatas.append({
                    'promo': promo,
                    'monto_descuento': Decimal('0.00'),
                    'porcentaje': Decimal('0.00'),
                    'requiere_confirmacion': promo.requiere_confirmacion,
                    'km_bono': km_bono,
                })

        # Stacking permitido: regresar todas las aplicables en orden de creación (más recientes primero)
        candidatas.sort(key=lambda x: x['promo'].creada_en, reverse=True)
        return candidatas

