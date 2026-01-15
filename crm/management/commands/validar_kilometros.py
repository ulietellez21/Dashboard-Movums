from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal

from crm.models import Cliente
from crm.services import KilometrosService


class Command(BaseCommand):
    help = "Valida y corrige la consistencia de kilómetros Movums para todos los clientes."

    def add_arguments(self, parser):
        parser.add_argument(
            '--corregir',
            action='store_true',
            help='Corrige automáticamente las inconsistencias encontradas',
        )
        parser.add_argument(
            '--cliente-id',
            type=int,
            help='Validar solo un cliente específico por ID',
        )
        parser.add_argument(
            '--forzar',
            action='store_true',
            help='Fuerza la corrección incluso si las diferencias son pequeñas',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Muestra información detallada de cada cliente',
        )

    def handle(self, *args, **options):
        corregir = options['corregir']
        cliente_id = options.get('cliente_id')
        forzar = options['forzar']
        verbose = options['verbose']
        
        if cliente_id:
            # Validar solo un cliente
            try:
                cliente = Cliente.objects.get(pk=cliente_id)
                if not cliente.participa_kilometros:
                    self.stdout.write(
                        self.style.WARNING(f"Cliente {cliente_id} no participa en kilómetros Movums.")
                    )
                    return
                
                self._validar_cliente(cliente, corregir, forzar, verbose)
            except Cliente.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Cliente con ID {cliente_id} no encontrado.")
                )
        else:
            # Validar todos los clientes
            resultado = KilometrosService.validar_todos_clientes()
            
            self.stdout.write(self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"RESUMEN DE VALIDACIÓN DE KILÓMETROS MOVUMS\n"
                f"{'='*60}\n"
                f"Total de clientes: {resultado['total']}\n"
                f"Clientes consistentes: {resultado['consistentes']}\n"
                f"Clientes inconsistentes: {resultado['inconsistentes']}\n"
                f"{'='*60}\n"
            ))
            
            if resultado['inconsistentes'] > 0:
                self.stdout.write(self.style.WARNING(
                    f"\n⚠️  Se encontraron {resultado['inconsistentes']} cliente(s) con inconsistencias:\n"
                ))
                
                for detalle in resultado['detalles']:
                    self.stdout.write(
                        f"\n  Cliente ID {detalle['cliente_id']}: {detalle['cliente_nombre']}\n"
                        f"    Acumulados: Calculado={detalle['calculados']['acumulados']:,.2f} km, "
                        f"Actual={detalle['actuales']['acumulados']:,.2f} km, "
                        f"Diferencia={detalle['diferencias']['acumulados']:,.2f} km\n"
                        f"    Disponibles: Calculado={detalle['calculados']['disponibles']:,.2f} km, "
                        f"Actual={detalle['actuales']['disponibles']:,.2f} km, "
                        f"Diferencia={detalle['diferencias']['disponibles']:,.2f} km"
                    )
                
                if corregir:
                    self.stdout.write(self.style.WARNING(
                        f"\n{'='*60}\n"
                        f"INICIANDO CORRECCIÓN AUTOMÁTICA...\n"
                        f"{'='*60}\n"
                    ))
                    
                    corregidos = 0
                    errores = 0
                    
                    for detalle in resultado['detalles']:
                        try:
                            cliente = Cliente.objects.get(pk=detalle['cliente_id'])
                            resultado_correccion = KilometrosService.corregir_consistencia_cliente(
                                cliente, 
                                forzar=forzar
                            )
                            
                            if resultado_correccion['corregido']:
                                corregidos += 1
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"✅ Cliente {cliente.pk} ({cliente}): {resultado_correccion['mensaje']}"
                                    )
                                )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"⚠️  Cliente {cliente.pk} ({cliente}): {resultado_correccion['mensaje']}"
                                    )
                                )
                        except Exception as e:
                            errores += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f"❌ Error corrigiendo cliente {detalle['cliente_id']}: {str(e)}"
                                )
                            )
                    
                    self.stdout.write(self.style.SUCCESS(
                        f"\n{'='*60}\n"
                        f"RESUMEN DE CORRECCIÓN\n"
                        f"{'='*60}\n"
                        f"Clientes corregidos: {corregidos}\n"
                        f"Errores: {errores}\n"
                        f"{'='*60}\n"
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"\n💡 Usa --corregir para corregir automáticamente las inconsistencias."
                    ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    "\n✅ Todos los clientes están consistentes."
                ))
    
    def _validar_cliente(self, cliente, corregir, forzar, verbose):
        """Valida y opcionalmente corrige un cliente específico."""
        validacion = KilometrosService.validar_consistencia_cliente(cliente)
        
        self.stdout.write(
            self.style.SUCCESS(f"\n{'='*60}\n")
            + f"VALIDACIÓN DE CLIENTE: {cliente} (ID: {cliente.pk})\n"
            + self.style.SUCCESS(f"{'='*60}\n")
        )
        
        if verbose or not validacion['consistente']:
            self.stdout.write(
                f"Acumulados:\n"
                f"  Calculado desde historial: {validacion['calculados']['acumulados']:,.2f} km\n"
                f"  Valor actual en cliente: {validacion['actuales']['acumulados']:,.2f} km\n"
                f"  Diferencia: {validacion['diferencias']['acumulados']:,.2f} km\n"
                f"\nDisponibles:\n"
                f"  Calculado desde historial: {validacion['calculados']['disponibles']:,.2f} km\n"
                f"  Valor actual en cliente: {validacion['actuales']['disponibles']:,.2f} km\n"
                f"  Diferencia: {validacion['diferencias']['disponibles']:,.2f} km\n"
            )
        
        if validacion['consistente']:
            self.stdout.write(self.style.SUCCESS("✅ Cliente consistente."))
        else:
            self.stdout.write(self.style.WARNING("⚠️  Cliente con inconsistencias detectadas."))
            
            if corregir:
                resultado_correccion = KilometrosService.corregir_consistencia_cliente(
                    cliente,
                    forzar=forzar
                )
                
                if resultado_correccion['corregido']:
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ {resultado_correccion['mensaje']}")
                    )
                    
                    # Validar después de la corrección
                    validacion_despues = resultado_correccion['validacion_despues']
                    if validacion_despues['consistente']:
                        self.stdout.write(self.style.SUCCESS("✅ Cliente corregido y ahora consistente."))
                    else:
                        self.stdout.write(self.style.WARNING("⚠️  Cliente corregido pero aún con pequeñas diferencias."))
                else:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️  {resultado_correccion['mensaje']}")
                    )
            else:
                self.stdout.write(
                    self.style.WARNING("💡 Usa --corregir para corregir automáticamente.")
                )









