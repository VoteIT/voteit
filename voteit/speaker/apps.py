from django.apps import AppConfig


class SpeakerConfig(AppConfig):
    name = "voteit.speaker"
    verbose_name = "Speaker"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.speaker import rules
        from voteit.speaker import roles
        from voteit.speaker import signals
        from voteit.meeting import channels
        from voteit.speaker import messages

        from .rest_api import views
        from voteit.speaker.app.list_methods import register

        register()
