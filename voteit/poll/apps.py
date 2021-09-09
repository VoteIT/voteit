from django.apps import AppConfig


class PollConfig(AppConfig):
    name = "voteit.poll"
    verbose_name = "Polls"

    def ready(self):
        from voteit.poll.app import polls
        from voteit.poll.app import er_policys
        from voteit.poll import rules
        from voteit.poll import rest_api
        from voteit.poll import channels
        from voteit.poll import messages
        from voteit.poll import signals
