"""
Comando de gestión para marcar la apertura/anticipo de una o más ventas como confirmada por folio.
Uso (en el servidor): python manage.py confirmar_apertura_por_folio PAQ-20260204-01
Uso (varios folios):  python manage.py confirmar_apertura_por_folio VAR-20260203-04 PAQ-20260202-08 VAR-20260202-06
"""
from django.core.management.base import BaseCommand
from ventas.models import VentaViaje


class Command(BaseCommand):
    help = "Marca el pago de apertura/anticipo de una o más ventas como confirmado por el contador (por folio)."

    def add_arguments(self, parser):
        parser.add_argument(
            "folios",
            nargs="+",
            type=str,
            help="Uno o más folios de venta (ej: VAR-20260203-04 PAQ-20260202-08)",
        )

    def handle(self, *args, **options):
        folios = [f.strip() for f in options["folios"] if f and f.strip()]
        if not folios:
            self.stdout.write(self.style.ERROR("No se indicaron folios."))
            return
        ok = 0
        for folio in folios:
            venta = VentaViaje.objects.filter(folio=folio).first()
            if not venta:
                self.stdout.write(self.style.ERROR(f"  {folio}: no encontrado."))
                continue
            if not venta.cantidad_apertura or venta.cantidad_apertura <= 0:
                self.stdout.write(self.style.WARNING(f"  {folio}: sin monto de apertura, se omite."))
                continue
            if venta.apertura_confirmada:
                self.stdout.write(self.style.WARNING(f"  {folio}: ya estaba confirmada."))
                ok += 1
                continue
            venta.apertura_confirmada = True
            venta.save(update_fields=["apertura_confirmada"])
            venta.actualizar_estado_financiero()
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {folio} (pk={venta.pk}): apertura confirmada. Total pagado: ${venta.total_pagado:,.2f}."
                )
            )
            ok += 1
        self.stdout.write(self.style.SUCCESS(f"\nProcesados: {ok}/{len(folios)} folios."))
