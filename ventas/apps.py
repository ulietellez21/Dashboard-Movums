from django.apps import AppConfig


class VentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ventas'
    
    def ready(self):
        """Carga las señales cuando la aplicación está lista."""
        import ventas.signals  # noqa