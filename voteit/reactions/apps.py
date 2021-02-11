from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ReactionsConfig(AppConfig):
    name = "voteit.reactions"
    verbose_name = _("Reactions")

    def ready(self):
        from voteit.reactions import rules
