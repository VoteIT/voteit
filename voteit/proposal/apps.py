from django.apps import AppConfig


class ProposalConfig(AppConfig):
    name = "voteit.proposal"
    verbose_name = "Proposals"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from voteit.proposal import rules  # noqa
        from voteit.proposal.rest_api import views  # noqa
        from voteit.proposal import messages  # noqa
        from voteit.proposal import signals  # noqa
        from voteit.proposal.app import proposal_id  # noqa
