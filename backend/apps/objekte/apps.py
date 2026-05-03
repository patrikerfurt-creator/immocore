from django.apps import AppConfig


class ObjekteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.objekte'
    verbose_name = 'Objekte'

    def ready(self):
        import apps.objekte.signals  # noqa: F401
