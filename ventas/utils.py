import os # Necesario para la manipulación de rutas de archivos (para PDF)
import logging
from datetime import datetime
from django.template.loader import render_to_string # Necesario para renderizar la plantilla HTML a PDF
from django.template import Template, Context 
from django.utils import formats
from django.utils.formats import localize
from django.conf import settings # Necesario para MEDIA_ROOT (para PDF)
from django.db.models import Sum # Necesario si VentaViaje usa Sum para calcular montos
from decimal import Decimal
from .models import VentaViaje, ContratoPlantilla, ContratoGenerado

# Importamos el modelo Cliente (asumo que está en crm.models)
from crm.models import Cliente

logger = logging.getLogger(__name__)

# --- Función para convertir números a texto en español ---

def numero_a_texto(numero):
    """
    Convierte un número decimal a texto en español.
    Ejemplo: 1500.50 -> "mil quinientos pesos 50/100 M.N."
    """
    if numero is None or numero == 0:
        return "cero pesos 00/100 M.N."
    
    # Convertir a Decimal para mayor precisión
    numero = Decimal(str(numero))
    
    # Separar parte entera y decimal
    parte_entera = int(numero)
    parte_decimal = int((numero - parte_entera) * 100)
    
    # Diccionarios para conversión
    unidades = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
    decenas = ['', '', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
    especiales = {
        10: 'diez', 11: 'once', 12: 'doce', 13: 'trece', 14: 'catorce', 15: 'quince',
        16: 'dieciséis', 17: 'diecisiete', 18: 'dieciocho', 19: 'diecinueve',
        20: 'veinte', 21: 'veintiuno', 22: 'veintidós', 23: 'veintitrés', 24: 'veinticuatro',
        25: 'veinticinco', 26: 'veintiséis', 27: 'veintisiete', 28: 'veintiocho', 29: 'veintinueve'
    }
    
    def convertir_tres_digitos(n):
        """Convierte un número de hasta 3 dígitos a texto"""
        if n == 0:
            return ''
        if n in especiales:
            return especiales[n]
        
        texto = ''
        centenas = n // 100
        resto = n % 100
        
        if centenas > 0:
            if centenas == 1:
                texto += 'cien' if resto == 0 else 'ciento'
            else:
                texto += unidades[centenas] + 'cientos'
            if resto > 0:
                texto += ' '
        
        if resto in especiales:
            texto += especiales[resto]
        elif resto > 0:
            decena = resto // 10
            unidad = resto % 10
            if decena > 0:
                texto += decenas[decena]
                if unidad > 0:
                    texto += ' y ' + unidades[unidad]
            else:
                texto += unidades[unidad]
        
        return texto
    
    def convertir_numero_completo(n):
        """Convierte un número completo a texto"""
        if n == 0:
            return 'cero'
        
        texto = ''
        millones = n // 1000000
        miles = (n % 1000000) // 1000
        resto = n % 1000
        
        if millones > 0:
            texto += convertir_tres_digitos(millones)
            if millones == 1:
                texto += ' millón'
            else:
                texto += ' millones'
            if miles > 0 or resto > 0:
                texto += ' '
        
        if miles > 0:
            if miles == 1:
                texto += 'mil'
            else:
                texto += convertir_tres_digitos(miles) + ' mil'
            if resto > 0:
                texto += ' '
        
        if resto > 0:
            texto += convertir_tres_digitos(resto)
        
        return texto.strip()
    
    # Convertir parte entera
    texto_entero = convertir_numero_completo(parte_entera)
    
    # Agregar "pesos" y la parte decimal
    if parte_entera == 1:
        texto_final = texto_entero + ' peso'
    else:
        texto_final = texto_entero + ' pesos'
    
    # Agregar centavos
    texto_final += f' {parte_decimal:02d}/100 M.N.'
    
    return texto_final 

# --- CONFIGURACIÓN DE PDF ---
# Importaciones para generar PDF. ¡Asegúrate de tener WeasyPrint instalado!
try:
    from weasyprint import HTML
    WEASYPRINT_INSTALLED = True
except ImportError:
    logger.warning("WeasyPrint no está instalado. Los PDF no se generarán.")
    WEASYPRINT_INSTALLED = False

# --- Función para GENERAR PDF (Si aplica) ---

def generar_pdf_contrato(contrato_generado):
    """
    Genera el archivo PDF a partir del contenido HTML final y lo guarda 
    en el campo 'archivo_pdf' del modelo ContratoGenerado.
    """
    if not WEASYPRINT_INSTALLED:
        return None
    
    # NOTA CLAVE: Aquí, 'contenido_final' ya tiene las variables sustituidas.
    # Necesitamos pasar esta información a 'contrato_pdf.html'.
    
    # 1. Preparamos el contexto MÍNIMO para la plantilla base HTML del PDF
    # La plantilla 'contrato_pdf.html' DEBE tener una variable que reciba
    # el 'contenido_html_sustituido' para insertarlo en el cuerpo del PDF.
    
    # ✅ NULL SAFETY: Validar que venta y cliente existan
    venta = contrato_generado.venta
    if not venta:
        logger.error(f"ContratoGenerado {contrato_generado.pk} no tiene venta asociada")
        return None
    
    cliente = venta.cliente
    if not cliente:
        logger.error(f"Venta {venta.pk} no tiene cliente asociado")
        return None
    
    contexto_pdf = {
        # Se pasa el contenido HTML que ya tiene los datos de la venta sustituidos
        'contenido_html_sustituido': contrato_generado.contenido_final, 
        
        # Pasar la venta y cliente por si el template base los necesita (ej. en el footer/header)
        'venta': venta,
        'cliente': cliente,
        
        # Dirección del cliente formateada
        'cliente_direccion_completa': (
            cliente.direccion_fiscal if cliente.tipo_cliente == 'EMPRESA' and cliente.direccion_fiscal
            else f"{cliente.nombre_completo_display} - {cliente.telefono or 'Sin teléfono'}"
        ),
        
        # Variables de formato global (si se usan fuera del bloque de contenido)
        'fecha_generacion': formats.date_format(datetime.now(), r"j \d\e F \d\e Y"),
    }

    # 2. Renderizar la plantilla HTML del PDF
    try:
        # Usamos la plantilla ubicada en 'ventas/templates/ventas/contrato_pdf.html'
        # Esta plantilla debe ser un LAYOUT que envuelve 'contenido_html_sustituido'
        html_string = render_to_string('ventas/contrato_pdf.html', contexto_pdf)
        
        # 3. Generar la ruta de guardado
        media_root = getattr(settings, 'MEDIA_ROOT', '/tmp/media')
        
        # Creamos una subcarpeta 'contratos' si no existe
        contratos_dir = os.path.join(media_root, 'contratos')
        if not os.path.exists(contratos_dir):
            os.makedirs(contratos_dir)

        # Nombre del archivo único (usando el ID de la venta y la fecha)
        file_name = f'contrato-{contrato_generado.venta.id}-{datetime.now().strftime("%Y%m%d%H%M%S")}.pdf'
        file_path = os.path.join(contratos_dir, file_name)
        
        # 4. Convertir HTML a PDF y guardarlo
        HTML(string=html_string).write_pdf(file_path)

        # 5. Guardar la ruta relativa en el campo del modelo
        ruta_relativa = os.path.join('contratos', file_name)
        
        contrato_generado.archivo_pdf = ruta_relativa
        contrato_generado.save(update_fields=['archivo_pdf'])
        
        return ruta_relativa

    except Exception as e:
        logger.error(f"Error crítico al generar el PDF o guardar el archivo: {e}", exc_info=True)
        return None

# --- Función principal: Generación de Contrato y PDF ---

def generar_contrato_para_venta(venta_viaje_id):
    """
    Busca la plantilla de contrato, genera el contenido final, guarda el 
    ContratoGenerado y, si es posible, genera el archivo PDF.
    
    Args:
        venta_viaje_id (int): ID de la instancia de VentaViaje.
        
    Returns:
        ContratoGenerado: La instancia del contrato generado, o None si falla.
    """
    try:
        # 1. Obtener la VentaViaje, Cliente y Vendedor
        venta = VentaViaje.objects.select_related('cliente', 'vendedor', 'proveedor').get(pk=venta_viaje_id)
        
        # ✅ NULL SAFETY: Validar que cliente exista
        cliente = venta.cliente
        if not cliente:
            logger.error(f"Venta {venta_viaje_id} no tiene cliente asociado")
            return None
        
        # 2. Buscar la plantilla correcta
        plantilla = ContratoPlantilla.objects.get(tipo=venta.tipo_viaje)
        
    except VentaViaje.DoesNotExist:
        logger.error(f"VentaViaje con ID {venta_viaje_id} no encontrada.")
        return None
    except ContratoPlantilla.DoesNotExist:
        logger.error(f"Plantilla de contrato para tipo {venta.tipo_viaje} no encontrada.")
        return None
    except Exception as e:
        logger.error(f"Error al obtener datos o plantilla: {e}", exc_info=True)
        return None

    # 3. Preparar el diccionario de contexto para la plantilla de BD
        
    # El diccionario 'contexto' ahora tiene TODAS las variables necesarias para 
    # la sustitución en 'plantilla.contenido_base'.
    contexto = {
        # Objetos completos para acceso directo en plantilla: {{ venta.campo }}, {{ cliente.campo }}
        'venta': venta,
        'cliente': cliente,
        
        # Propiedades calculadas y formateadas
        'cliente_nombre_completo': cliente.nombre_completo_display.upper(),
        'fecha_contrato': formats.date_format(datetime.now(), r"j \d\e F \d\e Y"),
        'vendedor_nombre': venta.vendedor.get_full_name() or venta.vendedor.username if venta.vendedor else 'No asignado',
        # Dirección del cliente: usar direccion_fiscal si es empresa, o construir desde los campos disponibles
        'cliente_direccion_completa': (
            cliente.direccion_fiscal if cliente.tipo_cliente == 'EMPRESA' and cliente.direccion_fiscal
            else f"{cliente.nombre_completo_display} - {cliente.telefono or 'Sin teléfono'}"
        ),
        
        # Servicios a texto: usar servicios_seleccionados en lugar de campos booleanos eliminados
        'servicios_seleccionados_display': venta.servicios_seleccionados_display if hasattr(venta, 'servicios_seleccionados_display') else venta.servicios_seleccionados or 'No especificado',
        # Mantener compatibilidad con plantillas antiguas usando servicios_seleccionados
        'servicio_vuelo_txt': 'Sí' if venta.servicios_seleccionados and 'VUE' in venta.servicios_seleccionados else 'No',
        'servicio_hospedaje_txt': 'Sí' if venta.servicios_seleccionados and 'HOS' in venta.servicios_seleccionados else 'No',
        'servicio_traslado_txt': 'Sí' if venta.servicios_seleccionados and 'TRA' in venta.servicios_seleccionados else 'No',
        'servicio_tour_txt': 'Sí' if venta.servicios_seleccionados and 'TOU' in venta.servicios_seleccionados else 'No',
        'servicio_circuito_int_txt': 'Sí' if venta.servicios_seleccionados and 'CIR' in venta.servicios_seleccionados else 'No',
        'servicio_renta_auto_txt': 'Sí' if venta.servicios_seleccionados and 'REN' in venta.servicios_seleccionados else 'No',
        'servicio_paquete_txt': 'Sí' if venta.servicios_seleccionados and 'PAQ' in venta.servicios_seleccionados else 'No',
        'servicio_crucero_txt': 'Sí' if venta.servicios_seleccionados and 'CRU' in venta.servicios_seleccionados else 'No',
        'servicio_seguro_txt': 'Sí' if venta.servicios_seleccionados and 'SEG' in venta.servicios_seleccionados else 'No',
        'servicio_tramite_visa_txt': 'No',  # Campo eliminado, mantener compatibilidad
        'servicio_tramite_pasaporte_txt': 'No',  # Campo eliminado, mantener compatibilidad

        # Montos localizados
        'costo_total_localizado': localize(venta.costo_venta_final),
        'monto_apertura_localizado': localize(venta.cantidad_apertura),
        'saldo_pendiente_localizado': localize(venta.saldo_restante),
        
        # Añade otras variables de VentaViaje que se usan en la plantilla de contrato (BD)
        'fecha_inicio_viaje': formats.date_format(venta.fecha_inicio_viaje, r"j \d\e F \d\e Y"),
        'fecha_fin_viaje': formats.date_format(venta.fecha_fin_viaje, r"j \d\e F \d\e Y") if venta.fecha_fin_viaje else 'Fecha no definida',
        'destino_viaje': venta.servicios_detalle_desde_logistica or 'No especificado',  # Usar servicios_detalle_desde_logistica para incluir todos los proveedores
        'pasajeros_detalle': venta.pasajeros or 'No especificado',
        
        # Información detallada de pasajeros (formateada)
        'pasajeros_lista': [p.strip() for p in venta.pasajeros.split('\n') if p.strip()] if venta.pasajeros else [],
        'pasajeros_cantidad': len([p.strip() for p in venta.pasajeros.split('\n') if p.strip()]) if venta.pasajeros else 0,
        'pasajeros_texto': venta.pasajeros.replace('\n', ', ') if venta.pasajeros else 'No especificado',
        
        # Información detallada de servicios (lista y texto)
        'servicios_lista': venta.servicios_seleccionados.split(',') if venta.servicios_seleccionados else [],
        'servicios_cantidad': len(venta.servicios_seleccionados.split(',')) if venta.servicios_seleccionados else 0,
        'servicios_detalle_texto': venta.servicios_detalle_desde_logistica.replace('\n', ', ') if venta.servicios_detalle_desde_logistica else 'No especificado',
        
        # Información adicional del cliente
        'cliente_rfc': cliente.rfc or 'No especificado',
        'cliente_telefono': cliente.telefono or 'No especificado',
        'cliente_email': cliente.email or 'No especificado',
        'cliente_tipo': cliente.get_tipo_cliente_display() if hasattr(cliente, 'get_tipo_cliente_display') else 'No especificado',
    }

    # 4. Sustituir las variables en el contenido base (Motor de Plantillas de Django)
    # ESTE PASO GENERA EL HTML DEL CONTRATO FINAL CON DATOS REALES.
    try:
        template = Template(plantilla.contenido_base)
        context = Context(contexto)
        contenido_final = template.render(context)
        
    except Exception as e:
        logger.error(f"Error al renderizar la plantilla de Django: {e}", exc_info=True)
        contenido_final = (
            f"<p>**ERROR DE RENDERIZADO EN PLANTILLA. REVISAR LA SINTAXIS DE DJANGO.**</p>"
            f"<p>Detalle del error: {e}</p>"
        )

    # 5. Guardar el Contrato Generado (update_or_create evita duplicados)
    contrato, creado = ContratoGenerado.objects.update_or_create(
        venta=venta,
        defaults={
            'plantilla': plantilla,
            'contenido_final': contenido_final,
            'fecha_generacion': datetime.now()
        }
    )
    
    # 6. Generar el PDF si la librería está disponible
    if WEASYPRINT_INSTALLED:
        generar_pdf_contrato(contrato)
    
    return contrato