# ventas/templatetags/venta_filters.py

from django import template

register = template.Library()

@register.filter
def add_max_attr(field, max_value):
    """Añade el atributo 'max' al widget del campo del formulario."""
    # Renderiza el campo con el nuevo atributo
    # La sintaxis de Django Widget Tweaks es la forma más limpia de hacer esto, 
    # pero si evitamos esa dependencia, podemos usar el método get_context_and_render.
    
    # Para simplicidad y si no quieres depender de otra librería aparte de las ya usadas:
    
    # Creamos un diccionario de attrs del widget
    attrs = field.field.widget.attrs
    attrs['max'] = max_value
    
    # Clonamos el campo y le asignamos el widget modificado
    # Nota: Este enfoque puede ser complejo y es más fácil usar un método directo
    # o Widget Tweaks. Dado que NO queremos usar Widget Tweaks, lo haremos con un 
    # método más simple de Django puro:
    
    return field.as_widget(attrs=attrs)

@register.filter
def get_item(dictionary, key):
    """Obtiene un valor de un diccionario usando una clave."""
    if dictionary is None:
        return None
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    # También permite acceder a campos del formulario usando form[field_name]
    if hasattr(dictionary, '__getitem__'):
        try:
            return dictionary[key]
        except (KeyError, TypeError):
            return None
    return None

@register.filter
def servicio_esta_contratado(servicios_str, codigo_servicio):
    """Verifica si un código de servicio está en la cadena de servicios seleccionados."""
    if not servicios_str:
        return False
    if not codigo_servicio:
        return False
    # Convertir la cadena a lista de códigos separados por coma
    servicios_codes = [s.strip() for s in str(servicios_str).split(',')]
    return codigo_servicio.strip() in servicios_codes

@register.filter
def solo_nombre_proveedor(nombre_completo):
    """Extrae solo el nombre del proveedor, eliminando los servicios entre paréntesis."""
    if not nombre_completo:
        return ''
    nombre_str = str(nombre_completo)
    # Si hay un paréntesis, tomar solo la parte antes de él
    if '(' in nombre_str:
        return nombre_str.split('(')[0].strip()
    return nombre_str.strip()

@register.filter
def formato_moneda_mx(value):
    """Formatea un valor numérico como moneda mexicana ($25,000.00)."""
    if not value or value == '-' or value == '':
        return '-'
    try:
        # Limpiar el valor si tiene formato previo
        if isinstance(value, str):
            # Remover $, comas y espacios
            valor_limpio = value.replace('$', '').replace(',', '').replace(' ', '').strip()
            if not valor_limpio or valor_limpio == '':
                return '-'
            numero = float(valor_limpio)
        else:
            numero = float(value)
        
        # Formatear con 2 decimales y comas cada 3 dígitos
        numero_formateado = f"{numero:,.2f}"
        return f"${numero_formateado}"
    except (ValueError, TypeError, AttributeError):
        # Si no se puede convertir, retornar el valor original
        return str(value) if value else '-'