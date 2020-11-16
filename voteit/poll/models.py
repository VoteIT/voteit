from __future__ import annotations

from collections import Counter
from hashlib import sha512
from json import dumps
from logging import getLogger

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import UniqueConstraint
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition, post_transition
from voteit.core.models import BaseContent
from voteit.meeting.models import Meeting
from voteit.poll.abcs import PollMethod
from voteit.poll.exceptions import (
    BallotChecksumError,
    ElectoralRegisterEmpty,
    ElectoralRegisterMissing,
    InvalidPollMethod,
    InvalidProposalCount,
    PollNotFinished,
)
from voteit.poll.workflows import PollWf

logger = getLogger(__name__)


class VoterWeight(models.Model):
    register = models.ForeignKey("ElectoralRegister", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    weight = models.PositiveIntegerField(default=1)


class ElectoralRegister(models.Model):
    created = models.DateTimeField(editable=False, auto_now_add=True)
    voters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through=VoterWeight,
        related_name="electoral_registers",
    )
    meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="electoral_registers", null=True
    )

    def get_voter_weight(self, user: AbstractUser) -> int:
        """
        Allow votes to have a weight in some contexts.
        Will raise VoterWeight.DoesNotExist if user not in registry.
        """
        return self.voterweight_set.get(user=user).weight


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
    proposals = models.ManyToManyField("proposal.Proposal", related_name="polls")
    method_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    method_id = models.PositiveIntegerField(null=True)
    method = GenericForeignKey("method_type", "method_id")
    created = models.DateTimeField(editable=False, auto_now_add=True)
    started = models.DateTimeField(editable=False, null=True)
    closed = models.DateTimeField(editable=False, null=True)
    initial_electoral_register = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="polls_initial",
    )
    electoral_register: ElectoralRegister = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="polls",
    )
    ballot_data = models.TextField(
        verbose_name=_("JSON-serialized ballot data"), editable=False, null=True
    )
    ballot_checksum = models.CharField(
        verbose_name=_("SHA512 checksum of ballot data"),
        max_length=128,
        editable=False,
        null=True,
    )
    abstains = models.PositiveIntegerField(
        verbose_name=_("Abstentions"), default=0, editable=False
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["method_type", "method_id"],
                name="%(app_label)s_%(class)s_method",
            )
        ]

    def start_check(self) -> bool:
        """ Check that this poll could be started. A very basic check for the most obvious things.
            Note that it's used as a transition condition, so it must return True if everything is ok!
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
        return True

    @transition(field=state, source=PollWf.PRIVATE, target=PollWf.UPCOMING)
    def upcoming(self):
        pass

    @transition(
        field=state,
        source=PollWf.UPCOMING,
        target=PollWf.ONGOING,
        conditions=[start_check],
    )
    def ongoing(self):
        self.started = now()

    @transition(
        field=state,
        source=[PollWf.ONGOING, PollWf.FAILED, PollWf.CLOSED],
        target=PollWf.CLOSED,
    )
    def close(self):
        """ Close the poll for further votes.
            The next step is always to count the votes via the method finish()
        """
        self._mark_closed()

    @transition(
        field=state,
        source=PollWf.CLOSED,
        target=PollWf.FINISHED,
        on_error=PollWf.FAILED,
    )
    def finish(self):
        """ Count the votes and finish up. """
        # Remove bad votes due to a change in electoral register during the poll.
        # This is probably not allowed in most meetings.
        self.vote_cleanup_set().delete()
        ballots, abstains = self.get_ballots()
        self.store_ballots(ballots, abstains)
        self.method.calculate_result(ballots)

    @transition(field=state, source=PollWf.ONGOING, target=PollWf.CANCELED)
    def cancel(self):
        self._mark_closed()

    @transition(field=state, source=PollWf.UPCOMING, target=PollWf.PRIVATE)
    def unpublish(self):
        pass

    def _mark_closed(self):
        if not self.closed:
            self.closed = now()

    def store_ballots(self, ballots: Counter, abstains=0):
        """ Make sure ballot data is saved even if the votes will be cleared later on.
        """
        self.abstains = abstains
        self.ballot_data = dumps(ballots)
        self.ballot_checksum = sha512(self.ballot_data.encode("utf-8")).hexdigest()
        logger.info(
            "Finalized ballots for %s. Checksum: %s", self, self.ballot_checksum
        )

    def get_ballots(self) -> (Counter, int):
        """ Return JSON-serializable result counter and number of abstentions.
        """
        counter = Counter()
        abstains = 0
        for v in self.method.get_votes():
            if v.abstain:
                abstains += v.weight
            else:
                counter[v.ballot] += v.weight
        return counter, abstains

    def verify_checksum(self):
        if self.state != PollWf.FINISHED:
            raise PollNotFinished()
        if not self.ballot_checksum:
            raise BallotChecksumError(f"Checksum empty for {self}")
        if not self.ballot_data:
            raise BallotChecksumError(f"Ballot data empty for {self}")
        checksum = sha512(self.ballot_data.encode("utf-8")).hexdigest()
        if self.ballot_checksum == checksum:
            return True
        else:
            raise BallotChecksumError(
                f"Checksum doesn't match for {self}. Stored: {self.ballot_checksum}, Current: {checksum}"
            )

    def vote_cleanup_set(self):
        """ Votes that shouldn't be here if the poll closes.
            Essentially that someone has voted but aren't in the current electoral register.
        """
        voters = self.electoral_register.voters.all()
        return self.get_votes().exclude(user__in=voters)

    def get_votes(self):
        return self.method.get_votes()

    def get_result(self):
        if self.state != PollWf.FINISHED:
            raise PollNotFinished(f"{self} is in state {self.state}")
        return self.method.get_result()

    def save(self, **kw):
        if self.method is not None:
            if not isinstance(self.method, PollMethod):
                # FIXME: Probably something Django-ish instead
                raise InvalidPollMethod(f"{self.method} is not a PollMethod instance.")
        super().save(**kw)


@receiver(post_transition, sender=Poll)
def finish_closed_poll(
    sender: Poll, instance: Poll, source: str, target: str, **kwargs
):
    """ As soon as the poll has closed, calculate the result.
        This method should probably offload this transition change to a worker later on.
    """
    if target == PollWf.CLOSED:
        instance.finish()
