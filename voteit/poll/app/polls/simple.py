from __future__ import annotations

from django.db import models
from django.utils.translation import gettext as _

from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.abcs import PollMethod, Vote
from voteit.poll.registries import poll_methods


@poll_methods
class Simple(PollMethod):
    """ This poll method is a simple approve / deny,
        but also the base for all tests that should run against the abstract PollMethod.
    """

    title = _("Simple")

    def start_check(self):
        if self.poll.proposals.count() != 1:
            raise InvalidProposalCount("Must be exactly one")

    @property
    def vote_factory(self) -> SimpleVote:
        return SimpleVote


class SimpleVote(Vote):
    APPROVE = 1
    DENY = 2
    VOTE_CHOICES = ((APPROVE, _("Approve")), (DENY, _("Deny")))

    choice = models.PositiveSmallIntegerField(choices=VOTE_CHOICES, null=True)
    method = models.ForeignKey(
        Simple, on_delete=models.CASCADE, related_name="vote_set"
    )

    def ballot(self):
        return self.choice
