from __future__ import annotations

import itertools
from collections import Counter
from contextlib import suppress
from datetime import datetime
from hashlib import sha512
from json import dumps
from logging import getLogger
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING
from typing import Type
from typing import Union

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError
from django.db import models
from django.db.models import Sum
from django.db.models import UniqueConstraint
from django.dispatch import receiver
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import TransitionNotAllowed
from django_fsm import post_transition
from django_fsm import transition
from pydantic import ValidationError
from pydantic.main import BaseModel
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent
from voteit.core.permissions import NOT_ALLOWED
from voteit.meeting.models import Meeting
from voteit.poll.exceptions import BallotChecksumError
from voteit.poll.exceptions import ElectoralRegisterEmpty
from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import InvalidPollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.exceptions import NotAllowedToVote
from voteit.poll.exceptions import PollNotFinished
from voteit.poll.permissions import PollPermissions
from voteit.poll.schemas import PollResult
from voteit.poll.utils import get_poll_method_registry
from voteit.poll.workflows import PollWf

if TYPE_CHECKING:
    from voteit.poll.abcs import PollMethod


__all__ = "VoterWeight", "ElectoralRegister", "Poll", "Vote"

logger = getLogger(__name__)


class VoterWeight(models.Model):
    register = models.ForeignKey("ElectoralRegister", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    weight = models.PositiveIntegerField(default=1)
    # Annotations
    objects: models.Manager


class ElectoralRegister(MeetingContext):
    name = "electoral_register"
    created = models.DateTimeField(editable=False, auto_now_add=True)
    voters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through=VoterWeight,
        related_name="electoral_registers",
    )
    meeting: Optional[Meeting] = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="electoral_registers", null=True
    )

    def get_voter_weight(self, user: AbstractUser) -> int:
        """
        Allow votes to have a weight in some contexts.
        Will raise VoterWeight.DoesNotExist if user not in registry.
        """
        return self.voterweight_set.get(user=user).weight

    def get_total_vote_weight(self) -> int:
        # FIXME: Is this the correct method? :)
        return self.voterweight_set.aggregate(Sum("weight"))["weight__sum"]

    class QuerySet(models.QuerySet):
        def for_user(self, user: AbstractUser):
            return self.filter(meeting__participants=user).distinct()

    class Manager(models.Manager):
        def get_queryset(self):
            return ElectoralRegister.QuerySet(self.model, using=self._db)

        def for_user(self, user: AbstractUser):
            return self.get_queryset().for_user(user)

    objects = Manager()


class Poll(BaseContent, MeetingContext, AgendaItemContext):
    name = "poll"
    state = FSMField(default=PollWf.initial, choices=PollWf.choices(), editable=False)
    title = models.CharField(max_length=70)
    description = models.CharField(max_length=200)
    meeting: Optional[Meeting] = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="polls", null=True
    )
    agenda_item = models.ForeignKey(
        "agenda.AgendaItem", on_delete=models.CASCADE, null=True, related_name="polls"
    )
    proposals = models.ManyToManyField("proposal.Proposal", related_name="polls")
    method_name: str = models.CharField(max_length=20)
    settings_data: Optional[Dict] = models.JSONField(null=True, blank=True)
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    started: Optional[datetime] = models.DateTimeField(editable=False, null=True)
    closed: Optional[datetime] = models.DateTimeField(editable=False, null=True)
    initial_electoral_register: Optional[ElectoralRegister] = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="polls_initial",
    )
    electoral_register: Optional[ElectoralRegister] = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="polls",
    )
    ballot_data: Optional[str] = models.TextField(
        verbose_name=_("JSON-serialized ballot data"), editable=False, null=True
    )
    ballot_checksum: Optional[str] = models.CharField(
        verbose_name=_("SHA512 checksum of ballot data"),
        max_length=128,
        editable=False,
        null=True,
    )
    abstains: int = models.PositiveIntegerField(
        verbose_name=_("Abstentions"), default=0, editable=False
    )
    result_data: Optional[Dict] = models.JSONField(
        verbose_name=_("JSON-serialized result data"),
        editable=False,
        null=True,
        encoder=DjangoJSONEncoder,
    )

    def get_method_class(self) -> Type[PollMethod]:
        """Fetch the poll method class, a django proxy model."""
        reg = get_poll_method_registry()
        if self.method_name not in reg:
            raise InvalidPollMethod(f"{self.method_name} is not a valid poll method.")
        return reg[self.method_name]

    @cached_property
    def method(self) -> PollMethod:
        method = self.get_method_class()
        return method(self)

    @property
    def settings(self):
        schema = self.method.settings_schema
        if schema is not None:
            data = self.settings_data
            if data is None:
                data = {}
            # We do want things to crash here!
            return schema(**data)

    @settings.setter
    def settings(self, value: Union[Dict, BaseModel, None]) -> None:
        if value is None:
            self.settings_data = None
            return
        schema = self.method.settings_schema
        if schema is None:
            raise ValueError(f"Poll method '{self.method_name}' has no settings")
        if isinstance(value, dict):
            data = schema(**value)
        elif isinstance(value, schema):
            data = value
        else:  # pragma: no cover
            raise ValueError(f"{value} is not a settings schema or a dict")
        self.settings_data = data.dict()

    @property
    def result(self) -> Optional[PollResult]:
        schema = self.method.result_schema
        if schema is not None:
            result = self.result_data
            if result is not None:
                return schema(**self.result_data)

    @result.setter
    def result(self, value: Union[Dict, PollResult]):
        schema = self.method.result_schema
        if isinstance(value, dict):
            data = schema(**value)
        elif isinstance(value, schema):
            data = value
        else:  # pragma: no cover
            raise ValueError(f"{value} is not a result schema or a dict")
        self.result_data = data.dict()

    def validate_settings_guard(self):
        """ Guard for transitions to upcoming or ongoing. """
        try:
            pset = self.settings  # Will raise exceptions on bad settings
        except ValidationError:
            return False
        return pset is None or isinstance(pset, BaseModel)

    def start_check(self) -> bool:
        """Check that this poll could be started. A very basic check for the most obvious things.
        Note that it's used as a transition condition, so it must return True if everything is ok!
        """
        if self.electoral_register is None:
            raise ElectoralRegisterMissing()
        if self.electoral_register.voters.count() < 1:
            raise ElectoralRegisterEmpty()
        if self.proposals.count() < 1:
            raise InvalidProposalCount("No proposals")
        method = self.method  # Will raise exception if doesn't exist
        # And check the specifics for the poll method
        method.start_check()
        return True

    @transition(
        field=state,
        source=PollWf.PRIVATE,
        target=PollWf.UPCOMING,
        conditions=[validate_settings_guard],
        permission=PollPermissions.CHANGE_STATE,
        custom={"title": _("Make upcoming")},
    )
    def upcoming(self):
        for proposal in self.proposals.all():
            with suppress(TransitionNotAllowed):
                proposal.lock_for_vote()
                proposal.save()

    @transition(
        field=state,
        source=PollWf.UPCOMING,
        target=PollWf.ONGOING,
        conditions=[validate_settings_guard, start_check],
        permission=PollPermissions.CHANGE_STATE,
        custom={"title": _("Start")},
    )
    def ongoing(self):
        # The guard should've taken care of this already
        assert self.electoral_register, "No electoral register"
        self.initial_electoral_register = self.electoral_register
        self.started = now()

    @transition(
        field=state,
        source=[PollWf.ONGOING, PollWf.FAILED, PollWf.CLOSED],
        target=PollWf.CLOSED,
        permission=PollPermissions.CHANGE_STATE,
        custom={"title": _("Close")},
    )
    def close(self):
        """Close the poll for further votes.
        The next step is always to count the votes via the method finish()
        """
        self._mark_closed()

    @transition(
        field=state,
        source=PollWf.CLOSED,
        target=PollWf.FINISHED,
        on_error=PollWf.FAILED,
        permission=NOT_ALLOWED,
        custom={"title": _("Finish")},
    )
    def finish(self):
        """ Count the votes and finish up. """
        # Remove bad votes due to a change in electoral register during the poll.
        # This is probably not allowed in most meetings.
        self.vote_cleanup_set().delete()
        # ballots, abstains = self.get_ballots()
        # self.store_ballots(ballots, abstains)
        counter = self.finalize_vote_data()
        assert self.ballot_data
        assert self.ballot_checksum
        self.result = self.method.calculate_result(counter)
        for proposal in self.proposals.filter(pk__in=self.result.approved):
            with suppress(TransitionNotAllowed):
                proposal.approved()
                proposal.save()
        for proposal in self.proposals.filter(pk__in=self.result.denied):
            with suppress(TransitionNotAllowed):
                proposal.denied()
                proposal.save()

    @transition(
        field=state,
        source=PollWf.ONGOING,
        target=PollWf.CANCELED,
        permission=PollPermissions.CHANGE_STATE,
        custom={"title": _("Cancel")},
    )
    def cancel(self):
        self._mark_closed()
        for proposal in self.proposals.all():
            proposal.publish()

    @transition(
        field=state,
        source=PollWf.UPCOMING,
        target=PollWf.PRIVATE,
        permission=PollPermissions.CHANGE_STATE,
        custom={"title": _("Revert to private")},
    )
    def unpublish(self):
        for proposal in self.proposals.all():
            proposal.publish()

    def _mark_closed(self):
        if not self.closed:
            self.closed = now()

    def finalize_vote_data(self) -> Counter:
        """Return JSON-serializable result counter.
        Will also save ballot data and create a checksum + store abstentions.
        """
        counter = Counter()
        abstains = 0
        for v in self.votes.all():
            if v.abstain:
                abstains += v.weight
            else:
                counter[v.vote_data] += v.weight
        self.abstains = abstains
        self.ballot_data = dumps(counter)
        self.ballot_checksum = sha512(self.ballot_data.encode("utf-8")).hexdigest()
        logger.debug(
            "Finalized ballots for poll %s. Checksum: %s", self.pk, self.ballot_checksum
        )
        self.save()
        return counter

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

    def vote_cleanup_set(self) -> models.QuerySet:
        """Votes that shouldn't be here if the poll closes.
        Essentially that someone has voted but aren't in the current electoral register.
        """
        voters = self.electoral_register.voters.all()
        return self.votes.exclude(user__in=voters)

    def save(self, **kw):
        """Make sure meeting is set, from agenda_items meeting.
        Also set title automatically."""
        self.get_method_class()  # Will raise error
        if self.pk is None:
            # FIXME: This "helper" seems to cause a lot more problems than it's worth... :( /Robin
            if (
                self.meeting is None
                and getattr(self.agenda_item, "meeting", None) is not None
            ):
                self.meeting = self.agenda_item.meeting
            if (
                not self.title
                and self.agenda_item is not None
                and self.meeting is not None
            ):
                # Create a unique slugified title
                base = self.agenda_item.title
                for x in itertools.count(1):
                    self.title = f"{base} {x}"
                    if not self.meeting.polls.filter(title=self.title).exists():
                        break
        # Make sure we don't have bad settings
        if not self.validate_settings_guard():
            raise IntegrityError("Invalid settings")
        super().save(**kw)

    @property
    def is_private(self) -> bool:
        return self.state == PollWf.PRIVATE

    # Type hinting
    objects = models.Manager()
    votes: models.QuerySet


class Vote(models.Model):
    """Contains data on the users vote in a specific poll."""

    name = "vote"
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    poll: Poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    changed: datetime = models.DateTimeField(editable=False, auto_now=True)
    abstain: bool = models.BooleanField(default=False)
    vote_data: Optional[str] = models.TextField(
        null=True, blank=True
    )  # This field should contain the value from PollMethod

    @property
    def vote(self) -> BaseModel:
        return self.vote_data and self.poll.method.vote_to_obj(self.vote_data)

    @vote.setter
    def vote(self, data: Union[BaseModel, str]):
        if isinstance(data, BaseModel):
            self.vote_data = self.poll.method.vote_to_str(data)
        elif isinstance(data, str):
            # Validate
            self.poll.method.vote_to_obj(data)
            self.vote_data = data
        else:
            raise ValueError("Not a str or vote_schema (pydantic BaseModel)")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["user", "poll"],
                name="%(app_label)s_%(class)s_unique_vote_for_user",
            )
        ]

    def __str__(self):  # pragma: no cover
        return f"<{self.__class__.__name__} from {self.user}>"

    @property
    def weight(self) -> int:
        return self.poll.electoral_register.get_voter_weight(self.user)

    def save(self, **kw):
        er = self.poll.electoral_register
        if not er:
            raise ElectoralRegisterMissing()
        if not er.voters.filter(id=self.user.id):
            raise NotAllowedToVote("Not allowed to vote")
        if self.abstain and self.vote_data is not None:
            self.vote_data = None
        super().save(**kw)

    # Instantiate this manually for type hinting
    objects = models.Manager()


@receiver(post_transition, sender=Poll)
def finish_closed_poll(
    sender: Poll, instance: Poll, source: str, target: str, **kwargs
):
    """As soon as the poll has closed, calculate the result.
    This method should probably offload this transition change to a worker later on.
    """
    if target == PollWf.CLOSED:
        instance.finish()
