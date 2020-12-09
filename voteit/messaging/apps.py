from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MessagingConfig(AppConfig):
    name = 'voteit.messaging'
    verbose_name = _("Messaging")

    def ready(self):
        from voteit.messaging import registries
        from voteit.messaging import messages
        messages.register()
        from voteit.messaging import channels
        channels.register()
        from voteit.messaging import signals
