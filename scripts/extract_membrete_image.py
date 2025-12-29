#!/usr/bin/env python
"""
Script para extraer la imagen del membrete desde el archivo DOCX.
"""
import os
import sys
from pathlib import Path

# Añadir el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from docx import Document
    from PIL import Image
    import io
except ImportError as e:
    print(f"Error: {e}")
    print("Instala las dependencias: pip install python-docx pillow")
    sys.exit(1)

def extract_membrete_image(docx_path, output_dir):
    """
    Extrae la primera imagen del documento DOCX y la guarda como PNG.
    """
    if not os.path.exists(docx_path):
        print(f"Error: No se encontró el archivo {docx_path}")
        return None
    
    try:
        doc = Document(docx_path)
        
        # Buscar imágenes en el documento
        # python-docx no tiene método directo, necesitamos acceder al XML
        from docx.oxml import parse_xml
        from docx.oxml.ns import qn
        
        # Buscar relaciones de imágenes
        part = doc.part
        image_parts = []
        
        # Buscar en el documento principal
        for rel in part.rels.values():
            if "image" in rel.target_ref:
                image_parts.append(rel.target_part)
        
        # También buscar en headers
        for header_part in doc.part.related_parts.values():
            if hasattr(header_part, 'rels'):
                for rel in header_part.rels.values():
                    if "image" in rel.target_ref:
                        image_parts.append(rel.target_part)
        
        if not image_parts:
            print("No se encontraron imágenes en el documento.")
            print("Intentando método alternativo...")
            # Método alternativo: buscar en el XML directamente
            return extract_from_xml(docx_path, output_dir)
        
        # Tomar la primera imagen
        image_part = image_parts[0]
        image_data = image_part.blob
        
        # Guardar como PNG
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'membrete.png')
        
        # Convertir a PIL Image y guardar
        img = Image.open(io.BytesIO(image_data))
        img.save(output_path, 'PNG')
        
        print(f"✅ Imagen extraída exitosamente: {output_path}")
        print(f"   Dimensiones: {img.size[0]}x{img.size[1]} píxeles")
        return output_path
        
    except Exception as e:
        print(f"Error al extraer imagen: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_from_xml(docx_path, output_dir):
    """
    Método alternativo: extraer imagen desde el XML del DOCX.
    """
    import zipfile
    import shutil
    
    try:
        # DOCX es un archivo ZIP
        with zipfile.ZipFile(docx_path, 'r') as zip_ref:
            # Buscar imágenes en word/media/
            image_files = [f for f in zip_ref.namelist() if f.startswith('word/media/')]
            
            if not image_files:
                print("No se encontraron imágenes en word/media/")
                return None
            
            # Tomar la primera imagen
            image_file = image_files[0]
            image_data = zip_ref.read(image_file)
            
            # Determinar extensión
            ext = os.path.splitext(image_file)[1].lower()
            if ext not in ['.png', '.jpg', '.jpeg']:
                # Convertir a PNG si es necesario
                img = Image.open(io.BytesIO(image_data))
                output_path = os.path.join(output_dir, 'membrete.png')
                img.save(output_path, 'PNG')
            else:
                output_path = os.path.join(output_dir, f'membrete{ext}')
                with open(output_path, 'wb') as f:
                    f.write(image_data)
            
            os.makedirs(output_dir, exist_ok=True)
            print(f"✅ Imagen extraída exitosamente: {output_path}")
            
            # Mostrar información
            img = Image.open(output_path)
            print(f"   Dimensiones: {img.size[0]}x{img.size[1]} píxeles")
            print(f"   Formato: {img.format}")
            
            return output_path
            
    except Exception as e:
        print(f"Error en método alternativo: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    # Rutas
    base_dir = Path(__file__).parent.parent
    docx_path = base_dir / 'docs' / 'membrete.docx'
    output_dir = base_dir / 'static' / 'img'
    
    print("=" * 60)
    print("Extractor de Imagen del Membrete")
    print("=" * 60)
    print(f"Archivo DOCX: {docx_path}")
    print(f"Directorio de salida: {output_dir}")
    print()
    
    result = extract_membrete_image(str(docx_path), str(output_dir))
    
    if result:
        print()
        print("=" * 60)
        print("✅ Proceso completado exitosamente")
        print("=" * 60)
    else:
        print()
        print("=" * 60)
        print("❌ Error al extraer la imagen")
        print("=" * 60)
        sys.exit(1)
