from django.apps import AppConfig


class ProposalConfig(AppConfig):
    name = "voteit.proposal"
    verbose_name = "Proposals"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.proposal import rules
        from .rest_api import views
        from voteit.proposal import messages
        from voteit.proposal import signals
        from voteit.proposal.app import proposal_id
