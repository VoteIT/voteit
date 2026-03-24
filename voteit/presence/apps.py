from django.apps import AppConfig


class PresenceConfig(AppConfig):
    name = "voteit.presence"
    verbose_name = "Presence"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.presence import components  # noqa
        from voteit.presence import rules  # noqa
