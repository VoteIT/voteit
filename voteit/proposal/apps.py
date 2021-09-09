from django.apps import AppConfig


class ProposalConfig(AppConfig):
    name = "voteit.proposal"
    verbose_name = "Proposals"

    def ready(self):
        from voteit.proposal import rules
        from voteit.proposal import rest_api
        from voteit.proposal import messages
        from voteit.proposal import signals
        from voteit.proposal.app import proposal_id
