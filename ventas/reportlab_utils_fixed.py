"""
Utilidades para generar PDFs de cotizaciones usando ReportLab.
Versión corregida sin tablas anidadas y con formato moderno mejorado.
"""
from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    KeepTogether
)


# ==================== CONSTANTES DE COLOR ====================

DARK_BLUE = colors.HexColor('#004a8e')
MEDIUM_BLUE = colors.HexColor('#0f5cc0')
LIGHT_BLUE = colors.HexColor('#5c8dd6')
DARK_PURPLE = colors.HexColor('#6b4c93')
LIGHT_GRAY = colors.HexColor('#f8f9fa')
MEDIUM_GRAY = colors.HexColor('#e0e0e0')
BORDER_GRAY = colors.HexColor('#dee2e6')
TEXT_DARK = colors.HexColor('#212529')
TEXT_LIGHT = colors.HexColor('#6c757d')
TEXT_MEDIUM = colors.HexColor('#495057')
WHITE = colors.white

# ==================== ICONOS Y SÍMBOLOS (Unicode simple) ====================

ICONOS = {
    'vuelo': '✈',
    'hospedaje': '■',
    'paquete': '●',
    'tour': '◆',
    'traslado': '►',
    'renta_autos': '◆',
    'cliente': '●',
    'email': '@',
    'telefono': '☎',
    'fecha': '◉',
    'pasajeros': '●',
    'ruta': '→'
}


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
    if not isinstance(data, dict):
        return default
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
        if current is None:
            return default
    return current if current != "" else default


# ==================== ESTILOS ====================

def get_styles():
    """Retorna los estilos personalizados."""
    styles = getSampleStyleSheet()
    
    # Encabezado principal
    if 'EncabezadoPrincipal' not in styles.byName:
        styles.add(ParagraphStyle(
            name='EncabezadoPrincipal',
            fontSize=38,
            textColor=WHITE,
            fontName='Helvetica-Bold',
            alignment=TA_LEFT,
            leading=44,
            spaceAfter=0,
            spaceBefore=0,
            letterSpacing=3
        ))
    
    # Título de sección (VUELO, HOSPEDAJE)
    if 'TituloSeccion' not in styles.byName:
        styles.add(ParagraphStyle(
            name='TituloSeccion',
            fontSize=20,
            textColor=WHITE,
            fontName='Helvetica-Bold',
            leading=24,
            letterSpacing=1.5
        ))
    
    # Subtítulo con viñeta
    if 'SubtituloVineta' not in styles.byName:
        styles.add(ParagraphStyle(
            name='SubtituloVineta',
            fontSize=15,
            textColor=DARK_BLUE,
            fontName='Helvetica-Bold',
            leading=18,
            spaceBefore=16,
            spaceAfter=8
        ))
    
    # Texto principal
    if 'TextoPrincipal' not in styles.byName:
        styles.add(ParagraphStyle(
            name='TextoPrincipal',
            fontSize=12,
            textColor=TEXT_DARK,
            fontName='Helvetica',
            leading=18,
            spaceAfter=6
        ))
    
    # Etiqueta tabla
    if 'InfoTablaLabel' not in styles.byName:
        styles.add(ParagraphStyle(
            name='InfoTablaLabel',
            fontSize=11,
            textColor=TEXT_MEDIUM,
            fontName='Helvetica-Bold',
            leading=14
        ))
    
    # Valor tabla
    if 'InfoTablaValue' not in styles.byName:
        styles.add(ParagraphStyle(
            name='InfoTablaValue',
            fontSize=11,
            textColor=TEXT_DARK,
            fontName='Helvetica',
            leading=14
        ))
    
    # Cotización para
    if 'CotizacionPara' not in styles.byName:
        styles.add(ParagraphStyle(
            name='CotizacionPara',
            fontSize=11,
            textColor=TEXT_MEDIUM,
            fontName='Helvetica',
            leading=13,
            spaceAfter=8,
            letterSpacing=2
        ))
    
    # Nombre cliente
    if 'NombreCliente' not in styles.byName:
        styles.add(ParagraphStyle(
            name='NombreCliente',
            fontSize=32,
            textColor=TEXT_DARK,
            fontName='Helvetica-Bold',
            leading=36,
            spaceAfter=20,
            letterSpacing=0.5
        ))
    
    # Sidebar título
    if 'SidebarTitulo' not in styles.byName:
        styles.add(ParagraphStyle(
            name='SidebarTitulo',
            fontSize=13,
            textColor=WHITE,
            fontName='Helvetica-Bold',
            leading=15,
            spaceAfter=10
        ))
    
    # Sidebar etiqueta
    if 'SidebarEtiqueta' not in styles.byName:
        styles.add(ParagraphStyle(
            name='SidebarEtiqueta',
            fontSize=11,
            textColor=WHITE,
            fontName='Helvetica-Bold',
            leading=13
        ))
    
    # Sidebar texto
    if 'SidebarTexto' not in styles.byName:
        styles.add(ParagraphStyle(
            name='SidebarTexto',
            fontSize=11,
            textColor=WHITE,
            leading=13
        ))
    
    # Total
    if 'Total' not in styles.byName:
        styles.add(ParagraphStyle(
            name='Total',
            fontSize=18,
            textColor=DARK_BLUE,
            fontName='Helvetica-Bold',
            leading=22,
            spaceAfter=6
        ))
    
    return styles


# ==================== FUNCIONES DE FORMATO ====================

def create_encabezado_bar():
    """Crea la barra azul oscura con 'COTIZACIÓN'."""
    styles = get_styles()
    data = [[Paragraph("COTIZACIÓN", styles['EncabezadoPrincipal'])]]
    table = Table(data, colWidths=[19*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 20),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ('LEFTPADDING', (0, 0), (-1, -1), 25),
        ('RIGHTPADDING', (0, 0), (-1, -1), 25),
    ]))
    return table


def get_icono_servicio(tipo_servicio):
    """Retorna el icono correspondiente al tipo de servicio."""
    iconos_map = {
        'VUELO': ICONOS['vuelo'],
        'HOSPEDAJE': ICONOS['hospedaje'],
        'PAQUETE': ICONOS['paquete'],
        'TOUR': ICONOS['tour'],
        'TRASLADO': ICONOS['traslado'],
        'RENTA DE AUTOS': ICONOS['renta_autos'],
        'RENTA_autos': ICONOS['renta_autos'],
    }
    return iconos_map.get(tipo_servicio.upper(), '●')


def create_titulo_seccion(texto):
    """Crea un título de sección moderno con icono."""
    styles = get_styles()
    icono = get_icono_servicio(texto)
    titulo_con_icono = f"{icono} {texto.upper()}"
    data = [[Paragraph(titulo_con_icono, styles['TituloSeccion'])]]
    table = Table(data, colWidths=[19*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK_BLUE),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('GRID', (0, 0), (-1, -1), 0, DARK_BLUE),
    ]))
    return table


def create_subtitulo_vineta(texto):
    """Crea un subtítulo con viñeta azul."""
    styles = get_styles()
    vineta_text = f"<font color='{DARK_BLUE.hexval()}'><b>●</b></font> <font color='{DARK_BLUE.hexval()}'><b>{texto}</b></font>"
    return Paragraph(vineta_text, styles['SubtituloVineta'])


def create_info_line(etiqueta, valor):
    """Crea una línea de información."""
    if not valor or valor == "-":
        return None
    styles = get_styles()
    texto = f"<b><font color='{TEXT_DARK.hexval()}'>{etiqueta}:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{str(valor)}</font>"
    return Paragraph(texto, styles['TextoPrincipal'])


def create_info_inline(pares_etiqueta_valor):
    """Crea múltiples campos en una sola línea."""
    if not pares_etiqueta_valor:
        return None
    styles = get_styles()
    partes = []
    for etiqueta, valor in pares_etiqueta_valor:
        if valor and valor != "-":
            partes.append(f"<b><font color='{TEXT_DARK.hexval()}'>{etiqueta}:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{str(valor)}</font>")
    if not partes:
        return None
    separador_html = f"<font color='{MEDIUM_GRAY.hexval()}'> • </font>"
    texto = separador_html.join(partes)
    return Paragraph(texto, styles['TextoPrincipal'])


def create_total(total_value):
    """Crea el total con diseño moderno."""
    styles = get_styles()
    total_formatted = format_currency(total_value)
    texto = f"<font color='{DARK_BLUE.hexval()}'><b>Total MXN {total_formatted} Pesos</b></font>"
    para = Paragraph(texto, styles['Total'])
    
    total_table = Table([[para]], colWidths=[19*cm])
    total_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 15),
        ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0, LIGHT_GRAY),
    ]))
    return total_table


def create_sidebar(title, data_dict, bg_color):
    """Crea un sidebar moderno."""
    styles = get_styles()
    elements = []
    
    # Título del sidebar
    title_table = Table([[Paragraph(title, styles['SidebarTitulo'])]], colWidths=[8*cm])
    title_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 18),
        ('RIGHTPADDING', (0, 0), (-1, -1), 18),
        ('TOPPADDING', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0, bg_color),
    ]))
    elements.append(title_table)
    
    # Datos del sidebar
    if data_dict:
        data_rows = []
        for key, value in data_dict.items():
            if value and value != "-":
                label_cell = Paragraph(f"<b>{key}:</b>", styles['SidebarEtiqueta'])
                value_cell = Paragraph(str(value), styles['SidebarTexto'])
                data_rows.append([label_cell, value_cell])
        
        if data_rows:
            data_table = Table(data_rows, colWidths=[3.5*cm, 4.5*cm])
            data_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), bg_color),
                ('TEXTCOLOR', (0, 0), (-1, -1), WHITE),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 18),
                ('RIGHTPADDING', (0, 0), (-1, -1), 18),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
                ('LINEBELOW', (0, 0), (-1, -2), 0.8, colors.HexColor('#ffffff50')),
                ('GRID', (0, 0), (-1, -1), 0, bg_color),
            ]))
            elements.append(data_table)
    
    elements.append(Spacer(1, 0.3*cm))
    return elements


def create_hospedaje_info_table(hotel):
    """Crea una tabla de 2 columnas para información de hospedaje."""
    styles = get_styles()
    data = []
    
    nombre = safe_get(hotel, 'nombre', default="-")
    plan = safe_get(hotel, 'plan', default="-")
    data.append([
        Paragraph(f"<b><font color='{TEXT_DARK.hexval()}'>Nombre:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{nombre}</font>", styles['TextoPrincipal']),
        Paragraph(f"<b><font color='{TEXT_DARK.hexval()}'>Plan de Alimentos:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{plan}</font>", styles['TextoPrincipal'])
    ])
    
    habitacion = safe_get(hotel, 'habitacion', default="-")
    forma_pago = safe_get(hotel, 'forma_pago', default=None)
    if forma_pago:
        data.append([
            Paragraph(f"<b><font color='{TEXT_DARK.hexval()}'>Habitación:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{habitacion}</font>", styles['TextoPrincipal']),
            Paragraph(f"<b><font color='{TEXT_DARK.hexval()}'>Forma de Pago:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{forma_pago}</font>", styles['TextoPrincipal'])
        ])
    else:
        data.append([
            Paragraph(f"<b><font color='{TEXT_DARK.hexval()}'>Habitación:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{habitacion}</font>", styles['TextoPrincipal']),
            Paragraph("", styles['TextoPrincipal'])
        ])
    
    direccion = safe_get(hotel, 'direccion', default="-")
    data.append([
        Paragraph(f"<b><font color='{TEXT_DARK.hexval()}'>Dirección:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{direccion}</font>", styles['TextoPrincipal']),
        Paragraph("", styles['TextoPrincipal'])
    ])
    
    notas = safe_get(hotel, 'notas', default=None)
    if notas and notas != "-":
        data.append([
            Paragraph(f"<b><font color='{TEXT_DARK.hexval()}'>Notas:</font></b> <font color='{TEXT_LIGHT.hexval()}'>{notas}</font>", styles['TextoPrincipal']),
            Paragraph("", styles['TextoPrincipal'])
        ])
    
    table = Table(data, colWidths=[8.5*cm, 8.5*cm])
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -2), 0.8, BORDER_GRAY),
        ('GRID', (0, 0), (-1, -1), 0, WHITE),
        ('BACKGROUND', (0, 0), (-1, -1), WHITE),
    ]))
    
    return table


# ==================== GENERADORES ESPECÍFICOS POR TIPO ====================

def generate_vuelos_table(propuestas):
    """Genera contenido para cotizaciones de tipo vuelos."""
    elements = []
    vuelos = propuestas.get('vuelos', [])
    if not vuelos:
        return elements
    
    for idx, vuelo in enumerate(vuelos, 1):
        elements.append(create_titulo_seccion("VUELO"))
        elements.append(Spacer(1, 0.2*cm))
        elements.append(create_subtitulo_vineta("Información del Vuelo"))
        
        info_inline = create_info_inline([
            ('Aerolínea', safe_get(vuelo, 'aerolinea', default="-")),
            ('Salida', safe_get(vuelo, 'salida', default="-")),
            ('Regreso', safe_get(vuelo, 'regreso', default="-"))
        ])
        if info_inline:
            elements.append(info_inline)
        
        incluye = safe_get(vuelo, 'incluye', default=None)
        if incluye and incluye != "-":
            incluye_line = create_info_line('Incluye', incluye)
            if incluye_line:
                elements.append(incluye_line)
        
        forma_pago = safe_get(vuelo, 'forma_pago', default=None)
        if forma_pago and forma_pago != "-":
            forma_pago_line = create_info_line('Forma de Pago', forma_pago)
            if forma_pago_line:
                elements.append(forma_pago_line)
        
        total = safe_get(vuelo, 'total', default="0")
        total_para = create_total(total)
        elements.append(total_para)
        
        if idx < len(vuelos):
            elements.append(Spacer(1, 0.4*cm))
    
    return elements


def generate_hospedaje_table(propuestas):
    """Genera contenido para cotizaciones de tipo hospedaje."""
    elements = []
    hoteles = propuestas.get('hoteles', [])
    if not hoteles:
        return elements
    
    for idx, hotel in enumerate(hoteles, 1):
        elements.append(create_titulo_seccion("HOSPEDAJE"))
        elements.append(Spacer(1, 0.2*cm))
        elements.append(create_subtitulo_vineta("Información del Alojamiento"))
        
        info_table = create_hospedaje_info_table(hotel)
        elements.append(KeepTogether(info_table))
        
        total = safe_get(hotel, 'total', default="0")
        total_para = create_total(total)
        elements.append(total_para)
        
        if idx < len(hoteles):
            elements.append(Spacer(1, 0.4*cm))
    
    return elements


def generate_paquete_table(propuestas):
    """Genera contenido para cotizaciones de tipo paquete."""
    elements = []
    paquete = propuestas.get('paquete', {})
    if not paquete:
        return elements
    
    elements.append(create_titulo_seccion("PAQUETE"))
    elements.append(Spacer(1, 0.2*cm))
    
    vuelo = paquete.get('vuelo', {})
    if vuelo:
        elements.append(create_subtitulo_vineta("Vuelo"))
        info_inline = create_info_inline([
            ('Aerolínea', safe_get(vuelo, 'aerolinea', default="-")),
            ('Salida', safe_get(vuelo, 'salida', default="-")),
            ('Regreso', safe_get(vuelo, 'regreso', default="-"))
        ])
        if info_inline:
            elements.append(info_inline)
        
        incluye = safe_get(vuelo, 'incluye', default=None)
        if incluye and incluye != "-":
            incluye_line = create_info_line('Incluye', incluye)
            if incluye_line:
                elements.append(incluye_line)
        
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
        
        elements.append(Spacer(1, 0.3*cm))
    
    hotel = paquete.get('hotel', {})
    if hotel:
        elements.append(create_subtitulo_vineta("Hospedaje"))
        info_table = create_hospedaje_info_table(hotel)
        elements.append(KeepTogether(info_table))
        
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
        
        forma_pago_paquete = safe_get(paquete, 'forma_pago', default=None)
        if forma_pago_paquete and forma_pago_paquete != "-":
            forma_pago_line = create_info_line('Forma de Pago del Paquete', forma_pago_paquete)
            if forma_pago_line:
                elements.append(forma_pago_line)
        
        elements.append(Spacer(1, 0.3*cm))
    
    total_paquete = safe_get(paquete, 'total', default="0")
    if total_paquete and total_paquete != "-":
        total_para = create_total(total_paquete)
        elements.append(total_para)
    
    return elements


def generate_tours_table(propuestas):
    """Genera contenido para cotizaciones de tipo tours."""
    elements = []
    tours = propuestas.get('tours', [])
    if not tours:
        if propuestas.get('tours'):
            tours = [propuestas.get('tours')]
        else:
            return elements
    
    for idx, tour in enumerate(tours, 1):
        elements.append(create_titulo_seccion("TOUR"))
        elements.append(Spacer(1, 0.2*cm))
        elements.append(create_subtitulo_vineta("Información del Tour"))
        
        numero_reserva = safe_get(tour, 'numero_reserva', default=None)
        if numero_reserva and numero_reserva != "-":
            elements.append(create_info_line('Número de Reserva', numero_reserva))
        
        nombre = safe_get(tour, 'nombre', default=None)
        if nombre and nombre != "-":
            elements.append(create_info_line('Nombre del Tour', nombre))
        
        especificaciones = safe_get(tour, 'especificaciones', default=None)
        if especificaciones and especificaciones != "-":
            elements.append(Spacer(1, 0.3*cm))
            elements.append(create_subtitulo_vineta("Especificaciones"))
            styles = get_styles()
            lineas = especificaciones.split('\n')
            for linea in lineas:
                if linea.strip():
                    para = Paragraph(linea.strip(), styles['TextoPrincipal'])
                    elements.append(para)
        
        forma_pago = safe_get(tour, 'forma_pago', default=None)
        if forma_pago and forma_pago != "-":
            elements.append(Spacer(1, 0.3*cm))
            elements.append(create_subtitulo_vineta("Forma de Pago"))
            elements.append(create_info_line('Forma de Pago', forma_pago))
        
        total = safe_get(tour, 'total', default=None)
        if total and total != "-":
            total_para = create_total(total)
            elements.append(total_para)
        
        if idx < len(tours):
            elements.append(Spacer(1, 0.4*cm))
    
    return elements


def generate_traslados_table(propuestas):
    """Genera contenido para cotizaciones de tipo traslados."""
    elements = []
    traslados = propuestas.get('traslados', {})
    if not traslados:
        return elements
    
    elements.append(create_titulo_seccion("TRASLADO"))
    elements.append(Spacer(1, 0.2*cm))
    
    elements.append(create_info_line('Desde', safe_get(traslados, 'desde', default="-")))
    elements.append(create_info_line('Hasta', safe_get(traslados, 'hasta', default="-")))
    
    tipo = safe_get(traslados, 'tipo', default=None)
    if tipo and tipo != "-":
        elements.append(create_info_line('Tipo', tipo))
    
    modalidad = safe_get(traslados, 'modalidad', default=None)
    if modalidad and modalidad != "-":
        elements.append(create_info_line('Modalidad', modalidad))
    
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
    
    forma_pago = safe_get(traslados, 'forma_pago', default=None)
    if forma_pago and forma_pago != "-":
        elements.append(create_info_line('Forma de Pago', forma_pago))
    
    descripcion = safe_get(traslados, 'descripcion', default=None)
    if descripcion and descripcion != "-":
        elements.append(Spacer(1, 0.3*cm))
        elements.append(create_subtitulo_vineta("Descripción"))
        styles = get_styles()
        lineas = descripcion.split('\n')
        for linea in lineas:
            if linea.strip():
                para = Paragraph(linea.strip(), styles['TextoPrincipal'])
                elements.append(para)
    
    total = safe_get(traslados, 'total', default="0")
    total_para = create_total(total)
    elements.append(total_para)
    
    return elements


def generate_renta_autos_table(propuestas):
    """Genera contenido para cotizaciones de tipo renta de autos."""
    elements = []
    renta = propuestas.get('renta_autos', {})
    if not renta:
        return elements
    
    elements.append(create_titulo_seccion("RENTA DE AUTOS"))
    elements.append(Spacer(1, 0.2*cm))
    
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
    styles = get_styles()
    
    elements.append(Paragraph("Detalles de la Cotización", styles['SubtituloVineta']))
    elements.append(Spacer(1, 0.3*cm))
    
    lineas = contenido.split('\n')
    for linea in lineas:
        if linea.strip():
            para = Paragraph(linea.strip(), styles['TextoPrincipal'])
            elements.append(para)
            elements.append(Spacer(1, 0.2*cm))
    
    return elements


# ==================== FUNCIÓN PRINCIPAL ====================

def generate_cotizacion_pdf(cotizacion):
    """
    Genera el PDF completo de una cotización con formato profesional.
    Layout de dos columnas SIMPLE sin tablas anidadas.
    """
    buffer = BytesIO()
    styles = get_styles()
    
    # Crear documento con márgenes más amplios
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.2*cm,
        bottomMargin=1.5*cm
    )
    
    story = []
    
    # ==================== ENCABEZADO ====================
    story.append(create_encabezado_bar())
    story.append(Spacer(1, 0.8*cm))
    
    # ==================== PREPARAR DATOS ====================
    
    cliente_nombre = cotizacion.cliente.nombre_completo_display
    origen = cotizacion.origen or "-"
    destino = cotizacion.destino or "-"
    fecha_inicio = format_date(cotizacion.fecha_inicio) if cotizacion.fecha_inicio else "-"
    fecha_fin = format_date(cotizacion.fecha_fin) if cotizacion.fecha_fin else "-"
    pasajeros_str = str(cotizacion.pasajeros) if cotizacion.pasajeros else "1"
    adultos_menores = f"{cotizacion.adultos or 0} Adultos / {cotizacion.menores or 0} Menores"
    if cotizacion.edades_menores:
        adultos_menores += f" (Edades: {cotizacion.edades_menores})"
    dias = f"{cotizacion.dias or '-'} días" if cotizacion.dias else "-"
    noches = f"{cotizacion.noches or '-'} noches" if cotizacion.noches else "-"
    fecha_cotizacion = format_date(cotizacion.creada_en.date() if cotizacion.creada_en else None)
    folio = cotizacion.folio or f"COT-{cotizacion.id}"
    
    # ==================== LAYOUT DE DOS COLUMNAS SIMPLE ====================
    
    # Preparar información para tabla de izquierda
    info_items = [
        ('Cliente', cliente_nombre),
        ('Origen / Destino', f"{origen} / {destino}"),
        ('Inicio / Fin', f"{fecha_inicio} / {fecha_fin}"),
        ('Pasajeros', f"{pasajeros_str} ({adultos_menores})"),
        ('Viaje', f"{dias} / {noches}"),
        ('Fecha de Cotización', fecha_cotizacion)
    ]
    
    # Crear tabla formateada para la información
    info_table_data = []
    for etiqueta, valor in info_items:
        label_cell = Paragraph(f"<b>{etiqueta}:</b>", styles['InfoTablaLabel'])
        value_cell = Paragraph(str(valor), styles['InfoTablaValue'])
        info_table_data.append([label_cell, value_cell])
    
    # Tabla de información con formato moderno
    info_table = Table(info_table_data, colWidths=[5.5*cm, 6*cm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        # Bordes sutiles entre filas
        ('LINEBELOW', (0, 0), (-1, -2), 0.8, BORDER_GRAY),
        ('GRID', (0, 0), (-1, -1), 0, WHITE),
        ('BACKGROUND', (0, 0), (-1, -1), WHITE),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [WHITE, LIGHT_GRAY]),
    ]))
    
    # Preparar sidebars
    detalles_data = {
        "NÚMERO DE COTIZACIÓN": folio,
        "FECHA DE COTIZACIÓN": fecha_cotizacion,
        "FECHA DE VIAJE": f"{fecha_inicio} / {fecha_fin}"
    }
    
    viaje_data = {
        "PASAJEROS": f"{ICONOS['pasajeros']} {adultos_menores}",
        "DURACIÓN": f"{ICONOS['fecha']} {cotizacion.dias or '-'} días / {cotizacion.noches or '-'} noches",
        "RUTA": f"{ICONOS['ruta']} {origen} → {destino}"
    }
    
    contacto_data = {}
    if cliente_nombre:
        contacto_data["CLIENTE"] = f"{ICONOS['cliente']} {cliente_nombre}"
    if cotizacion.cliente.email:
        contacto_data["EMAIL"] = f"{ICONOS['email']} {cotizacion.cliente.email}"
    if cotizacion.cliente.telefono:
        contacto_data["TELÉFONO"] = f"{ICONOS['telefono']} {cotizacion.cliente.telefono}"
    
    sidebar1 = create_sidebar("DETALLES DE COTIZACIÓN", detalles_data, MEDIUM_BLUE)
    sidebar2 = create_sidebar("INFORMACIÓN DEL VIAJE", viaje_data, DARK_PURPLE)
    sidebar3 = create_sidebar("CONTACTO", contacto_data, LIGHT_BLUE)
    
    # Crear layout de dos columnas SIN tablas anidadas
    # Usaremos una tabla simple fila por fila
    
    # Fila 1: "COTIZACIÓN PARA" y título del sidebar 1
    row1 = Table([
        [Paragraph("COTIZACIÓN PARA", styles['CotizacionPara']), sidebar1[0] if sidebar1 else Paragraph("", styles['TextoPrincipal'])]
    ], colWidths=[11.5*cm, 7.5*cm])
    row1.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('GRID', (0, 0), (-1, -1), 0, WHITE),
    ]))
    story.append(row1)
    story.append(Spacer(1, 0.3*cm))
    
    # Fila 2: Nombre del cliente y contenido del sidebar 1
    # Crear una celda con el nombre del cliente
    cliente_cell = Paragraph(cliente_nombre, styles['NombreCliente'])
    
    # Para el sidebar 1, necesitamos su contenido después del título
    sidebar1_content = sidebar1[1:] if len(sidebar1) > 1 else []
    
    # Combinar en una fila
    row2 = Table([
        [cliente_cell, sidebar1_content[0] if sidebar1_content else Paragraph("", styles['TextoPrincipal'])]
    ], colWidths=[11.5*cm, 7.5*cm])
    row2.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('GRID', (0, 0), (-1, -1), 0, WHITE),
    ]))
    story.append(row2)
    story.append(Spacer(1, 0.6*cm))
    
    # Fila 3: Tabla de información (izquierda) y continuación de sidebar 1 (derecha)
    # Necesitamos continuar con el contenido de sidebar 1 si hay más
    sidebar1_rest = sidebar1_content[1:] if len(sidebar1_content) > 1 else []
    sidebar1_rest_elem = sidebar1_rest[0] if sidebar1_rest else Paragraph("", styles['TextoPrincipal'])
    
    row3 = Table([
        [info_table, sidebar1_rest_elem]
    ], colWidths=[11.5*cm, 7.5*cm])
    row3.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('GRID', (0, 0), (-1, -1), 0, WHITE),
    ]))
    story.append(row3)
    
    # Continuar con el resto de los sidebars en filas adicionales
    # Sidebar 1 restante
    if len(sidebar1_rest) > 1:
        for elem in sidebar1_rest[1:]:
            sidebar_row = Table([
                [Paragraph("", styles['TextoPrincipal']), elem]
            ], colWidths=[11.5*cm, 7.5*cm])
            sidebar_row.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 0, WHITE),
            ]))
            story.append(sidebar_row)
    
    story.append(Spacer(1, 0.4*cm))
    
    # Sidebar 2 y 3
    for sidebar in [sidebar2, sidebar3]:
        if sidebar:
            for elem in sidebar:
                sidebar_row = Table([
                    [Paragraph("", styles['TextoPrincipal']), elem]
                ], colWidths=[11.5*cm, 7.5*cm])
                sidebar_row.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('GRID', (0, 0), (-1, -1), 0, WHITE),
                ]))
                story.append(sidebar_row)
        story.append(Spacer(1, 0.4*cm))
    
    story.append(Spacer(1, 1*cm))
    
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
    
    # Total estimado si existe
    if cotizacion.total_estimado and cotizacion.total_estimado > 0:
        story.append(Spacer(1, 0.5*cm))
        total_para = create_total(cotizacion.total_estimado)
        story.append(total_para)
    
    # Generar PDF
    doc.build(story)
    buffer.seek(0)
    
    return buffer


