from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PNConfig(AppConfig):
    name = "voteit.participant_number"
    verbose_name = _("Participant number")

    def ready(self):
        pass
