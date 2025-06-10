from django.apps import AppConfig


class SpeakerConfig(AppConfig):
    name = "voteit.speaker"
    verbose_name = "Speaker"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.speaker import rules  # noqa
        from voteit.speaker import roles  # noqa
        from voteit.speaker import signals  # noqa
        from voteit.speaker import messages  # noqa
        from voteit.speaker.rest_api import views  # noqa

        from voteit.speaker.app.list_methods import register

        register()
