from django.apps import AppConfig


class ReactionsConfig(AppConfig):
    name = "voteit.reactions"
    verbose_name = "Reactions"

    def ready(self):
        from voteit.reactions import rules
        from voteit.reactions import signals
