from __future__ import annotations

from collections import Counter

from django.db import models
from django.utils.translation import gettext_lazy as _

from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.abcs import PollMethod, Vote
from voteit.poll.registries import poll_methods


class SimpleVote(Vote):
    APPROVE = 1
    DENY = 2
    VOTE_CHOICES = ((APPROVE, _("Approve")), (DENY, _("Deny")))

    choice = models.PositiveSmallIntegerField(choices=VOTE_CHOICES, null=True)
    method = models.ForeignKey(
        'poll.Simple', on_delete=models.CASCADE, related_name="vote_set"
    )

    @property
    def ballot(self):
        return self.choice


@poll_methods
class Simple(PollMethod):
    """ This poll method is a simple approve / deny,
        but also the base for all tests that should run against the abstract PollMethod.
    """
    title = _("Simple")
    vote_model = SimpleVote
    approves = models.PositiveIntegerField(null=True, editable=False)
    denies = models.PositiveIntegerField(null=True, editable=False)

    def calculate_result(self, ballots: Counter):
        self.approves = ballots[SimpleVote.APPROVE]
        self.denies = ballots[SimpleVote.DENY]
        return self.get_result()

    def get_result(self) -> dict:
        return {
            "approve": self.approves and self.approves or 0,
            "deny": self.denies and self.denies or 0,
        }

    def start_check(self):
        if self.poll.proposals.count() != 1:
            raise InvalidProposalCount("Must be exactly one")
