from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal

from crm.services import KilometrosService


class Command(BaseCommand):
    help = "Muestra métricas del sistema de Kilómetros Movums."

    def add_arguments(self, parser):
        parser.add_argument(
            '--formato',
            choices=['simple', 'detallado', 'json'],
            default='detallado',
            help='Formato de salida (simple, detallado, json)',
        )

    def handle(self, *args, **options):
        formato = options['formato']
        metricas = KilometrosService.obtener_metricas_sistema()
        
        if formato == 'json':
            import json
            from django.core.serializers.json import DjangoJSONEncoder
            
            class DecimalEncoder(DjangoJSONEncoder):
                def default(self, obj):
                    if isinstance(obj, Decimal):
                        return float(obj)
                    return super().default(obj)
            
            self.stdout.write(json.dumps(metricas, cls=DecimalEncoder, indent=2, default=str))
            return
        
        # Formato simple
        if formato == 'simple':
            self.stdout.write(
                f"Clientes: {metricas['total_clientes']}\n"
                f"KM Acumulados: {metricas['total_km_acumulados']:,.2f}\n"
                f"KM Disponibles: {metricas['total_km_disponibles']:,.2f}\n"
                f"KM Redimidos: {metricas['total_km_redimidos']:,.2f}\n"
                f"Valor Equivalente: ${metricas['valor_total_equivalente']:,.2f} MXN"
            )
            return
        
        # Formato detallado
        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*70}\n"
            f"MÉTRICAS DEL SISTEMA DE KILÓMETROS MOVUMS\n"
            f"{'='*70}\n"
        ))
        
        self.stdout.write(
            f"\n📊 RESUMEN GENERAL:\n"
            f"  Total de Clientes: {metricas['total_clientes']}\n"
            f"  Promedio KM por Cliente: {metricas['promedio_km_por_cliente']:,.2f} km\n"
            f"  Valor Total Equivalente: ${metricas['valor_total_equivalente']:,.2f} MXN\n"
        )
        
        self.stdout.write(
            f"\n📈 KILÓMETROS ACUMULADOS:\n"
            f"  Total Histórico: {metricas['total_km_acumulados']:,.2f} km\n"
            f"  Disponibles Actualmente: {metricas['total_km_disponibles']:,.2f} km\n"
            f"  Redimidos: {metricas['total_km_redimidos']:,.2f} km\n"
            f"  Expirados: {metricas['total_km_expirados']:,.2f} km\n"
        )
        
        actividad = metricas['actividad_30_dias']
        self.stdout.write(
            f"\n📅 ACTIVIDAD (Últimos 30 días):\n"
            f"  Movimientos Totales: {actividad['movimientos']}\n"
            f"  Acumulaciones: {actividad['acumulaciones']:,.2f} km\n"
            f"  Redenciones: {actividad['redenciones']:,.2f} km\n"
        )
        
        bonos = metricas['bonos_promociones_90_dias']
        self.stdout.write(
            f"\n🎁 BONOS DE PROMOCIONES (Últimos 90 días):\n"
            f"  Total Bonificado: {bonos['total_km']:,.2f} km\n"
            f"  Cantidad de Bonos: {bonos['cantidad']}\n"
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'='*70}\n"
                f"Consulta realizada: {metricas['fecha_consulta'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"{'='*70}\n"
            )
        )









