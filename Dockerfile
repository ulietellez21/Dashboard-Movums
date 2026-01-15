FROM python:3.12-slim

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements y instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar proyecto
COPY . .

# Recopilar archivos estáticos
RUN python manage.py collectstatic --noinput || true

# Exponer puerto
EXPOSE 8000

# Comando por defecto
CMD ["gunicorn", "agencia_web.wsgi:application", "--bind", "0.0.0.0:8000"]





















