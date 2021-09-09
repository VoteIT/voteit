from django.apps import AppConfig


class SpeakerConfig(AppConfig):
    name = "voteit.speaker"
    verbose_name = "Speaker"

    def ready(self):
        from voteit.speaker import rules
        from voteit.speaker import roles
        from voteit.speaker import signals
        from voteit.speaker import messages
        from voteit.speaker import rest_api
        from voteit.speaker.app.list_methods import register

        register()
