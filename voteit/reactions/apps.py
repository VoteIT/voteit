from django.apps import AppConfig


class ReactionsConfig(AppConfig):
    name = "voteit.reactions"
    verbose_name = "Reactions"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.reactions import rules
        from voteit.reactions import signals
        from .rest_api import views
