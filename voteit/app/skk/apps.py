from django.apps import AppConfig


class SKKConfig(AppConfig):
    name = "voteit.app.skk"
    verbose_name = "SKK"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import er  # noqa
