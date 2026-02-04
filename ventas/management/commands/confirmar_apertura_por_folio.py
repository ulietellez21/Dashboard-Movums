"""
Comando de gestión para marcar la apertura/anticipo de una venta como confirmada por folio.
Uso (en el servidor): python manage.py confirmar_apertura_por_folio PAQ-20260204-01
"""
from django.core.management.base import BaseCommand
from ventas.models import VentaViaje


class Command(BaseCommand):
    help = "Marca el pago de apertura/anticipo de una venta como confirmado por el contador (por folio)."

    def add_arguments(self, parser):
        parser.add_argument(
            "folio",
            type=str,
            help="Folio de la venta (ej: PAQ-20260204-01)",
        )

    def handle(self, *args, **options):
        folio = options["folio"].strip()
        venta = VentaViaje.objects.filter(folio=folio).first()
        if not venta:
            self.stdout.write(self.style.ERROR(f"No se encontró ninguna venta con folio: {folio}"))
            return
        if not venta.cantidad_apertura or venta.cantidad_apertura <= 0:
            self.stdout.write(self.style.ERROR(f"La venta {folio} no tiene monto de apertura."))
            return
        if venta.apertura_confirmada:
            self.stdout.write(self.style.WARNING(f"La apertura de la venta {folio} ya estaba marcada como confirmada."))
            return
        venta.apertura_confirmada = True
        venta.save(update_fields=["apertura_confirmada"])
        venta.actualizar_estado_financiero()
        self.stdout.write(
            self.style.SUCCESS(
                f"Apertura de venta {folio} (pk={venta.pk}) marcada como confirmada. "
                f"Total pagado ahora: ${venta.total_pagado:,.2f}. Estado: {venta.estado_confirmacion}."
            )
        )
