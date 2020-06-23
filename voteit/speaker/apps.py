from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SpeakerConfig(AppConfig):
    name = 'voteit.speaker'
    verbose_name = _("Speaker")

    def ready(self):
        pass
        # from voteit.speaker import rules
