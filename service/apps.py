from django.apps import AppConfig


class ServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'service'

    def ready(self):
        # Registra las señales que mantienen Ticket.total sincronizado.
        from . import signals  # noqa: F401
