from django.core.management.base import BaseCommand

from crm.services import KilometrosService


class Command(BaseCommand):
    help = "Procesa la expiración de Kilómetros Movums vencidos."

    def handle(self, *args, **options):
        procesados = KilometrosService.expirar_kilometros()
        self.stdout.write(self.style.SUCCESS(f"Kilómetros expirados procesados: {procesados}"))

