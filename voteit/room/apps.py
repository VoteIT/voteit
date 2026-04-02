from django.apps import AppConfig


class RoomConfig(AppConfig):
    name = "voteit.room"
    verbose_name = "Room"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import rules  # noqa
        from . import signals  # noqa
        from .rest_api import views  # noqa
