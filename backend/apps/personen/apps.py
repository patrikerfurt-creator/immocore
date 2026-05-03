from django.apps import AppConfig


class PersonenConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.personen'
    verbose_name = 'Personen'

    def ready(self):
        import apps.personen.signals  # noqa: F401
