from django.apps import AppConfig


class PresenceConfig(AppConfig):
    # Deprecated, models dropped in 0008. Kept only so that migration can run.
    name = "voteit.presence"
    verbose_name = "Presence"
    default_auto_field = "django.db.models.BigAutoField"
