from django.db import models
from django.utils.translation import gettext as _
from voteit.poll.exceptions import InvalidProposalCount

from voteit.poll.models import poll_methods, PollMethod, Vote


class SimpleVote(Vote):
    APPROVE = 1
    DENY = 2
    VOTE_CHOICES = ((APPROVE, _("Approve")), (DENY, _("Deny")))

    choice = models.PositiveSmallIntegerField(choices=VOTE_CHOICES, null=True)

    def ballot(self):
        return self.choice


@poll_methods
class Simple(PollMethod):
    title = _("Simple")
    Vote = SimpleVote

    def start_check(self):
        if self.poll.proposals.count() != 1:
            raise InvalidProposalCount("Must be exactly one")
