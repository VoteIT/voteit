from django.apps import AppConfig
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    name = "voteit.core"
    verbose_name = _("VoteIT Core")

    def ready(self):
        from voteit.core import rules
        from voteit.core import signals
        from voteit.core import messages
        from voteit.core.registries import content_types

        # Register some of the other content types we might care about
        User = get_user_model()
        content_types["user"] = User
