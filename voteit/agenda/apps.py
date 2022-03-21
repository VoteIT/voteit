from django.apps import AppConfig


class AgendaConfig(AppConfig):
    name = "voteit.agenda"
    verbose_name = "Agenda"

    def ready(self):
        from voteit.agenda import rules
        from .rest_api import views
        from voteit.agenda import channels
        from voteit.agenda import messages
        from voteit.agenda import signals
