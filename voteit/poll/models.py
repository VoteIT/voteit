from __future__ import annotations

import itertools
from collections import Counter
from contextlib import suppress
from datetime import datetime
from hashlib import sha512
from json import dumps
from logging import getLogger
from typing import TYPE_CHECKING

from auditlog.registry import auditlog
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
from rules.contrib.models import RulesModelMixin

from voteit.core import PERM
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent
from voteit.core.permissions import NOT_ALLOWED
from voteit.poll.exceptions import BallotChecksumError
from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import InvalidPollMethod
from voteit.poll.exceptions import NotAllowedToVote
from voteit.poll.exceptions import PollError
from voteit.poll.exceptions import PollNotFinished
from voteit.poll.schemas import PollResult
from voteit.poll.utils import get_poll_method_registry
from voteit.poll.workflows import PollWf
from voteit.proposal.workflows import ProposalWf
from voteit.stats.registry import history_log

if TYPE_CHECKING:
    from voteit.agenda.models import AgendaItem
    from voteit.meeting.models import Meeting
    from voteit.poll.abcs import PollMethod

__all__ = (
    "ElectoralRegister",
    "Poll",
    "Vote",
    "VoteTransfer",
    "VoterWeight",
)

logger = getLogger(__name__)


class VoterWeight(MeetingContext):
    name = "voter_weight"
    register: ElectoralRegister = models.ForeignKey(
        "ElectoralRegister", on_delete=models.CASCADE
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    weight: int = models.PositiveIntegerField(default=1)

    importers = {
        "organisation": {"remap_relations": {"electoral_register": "register"}}
    }

    @property
    def meeting(self) -> Meeting | None:
        return self.register.meeting

    # Annotations
    objects: models.Manager

    def __str__(self):
        return f"{self.__class__.__name__}:{self.pk} for {self.user.userid}"


@auditlog.register(
    include_fields=[
        "source",
        "meeting",
    ],
)
@history_log("meeting__organisation")
class ElectoralRegister(RulesModelMixin, MeetingContext):
    name = "electoral_register"
    created: datetime = models.DateTimeField(editable=False, default=now)
    source: str | None = models.CharField(max_length=20, null=True, blank=True)
    voters = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through=VoterWeight,
        related_name="electoral_registers",
    )
    meeting: Meeting | None = models.ForeignKey(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="electoral_registers",
        null=True,
    )

    importers = {
        "organisation": {"remap_relations": {"user": {"last_modified_by", "author"}}}
    }

    def get_voter_weight(self, user: AbstractUser) -> int:
        """
        Allow votes to have a weight in some contexts.
        Will raise VoterWeight.DoesNotExist if user not in registry.
        """
        return self.voterweight_set.get(user=user).weight

    def get_total_vote_weight(self) -> int:
        return self.voterweight_set.aggregate(Sum("weight"))["weight__sum"]

    def get_weight_dict(self) -> dict[int, int]:
        """
        Uncached version
        """
        return dict(self.voterweight_set.values_list("user_id", "weight"))

    @cached_property
    def weight_dict(self) -> dict[int, int]:
        """
        Return a dict with user PK as key and weight as value.
        """
        return self.get_weight_dict()

    def set_voters_from_dict(self, values: dict[int, int]):
        """
        Adjust and set voters exactly according to {user PK: weight}
        Note that this is a low-lever function that does very little validation. It won't check that set users
        even have permission to view the meeting!
        """
        # FIXME: This touches models several times, fix this
        self.voters.set(values.keys())
        user_weights_to_adjust = {k for (k, v) in values.items() if v > 1}
        for vw in self.voterweight_set.filter(user__in=user_weights_to_adjust):
            vw.weight = values[vw.user_id]
            vw.save()

    class QuerySet(models.QuerySet):
        def for_user(self, user: AbstractUser):
            # Note: This returns _all_ ERs from any meeting where a user is a participant!
            return self.filter(meeting__participants=user).distinct()

    class Manager(models.Manager):
        def get_queryset(self):
            return ElectoralRegister.QuerySet(self.model, using=self._db)

        def for_user(self, user: AbstractUser):
            return self.get_queryset().for_user(user)

    objects = Manager()
    voterweight_set: models.QuerySet
    polls: models.QuerySet
    polls_initial: models.QuerySet
    meeting_id: int | None

    def __str__(self):
        return (
            f"{self.__class__.__name__}:{self.pk} with {self.voters.count()} voter(s)"
        )


@history_log("meeting__organisation")
@auditlog.register(
    include_fields=[
        "state",
        "title",
        "meeting",
        "agenda_item",
        "method_name",
        "p_ord",
        "withheld_result",
    ],
)
class Poll(BaseContent, MeetingContext, AgendaItemContext):
    P_ORD_CHOICES = (("c", "Chronological"), ("a", "Alphabetical"), ("r", "Random"))
    PERM_CHANGE_STATE = f"poll.{PERM.CHANGE_STATE}_poll"

    name = "poll"
    state: str = FSMField(
        default=PollWf.initial, choices=PollWf.choices(), editable=False
    )
    title: str = models.CharField(max_length=70)
    meeting: Meeting | None = models.ForeignKey(
        "meeting.Meeting", on_delete=models.CASCADE, related_name="polls", null=True
    )
    agenda_item: AgendaItem | None = models.ForeignKey(
        "agenda.AgendaItem", on_delete=models.CASCADE, null=True, related_name="polls"
    )
    proposals = models.ManyToManyField("proposal.Proposal", related_name="polls")
    method_name: str = models.CharField(max_length=20)
    settings_data: dict | None = models.JSONField(null=True, blank=True)
    created: datetime = models.DateTimeField(editable=False, default=now)
    started: datetime | None = models.DateTimeField(editable=False, null=True)
    closed: datetime | None = models.DateTimeField(editable=False, null=True)
    initial_electoral_register: ElectoralRegister | None = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="polls_initial",
    )
    electoral_register: ElectoralRegister | None = models.ForeignKey(
        "ElectoralRegister",
        on_delete=models.SET_NULL,
        editable=False,
        null=True,
        related_name="polls",
    )
    ballot_data: str | None = models.TextField(
        verbose_name="JSON-serialized ballot data", editable=False, null=True
    )
    ballot_checksum: str | None = models.CharField(
        verbose_name="SHA512 checksum of ballot data",
        max_length=128,
        editable=False,
        null=True,
    )
    abstains: int = models.PositiveIntegerField(
        verbose_name="Abstentions",
        default=0,
        editable=False,
    )
    result_data: dict | None = models.JSONField(
        verbose_name="JSON-serialized result data",
        editable=False,
        null=True,
        encoder=DjangoJSONEncoder,
    )
    p_ord: str = models.CharField(
        verbose_name="Proposal ordering",
        default="c",
        choices=P_ORD_CHOICES,
        max_length=1,
    )
    withheld_result: bool = models.BooleanField(
        verbose_name="Withheld result",
        default=False,
    )

    importers = {
        "organisation": {
            "remap_relations": {
                "electoral_register": {
                    "initial_electoral_register",
                    "electoral_register",
                },
                "proposal": {"proposals"},
                "user": {"last_modified_by", "author"},
            }
        }
    }

    def get_method_class(self) -> type[PollMethod]:
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
    def settings(self, value: dict | BaseModel | None) -> None:
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
    def result(self) -> PollResult | None:
        schema = self.method.result_schema
        if schema is not None:
            result = self.result_data
            if result is not None:
                return schema(**self.result_data)

    @result.setter
    def result(self, value: dict | PollResult):
        schema = self.method.result_schema
        if isinstance(value, dict):
            data = schema(**value)
        elif isinstance(value, schema):
            data = value
        else:  # pragma: no cover
            raise ValueError(f"{value} is not a result schema or a dict")
        self.result_data = data.dict()

    def validate_settings_guard(self) -> bool:
        """
        Guard for transitions to upcoming or ongoing.
        """
        try:
            pset = self.settings  # Will raise exceptions on bad settings
        except ValidationError:
            return False
        return pset is None or isinstance(pset, BaseModel)

    validate_settings_guard.title = _("Invalid settings")

    def valid_er_policy_guard(self):
        if self.meeting is None:
            return True  # Skip for unittests
        return self.meeting.valid_er_policy_guard()

    valid_er_policy_guard.title = _(
        "There's no electoral register method on this meeting - check configuration"
    )

    def method_guard(self):
        try:
            method = self.method  # Will raise exception if doesn't exist
            # And check the specifics for the poll method
            method.start_check()
        except PollError:
            logger.exception("Poll can't start")
            return False
        return True

    method_guard.title = _("Poll method settings invalid")

    def manual_er_needed_guard(self):
        if (
            self.meeting  # Skip unittests!
            and not self.meeting.latest_er
            and self.valid_er_policy_guard()
            and self.meeting.er_policy.require_manual
        ):
            return False
        return True

    manual_er_needed_guard.title = _(
        "This electoral register method requires you to create electoral registers manually before starting a poll."
    )

    def _lock_proposals(self):
        for proposal in self.proposals.filter(
            state=ProposalWf.PUBLISHED
        ).select_subclasses():
            with suppress(TransitionNotAllowed):
                proposal.lock_for_vote()
                proposal.save()

    def _publish_proposals(self):
        for proposal in self.proposals.filter(
            state=ProposalWf.VOTING
        ).select_subclasses():
            with suppress(TransitionNotAllowed):
                # It doesn't really matter if this fails. Proposals might already be published for some reason.
                proposal.publish()
                proposal.save()

    def set_proposals_from_result(self):
        for proposal in self.proposals.filter(
            pk__in=self.result.approved
        ).select_subclasses():
            with suppress(TransitionNotAllowed):
                proposal.approved()
                proposal.save()
        for proposal in self.proposals.filter(
            pk__in=self.result.denied
        ).select_subclasses():
            with suppress(TransitionNotAllowed):
                proposal.denied()
                proposal.save()

    def set_result(self):
        counter = self.finalize_vote_data()
        assert self.ballot_data
        assert self.ballot_checksum
        result = self.method.calculate_result(counter)
        # Ensure vote count is same as the poll method uses, including vote weight.
        # Abstains aren't included here
        result.vote_count = sum(counter.values())
        self.result = result

    @transition(
        field=state,
        source=PollWf.PRIVATE,
        target=PollWf.UPCOMING,
        conditions=[validate_settings_guard],
        permission=PERM_CHANGE_STATE,
        custom={"title": _("Make upcoming")},
    )
    def upcoming(self):
        self._lock_proposals()

    @transition(
        field=state,
        source=[PollWf.UPCOMING, PollWf.PRIVATE],
        target=PollWf.ONGOING,
        conditions=[
            validate_settings_guard,
            valid_er_policy_guard,
            manual_er_needed_guard,
            method_guard,
        ],
        permission=PERM_CHANGE_STATE,
        custom={"title": _("Start")},
    )
    def ongoing(self):
        if self.electoral_register:
            self.initial_electoral_register = self.electoral_register
        self.started = now()
        self._lock_proposals()

    @transition(
        field=state,
        source=[PollWf.ONGOING, PollWf.FAILED, PollWf.CANCELED],
        target=PollWf.CLOSED,
        permission=PERM_CHANGE_STATE,
        custom={"title": _("Close")},
    )
    def close(self):
        """
        Close the poll for further votes.
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
        """
        Count the votes and finish up.
        """
        self.set_result()
        self.set_proposals_from_result()

    @transition(
        field=state,
        source=PollWf.CLOSED,
        target=PollWf.WITHHELD,
        on_error=PollWf.FAILED,
        permission=NOT_ALLOWED,
    )
    def finish_withhold(self):
        """
        Count the votes and finish up but don't publish the result just yet.
        """
        self.set_result()

    @transition(
        field=state,
        source=PollWf.WITHHELD,
        target=PollWf.FINISHED,
        on_error=PollWf.FAILED,
        permission=PERM_CHANGE_STATE,
        custom={"title": _("Publish result")},
    )
    def publish_result(self):
        self.set_proposals_from_result()
        self.withheld_result = False

    @transition(
        field=state,
        source=PollWf.FINISHED,
        target=PollWf.WITHHELD,
        on_error=PollWf.FAILED,
        permission=PERM_CHANGE_STATE,
        custom={"title": _("Withold detailed result")},
    )
    def withhold_result(self):
        self.withheld_result = True

    @transition(
        field=state,
        source=PollWf.ONGOING,
        target=PollWf.CANCELED,
        permission=PERM_CHANGE_STATE,
        custom={"title": _("Cancel")},
    )
    def cancel(self):
        self._mark_closed()
        self._publish_proposals()

    @transition(
        field=state,
        source=PollWf.UPCOMING,
        target=PollWf.PRIVATE,
        permission=PERM_CHANGE_STATE,
        custom={"title": _("Revert to private")},
    )
    def unpublish(self):
        self._publish_proposals()

    @transition(
        field=state,
        source="+",
        target=PollWf.FAILED,
        permission=NOT_ALLOWED,
        custom={"title": _("Failed")},
    )
    def failed(self):
        """
        Transition to failed when we have some sort of error that's not recoverable.
        """
        self._mark_closed()

    @transition(
        field=state,
        source=PollWf.CLOSED,
        target=PollWf.NO_RESULT,
        permission=NOT_ALLOWED,
        custom={"title": _("No result")},
    )
    def no_result(self):
        """
        No valid votes to calculate the result from. If there are no votes or all votes are abstentions.
        """
        self._mark_closed()

    def _mark_closed(self):
        if not self.closed:
            self.closed = now()

    def finalize_vote_data(self) -> Counter:
        """
        Return JSON-serializable result counter.
        Will also save ballot data and create a checksum + store abstentions.
        """
        if self.ballot_data is not None:
            raise PollError("Poll already finalized")
        counter = Counter()
        abstains = 0
        for v in self.votes.annotate_weight().order_by("pk"):
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
        """
        Votes that shouldn't be here if the poll closes.
        Essentially that someone has voted but aren't in the current electoral register.
        """
        if self.electoral_register is None:
            raise PollError("No electoral register")
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
        # At this point we must have an attached valid electoral register
        # if self.state == PollWf.ONGOING and self.electoral_register is None:
        #     raise ElectoralRegisterMissing()
        # Make sure we don't have bad settings
        if not self.validate_settings_guard():
            raise IntegrityError("Invalid settings")
        super().save(**kw)

    @property
    def is_private(self) -> bool:
        return self.state == PollWf.PRIVATE

    @property
    def is_finished(self) -> bool:
        return self.state in PollWf.finished_states

    # Annotations
    objects: models.Manager
    votes: Vote.QuerySet
    meeting_id: int | None


def _remove_all_mask(value: str) -> str:
    return "*"


# FIXME: We don't log votes right now, but that might be a good idea, at least the actor?
@history_log("user__organisation")
@auditlog.register(
    include_fields=[
        "user",
        "poll",
        "vote_data",
        "abstain",
    ],
    mask_fields=["vote_data", "abstain"],
    mask_callable="voteit.poll.models._remove_all_mask",
)
class Vote(RulesModelMixin, models.Model):
    """Contains data on the users vote in a specific poll."""

    name = "vote"
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT
    )
    poll: Poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    created: datetime = models.DateTimeField(editable=False, default=now)
    changed: datetime = models.DateTimeField(editable=False, auto_now=True)
    abstain: bool = models.BooleanField(default=False)
    vote_data: str | None = models.TextField(
        null=True, blank=True
    )  # This field should contain the value from PollMethod

    importers = {"organisation": {}}

    @property
    def vote(self) -> BaseModel:
        return self.vote_data and self.poll.method.vote_to_obj(self.vote_data)

    @vote.setter
    def vote(self, data: BaseModel | str):
        if isinstance(data, BaseModel):
            self.vote_data = self.poll.method.vote_to_str(data)
        elif isinstance(data, str):
            # Validate
            self.poll.method.vote_to_obj(data)
            self.vote_data = data
        elif data is None:
            self.vote_data = None
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
        return f"{self.__class__.__name__} from {self.user}"

    def save(self, **kw):
        er = self.poll.electoral_register
        if not er:
            raise ElectoralRegisterMissing()
        if not er.voters.filter(id=self.user.id):
            raise NotAllowedToVote("Not allowed to vote")
        if self.abstain and self.vote_data is not None:
            self.vote_data = None
        super().save(**kw)

    class QuerySet(models.QuerySet):
        def annotate_weight(self):
            """Add vote weight using subquery."""
            return self.annotate(
                weight=models.Subquery(
                    VoterWeight.objects.filter(
                        register=models.OuterRef("poll__electoral_register"),
                        user=models.OuterRef("user"),
                    )[:1].values_list("weight", flat=True)
                )
            )

    objects = QuerySet.as_manager()


@auditlog.register(
    exclude_fields=["id"],
)
class VoteTransfer(MeetingContext, RulesModelMixin):
    """
    Transfer voting rights to another user.

    """

    name = "vote_transfer"
    meeting: Meeting = models.ForeignKey(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="vote_transfers",
    )
    source: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )
    target: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
    )

    class Meta:
        constraints = [
            # Not true for liquid
            # UniqueConstraint(
            #    fields=["target", "meeting"],
            #    name="%(app_label)s_%(class)s_meeting_target",
            # ),
            # A user can only give away their vote once
            UniqueConstraint(
                fields=["source", "meeting"],
                name="%(app_label)s_%(class)s_meeting_source",
            ),
        ]

    def save(self, **kwargs):
        # if self.target == self.source:
        #    raise IntegrityError("Can't transfer to self")
        if self.meeting.roles.filter(user__in=[self.target, self.source]).count() != 2:
            raise IntegrityError(
                "Both source and target user must exist within meeting."
            )
        return super().save(**kwargs)

    objects: models.Manager
    meeting_id: int
    source_id: int
    target_id: int


@receiver(post_transition, sender=Poll)
def finish_closed_poll(
    sender: Poll, instance: Poll, source: str, target: str, **kwargs
):
    """
    As soon as the poll has closed, calculate the result.
    This method should probably offload this transition change to a worker later on.
    """
    if target == PollWf.CLOSED:
        # Sometimes polls can exist without an electoral register, in that case fail!
        if instance.electoral_register is None:
            instance.no_result()
            return
        # Remove bad votes due to a change in electoral register during the poll.
        # This is probably not allowed in most meetings.
        instance.vote_cleanup_set().delete()
        if instance.votes.filter(abstain=False).count():
            if instance.withheld_result:
                instance.finish_withhold()
            else:
                instance.finish()
        else:
            instance.no_result()
