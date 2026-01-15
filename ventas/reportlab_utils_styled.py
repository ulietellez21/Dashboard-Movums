"""
Utilidades para generar PDFs de cotizaciones usando ReportLab.
Recrea el formato visual anterior con mejor control de tablas.
"""
from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch, pt
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


# ==================== CONSTANTES DE COLOR ====================

MOVUMS_BLUE_CORP = colors.HexColor('#004a8e')  # Color corporativo #004a8e


# ==================== FUNCIONES HELPER ====================

def format_currency(value):
    """Formatea un valor decimal como moneda mexicana."""
    if value is None:
        return "$0.00"
    try:
        if isinstance(value, str):
            value = Decimal(value)
        return f"${value:,.2f}"
    except (ValueError, InvalidOperation):
        return "$0.00"


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


# ==================== FUNCIONES DE FORMATO ====================

def create_titulo_seccion(texto):
    """Crea un título de sección con fondo azul oscuro y texto blanco (ej: VUELO, HOSPEDAJE)."""
    # Crear una tabla de una celda con fondo azul para simular el título con fondo
    data = [[Paragraph(texto.upper(), get_titulo_seccion_style())]]
    table = Table(data, colWidths=[17*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), MOVUMS_BLUE_CORP),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 18),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0, MOVUMS_BLUE_CORP),  # Sin bordes visibles, solo fondo
    ]))
    return table


def get_titulo_seccion_style():
    """Retorna el estilo para títulos de sección."""
    styles = getSampleStyleSheet()
    if 'TituloSeccion' not in styles.byName:
        styles.add(ParagraphStyle(
            name='TituloSeccion',
            parent=styles['Normal'],
            fontSize=18,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            leading=22
        ))
    return styles['TituloSeccion']


def create_subtitulo_vineta(texto):
    """Crea un subtítulo con viñeta azul (ej: • Información del Vuelo)."""
    styles = getSampleStyleSheet()
    if 'SubtituloVineta' not in styles.byName:
        styles.add(ParagraphStyle(
            name='SubtituloVineta',
            parent=styles['Normal'],
            fontSize=14,
            textColor=MOVUMS_BLUE_CORP,
            fontName='Helvetica-Bold',
            leading=16,
            spaceBefore=10,
            spaceAfter=4
        ))
    
    # Crear párrafo con viñeta azul
    vineta_text = f"<font color='#004a8e'><b>•</b></font> <font color='#004a8e'><b>{texto}</b></font>"
    return Paragraph(vineta_text, styles['SubtituloVineta'])


def create_info_line(etiqueta, valor):
    """Crea una línea de información con etiqueta en negrita y valor normal."""
    if not valor or valor == "-":
        return None
    
    styles = getSampleStyleSheet()
    if 'InfoLine' not in styles.byName:
        styles.add(ParagraphStyle(
            name='InfoLine',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.black,
            leading=14,
            spaceAfter=4
        ))
    
    texto = f"<b>{etiqueta}:</b> {str(valor)}"
    return Paragraph(texto, styles['InfoLine'])


def create_info_inline(pares_etiqueta_valor, separador=" | "):
    """Crea múltiples campos en una sola línea separados por |."""
    if not pares_etiqueta_valor:
        return None
    
    styles = getSampleStyleSheet()
    if 'InfoLine' not in styles.byName:
        styles.add(ParagraphStyle(
            name='InfoLine',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.black,
            leading=14,
            spaceAfter=4
        ))
    
    partes = []
    for etiqueta, valor in pares_etiqueta_valor:
        if valor and valor != "-":
            partes.append(f"<b>{etiqueta}:</b> {str(valor)}")
    
    if not partes:
        return None
    
    texto = separador.join(partes)
    return Paragraph(texto, styles['InfoLine'])


def create_total(total_value):
    """Crea el total en azul, tamaño 18, negrita y subrayado."""
    styles = getSampleStyleSheet()
    if 'Total' not in styles.byName:
        styles.add(ParagraphStyle(
            name='Total',
            parent=styles['Normal'],
            fontSize=18,
            textColor=MOVUMS_BLUE_CORP,
            fontName='Helvetica-Bold',
            leading=22,
            spaceBefore=0,
            spaceAfter=6
        ))
    
    total_formatted = format_currency(total_value)
    texto = f"Total MXN {total_formatted} Pesos"
    # Usar HTML para subrayado ya que ReportLab no tiene underline directo en ParagraphStyle
    para = Paragraph(f"<u>{texto}</u>", styles['Total'])
    return para


def create_hospedaje_info_table(hotel):
    """Crea una tabla de 2 columnas para información de hospedaje."""
    # Preparar datos para la tabla
    data = []
    
    # Fila 1: Nombre | Plan de Alimentos
    nombre = safe_get(hotel, 'nombre', default="-")
    plan = safe_get(hotel, 'plan', default="-")
    data.append([
        Paragraph(f"<b>Nombre:</b> {nombre}", get_texto_style()),
        Paragraph(f"<b>Plan de Alimentos:</b> {plan}", get_texto_style())
    ])
    
    # Fila 2: Habitación | Forma de Pago (si existe)
    habitacion = safe_get(hotel, 'habitacion', default="-")
    forma_pago = safe_get(hotel, 'forma_pago', default=None)
    if forma_pago:
        data.append([
            Paragraph(f"<b>Habitación:</b> {habitacion}", get_texto_style()),
            Paragraph(f"<b>Forma de Pago:</b> {forma_pago}", get_texto_style())
        ])
    else:
        data.append([
            Paragraph(f"<b>Habitación:</b> {habitacion}", get_texto_style()),
            Paragraph("", get_texto_style())
        ])
    
    # Fila 3: Dirección | (vacío)
    direccion = safe_get(hotel, 'direccion', default="-")
    data.append([
        Paragraph(f"<b>Dirección:</b> {direccion}", get_texto_style()),
        Paragraph("", get_texto_style())
    ])
    
    # Fila 4: Notas (si existe) | (vacío)
    notas = safe_get(hotel, 'notas', default=None)
    if notas and notas != "-":
        data.append([
            Paragraph(f"<b>Notas:</b> {notas}", get_texto_style()),
            Paragraph("", get_texto_style())
        ])
    
    # Crear tabla con 2 columnas de igual ancho
    table = Table(data, colWidths=[8.5*cm, 8.5*cm])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        # Sin bordes, solo espaciado
    ]))
    
    return table


def get_texto_style():
    """Retorna el estilo para texto normal."""
    styles = getSampleStyleSheet()
    if 'TextoNormal' not in styles.byName:
        styles.add(ParagraphStyle(
            name='TextoNormal',
            parent=styles['Normal'],
            fontSize=12,
            textColor=colors.black,
            leading=14
        ))
    return styles['TextoNormal']


def create_salto():
    """Crea un salto de línea entre secciones."""
    return Spacer(1, 0.4*cm)


# ==================== GENERADORES ESPECÍFICOS POR TIPO ====================

def generate_vuelos_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo vuelos con formato visual anterior."""
    elements = []
    
    vuelos = propuestas.get('vuelos', [])
    if not vuelos:
        return elements
    
    for idx, vuelo in enumerate(vuelos, 1):
        # Título principal con fondo azul
        elements.append(create_titulo_seccion("VUELO"))
        elements.append(Spacer(1, 0.2*cm))
        
        # Subtítulo con viñeta
        elements.append(create_subtitulo_vineta("Información del Vuelo"))
        
        # Información inline (Aerolínea | Salida | Regreso)
        info_inline = create_info_inline([
            ('Aerolínea', safe_get(vuelo, 'aerolinea', default="-")),
            ('Salida', safe_get(vuelo, 'salida', default="-")),
            ('Regreso', safe_get(vuelo, 'regreso', default="-"))
        ])
        if info_inline:
            elements.append(info_inline)
        
        # Incluye
        incluye = safe_get(vuelo, 'incluye', default=None)
        if incluye and incluye != "-":
            incluye_line = create_info_line('Incluye', incluye)
            if incluye_line:
                elements.append(incluye_line)
        
        # Forma de pago si está presente
        forma_pago = safe_get(vuelo, 'forma_pago', default=None)
        if forma_pago and forma_pago != "-":
            forma_pago_line = create_info_line('Forma de Pago', forma_pago)
            if forma_pago_line:
                elements.append(forma_pago_line)
        
        # Total
        total = safe_get(vuelo, 'total', default="0")
        total_para = create_total(total)
        elements.append(total_para)
        
        # Salto entre secciones (excepto en el último)
        if idx < len(vuelos):
            elements.append(create_salto())
    
    return elements


def generate_hospedaje_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo hospedaje con formato visual anterior."""
    elements = []
    
    hoteles = propuestas.get('hoteles', [])
    if not hoteles:
        return elements
    
    for idx, hotel in enumerate(hoteles, 1):
        # Título principal con fondo azul
        elements.append(create_titulo_seccion("HOSPEDAJE"))
        elements.append(Spacer(1, 0.2*cm))
        
        # Subtítulo con viñeta
        elements.append(create_subtitulo_vineta("Información del Alojamiento"))
        
        # Tabla de 2 columnas con información
        info_table = create_hospedaje_info_table(hotel)
        elements.append(KeepTogether(info_table))
        
        # Total
        total = safe_get(hotel, 'total', default="0")
        total_para = create_total(total)
        elements.append(total_para)
        
        # Salto entre secciones (excepto en el último)
        if idx < len(hoteles):
            elements.append(create_salto())
    
    return elements


def generate_paquete_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo paquete con formato visual anterior."""
    elements = []
    
    paquete = propuestas.get('paquete', {})
    if not paquete:
        return elements
    
    # Título principal
    elements.append(create_titulo_seccion("PAQUETE"))
    elements.append(Spacer(1, 0.2*cm))
    
    # Sección Vuelo
    vuelo = paquete.get('vuelo', {})
    if vuelo:
        elements.append(create_subtitulo_vineta("Vuelo"))
        
        # Información inline
        info_inline = create_info_inline([
            ('Aerolínea', safe_get(vuelo, 'aerolinea', default="-")),
            ('Salida', safe_get(vuelo, 'salida', default="-")),
            ('Regreso', safe_get(vuelo, 'regreso', default="-"))
        ])
        if info_inline:
            elements.append(info_inline)
        
        # Incluye
        incluye = safe_get(vuelo, 'incluye', default=None)
        if incluye and incluye != "-":
            incluye_line = create_info_line('Incluye', incluye)
            if incluye_line:
                elements.append(incluye_line)
        
        # Total y Forma de pago del vuelo
        total_vuelo = safe_get(vuelo, 'total', default=None)
        if total_vuelo and total_vuelo != "-":
            total_vuelo_line = create_info_line('Total MXN', format_currency(total_vuelo))
            if total_vuelo_line:
                elements.append(total_vuelo_line)
        
        forma_pago_vuelo = safe_get(vuelo, 'forma_pago', default=None)
        if forma_pago_vuelo and forma_pago_vuelo != "-":
            forma_pago_line = create_info_line('Forma de Pago', forma_pago_vuelo)
            if forma_pago_line:
                elements.append(forma_pago_line)
        
        elements.append(create_salto())
    
    # Sección Hospedaje
    hotel = paquete.get('hotel', {})
    if hotel:
        elements.append(create_subtitulo_vineta("Hospedaje"))
        
        # Tabla de 2 columnas
        info_table = create_hospedaje_info_table(hotel)
        elements.append(KeepTogether(info_table))
        
        # Total y Forma de pago del hotel
        total_hotel = safe_get(hotel, 'total', default=None)
        if total_hotel and total_hotel != "-":
            total_hotel_line = create_info_line('Total MXN', format_currency(total_hotel))
            if total_hotel_line:
                elements.append(total_hotel_line)
        
        forma_pago_hotel = safe_get(hotel, 'forma_pago', default=None)
        if forma_pago_hotel and forma_pago_hotel != "-":
            forma_pago_line = create_info_line('Forma de Pago', forma_pago_hotel)
            if forma_pago_line:
                elements.append(forma_pago_line)
        
        # Forma de pago del paquete
        forma_pago_paquete = safe_get(paquete, 'forma_pago', default=None)
        if forma_pago_paquete and forma_pago_paquete != "-":
            forma_pago_line = create_info_line('Forma de Pago del Paquete', forma_pago_paquete)
            if forma_pago_line:
                elements.append(forma_pago_line)
        
        elements.append(create_salto())
    
    # Total del paquete
    total_paquete = safe_get(paquete, 'total', default="0")
    if total_paquete and total_paquete != "-":
        total_para = create_total(total_paquete)
        elements.append(total_para)
    
    return elements


def generate_tours_table(propuestas):
    """Genera tabla(s) para cotizaciones de tipo tours con formato visual anterior."""
    elements = []
    
    tours = propuestas.get('tours', [])
    if not tours:
        # Compatibilidad: puede ser un objeto único
        if propuestas.get('tours'):
            tours = [propuestas.get('tours')]
        else:
            return elements
    
    for idx, tour in enumerate(tours, 1):
        # Título principal
        elements.append(create_titulo_seccion("TOUR"))
        elements.append(Spacer(1, 0.2*cm))
        
        elements.append(create_subtitulo_vineta("Información del Tour"))
        
        # Información del tour
        numero_reserva = safe_get(tour, 'numero_reserva', default=None)
        if numero_reserva and numero_reserva != "-":
            elements.append(create_info_line('Número de Reserva', numero_reserva))
        
        nombre = safe_get(tour, 'nombre', default=None)
        if nombre and nombre != "-":
            elements.append(create_info_line('Nombre del Tour', nombre))
        
        # Especificaciones si existen
        especificaciones = safe_get(tour, 'especificaciones', default=None)
        if especificaciones and especificaciones != "-":
            elements.append(create_salto())
            elements.append(create_subtitulo_vineta("Especificaciones"))
            
            # Dividir por líneas
            lineas = especificaciones.split('\n')
            for linea in lineas:
                if linea.strip():
                    para = Paragraph(linea.strip(), get_texto_style())
                    elements.append(para)
                    elements.append(Spacer(1, 0.2*cm))
        
        # Forma de pago
        forma_pago = safe_get(tour, 'forma_pago', default=None)
        if forma_pago and forma_pago != "-":
            elements.append(create_salto())
            elements.append(create_subtitulo_vineta("Forma de Pago"))
            elements.append(create_info_line('Forma de Pago', forma_pago))
        
        # Total si existe
        total = safe_get(tour, 'total', default=None)
        if total and total != "-":
            total_para = create_total(total)
            elements.append(total_para)
        
        if idx < len(tours):
            elements.append(create_salto())
    
    return elements


def generate_traslados_table(propuestas):
    """Genera tabla para cotizaciones de tipo traslados."""
    elements = []
    
    traslados = propuestas.get('traslados', {})
    if not traslados:
        return elements
    
    # Título principal
    elements.append(create_titulo_seccion("TRASLADO"))
    elements.append(Spacer(1, 0.2*cm))
    
    # Información
    tipo = safe_get(traslados, 'tipo', default=None)
    modalidad = safe_get(traslados, 'modalidad', default=None)
    
    elements.append(create_info_line('Desde', safe_get(traslados, 'desde', default="-")))
    elements.append(create_info_line('Hasta', safe_get(traslados, 'hasta', default="-")))
    
    if tipo and tipo != "-":
        elements.append(create_info_line('Tipo', tipo))
    if modalidad and modalidad != "-":
        elements.append(create_info_line('Modalidad', modalidad))
    
    # Fechas y horas si es redondo
    if modalidad == 'REDONDO':
        fecha_ida = safe_get(traslados, 'fecha_ida', default=None)
        fecha_regreso = safe_get(traslados, 'fecha_regreso', default=None)
        hora_ida = safe_get(traslados, 'hora_ida', default=None)
        hora_regreso = safe_get(traslados, 'hora_regreso', default=None)
        
        if fecha_ida and fecha_ida != "-":
            elements.append(create_info_line('Fecha de Ida', fecha_ida))
        if fecha_regreso and fecha_regreso != "-":
            elements.append(create_info_line('Fecha de Regreso', fecha_regreso))
        if hora_ida and hora_ida != "-":
            elements.append(create_info_line('Hora de Ida', hora_ida))
        if hora_regreso and hora_regreso != "-":
            elements.append(create_info_line('Hora de Regreso', hora_regreso))
    
    # Forma de pago
    forma_pago = safe_get(traslados, 'forma_pago', default=None)
    if forma_pago and forma_pago != "-":
        elements.append(create_info_line('Forma de Pago', forma_pago))
    
    # Descripción
    descripcion = safe_get(traslados, 'descripcion', default=None)
    if descripcion and descripcion != "-":
        elements.append(create_salto())
        elements.append(create_subtitulo_vineta("Descripción"))
        lineas = descripcion.split('\n')
        for linea in lineas:
            if linea.strip():
                para = Paragraph(linea.strip(), get_texto_style())
                elements.append(para)
                elements.append(Spacer(1, 0.2*cm))
    
    # Total
    total = safe_get(traslados, 'total', default="0")
    total_para = create_total(total)
    elements.append(total_para)
    
    return elements


def generate_renta_autos_table(propuestas):
    """Genera tabla para cotizaciones de tipo renta de autos."""
    elements = []
    
    renta = propuestas.get('renta_autos', {})
    if not renta:
        return elements
    
    # Título principal
    elements.append(create_titulo_seccion("RENTA DE AUTOS"))
    elements.append(Spacer(1, 0.2*cm))
    
    # Información
    elements.append(create_info_line('Arrendadora', safe_get(renta, 'arrendadora', default="-")))
    elements.append(create_info_line('Punto de Origen', safe_get(renta, 'punto_origen', default="-")))
    elements.append(create_info_line('Punto de Regreso', safe_get(renta, 'punto_regreso', default="-")))
    
    hora_pickup = safe_get(renta, 'hora_pickup', default=None)
    if hora_pickup and hora_pickup != "-":
        elements.append(create_info_line('Hora Pickup', hora_pickup))
    
    hora_devolucion = safe_get(renta, 'hora_devolucion', default=None)
    if hora_devolucion and hora_devolucion != "-":
        elements.append(create_info_line('Hora Devolución', hora_devolucion))
    
    forma_pago = safe_get(renta, 'forma_pago', default=None)
    if forma_pago and forma_pago != "-":
        elements.append(create_info_line('Forma de Pago', forma_pago))
    
    # Total
    total = safe_get(renta, 'total', default="0")
    total_para = create_total(total)
    elements.append(total_para)
    
    return elements


def generate_generica_table(propuestas):
    """Genera contenido para cotizaciones genéricas."""
    elements = []
    
    generica = propuestas.get('generica', {})
    if not generica:
        return elements
    
    contenido = safe_get(generica, 'contenido', default="Sin contenido específico.")
    
    elements.append(Paragraph("Detalles de la Cotización", get_titulo_seccion_style()))
    elements.append(Spacer(1, 0.3*cm))
    
    # Dividir por líneas
    lineas = contenido.split('\n')
    for linea in lineas:
        if linea.strip():
            para = Paragraph(linea.strip(), get_texto_style())
            elements.append(para)
            elements.append(Spacer(1, 0.2*cm))
    
    return elements


# ==================== FUNCIÓN PRINCIPAL ====================

def generate_cotizacion_pdf(cotizacion):
    """
    Función principal que genera el PDF completo de una cotización usando ReportLab.
    Recrea el formato visual anterior con mejor control de tablas.
    
    Args:
        cotizacion: Objeto Cotizacion de Django
    
    Returns:
        BytesIO: Buffer con el contenido del PDF
    """
    # Crear buffer para el PDF
    buffer = BytesIO()
    
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
    
    # ==================== INFORMACIÓN GENERAL ====================
    
    # Fecha de cotización (alineada a la derecha)
    fecha_generacion = format_date(cotizacion.actualizada_en or cotizacion.creada_en, "%d/%m/%Y %H:%M")
    fecha_para = Paragraph(
        f"<b>Fecha de Cotización:</b> {fecha_generacion}",
        ParagraphStyle(
            name='FechaCotizacion',
            fontSize=14,
            textColor=MOVUMS_BLUE_CORP,
            fontName='Helvetica-Bold',
            alignment=TA_RIGHT,
            spaceAfter=6
        )
    )
    story.append(fecha_para)
    
    # Tabla de información general (4 filas x 3 columnas)
    info_data = []
    
    origen = cotizacion.origen or "-"
    destino = cotizacion.destino or "-"
    info_data.append([
        Paragraph("<b>Origen / Destino</b>", get_texto_style()),
        Paragraph(origen, get_texto_style()),
        Paragraph(destino, get_texto_style())
    ])
    
    fecha_inicio = format_date(cotizacion.fecha_inicio) if cotizacion.fecha_inicio else "-"
    fecha_fin = format_date(cotizacion.fecha_fin) if cotizacion.fecha_fin else "-"
    info_data.append([
        Paragraph("<b>Inicio / Fin</b>", get_texto_style()),
        Paragraph(fecha_inicio, get_texto_style()),
        Paragraph(fecha_fin, get_texto_style())
    ])
    
    pasajeros_str = str(cotizacion.pasajeros) if cotizacion.pasajeros else "1"
    adultos_menores = f"{cotizacion.adultos or 0} Adultos / {cotizacion.menores or 0} Menores"
    info_data.append([
        Paragraph("<b>Pasajeros</b>", get_texto_style()),
        Paragraph(pasajeros_str, get_texto_style()),
        Paragraph(adultos_menores, get_texto_style())
    ])
    
    dias = f"{cotizacion.dias or '-'} días" if cotizacion.dias else "-"
    noches = f"{cotizacion.noches or '-'} noches" if cotizacion.noches else "-"
    info_data.append([
        Paragraph("<b>Viaje</b>", get_texto_style()),
        Paragraph(dias, get_texto_style()),
        Paragraph(noches, get_texto_style())
    ])
    
    info_table = Table(info_data, colWidths=[5*cm, 6*cm, 6*cm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(KeepTogether(info_table))
    story.append(Spacer(1, 0.5*cm))
    
    # ==================== PROPUESTAS (SEGÚN TIPO) ====================
    
    propuestas = cotizacion.propuestas if isinstance(cotizacion.propuestas, dict) else {}
    tipo = propuestas.get('tipo', 'generica') if isinstance(propuestas, dict) else 'generica'
    
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
        total_para = create_total(cotizacion.total_estimado)
        story.append(total_para)
    
    # ==================== GENERAR PDF ====================
    
    doc.build(story)
    buffer.seek(0)
    
    return buffer


