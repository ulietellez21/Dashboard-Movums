"""
Comando para recuperar apertura_confirmada en ventas que el contador ya había confirmado
pero quedaron en False por el bug de refresh_from_db() (notificación PAGO_CONFIRMADO sin abono).

Uso:
  python manage.py recuperar_apertura_confirmada           # ejecuta cambios
  python manage.py recuperar_apertura_confirmada --dry-run  # solo lista qué se actualizaría
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from ventas.models import VentaViaje, Notificacion


class Command(BaseCommand):
    help = (
        "Marca apertura_confirmada=True en ventas que tienen notificación PAGO_CONFIRMADO "
        "sin abono (confirmación de apertura) pero apertura_confirmada=False (bug pasado)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Solo listar ventas que se actualizarían, sin guardar.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        # Notificaciones de tipo PAGO_CONFIRMADO sin abono = confirmación de apertura
        notifs = Notificacion.objects.filter(
            tipo="PAGO_CONFIRMADO",
            venta__isnull=False,
            abono__isnull=True,
        ).select_related("venta")
        venta_ids = notifs.values_list("venta_id", flat=True).distinct()
        ventas = VentaViaje.objects.filter(
            pk__in=venta_ids,
            apertura_confirmada=False,
            cantidad_apertura__gt=0,
        ).filter(
            Q(modo_pago_apertura__in=["TRN", "TAR", "DEP"]) | Q(modo_pago_apertura__isnull=True)
        )  # TRN/TAR/DEP son los que requieren confirmación del contador; null por datos antiguos
        ventas = list(ventas.order_by("pk"))
        if not ventas:
            self.stdout.write(
                self.style.SUCCESS("No hay ventas con apertura confirmada (notificación) pero apertura_confirmada=False.")
            )
            return
        self.stdout.write(
            self.style.WARNING(f"Ventas a actualizar (apertura_confirmada=True): {len(ventas)}")
        )
        for venta in ventas:
            self.stdout.write(
                f"  {venta.folio or venta.pk} (pk={venta.pk}) - apertura ${venta.cantidad_apertura:,.2f}"
            )
        if dry_run:
            self.stdout.write(self.style.WARNING("\n[--dry-run] No se guardó nada. Quita --dry-run para aplicar."))
            return
        updated = 0
        for venta in ventas:
            venta.apertura_confirmada = True
            venta.save(update_fields=["apertura_confirmada"])
            venta.actualizar_estado_financiero()
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {venta.folio or venta.pk} (pk={venta.pk}): apertura_confirmada=True. Total pagado: ${venta.total_pagado:,.2f}"
                )
            )
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"\nActualizadas: {updated} ventas."))
