from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SpeakerConfig(AppConfig):
    name = 'voteit.speaker'
    verbose_name = _("Speaker")

    def ready(self):
        from voteit.speaker import rules
        from voteit.speaker import roles
        from voteit.speaker import signals
        from voteit.speaker import messages
        from voteit.speaker.app.list_methods import register
        register()
