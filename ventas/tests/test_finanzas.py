from decimal import Decimal
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from crm.models import Cliente
from ventas.models import VentaViaje, ContratoPlantilla


class VentaFinanzasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='tester')
        self.cliente = Cliente.objects.create(
            tipo_cliente='PARTICULAR',
            nombre='Cliente',
            apellido='Demo',
            telefono='5550001111',
            email='cliente@example.com',
        )
        ContratoPlantilla.objects.create(
            nombre='Contrato Nacional',
            tipo='NAC',
            contenido_base='Contrato base'
        )

    def crear_venta(self, **kwargs):
        data = {
            'cliente': self.cliente,
            'vendedor': self.user,
            'tipo_viaje': 'NAC',
            'fecha_inicio_viaje': date.today(),
            'costo_venta_final': Decimal('1000.00'),
            'costo_neto': Decimal('700.00'),
        }
        data.update(kwargs)
        return VentaViaje.objects.create(**data)

    def test_total_con_descuento_incluye_modificaciones(self):
        venta = self.crear_venta(
            costo_modificacion=Decimal('150.00'),
            aplica_descuento_kilometros=True,
            descuento_kilometros_mxn=Decimal('100.00'),
        )
        self.assertEqual(venta.costo_total_con_modificacion, Decimal('1050.00'))
        self.assertEqual(venta.total_con_descuento, Decimal('1050.00'))

    def test_actualizar_estado_financiero(self):
        venta = self.crear_venta(costo_modificacion=Decimal('200.00'))
        self.assertEqual(venta.estado_confirmacion, 'PENDIENTE')

        # Simular pago total
        venta.cantidad_apertura = Decimal('1200.00')
        venta.modo_pago_apertura = 'EFE'
        venta.save()
        venta.actualizar_estado_financiero()
        venta.refresh_from_db()
        self.assertEqual(venta.estado_confirmacion, 'COMPLETADO')

        # Reducir pago para probar regreso a pendiente
        venta.cantidad_apertura = Decimal('100.00')
        venta.save()
        venta.actualizar_estado_financiero()
        venta.refresh_from_db()
        self.assertEqual(venta.estado_confirmacion, 'PENDIENTE')

