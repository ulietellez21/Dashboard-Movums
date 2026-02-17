"""
Comando para dejar solo los servicios logísticos "por defecto" en una venta (uno por tipo).
Elimina las filas extra de Vuelo/Hospedaje/Tour que se añadieron al probar "Añadir otro X".

Uso: python manage.py reset_logistica_por_folio VAR-20260216-01
"""
from django.core.management.base import BaseCommand
from ventas.models import VentaViaje, LogisticaServicio


class Command(BaseCommand):
    help = "Deja solo un servicio logístico por tipo (codigo_servicio) para la venta indicada por folio."

    def add_arguments(self, parser):
        parser.add_argument(
            "folio",
            type=str,
            help="Folio de la venta (ej: VAR-20260216-01)",
        )

    def handle(self, *args, **options):
        folio = (options.get("folio") or "").strip()
        if not folio:
            self.stdout.write(self.style.ERROR("Indica el folio de la venta."))
            return

        venta = VentaViaje.objects.filter(folio=folio).first()
        if not venta:
            self.stdout.write(self.style.ERROR(f"Venta con folio '{folio}' no encontrada."))
            return

        servicios = list(venta.servicios_logisticos.all().order_by("orden", "pk"))
        if not servicios:
            self.stdout.write(self.style.WARNING(f"  {folio}: no tiene servicios logísticos."))
            return

        # Por cada codigo_servicio, quedarnos solo con el primero (orden, pk); borrar el resto
        a_mantener = set()
        vistos = {}
        for s in servicios:
            cod = s.codigo_servicio
            if cod not in vistos:
                vistos[cod] = s.pk
                a_mantener.add(s.pk)

        a_borrar = [s for s in servicios if s.pk not in a_mantener]
        for s in a_borrar:
            self.stdout.write(f"  Eliminando: {s.nombre_servicio} (pk={s.pk}, codigo={s.codigo_servicio})")
            s.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"  {folio}: se mantienen {len(a_mantener)} servicio(s) (uno por tipo). "
                f"Eliminados: {len(a_borrar)}."
            )
        )
