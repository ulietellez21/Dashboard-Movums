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