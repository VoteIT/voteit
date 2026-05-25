from django.apps import AppConfig


class MeetingTokenAPIConfig(AppConfig):
    name = "voteit.token_api"
    verbose_name = "Meeting Token API"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import api  # noqa
        from . import rules  # noqa

        from voteit.token_api.views import register

        register()
