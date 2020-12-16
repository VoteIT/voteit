from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AgendaConfig(AppConfig):
    name = 'voteit.agenda'
    verbose_name = _('Agenda')

    def ready(self):
        from voteit.agenda import rules
        from voteit.agenda import rest_api
        from voteit.agenda import channels
        from voteit.agenda import messages
