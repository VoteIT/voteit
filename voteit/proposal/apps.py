from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProposalConfig(AppConfig):
    name = "voteit.proposal"
    verbose_name = _("Proposals")

    def ready(self):
        from voteit.proposal import rules
        from voteit.proposal import rest_api
        from voteit.proposal import messages
