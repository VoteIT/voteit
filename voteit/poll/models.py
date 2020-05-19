from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import UniqueConstraint
from django_fsm import FSMField, transition
from voteit.core.models import BaseContent
from voteit.meeting.models import Meeting
from voteit.poll.exceptions import (
    ElectoralRegisterEmpty,
    ElectoralRegisterMissing,
    InvalidPollMethod,
    InvalidProposalCount,
)
from voteit.poll.workflows import PollWf
from voteit.poll.abcs import PollMethod


class ElectoralRegister(models.Model):
    created = models.DateTimeField(editable=False, auto_now_add=True)
    voters = models.ManyToManyField(User, related_name="electoral_registers")
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="electoral_registers", null=True
    )


class Poll(BaseContent):
    state = FSMField(default=PollWf.initial, choices=PollWf.choices(), protected=True)
    title = models.CharField(max_length=70)
    description = models.CharField(max_length=200)
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="polls", null=True
    )
    agenda_item = models.ForeignKey(
        "agenda.AgendaItem", on_delete=models.CASCADE, null=True, related_name="polls"
    )
    proposals = models.ManyToManyField("proposal.Proposal")
    method_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    method_id = models.PositiveIntegerField(null=True)
    method = GenericForeignKey("method_type", "method_id")
    created = models.DateTimeField(editable=False, auto_now_add=True)
    started = models.DateTimeField(editable=False, null=True)
    closed = models.DateTimeField(editable=False, null=True)
    initial_electoral_register = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.PROTECT,
        editable=False,
        null=True,
        related_name="polls_initial",
    )
    electoral_register = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.PROTECT,
        editable=False,
        null=True,
        related_name="polls",
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["method_type", "method_id"],
                name="%(app_label)s_%(class)s_method",
            )
        ]

    @transition(field=state, source=PollWf.PRIVATE, target=PollWf.UPCOMING)
    def upcoming(self):
        # Attach electoral register
        pass

    @transition(field=state, source=PollWf.UPCOMING, target=PollWf.ONGOING)
    def ongoing(self):
        self.start_check()

    @transition(field=state, source=PollWf.ONGOING, target=PollWf.CLOSED, on_error=PollWf.FAILED)
    def close(self):
        """ Failing poll methods should set the result to the reason for failing and raise an exception.
        """
        # Remove bad votes
        self.vote_cleanup_set().delete()
        # TODO: Get result and store somewhere.
        # self.result = self.method.get_result()
        # Or maybe:
        # self.method.calculate_result()

    @transition(field=state, source=PollWf.ONGOING, target=PollWf.CANCELED)
    def cancel(self):
        # Nothing really?
        pass

    def start_check(self):
        """ Check that this poll could be started. A very basic check for the most obvious things.
        """
        if self.electoral_register is None:
            raise ElectoralRegisterMissing()
        if self.electoral_register.voters.count() < 1:
            raise ElectoralRegisterEmpty()
        if not isinstance(self.method, PollMethod):
            raise InvalidPollMethod()
        if self.proposals.count() < 1:
            raise InvalidProposalCount("No proposals")
        # And check the specifics for the poll method
        self.method.start_check()

    def vote_cleanup_set(self):
        """ Votes that shouldn't be here if the poll closes.
            Essentially that someone has voted but aren't in the current electoral register.
        """
        voters = self.electoral_register.voters.all()
        return self.get_votes().exclude(user__in=voters)

    def get_votes(self):
        return self.method.get_votes()

    def get_vote_weight(self, user: User) -> int:
        """ Allow vote weight in some contexts. """
        # TODO
        return 1

    def save(self, **kw):
        if self.method is not None:
            if not isinstance(self.method, PollMethod):
                # FIXME: Probably something Django-ish instead
                raise InvalidPollMethod(f"{self.method} is not a PollMethod instance.")
        super().save(**kw)


# Touch DB models in apps
# FIXME: Is there no smarter way to do this?
from voteit.poll.app.polls import *
from voteit.poll.app.er_policys import *
