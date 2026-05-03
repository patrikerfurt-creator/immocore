from django.apps import AppConfig


class KontenConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.konten'
    verbose_name = 'Konten'

    def ready(self):
        import apps.konten.signals  # noqa: F401
