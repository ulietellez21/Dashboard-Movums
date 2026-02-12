# Makefile - Comandos útiles del proyecto
# Uso: make <target>

.PHONY: backup run test migrate

# Copia db.sqlite3 a backups/ con fecha/hora y elimina backups > 7 días
backup:
	./backup.sh

# Ejecutar servidor de desarrollo (requiere venv activado)
run:
	python manage.py runserver

# Ejecutar tests
test:
	pytest -v

# Aplicar migraciones
migrate:
	python manage.py migrate
