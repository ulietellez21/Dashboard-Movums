#!/usr/bin/env python3
"""Script temporal para corregir la indentación en ventas/forms.py"""

# Leer el archivo
with open('ventas/forms.py', 'r') as f:
    lines = f.readlines()

# Corregir la línea 436 (índice 435)
if lines[435].strip().startswith('self.fields[field_name]'):
    lines[435] = '                ' + lines[435].lstrip()

# Corregir la línea 455 (índice 454)
if lines[454].strip().startswith('self.fields[field_name]'):
    lines[454] = '                ' + lines[454].lstrip()

# Escribir el archivo corregido
with open('ventas/forms.py', 'w') as f:
    f.writelines(lines)

print("Indentación corregida")

























