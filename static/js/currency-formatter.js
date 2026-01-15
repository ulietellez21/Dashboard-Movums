/**
 * Formateador de Moneda en Tiempo Real
 * Funciones reutilizables para formatear campos monetarios mientras el usuario escribe
 */

// Función para limpiar el formato y obtener solo el número (sin $ y sin comas)
function limpiarFormatoMoneda(valor) {
    if (!valor) return '';
    // Remover $, comas y espacios, mantener solo números y punto decimal
    return valor.toString().replace(/[^\d.]/g, '');
}

// Función para formatear en tiempo real manteniendo la posición del cursor
function formatearEnTiempoReal(input) {
    // 1. Guardar posición del cursor y contar dígitos a su izquierda
    const cursorPosition = input.selectionStart;
    const originalValue = input.value;
    let digitsBeforeCursor = 0;
    for (let i = 0; i < cursorPosition; i++) {
        if (/[0-9]/.test(originalValue[i])) digitsBeforeCursor++;
    }
    // 2. Limpiar valor (quitar todo lo que no sea número o punto)
    let value = input.value.replace(/[^0-9.]/g, '');
    
    // Si está vacío, borrar y salir
    if (!value) {
        input.value = '';
        return;
    }
    // 3. Separar enteros y decimales para no forzar .00
    const parts = value.split('.');
    let integerPart = parts[0];
    let decimalPart = parts.length > 1 ? '.' + parts[1].substring(0, 2) : ''; // Máximo 2 decimales
    // 4. Formatear enteros con comas
    if (integerPart) {
        // Usar toLocaleString para las comas, pero asegurando base 10
        integerPart = parseInt(integerPart, 10).toLocaleString('es-MX');
    } else if (parts.length > 1) {
        // Si escribe ".50", asumimos "0.50"
        integerPart = '0';
    }
    // 5. Construir el nuevo valor final
    const newValue = '$' + integerPart + decimalPart;
    
    // Evitar re-asignar si no hubo cambios (evita parpadeos)
    if (input.value !== newValue) {
        input.value = newValue;
        // 6. Restaurar posición del cursor inteligente
        // Recorremos el nuevo valor buscando dónde calzan nuestros "digitsBeforeCursor"
        let newCursorPos = 0;
        let digitsFound = 0;
        for (let i = 0; i < newValue.length; i++) {
            if (/[0-9]/.test(newValue[i])) {
                digitsFound++;
            }
            if (digitsFound >= digitsBeforeCursor) {
                // Si encontramos el dígito, el cursor va justo después
                // Ajuste especial: si el siguiente char es una coma o punto, avanzamos uno más
                newCursorPos = i + 1; 
                // Si acabamos de pasar el último dígito deseado, paramos
                if (digitsFound === digitsBeforeCursor) break;
            }
        }
        
        // Si el cursor estaba al inicio (antes de cualquier dígito), ponerlo después del $
        if (digitsBeforeCursor === 0) newCursorPos = 1;
        
        input.setSelectionRange(newCursorPos, newCursorPos);
    }
}

// Función para inicializar el formato de moneda en campos específicos
function inicializarFormatoMonedaEnCampos(selectores) {
    selectores.forEach(selector => {
        const campos = document.querySelectorAll(selector);
        campos.forEach(campo => {
            // Verificar si el campo ya tiene event listeners para evitar duplicados
            if (campo.hasAttribute('data-formato-inicializado')) return;
            
            campo.setAttribute('data-formato-inicializado', 'true');
            
            // Formato inicial si ya tiene valor
            if (campo.value && !campo.value.startsWith('$')) {
                formatearEnTiempoReal(campo);
            }
            
            // EVENTO CLAVE: 'input' para formatear mientras escribes
            campo.addEventListener('input', function() {
                formatearEnTiempoReal(this);
            });
            
            // Blur limpia entradas inválidas como "$" solo
            campo.addEventListener('blur', function() {
                if (this.value === '$') this.value = '';
            });
        });
    });
}













