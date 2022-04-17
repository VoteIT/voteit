from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PNConfig(AppConfig):
    name = "voteit.participant_number"
    verbose_name = _("Participant number")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.participant_number import signals
        from voteit.participant_number import messages
