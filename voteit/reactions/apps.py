from django.apps import AppConfig


class ReactionsConfig(AppConfig):
    name = "voteit.reactions"
    verbose_name = "Reactions"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.reactions import rules  # noqa
        from voteit.reactions import signals  # noqa
        from voteit.reactions.rest_api import views  # noqa
