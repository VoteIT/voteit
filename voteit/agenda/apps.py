from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AgendaConfig(AppConfig):
    name = 'voteit.agenda'
    verbose_name = _('Agenda')

    def ready(self):
        # Make sure rules are loaded
        from voteit.agenda import rules
