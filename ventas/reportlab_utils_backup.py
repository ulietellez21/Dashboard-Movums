"""
Utilidades para generar PDFs de cotizaciones usando ReportLab.
Proporciona funciones helper para crear documentos PDF bien formateados
con control preciso sobre tablas y layout.
"""
from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, Image, KeepTogether, PageTemplate, BaseDocTemplate, Frame
)
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ==================== CONSTANTES DE COLOR ====================

MOVUMS_BLUE_CORP = colors.HexColor('#004a8e')  # Color corporativo #004a8e
MOVUMS_BLUE = colors.HexColor('#0f5cc0')
MOVUMS_LIGHT_BLUE = colors.HexColor('#5c8dd6')
TEXT_COLOR = colors.HexColor('#141414')


# ==================== ESTILOS GLOBALES ====================

def get_custom_styles():
    """Retorna un diccionario con estilos personalizados para el PDF."""
    styles = getSampleStyleSheet()
    
    # Estilo para títulos principales (con fondo azul)
    styles.add(ParagraphStyle(
        name='TituloSeccion',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.white,
        spaceAfter=10,
        spaceBefore=12,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        backColor=MOVUMS_BLUE_CORP,
        leading=22
    ))
    
    # Estilo para subtítulos con viñeta (azul corporativo)
    styles.add(ParagraphStyle(
        name='SubtituloVineta',
        parent=styles['Normal'],
        fontSize=14,
        textColor=MOVUMS_BLUE_CORP,
        spaceAfter=4,
        spaceBefore=10,
        fontName='Helvetica-Bold',
        leading=16
    ))
    
    # Estilo para información de cliente
    styles.add(ParagraphStyle(
        name='InfoCliente',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        alignment=TA_CENTER,
        spaceAfter=10
    ))
    
    # Estilo para texto normal
    styles.add(ParagraphStyle(
        name='TextoNormal',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        leading=14
    ))
    
    # Estilo para etiquetas (negrita)
    styles.add(ParagraphStyle(
        name='Etiqueta',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        fontName='Helvetica-Bold',
        leading=14
    ))
    
    # Estilo para totales (azul, grande, negrita, subrayado)
    styles.add(ParagraphStyle(
        name='Total',
        parent=styles['Normal'],
        fontSize=18,
        textColor=MOVUMS_BLUE_CORP,
        fontName='Helvetica-Bold',
        alignment=TA_LEFT,
        spaceBefore=0,
        spaceAfter=6,
        leading=22
    ))
    
    # Estilo para encabezados de tabla
    styles.add(ParagraphStyle(
        name='EncabezadoTabla',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.white,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER
    ))
    
    # Estilo para celdas de tabla
    styles.add(ParagraphStyle(
        name='CeldaTabla',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.black,
        leading=14
    ))
    
    return styles


# ==================== FUNCIONES HELPER ====================

def format_currency(value):
    """Formatea un valor decimal como moneda mexicana."""
    if value is None:
        return "$0.00 MXN"
    try:
        if isinstance(value, str):
            value = Decimal(value)
        return f"${value:,.2f} MXN"
    except (ValueError, InvalidOperation):
        return "$0.00 MXN"


def format_date(date_value, format_str="%d/%m/%Y"):
    """Formatea una fecha."""
    if date_value is None:
        return "-"
    if isinstance(date_value, str):
        try:
            date_value = datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            return date_value
    if hasattr(date_value, 'strftime'):
        return date_value.strftime(format_str)
    return str(date_value)


def safe_get(data, *keys, default="-"):
    """Obtiene un valor de un diccionario anidado de forma segura."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return current if current != "" else default


# ==================== GENERADORES DE TABLAS ====================

def create_info_table(header, rows, col_widths=None, style_overrides=None):
    """
    Crea una tabla de información con encabezado y filas.
    
    Args:
        header: Lista de strings para el encabezado
        rows: Lista de listas con los datos de cada fila
        col_widths: Lista de anchos de columna (opcional)
        style_overrides: Diccionario con estilos personalizados (opcional)
    
    Returns:
        Table de ReportLab lista para agregar al documento
    """
    styles = get_custom_styles()
    
    # Preparar datos con estilos
    data = []
    
    # Encabezado
    header_cells = [Paragraph(cell, styles['EncabezadoTabla']) for cell in header]
    data.append(header_cells)
    
    # Filas de datos
    for row in rows:
        row_cells = [Paragraph(str(cell) if cell else "-", styles['CeldaTabla']) for cell in row]
        data.append(row_cells)
    
    # Calcular anchos de columna si no se proporcionan
    if col_widths is None:
        num_cols = len(header)
        if num_cols == 2:
            col_widths = [6*cm, 12*cm]  # Columna label y columna valor
        elif num_cols == 3:
            col_widths = [5*cm, 5*cm, 8*cm]
        elif num_cols == 4:
            col_widths = [4*cm, 4*cm, 4*cm, 6*cm]
        else:
            col_widths = [17*cm / num_cols] * num_cols
    
    # Crear tabla
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    # Aplicar estilos
    table_style = [
        # Encabezado
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#004a8e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        
        # Cuerpo de la tabla
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Filas alternadas
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fb')]),
    ]
    
    # Aplicar estilos personalizados si se proporcionan
    if style_overrides:
        table_style.extend(style_overrides)
    
    table.setStyle(TableStyle(table_style))
    
    return table


def create_simple_info_table(data_dict, label_width=6*cm, value_width=11*cm):
    """
    Crea una tabla simple de dos columnas (Etiqueta | Valor).
    
    Args:
        data_dict: Diccionario con {etiqueta: valor}
        label_width: Ancho de la columna de etiqueta
        value_width: Ancho de la columna de valor
    
    Returns:
        Table de ReportLab
    """
    rows = [[key, value] for key, value in data_dict.items() if value]
    
    return create_info_table(
        header=["", ""],  # Sin encabezado visible
        rows=rows,
        col_widths=[label_width, value_width],
        style_overrides=[
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),  # Labels en negrita
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]
    )


# ==================== GENERADORES ESPECÍFICOS POR TIPO ====================

def generate_vuelos_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo vuelos."""
    elements = []
    styles = get_custom_styles()
    
    vuelos = propuestas.get('vuelos', [])
    if not vuelos:
        return elements
    
    elements.append(Paragraph("Propuestas de Vuelos", styles['SubtituloSeccion']))
    elements.append(Spacer(1, 0.3*cm))
    
    for idx, vuelo in enumerate(vuelos, 1):
        # Información básica del vuelo
        info_data = {
            "Opción": f"Opción {idx}",
            "Aerolínea": safe_get(vuelo, 'aerolinea', default="-"),
            "Salida": safe_get(vuelo, 'salida', default="-"),
            "Regreso": safe_get(vuelo, 'regreso', default="-"),
            "Incluye": safe_get(vuelo, 'incluye', default="-"),
            "Forma de pago": safe_get(vuelo, 'forma_pago', default="-"),
        }
        
        table = create_simple_info_table(info_data)
        elements.append(KeepTogether(table))
        
        # Total
        total = safe_get(vuelo, 'total', default="0")
        total_formatted = format_currency(total)
        elements.append(Spacer(1, 0.2*cm))
        elements.append(Paragraph(f"<b>Total:</b> {total_formatted}", styles['Total']))
        
        # Espaciado entre opciones
        if idx < len(vuelos):
            elements.append(Spacer(1, 0.5*cm))
    
    return elements


def generate_hospedaje_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo hospedaje."""
    elements = []
    styles = get_custom_styles()
    
    hoteles = propuestas.get('hoteles', [])
    if not hoteles:
        return elements
    
    elements.append(Paragraph("Propuestas de Hospedaje", styles['SubtituloSeccion']))
    elements.append(Spacer(1, 0.3*cm))
    
    for idx, hotel in enumerate(hoteles, 1):
        info_data = {
            "Opción": f"Opción {idx}",
            "Hotel": safe_get(hotel, 'nombre', default="-"),
            "Habitación": safe_get(hotel, 'habitacion', default="-"),
            "Plan": safe_get(hotel, 'plan', default="-"),
            "Dirección": safe_get(hotel, 'direccion', default="-"),
            "Forma de pago": safe_get(hotel, 'forma_pago', default="-"),
        }
        
        table = create_simple_info_table(info_data)
        elements.append(KeepTogether(table))
        
        # Total
        total = safe_get(hotel, 'total', default="0")
        total_formatted = format_currency(total)
        elements.append(Spacer(1, 0.2*cm))
        elements.append(Paragraph(f"<b>Total:</b> {total_formatted}", styles['Total']))
        
        # Espaciado entre opciones
        if idx < len(hoteles):
            elements.append(Spacer(1, 0.5*cm))
    
    return elements


def generate_paquete_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo paquete."""
    elements = []
    styles = get_custom_styles()
    
    paquete = propuestas.get('paquete', {})
    if not paquete:
        return elements
    
    elements.append(Paragraph("Paquete Completo", styles['SubtituloSeccion']))
    elements.append(Spacer(1, 0.3*cm))
    
    # Sección Vuelo
    vuelo = paquete.get('vuelo', {})
    if vuelo:
        elements.append(Paragraph("Vuelo", styles['SubtituloSeccion']))
        vuelo_data = {
            "Aerolínea": safe_get(vuelo, 'aerolinea', default="-"),
            "Salida": safe_get(vuelo, 'salida', default="-"),
            "Regreso": safe_get(vuelo, 'regreso', default="-"),
            "Incluye": safe_get(vuelo, 'incluye', default="-"),
            "Forma de pago": safe_get(vuelo, 'forma_pago', default="-"),
        }
        table = create_simple_info_table(vuelo_data)
        elements.append(KeepTogether(table))
        
        total_vuelo = safe_get(vuelo, 'total', default="0")
        if total_vuelo != "-":
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Total Vuelo:</b> {format_currency(total_vuelo)}", styles['Total']))
        
        elements.append(Spacer(1, 0.5*cm))
    
    # Sección Hotel
    hotel = paquete.get('hotel', {})
    if hotel:
        elements.append(Paragraph("Hospedaje", styles['SubtituloSeccion']))
        hotel_data = {
            "Hotel": safe_get(hotel, 'nombre', default="-"),
            "Habitación": safe_get(hotel, 'habitacion', default="-"),
            "Dirección": safe_get(hotel, 'direccion', default="-"),
            "Plan": safe_get(hotel, 'plan', default="-"),
            "Notas": safe_get(hotel, 'notas', default="-"),
            "Forma de pago": safe_get(hotel, 'forma_pago', default="-"),
        }
        table = create_simple_info_table(hotel_data)
        elements.append(KeepTogether(table))
        
        total_hotel = safe_get(hotel, 'total', default="0")
        if total_hotel != "-":
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Total Hospedaje:</b> {format_currency(total_hotel)}", styles['Total']))
        
        elements.append(Spacer(1, 0.5*cm))
    
    # Tours del paquete
    tours = paquete.get('tours', [])
    if tours:
        elements.append(Paragraph("Tours Incluidos", styles['SubtituloSeccion']))
        for idx, tour in enumerate(tours, 1):
            tour_data = {
                "Tour": f"{idx}. {safe_get(tour, 'nombre', default='Tour sin nombre')}",
                "Forma de pago": safe_get(tour, 'forma_pago', default="-"),
            }
            table = create_simple_info_table(tour_data)
            elements.append(KeepTogether(table))
            
            total_tour = safe_get(tour, 'total', default="0")
            if total_tour != "-":
                elements.append(Spacer(1, 0.2*cm))
                elements.append(Paragraph(f"<b>Total Tour:</b> {format_currency(total_tour)}", styles['Total']))
            
            # Especificaciones
            especificaciones = safe_get(tour, 'especificaciones', default="")
            if especificaciones != "-":
                elements.append(Spacer(1, 0.2*cm))
                elements.append(Paragraph("<b>Especificaciones:</b>", styles['TextoNormal']))
                elements.append(Paragraph(especificaciones, styles['TextoNormal']))
            
            if idx < len(tours):
                elements.append(Spacer(1, 0.3*cm))
    
    # Total del paquete
    total_paquete = safe_get(paquete, 'total', default="0")
    if total_paquete != "-":
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph(f"<b>TOTAL DEL PAQUETE:</b> {format_currency(total_paquete)}", styles['Total']))
    
    return elements


def generate_tours_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo tours."""
    elements = []
    styles = get_custom_styles()
    
    tours = propuestas.get('tours', [])
    if not tours:
        # Compatibilidad: puede ser un objeto único
        tours = [propuestas.get('tours', {})] if propuestas.get('tours') else []
    
    if not tours or (len(tours) == 1 and not tours[0]):
        return elements
    
    elements.append(Paragraph("Tours", styles['SubtituloSeccion']))
    elements.append(Spacer(1, 0.3*cm))
    
    for idx, tour in enumerate(tours, 1):
        tour_data = {
            "Tour": f"{idx}. {safe_get(tour, 'nombre', default='Tour sin nombre')}",
            "Forma de pago": safe_get(tour, 'forma_pago', default="-"),
        }
        table = create_simple_info_table(tour_data)
        elements.append(KeepTogether(table))
        
        total = safe_get(tour, 'total', default="0")
        if total != "-":
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Total:</b> {format_currency(total)}", styles['Total']))
        
        # Especificaciones
        especificaciones = safe_get(tour, 'especificaciones', default="")
        if especificaciones != "-":
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph("<b>Especificaciones:</b>", styles['TextoNormal']))
            elements.append(Paragraph(especificaciones, styles['TextoNormal']))
        
        if idx < len(tours):
            elements.append(Spacer(1, 0.5*cm))
    
    return elements


def generate_traslados_table(propuestas):
    """Genera tabla para cotizaciones de tipo traslados."""
    elements = []
    styles = get_custom_styles()
    
    traslados = propuestas.get('traslados', {})
    if not traslados:
        return elements
    
    elements.append(Paragraph("Traslado", styles['SubtituloSeccion']))
    elements.append(Spacer(1, 0.3*cm))
    
    traslado_data = {
        "Tipo": safe_get(traslados, 'tipo', default="-"),
        "Modalidad": safe_get(traslados, 'modalidad', default="-"),
        "Desde": safe_get(traslados, 'desde', default="-"),
        "Hasta": safe_get(traslados, 'hasta', default="-"),
    }
    
    # Fechas y horas si es redondo
    if safe_get(traslados, 'modalidad') == 'REDONDO':
        traslado_data["Fecha Ida"] = safe_get(traslados, 'fecha_ida', default="-")
        traslado_data["Fecha Regreso"] = safe_get(traslados, 'fecha_regreso', default="-")
        traslado_data["Hora Ida"] = safe_get(traslados, 'hora_ida', default="-")
        traslado_data["Hora Regreso"] = safe_get(traslados, 'hora_regreso', default="-")
    
    traslado_data["Forma de pago"] = safe_get(traslados, 'forma_pago', default="-")
    
    table = create_simple_info_table(traslado_data)
    elements.append(KeepTogether(table))
    
    # Descripción
    descripcion = safe_get(traslados, 'descripcion', default="")
    if descripcion != "-":
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph("<b>Descripción:</b>", styles['TextoNormal']))
        elements.append(Paragraph(descripcion, styles['TextoNormal']))
    
    # Total
    total = safe_get(traslados, 'total', default="0")
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"<b>Total:</b> {format_currency(total)}", styles['Total']))
    
    return elements


def generate_renta_autos_table(propuestas):
    """Genera tabla para cotizaciones de tipo renta de autos."""
    elements = []
    styles = get_custom_styles()
    
    renta = propuestas.get('renta_autos', {})
    if not renta:
        return elements
    
    elements.append(Paragraph("Renta de Autos", styles['SubtituloSeccion']))
    elements.append(Spacer(1, 0.3*cm))
    
    renta_data = {
        "Arrendadora": safe_get(renta, 'arrendadora', default="-"),
        "Punto de Origen": safe_get(renta, 'punto_origen', default="-"),
        "Punto de Regreso": safe_get(renta, 'punto_regreso', default="-"),
        "Hora Pickup": safe_get(renta, 'hora_pickup', default="-"),
        "Hora Devolución": safe_get(renta, 'hora_devolucion', default="-"),
        "Forma de pago": safe_get(renta, 'forma_pago', default="-"),
    }
    
    table = create_simple_info_table(renta_data)
    elements.append(KeepTogether(table))
    
    # Total
    total = safe_get(renta, 'total', default="0")
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"<b>Total:</b> {format_currency(total)}", styles['Total']))
    
    return elements


def generate_generica_table(propuestas):
    """Genera contenido para cotizaciones genéricas."""
    elements = []
    styles = get_custom_styles()
    
    generica = propuestas.get('generica', {})
    if not generica:
        return elements
    
    contenido = safe_get(generica, 'contenido', default="Sin contenido específico.")
    
    elements.append(Paragraph("Detalles de la Cotización", styles['SubtituloSeccion']))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(contenido, styles['TextoNormal']))
    
    return elements


# ==================== FUNCIÓN PRINCIPAL ====================

def generate_cotizacion_pdf(cotizacion):
    """
    Función principal que genera el PDF completo de una cotización usando ReportLab.
    
    Args:
        cotizacion: Objeto Cotizacion de Django
    
    Returns:
        BytesIO: Buffer con el contenido del PDF
    """
    from django.conf import settings
    import os
    
    # Crear buffer para el PDF
    buffer = BytesIO()
    
    # Obtener estilos
    styles = get_custom_styles()
    
    # Crear documento
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # Lista de elementos para el PDF
    story = []
    
    # ==================== ENCABEZADO ====================
    
    # Título principal
    story.append(Paragraph("COTIZACIÓN DE SERVICIOS TURÍSTICOS", styles['TituloPrincipal']))
    story.append(Spacer(1, 0.5*cm))
    
    # Información del folio y fecha
    folio = cotizacion.folio or f"COT-{cotizacion.id}"
    fecha_generacion = format_date(cotizacion.actualizada_en or cotizacion.creada_en, "%d/%m/%Y %H:%M")
    story.append(Paragraph(
        f"<b>Folio:</b> {folio} | <b>Fecha:</b> {fecha_generacion}",
        styles['InfoCliente']
    ))
    story.append(Spacer(1, 0.5*cm))
    
    # ==================== INFORMACIÓN DEL CLIENTE ====================
    
    cliente_info = {
        "Cliente": cotizacion.cliente.nombre_completo_display,
        "Tipo": cotizacion.cliente.get_tipo_cliente_display() if hasattr(cotizacion.cliente, 'get_tipo_cliente_display') else "-",
        "Asesor": cotizacion.vendedor.username if cotizacion.vendedor else "-",
    }
    
    cliente_table = create_simple_info_table(cliente_info)
    story.append(Paragraph("Información del Cliente", styles['SubtituloSeccion']))
    story.append(KeepTogether(cliente_table))
    story.append(Spacer(1, 0.5*cm))
    
    # ==================== INFORMACIÓN DEL VIAJE ====================
    
    tipo = cotizacion.propuestas.get('tipo', 'generica') if isinstance(cotizacion.propuestas, dict) else 'generica'
    
    viaje_info = {}
    
    if tipo == 'traslados':
        viaje_info["Desde"] = cotizacion.propuestas.get('traslados', {}).get('desde', cotizacion.origen) or "-"
        viaje_info["Hasta"] = cotizacion.propuestas.get('traslados', {}).get('hasta', cotizacion.destino) or "-"
    elif tipo == 'renta_autos':
        viaje_info["Punto de Origen"] = cotizacion.propuestas.get('renta_autos', {}).get('punto_origen', "-")
        viaje_info["Punto de Regreso"] = cotizacion.propuestas.get('renta_autos', {}).get('punto_regreso', "-")
    else:
        viaje_info["Origen"] = cotizacion.origen or "-"
        viaje_info["Destino"] = cotizacion.destino or "-"
        if cotizacion.fecha_inicio:
            viaje_info["Fecha Inicio"] = format_date(cotizacion.fecha_inicio)
        if cotizacion.fecha_fin:
            viaje_info["Fecha Fin"] = format_date(cotizacion.fecha_fin)
        viaje_info["Días"] = str(cotizacion.dias) if cotizacion.dias else "-"
        viaje_info["Noches"] = str(cotizacion.noches) if cotizacion.noches else "-"
    
    if viaje_info:
        story.append(Paragraph("Datos del Viaje", styles['SubtituloSeccion']))
        viaje_table = create_simple_info_table(viaje_info)
        story.append(KeepTogether(viaje_table))
        story.append(Spacer(1, 0.5*cm))
    
    # ==================== INFORMACIÓN DE PASAJEROS ====================
    
    pasajeros_info = {
        "Total Pasajeros": str(cotizacion.pasajeros),
        "Adultos": str(cotizacion.adultos),
        "Menores": str(cotizacion.menores),
    }
    
    if cotizacion.edades_menores:
        pasajeros_info["Edades de Menores"] = cotizacion.edades_menores
    
    story.append(Paragraph("Pasajeros", styles['SubtituloSeccion']))
    pasajeros_table = create_simple_info_table(pasajeros_info)
    story.append(KeepTogether(pasajeros_table))
    story.append(Spacer(1, 0.5*cm))
    
    # ==================== NOTAS ====================
    
    if cotizacion.notas:
        story.append(Paragraph("Notas", styles['SubtituloSeccion']))
        story.append(Paragraph(cotizacion.notas, styles['TextoNormal']))
        story.append(Spacer(1, 0.5*cm))
    
    # ==================== PROPUESTAS (SEGÚN TIPO) ====================
    
    propuestas = cotizacion.propuestas if isinstance(cotizacion.propuestas, dict) else {}
    
    if tipo == 'vuelos':
        story.extend(generate_vuelos_table(propuestas))
    elif tipo == 'hospedaje':
        story.extend(generate_hospedaje_table(propuestas))
    elif tipo == 'paquete':
        story.extend(generate_paquete_table(propuestas))
    elif tipo == 'tours':
        story.extend(generate_tours_table(propuestas))
    elif tipo == 'traslados':
        story.extend(generate_traslados_table(propuestas))
    elif tipo == 'renta_autos':
        story.extend(generate_renta_autos_table(propuestas))
    else:
        story.extend(generate_generica_table(propuestas))
    
    # ==================== TOTAL ESTIMADO (si aplica) ====================
    
    if cotizacion.total_estimado and cotizacion.total_estimado > 0:
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"<b>TOTAL ESTIMADO:</b> {format_currency(cotizacion.total_estimado)}",
            styles['Total']
        ))
    
    # ==================== ESTADO ====================
    
    story.append(Spacer(1, 0.5*cm))
    estado_display = cotizacion.get_estado_display() if hasattr(cotizacion, 'get_estado_display') else cotizacion.estado
    story.append(Paragraph(f"<b>Estado:</b> {estado_display}", styles['TextoNormal']))
    
    # ==================== GENERAR PDF ====================
    
    doc.build(story)
    buffer.seek(0)
    
    return buffer

