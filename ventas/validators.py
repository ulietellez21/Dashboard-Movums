"""
Validadores de seguridad para la aplicación de ventas.
"""
import os
import logging

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# Configuración de tipos de archivo permitidos
ALLOWED_MIME_TYPES = {
    # PDFs
    'application/pdf': ['.pdf'],
    # Imágenes
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/gif': ['.gif'],
    'image/webp': ['.webp'],
    # Microsoft Word
    'application/msword': ['.doc'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    # Microsoft Excel (opcional)
    'application/vnd.ms-excel': ['.xls'],
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
}

# Tamaño máximo de archivo: 10 MB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB en bytes

# Extensiones permitidas (derivadas de ALLOWED_MIME_TYPES)
ALLOWED_EXTENSIONS = set()
for extensions in ALLOWED_MIME_TYPES.values():
    ALLOWED_EXTENSIONS.update(extensions)


def validate_uploaded_file(file):
    """
    Valida un archivo subido verificando:
    1. Tamaño máximo (10 MB)
    2. Tipo MIME real (usando python-magic)
    3. Extensión coincide con el tipo MIME
    
    Args:
        file: Objeto de archivo de Django (InMemoryUploadedFile o TemporaryUploadedFile)
    
    Returns:
        True si el archivo es válido
        
    Raises:
        ValidationError: Si el archivo no cumple con los requisitos
    """
    if not file:
        raise ValidationError('No se proporcionó ningún archivo.')
    
    # 1. Validar tamaño
    if file.size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        file_mb = file.size / (1024 * 1024)
        raise ValidationError(
            f'El archivo "{file.name}" excede el tamaño máximo permitido de {max_mb} MB. '
            f'Tamaño actual: {file_mb:.2f} MB.'
        )
    
    # 2. Validar extensión primero (verificación rápida)
    file_ext = os.path.splitext(file.name)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f'Extensión de archivo no permitida: {file_ext}. '
            f'Extensiones permitidas: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
        )
    
    # 3. Validar tipo MIME real (usando python-magic si está disponible)
    if MAGIC_AVAILABLE:
        try:
            # Leer los primeros bytes para detectar el tipo MIME real
            file.seek(0)
            file_header = file.read(2048)
            file.seek(0)  # Resetear el puntero del archivo
            
            detected_mime = magic.from_buffer(file_header, mime=True)
            
            if detected_mime not in ALLOWED_MIME_TYPES:
                raise ValidationError(
                    f'Tipo de archivo no permitido: {detected_mime}. '
                    f'Solo se permiten: PDF, imágenes (JPG, PNG, GIF, WebP) y documentos Word.'
                )
            
            # 4. Verificar que la extensión coincida con el tipo MIME detectado
            valid_extensions = ALLOWED_MIME_TYPES.get(detected_mime, [])
            if file_ext not in valid_extensions:
                raise ValidationError(
                    f'La extensión del archivo ({file_ext}) no coincide con su contenido real ({detected_mime}). '
                    f'Esto puede indicar un archivo manipulado.'
                )
                
        except Exception as e:
            # Si hay error al detectar, loguear pero permitir (fallback a validación por extensión)
            logger.warning(f"Error al validar tipo MIME de {file.name}: {str(e)}")
    else:
        # Si python-magic no está disponible, solo validar por extensión
        logger.warning("python-magic no disponible. Validando solo por extensión.")
    
    return True


def validate_image_file(file):
    """
    Validador específico para archivos de imagen.
    Más restrictivo que validate_uploaded_file.
    """
    ALLOWED_IMAGE_MIMES = {
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png'],
        'image/gif': ['.gif'],
        'image/webp': ['.webp'],
    }
    
    if not file:
        raise ValidationError('No se proporcionó ningún archivo de imagen.')
    
    # Validar tamaño (5 MB para imágenes)
    max_size = 5 * 1024 * 1024
    if file.size > max_size:
        raise ValidationError(
            f'La imagen excede el tamaño máximo de 5 MB. Tamaño: {file.size / (1024*1024):.2f} MB.'
        )
    
    # Validar extensión
    file_ext = os.path.splitext(file.name)[1].lower()
    allowed_ext = set()
    for exts in ALLOWED_IMAGE_MIMES.values():
        allowed_ext.update(exts)
    
    if file_ext not in allowed_ext:
        raise ValidationError(
            f'Solo se permiten imágenes: {", ".join(sorted(allowed_ext))}'
        )
    
    # Validar MIME si magic está disponible
    if MAGIC_AVAILABLE:
        try:
            file.seek(0)
            detected_mime = magic.from_buffer(file.read(2048), mime=True)
            file.seek(0)
            
            if detected_mime not in ALLOWED_IMAGE_MIMES:
                raise ValidationError(
                    f'El archivo no es una imagen válida. Tipo detectado: {detected_mime}'
                )
        except Exception as e:
            logger.warning(f"Error validando imagen: {e}")
    
    return True


def safe_int(value, default=None):
    """
    Convierte un valor a entero de forma segura.
    
    Evita errores 500 cuando el usuario manipula parámetros de URL.
    
    Args:
        value: Valor a convertir (puede ser string, None, etc.)
        default: Valor por defecto si la conversión falla
    
    Returns:
        int o el valor default si la conversión falla
    
    Examples:
        >>> safe_int('123')
        123
        >>> safe_int('abc', default=0)
        0
        >>> safe_int(None, default=1)
        1
        >>> safe_int('12.5', default=12)
        12
    """
    if value is None:
        return default
    
    try:
        # Intentar convertir directamente
        return int(value)
    except (ValueError, TypeError):
        try:
            # Intentar convertir desde float (para casos como '12.0')
            return int(float(value))
        except (ValueError, TypeError):
            return default
