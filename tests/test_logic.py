"""
Tests para verificar la corrección de los cálculos monetarios y financieros.
Estos tests son CRÍTICOS para asegurar que los totales no se rompan al modificar el código.

QA Lead: Blindaje de la lógica financiera del sistema.
"""
import pytest
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
from django.db import transaction

from ventas.models import VentaViaje, AbonoPago, AbonoProveedor
from crm.models import Cliente


@pytest.mark.django_db
class TestVentaCalculosBasicos:
    """Tests para cálculos básicos de VentaViaje."""
    
    def test_costo_total_con_modificacion_sin_modificacion(self, cliente_particular, normal_user, db):
        """Test: costo_total_con_modificacion sin costo de modificación."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            costo_modificacion=Decimal('0.00'),
            cantidad_apertura=Decimal('3000.00')
        )
        
        total = venta.costo_total_con_modificacion
        assert total == Decimal('10000.00')
    
    def test_costo_total_con_modificacion_con_modificacion(self, cliente_particular, normal_user, db):
        """Test: costo_total_con_modificacion con costo de modificación."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            costo_modificacion=Decimal('1500.00'),
            cantidad_apertura=Decimal('3000.00')
        )
        
        total = venta.costo_total_con_modificacion
        assert total == Decimal('11500.00')
    
    def test_costo_total_con_modificacion_con_descuento_kilometros(self, cliente_particular, normal_user, db):
        """Test: costo_total_con_modificacion aplica descuento de kilómetros."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            costo_modificacion=Decimal('0.00'),
            cantidad_apertura=Decimal('3000.00'),
            aplica_descuento_kilometros=True,
            descuento_kilometros_mxn=Decimal('1000.00')  # 10% de 10000
        )
        
        total = venta.costo_total_con_modificacion
        assert total == Decimal('9000.00')  # 10000 - 1000
    
    def test_costo_total_con_modificacion_con_precio_cero(self, cliente_particular, normal_user, db):
        """Test: costo_total_con_modificacion con precio 0 (caso borde)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('0.00'),
            costo_neto=Decimal('0.00'),
            costo_modificacion=Decimal('0.00'),
            cantidad_apertura=Decimal('0.00')
        )
        
        total = venta.costo_total_con_modificacion
        assert total == Decimal('0.00')
        assert total >= Decimal('0.00')  # Nunca negativo
    
    def test_costo_total_con_modificacion_con_decimales(self, cliente_particular, normal_user, db):
        """Test: costo_total_con_modificacion con decimales precisos."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('1234.56'),
            costo_neto=Decimal('1000.00'),
            costo_modificacion=Decimal('789.12'),
            cantidad_apertura=Decimal('300.00')
        )
        
        total = venta.costo_total_con_modificacion
        expected = Decimal('2023.68')  # 1234.56 + 789.12
        assert total == expected
    
    def test_total_con_descuento_sin_descuento(self, cliente_particular, normal_user, db):
        """Test: total_con_descuento sin descuento aplicado."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            aplica_descuento_kilometros=False
        )
        
        total = venta.total_con_descuento
        assert total == Decimal('10000.00')
    
    def test_total_con_descuento_con_descuento_10_porciento(self, cliente_particular, normal_user, db):
        """Test: total_con_descuento aplica descuento del 10%."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            aplica_descuento_kilometros=True,
            descuento_kilometros_mxn=Decimal('1000.00')  # Exactamente 10% de 10000
        )
        
        total = venta.total_con_descuento
        assert total == Decimal('9000.00')  # 10000 - 1000


@pytest.mark.django_db
class TestVentaTotalPagado:
    """Tests para el cálculo de total_pagado."""
    
    def test_total_pagado_sin_abonos(self, cliente_particular, normal_user, db):
        """Test: total_pagado sin abonos registrados."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('0.00'),
            modo_pago_apertura='TRN',
            estado_confirmacion='PENDIENTE'
        )
        
        total = venta.total_pagado
        assert total == Decimal('0.00')
    
    def test_total_pagado_solo_apertura_efectivo(self, cliente_particular, normal_user, db):
        """Test: total_pagado con apertura en efectivo (se cuenta automáticamente)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='EFE'  # Efectivo se cuenta automáticamente
        )
        
        total = venta.total_pagado
        assert total == Decimal('3000.00')
    
    def test_total_pagado_apertura_transferencia_confirmada(self, cliente_particular, normal_user, db):
        """Test: total_pagado con apertura en transferencia confirmada."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='TRN',
            estado_confirmacion='COMPLETADO'  # Confirmado, se cuenta
        )
        
        total = venta.total_pagado
        assert total == Decimal('3000.00')
    
    def test_total_pagado_apertura_transferencia_pendiente_no_cuenta(self, cliente_particular, normal_user, db):
        """Test: total_pagado con apertura en transferencia EN_CONFIRMACION no cuenta."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='TRN',
            estado_confirmacion='EN_CONFIRMACION'  # Pendiente, NO se cuenta
        )
        
        total = venta.total_pagado
        assert total == Decimal('0.00')
    
    def test_total_pagado_con_abono_confirmado(self, cliente_particular, normal_user, db):
        """Test: total_pagado con abono confirmado."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('0.00'),
            modo_pago_apertura='EFE'
        )
        
        # Crear abono confirmado
        AbonoPago.objects.create(
            venta=venta,
            monto=Decimal('2000.00'),
            forma_pago='TRN',
            confirmado=True
        )
        
        total = venta.total_pagado
        assert total == Decimal('2000.00')
    
    def test_total_pagado_con_abono_no_confirmado_no_cuenta(self, cliente_particular, normal_user, db):
        """Test: total_pagado NO cuenta abonos no confirmados (excepto efectivo)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('0.00'),
            modo_pago_apertura='EFE'
        )
        
        # Crear abono NO confirmado
        AbonoPago.objects.create(
            venta=venta,
            monto=Decimal('2000.00'),
            forma_pago='TRN',
            confirmado=False  # NO confirmado
        )
        
        total = venta.total_pagado
        assert total == Decimal('0.00')
    
    def test_total_pagado_con_abono_efectivo_cuenta_siempre(self, cliente_particular, normal_user, db):
        """Test: total_pagado cuenta abonos en efectivo siempre (aunque no confirmados)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('0.00'),
            modo_pago_apertura='EFE'
        )
        
        # Crear abono en efectivo (NO confirmado, pero debe contarse)
        AbonoPago.objects.create(
            venta=venta,
            monto=Decimal('1500.00'),
            forma_pago='EFE',
            confirmado=False  # Efectivo se cuenta aunque no esté confirmado
        )
        
        total = venta.total_pagado
        assert total == Decimal('1500.00')
    
    def test_total_pagado_suma_multiplos_abonos(self, cliente_particular, normal_user, db):
        """Test: total_pagado suma múltiples abonos correctamente."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='EFE'
        )
        
        # Crear múltiples abonos
        AbonoPago.objects.create(venta=venta, monto=Decimal('2000.00'), forma_pago='TRN', confirmado=True)
        AbonoPago.objects.create(venta=venta, monto=Decimal('1500.00'), forma_pago='TRN', confirmado=True)
        AbonoPago.objects.create(venta=venta, monto=Decimal('500.00'), forma_pago='EFE', confirmado=False)  # Efectivo
        
        total = venta.total_pagado
        # Apertura: 3000 + Abonos: 2000 + 1500 + 500 = 7000
        assert total == Decimal('7000.00')
    
    def test_total_pagado_con_decimales(self, cliente_particular, normal_user, db):
        """Test: total_pagado maneja decimales correctamente."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('1234.56'),
            modo_pago_apertura='EFE'
        )
        
        AbonoPago.objects.create(venta=venta, monto=Decimal('789.12'), forma_pago='TRN', confirmado=True)
        
        total = venta.total_pagado
        expected = Decimal('2023.68')  # 1234.56 + 789.12
        assert total == expected


@pytest.mark.django_db
class TestVentaSaldoRestante:
    """Tests para el cálculo de saldo_restante."""
    
    def test_saldo_restante_sin_pagos(self, cliente_particular, normal_user, db):
        """Test: saldo_restante sin pagos registrados."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('0.00'),
            modo_pago_apertura='EFE'
        )
        
        saldo = venta.saldo_restante
        assert saldo == Decimal('10000.00')
    
    def test_saldo_restante_con_pago_parcial(self, cliente_particular, normal_user, db):
        """Test: saldo_restante con pago parcial."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='EFE'
        )
        
        AbonoPago.objects.create(venta=venta, monto=Decimal('2000.00'), forma_pago='TRN', confirmado=True)
        
        saldo = venta.saldo_restante
        # Total: 10000 - Pagado: 5000 = 5000
        assert saldo == Decimal('5000.00')
    
    def test_saldo_restante_con_descuento_kilometros(self, cliente_particular, normal_user, db):
        """Test: saldo_restante aplica descuento de kilómetros."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='EFE',
            aplica_descuento_kilometros=True,
            descuento_kilometros_mxn=Decimal('1000.00')
        )
        
        saldo = venta.saldo_restante
        # Total con descuento: 9000 - Pagado: 3000 = 6000
        assert saldo == Decimal('6000.00')
    
    def test_saldo_restante_con_descuento_promociones(self, cliente_particular, normal_user, db):
        """Test: saldo_restante aplica descuento de promociones."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='EFE',
            descuento_promociones_mxn=Decimal('500.00')
        )
        
        saldo = venta.saldo_restante
        # Total con descuento: 9500 - Pagado: 3000 = 6500
        assert saldo == Decimal('6500.00')
    
    def test_saldo_restante_nunca_negativo(self, cliente_particular, normal_user, db):
        """Test: saldo_restante nunca es negativo (caso borde)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('8000.00'),
            modo_pago_apertura='EFE'
        )
        
        # Crear abono que sobrepase el total
        AbonoPago.objects.create(venta=venta, monto=Decimal('5000.00'), forma_pago='TRN', confirmado=True)
        
        saldo = venta.saldo_restante
        # Total: 10000 - Pagado: 13000 = -3000, pero debe ser 0
        assert saldo == Decimal('0.00')
        assert saldo >= Decimal('0.00')
    
    def test_saldo_restante_venta_pagada_completa(self, cliente_particular, normal_user, db):
        """Test: saldo_restante con venta completamente pagada."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('5000.00'),
            modo_pago_apertura='EFE'
        )
        
        AbonoPago.objects.create(venta=venta, monto=Decimal('5000.00'), forma_pago='TRN', confirmado=True)
        
        saldo = venta.saldo_restante
        assert saldo == Decimal('0.00')
        assert venta.esta_pagada == True


@pytest.mark.django_db
class TestVentaCalculosUSD:
    """Tests para cálculos de ventas internacionales en USD."""
    
    def test_total_usd_venta_nacional_retorna_cero(self, cliente_particular, normal_user, db):
        """Test: total_usd retorna 0 para venta nacional."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',  # Nacional
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00')
        )
        
        total_usd = venta.total_usd
        assert total_usd == Decimal('0.00')
    
    def test_total_usd_calcula_correctamente(self, cliente_particular, normal_user, db):
        """Test: total_usd calcula correctamente la suma de componentes USD."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            tipo_cambio=Decimal('20.00'),
            tarifa_base_usd=Decimal('500.00'),
            impuestos_usd=Decimal('100.00'),
            suplementos_usd=Decimal('50.00'),
            tours_usd=Decimal('25.00')
        )
        
        total_usd = venta.total_usd
        expected = Decimal('675.00')  # 500 + 100 + 50 + 25
        assert total_usd == expected
    
    def test_cantidad_apertura_usd_convierte_correctamente(self, cliente_particular, normal_user, db):
        """Test: cantidad_apertura_usd convierte MXN a USD correctamente."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('1000.00'),  # 1000 MXN
            tipo_cambio=Decimal('20.00')  # 1 USD = 20 MXN
        )
        
        apertura_usd = venta.cantidad_apertura_usd
        expected = Decimal('50.00')  # 1000 / 20 = 50
        assert apertura_usd == expected
    
    def test_cantidad_apertura_usd_redondea_a_2_decimales(self, cliente_particular, normal_user, db):
        """Test: cantidad_apertura_usd redondea a 2 decimales."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('1000.00'),
            tipo_cambio=Decimal('17.3456')  # Tipo de cambio con muchos decimales
        )
        
        apertura_usd = venta.cantidad_apertura_usd
        # 1000 / 17.3456 = 57.6569... -> debe redondear a 57.66
        assert apertura_usd.quantize(Decimal('0.01')) == apertura_usd
    
    def test_total_pagado_usd_suma_apertura_y_abonos(self, cliente_particular, normal_user, db):
        """Test: total_pagado_usd suma apertura y abonos en USD."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('2000.00'),  # 2000 MXN = 100 USD (tipo_cambio 20)
            tipo_cambio=Decimal('20.00'),
            modo_pago_apertura='EFE'
        )
        
        # Crear abono con monto_usd directamente
        AbonoPago.objects.create(
            venta=venta,
            monto=Decimal('1000.00'),  # 1000 MXN
            monto_usd=Decimal('50.00'),  # 50 USD
            forma_pago='TRN',
            confirmado=True,
            tipo_cambio_aplicado=Decimal('20.00')
        )
        
        total_pagado_usd = venta.total_pagado_usd
        expected = Decimal('150.00')  # 100 USD (apertura) + 50 USD (abono)
        assert total_pagado_usd == expected
    
    def test_saldo_restante_usd_calcula_correctamente(self, cliente_particular, normal_user, db):
        """Test: saldo_restante_usd calcula correctamente."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('2000.00'),
            tipo_cambio=Decimal('20.00'),
            modo_pago_apertura='EFE',
            tarifa_base_usd=Decimal('400.00'),
            impuestos_usd=Decimal('100.00')
        )
        
        # Total USD: 500, Pagado USD: 100 (apertura), Saldo: 400
        saldo_usd = venta.saldo_restante_usd
        expected = Decimal('400.00')  # 500 - 100
        assert saldo_usd == expected


@pytest.mark.django_db
class TestDescuentos:
    """Tests para cálculos de descuentos."""
    
    def test_descuento_kilometros_10_porciento(self, cliente_particular, normal_user, db):
        """Test: Verificar que el descuento de kilómetros es exactamente 10%."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            aplica_descuento_kilometros=True,
            descuento_kilometros_mxn=Decimal('1000.00')  # 10% de 10000
        )
        
        # Verificar que el descuento es exactamente 10%
        descuento_esperado = Decimal('1000.00')
        assert venta.descuento_kilometros_mxn == descuento_esperado
    
    def test_descuento_kilometros_con_precio_100_es_10(self, cliente_particular, normal_user, db):
        """Test: Descuento del 10% de 100 debe ser exactamente 10."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('100.00'),
            costo_neto=Decimal('80.00'),
            cantidad_apertura=Decimal('30.00'),
            aplica_descuento_kilometros=True,
            descuento_kilometros_mxn=Decimal('10.00')  # 10% de 100 = 10
        )
        
        assert venta.descuento_kilometros_mxn == Decimal('10.00')
        total_con_descuento = venta.total_con_descuento
        assert total_con_descuento == Decimal('90.00')  # 100 - 10
    
    def test_descuento_kilometros_con_decimales(self, cliente_particular, normal_user, db):
        """Test: Descuento de kilómetros con precios decimales."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('1234.56'),
            costo_neto=Decimal('1000.00'),
            cantidad_apertura=Decimal('300.00'),
            aplica_descuento_kilometros=True,
            descuento_kilometros_mxn=Decimal('123.46')  # 10% de 1234.56 = 123.456 -> redondeado
        )
        
        total_con_descuento = venta.total_con_descuento
        # 1234.56 - 123.46 = 1111.10
        assert total_con_descuento == Decimal('1111.10')


@pytest.mark.django_db
class TestEstaPagada:
    """Tests para la propiedad esta_pagada."""
    
    def test_esta_pagada_false_con_saldo_restante(self, cliente_particular, normal_user, db):
        """Test: esta_pagada es False cuando hay saldo restante."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            modo_pago_apertura='EFE'
        )
        
        assert venta.esta_pagada == False
    
    def test_esta_pagada_true_cuando_saldo_cero(self, cliente_particular, normal_user, db):
        """Test: esta_pagada es True cuando saldo_restante es 0."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('5000.00'),
            modo_pago_apertura='EFE'
        )
        
        AbonoPago.objects.create(venta=venta, monto=Decimal('5000.00'), forma_pago='TRN', confirmado=True)
        
        assert venta.esta_pagada == True
    
    def test_esta_pagada_true_cuando_saldo_negativo(self, cliente_particular, normal_user, db):
        """Test: esta_pagada es True cuando saldo_restante es negativo (sobrepago)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('8000.00'),
            modo_pago_apertura='EFE'
        )
        
        AbonoPago.objects.create(venta=venta, monto=Decimal('5000.00'), forma_pago='TRN', confirmado=True)
        
        # Saldo restante será 0 (no negativo), pero esta_pagada debe ser True
        assert venta.saldo_restante == Decimal('0.00')
        assert venta.esta_pagada == True


@pytest.mark.django_db
class TestAbonoProveedorCalculos:
    """Tests para cálculos de abonos a proveedores en ventas internacionales."""
    
    def test_total_abonado_proveedor_venta_nacional_retorna_cero(self, cliente_particular, normal_user, db):
        """Test: total_abonado_proveedor retorna 0 para venta nacional."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',  # Nacional
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00')
        )
        
        total_abonado = venta.total_abonado_proveedor
        assert total_abonado == Decimal('0.00')
    
    def test_total_abonado_proveedor_solo_completados(self, cliente_particular, normal_user, db):
        """Test: total_abonado_proveedor solo cuenta abonos COMPLETADOS."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            tipo_cambio=Decimal('20.00')
        )
        
        # Crear abono completado
        AbonoProveedor.objects.create(
            venta=venta,
            proveedor='Aerolínea Test',
            monto=Decimal('2000.00'),  # 2000 MXN
            monto_usd=Decimal('100.00'),  # 100 USD
            tipo_cambio_aplicado=Decimal('20.00'),
            estado='COMPLETADO',
            solicitud_por=normal_user
        )
        
        # Crear abono pendiente (NO debe contarse)
        AbonoProveedor.objects.create(
            venta=venta,
            proveedor='Hotel Test',
            monto=Decimal('1000.00'),
            monto_usd=Decimal('50.00'),
            tipo_cambio_aplicado=Decimal('20.00'),
            estado='PENDIENTE',
            solicitud_por=normal_user
        )
        
        total_abonado = venta.total_abonado_proveedor
        assert total_abonado == Decimal('100.00')  # Solo el completado
    
    def test_total_abonado_proveedor_convierte_mxn_a_usd(self, cliente_particular, normal_user, db):
        """Test: total_abonado_proveedor convierte MXN a USD si no tiene monto_usd."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            tipo_cambio=Decimal('20.00')
        )
        
        # Crear abono sin monto_usd (debe convertir)
        AbonoProveedor.objects.create(
            venta=venta,
            proveedor='Aerolínea Test',
            monto=Decimal('2000.00'),  # 2000 MXN
            monto_usd=None,  # Sin monto USD directo
            tipo_cambio_aplicado=Decimal('20.00'),
            estado='COMPLETADO',
            solicitud_por=normal_user
        )
        
        total_abonado = venta.total_abonado_proveedor
        expected = Decimal('100.00')  # 2000 / 20 = 100
        assert total_abonado == expected
    
    def test_saldo_pendiente_proveedor_calcula_correctamente(self, cliente_particular, normal_user, db):
        """Test: saldo_pendiente_proveedor calcula correctamente."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            tipo_cambio=Decimal('20.00'),
            tarifa_base_usd=Decimal('500.00'),
            impuestos_usd=Decimal('100.00')
        )
        
        # Total USD: 600, Abonado: 200, Saldo: 400
        AbonoProveedor.objects.create(
            venta=venta,
            proveedor='Aerolínea Test',
            monto=Decimal('4000.00'),
            monto_usd=Decimal('200.00'),
            tipo_cambio_aplicado=Decimal('20.00'),
            estado='COMPLETADO',
            solicitud_por=normal_user
        )
        
        saldo_pendiente = venta.saldo_pendiente_proveedor
        expected = Decimal('400.00')  # 600 - 200 = 400
        assert saldo_pendiente == expected
    
    def test_saldo_pendiente_proveedor_nunca_negativo(self, cliente_particular, normal_user, db):
        """Test: saldo_pendiente_proveedor nunca es negativo."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            tipo_cambio=Decimal('20.00'),
            tarifa_base_usd=Decimal('500.00')
        )
        
        # Abonar más de lo que se debe
        AbonoProveedor.objects.create(
            venta=venta,
            proveedor='Aerolínea Test',
            monto=Decimal('12000.00'),
            monto_usd=Decimal('600.00'),  # 600 USD (más que 500)
            tipo_cambio_aplicado=Decimal('20.00'),
            estado='COMPLETADO',
            solicitud_por=normal_user
        )
        
        saldo_pendiente = venta.saldo_pendiente_proveedor
        # Total: 500, Abonado: 600, Saldo: -100 -> debe ser 0
        assert saldo_pendiente == Decimal('0.00')
        assert saldo_pendiente >= Decimal('0.00')


@pytest.mark.django_db
class TestCasosBordeMonetarios:
    """Tests para casos borde en cálculos monetarios."""
    
    def test_calculo_con_costo_modificacion_cero(self, cliente_particular, normal_user, db):
        """Test: Cálculos manejan costo_modificacion en 0 correctamente."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('0.00'),
            costo_modificacion=Decimal('0.00'),  # 0 en lugar de None
            modo_pago_apertura='EFE'
        )
        
        total = venta.costo_total_con_modificacion
        # Debe manejar 0 como 0.00
        assert total == Decimal('10000.00')
    
    def test_calculo_con_decimales_largos(self, cliente_particular, normal_user, db):
        """Test: Cálculos manejan decimales largos correctamente."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('999999.99'),
            costo_neto=Decimal('800000.00'),
            cantidad_apertura=Decimal('333333.33'),
            costo_modificacion=Decimal('111111.11'),
            modo_pago_apertura='EFE'
        )
        
        total = venta.costo_total_con_modificacion
        expected = Decimal('1111111.10')  # 999999.99 + 111111.11
        assert total == expected
    
    def test_conversion_usd_con_tipo_cambio_cero(self, cliente_particular, normal_user, db):
        """Test: Conversión USD retorna 0 si tipo_cambio es 0 (caso borde)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='INT',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            tipo_cambio=Decimal('0.00')  # Tipo de cambio 0
        )
        
        total_usd = venta.total_usd
        assert total_usd == Decimal('0.00')
        
        apertura_usd = venta.cantidad_apertura_usd
        assert apertura_usd == Decimal('0.00')
    
    def test_saldo_restante_con_costo_modificacion_negativo(self, cliente_particular, normal_user, db):
        """Test: saldo_restante maneja costo_modificacion negativo (no debería pasar, pero hay que verificar)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('3000.00'),
            costo_modificacion=Decimal('-1000.00'),  # Negativo (descuento adicional)
            modo_pago_apertura='EFE'
        )
        
        saldo = venta.saldo_restante
        # Total: 10000 - 1000 = 9000, Pagado: 3000, Saldo: 6000
        expected = Decimal('6000.00')
        assert saldo == expected
    
    def test_total_pagado_con_abono_decimal_largo(self, cliente_particular, normal_user, db):
        """Test: total_pagado maneja abonos con decimales largos (se redondean al guardar)."""
        venta = VentaViaje.objects.create(
            cliente=cliente_particular,
            vendedor=normal_user,
            tipo_viaje='NAC',
            fecha_inicio_viaje=date.today() + timedelta(days=30),
            costo_venta_final=Decimal('10000.00'),
            costo_neto=Decimal('8000.00'),
            cantidad_apertura=Decimal('0.00'),
            modo_pago_apertura='EFE'
        )
        
        # Crear abono - el campo DecimalField solo permite 2 decimales, así que se guarda como 3333.33
        abono = AbonoPago.objects.create(
            venta=venta,
            monto=Decimal('3333.33'),  # 2 decimales máximo (redondeado desde 3333.333333)
            forma_pago='TRN',
            confirmado=True
        )
        
        total = venta.total_pagado
        # El monto se guarda con 2 decimales, así que el total también debe tener 2 decimales
        assert total == Decimal('3333.33')
        assert total.quantize(Decimal('0.01')) == total  # Verifica que tiene exactamente 2 decimales
