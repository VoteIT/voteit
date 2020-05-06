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
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="electoral_registers", null=True)


class Poll(BaseContent):
    state = FSMField(default=PollWf.initial, choices=PollWf.choices(), protected=True)
    title = models.CharField(max_length=70)
    description = models.CharField(max_length=200)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="polls", null=True)
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

    def change_electoral_register(
        self, electoral_register: ElectoralRegister, user: User
    ):
        self.electoral_register = electoral_register
        # FIXME: Delete all votes from users who aren't in the new registry when the poll closes?

    @transition(field=state, source=PollWf.PRIVATE, target=PollWf.UPCOMING)
    def upcoming(self):
        # Attach electoral register
        pass

    @transition(field=state, source=PollWf.UPCOMING, target=PollWf.ONGOING)
    def ongoing(self):
        self.start_check()

    @transition(field=state, source=PollWf.ONGOING, target=PollWf.CLOSED)
    def close(self):
        # Remove bad votes
        pass

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

    def get_votes(self):
        return self.method.get_votes()

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
