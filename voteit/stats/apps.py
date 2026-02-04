from django.apps import AppConfig


class StatsConfig(AppConfig):
    name = "voteit.stats"
    verbose_name = "VoteIT Statistics"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        # Register
        from . import jobs  # noqa
