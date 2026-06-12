from django.apps import AppConfig


class SKRConfig(AppConfig):
    name = "voteit.app.skr"
    verbose_name = "SKR"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import er  # noqa
