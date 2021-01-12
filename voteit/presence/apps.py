from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PresenceConfig(AppConfig):
    name = 'voteit.presence'
    verbose_name = _("Presence")

    def ready(self):
        from voteit.presence import rules
        from voteit.presence import channels
        from voteit.presence import messages
        from voteit.presence import signals
        from voteit.presence import rest_api
