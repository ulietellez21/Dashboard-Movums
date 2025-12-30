from django.apps import AppConfig


class AuditoriaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auditoria'
    verbose_name = 'Auditoría del Sistema'
    
    def ready(self):
        """Importa las señales cuando la app está lista."""
        import auditoria.signals  # noqa

