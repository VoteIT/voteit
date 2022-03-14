from django.apps import AppConfig


class PollConfig(AppConfig):
    name = "voteit.poll"
    verbose_name = "Polls"

    def ready(self):
        from voteit.poll import rules
        from .rest_api import views
        from voteit.poll import channels
        from voteit.poll import messages
        from voteit.poll import signals
        from voteit.poll.app.polls import register

        register()

        from voteit.poll.app import er_policies
