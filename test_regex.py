
import re

def test_regex():
    regex = r'escalas_ida\[(\d+)\]\[(\w+)\]'
    
    test_cases = [
        "escalas_ida[0][ciudad]",
        "escalas_ida[0][aeropuerto]",
        "escalas_ida[0][hora_llegada]",  # has underscore
        "escalas_ida[0][hora_salida]",   # has underscore
        "escalas_ida[0][numero_vuelo]",  # has underscore
        "escalas_ida[0][duracion]",
        # Potential failure cases
        "escalas_ida[0][ciudad-name]",   # hyphen
        "escalas_ida[0][ciudad name]",   # space
        "escalas_ida[0][ciudad.name]",   # dot
    ]

    print(f"Testing regex: {regex}")
    for case in test_cases:
        match = re.match(regex, case)
        if match:
            print(f"MATCH: '{case}' -> idx={match.group(1)}, field={match.group(2)}")
        else:
            print(f"FAIL : '{case}'")

if __name__ == "__main__":
    test_regex()
