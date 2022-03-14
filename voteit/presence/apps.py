from django.apps import AppConfig


class PresenceConfig(AppConfig):
    name = "voteit.presence"
    verbose_name = "Presence"

    def ready(self):
        from voteit.presence import rules
        from voteit.presence import channels
        from voteit.presence import messages
        from voteit.presence import signals
        from .rest_api import views
