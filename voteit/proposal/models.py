from django.db import models

from django_fsm import FSMField, transition
from voteit.core.models import BaseContent
from voteit.proposal.workflows import ProposalWf


class Proposal(BaseContent):
    state = FSMField(
        default=ProposalWf.initial, choices=ProposalWf.choices(), protected=True
    )
    prop_id = models.CharField(max_length=50)
    agenda_item = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        null=True,
        related_name="proposals",
    )

    @transition(field=state, source=ProposalWf.PUBLISHED, target=ProposalWf.RETRACTED)
    def retract(self):
        """ Normal user operation to retract. """
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.RETRACTED],
        target=ProposalWf.VOTING,
    )
    def lock_for_vote(self):
        """ When a vote starts, mark all proposals as "voting" so they can't be retracted.
            In case a retracted proposal is part of the vote, lock that too
            since it might have been retracted very late.
        """
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.VOTING],
        target=ProposalWf.APPROVED,
    )
    def approved(self):
        """ Proposal approved via poll or moderator. """
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.VOTING],
        target=ProposalWf.DENIED,
    )
    def denied(self):
        """ Proposal denied via poll or moderator. """
        pass

    @transition(field=state, source=ProposalWf.PUBLISHED, target=ProposalWf.UNHANDLED)
    def unhandled(self):
        """ Proposal was never handled. Automatic transition or from moderator. """
        pass

    @transition(field=state, target=ProposalWf.PUBLISHED)
    def publish(self):
        """ Reset proposal back to published. """
        pass
