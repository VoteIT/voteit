from django.apps import AppConfig


class AgendaConfig(AppConfig):
    name = "voteit.agenda"
    verbose_name = "Agenda"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.agenda import rules  # noqa
        from voteit.agenda import channels  # noqa
        from voteit.agenda import messages  # noqa
        from voteit.agenda import signals  # noqa
        from voteit.agenda.rest_api import views  # noqa
