from django.apps import AppConfig


class BuchhaltungConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.buchhaltung'
    verbose_name = 'Buchhaltung'

    def ready(self):
        import apps.buchhaltung.signals  # noqa: F401
