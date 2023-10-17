from django.apps import AppConfig


class RoomConfig(AppConfig):
    name = "voteit.room"
    verbose_name = "Room"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import permissions
        from . import rules
        from . import signals
        from .rest_api import views
