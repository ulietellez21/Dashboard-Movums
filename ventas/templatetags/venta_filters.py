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