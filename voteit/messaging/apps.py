from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MessagingConfig(AppConfig):
    name = "voteit.messaging"
    verbose_name = _("Messaging")

    def ready(self):
        from voteit.messaging import channels
        from voteit.messaging import signals
        from voteit.messaging import messages

        channels.register()
        messages.register()
