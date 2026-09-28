from django.apps import AppConfig


class ScouternaConfig(AppConfig):
    name = "voteit.app.scouterna"
    verbose_name = "Scouterna"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.app.scouterna import backends  # noqa
