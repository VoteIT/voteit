from __future__ import annotations

from logging import getLogger
from random import sample
from string import ascii_lowercase
from typing import Optional
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django_fsm import FSMField
from django_fsm import transition

from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent
from voteit.proposal.permissions import ProposalPermissions
from voteit.proposal.workflows import ProposalWf
from voteit.reactions.mixins import Reactable

if TYPE_CHECKING:
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import Meeting
    from voteit.meeting.models import MeetingGroup

__all__ = ("Proposal",)

logger = getLogger(__name__)


class Proposal(BaseContent, AgendaItemContext, MeetingContext, Reactable):
    state: str = FSMField(
        default=ProposalWf.initial, choices=ProposalWf.choices(), protected=True
    )
    author: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="proposals",
    )
    meeting_group: MeetingGroup = models.ForeignKey(
        "meeting.MeetingGroup",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="proposals",
    )
    prop_id: str = models.CharField(max_length=50)
    agenda_item: AgendaItem = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        null=True,
        related_name="proposals",
    )

    @property
    def meeting(self) -> Optional[Meeting]:
        """ While not directly related, it still good to be able to do lookups this way"""
        if self.agenda_item:
            return self.agenda_item.meeting

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["prop_id", "agenda_item"],
                name="prop_id_unique_for_ai",
            )
        ]

    @transition(
        field=state,
        source=ProposalWf.PUBLISHED,
        target=ProposalWf.RETRACTED,
        permission=ProposalPermissions.RETRACT,
    )
    def retract(self):
        """ Normal user operation to retract. Or for moderators."""
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.RETRACTED],
        target=ProposalWf.VOTING,
        permission=ProposalPermissions.CHANGE,
    )
    def lock_for_vote(self):
        """When a vote starts, mark all proposals as "voting" so they can't be retracted.
        In case a retracted proposal is part of the vote, lock that too
        since it might have been retracted very late.
        """
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.VOTING],
        target=ProposalWf.APPROVED,
        permission=ProposalPermissions.CHANGE,
    )
    def approved(self):
        """ Proposal approved via poll or moderator. """
        pass

    @transition(
        field=state,
        source=[ProposalWf.PUBLISHED, ProposalWf.VOTING],
        target=ProposalWf.DENIED,
        permission=ProposalPermissions.CHANGE,
    )
    def denied(self):
        """ Proposal denied via poll or moderator. """
        pass

    @transition(
        field=state,
        source=ProposalWf.PUBLISHED,
        target=ProposalWf.UNHANDLED,
        permission=ProposalPermissions.CHANGE,
    )
    def unhandled(self):
        """ Proposal was never handled. Automatic transition or from moderator. """
        pass

    @transition(
        field=state, target=ProposalWf.PUBLISHED, permission=ProposalPermissions.CHANGE
    )
    def publish(self):
        """ Reset proposal back to published. """
        pass

    def set_tags(self):
        super().set_tags()
        if self.prop_id not in self.tags:
            self.tags.append(self.prop_id)

    def save(self, **kw):
        if not self.prop_id and self.meeting is not None:
            pid_policy = self.meeting.pid_policy
            suggestion = pid_policy(self)
            if suggestion:
                self.prop_id = suggestion
            else:
                self.prop_id = _new_proposal_id(self)
        super().save(**kw)


def _new_proposal_id(proposal: Proposal) -> str:
    # FIXME: Do something nice here that isn't just random
    return "".join(sample(ascii_lowercase, 8))
