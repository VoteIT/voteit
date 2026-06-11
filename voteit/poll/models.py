from __future__ import annotations

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
from django.db.models import UniqueConstraint
from django.utils.functional import cached_property
from django.utils.timezone import now
from statemachine.exceptions import TransitionNotAllowed
from statemachine.mixins import MachineMixin
from pydantic.main import BaseModel
from rules.contrib.models import RulesModelMixin

from voteit.core import PERM
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent
from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import InvalidPollMethod
from voteit.poll.exceptions import NotAllowedToVote
from voteit.poll.exceptions import PollError
from voteit.poll.schemas import PollResult
from voteit.poll.utils import get_poll_method_registry
from voteit.poll.statemachines import PollStateMachine
from voteit.proposal.statemachines import ProposalStateMachine
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
)

logger = getLogger(__name__)


@auditlog.register(
    include_fields=[
        "source",
        "meeting",
    ],
)
@history_log("meeting__organisation")
class ElectoralRegister(RulesModelMixin, MeetingContext):
    """
    A snapshot of who is allowed to vote in a meeting and with what weight.

    Created by an electoral register policy (``Meeting.er_policy``) and
    attached to one or more polls. Once saved, ``voter_data`` is immutable —
    use ``set_voters_from_dict()`` on a fresh instance instead of writing
    the field directly. This ensures checksums and audit trails stay consistent.

    ``voter_data`` is a JSON dict of ``{str(user_pk): vote_weight}``.
    """

    name = "electoral_register"
    created: datetime = models.DateTimeField(editable=False, default=now)
    source: str | None = models.CharField(max_length=20, null=True, blank=True)
    meeting: Meeting | None = models.ForeignKey(
        "meeting.Meeting",
        on_delete=models.CASCADE,
        related_name="electoral_registers",
        null=True,
    )
    voter_data: dict = models.JSONField(default=dict)

    @staticmethod
    def _voter_key(user: AbstractUser | int | str) -> str:
        if isinstance(user, str):
            return user
        if isinstance(user, int):
            return str(user)
        return str(user.pk)

    def has_voter(self, user: AbstractUser | int | str) -> bool:
        return self._voter_key(user) in self.voter_data

    def get_voter_weight(self, user: AbstractUser) -> int:
        key = self._voter_key(user)
        if key not in self.voter_data:
            raise KeyError(f"User {user.pk} not in electoral register")
        return self.voter_data[key]

    def get_total_vote_weight(self) -> int:
        return sum(self.voter_data.values())

    def get_weight_dict(self) -> dict[int, int]:
        """
        Uncached version
        """
        return {int(k): v for k, v in self.voter_data.items()}

    @cached_property
    def weight_dict(self) -> dict[int, int]:
        """
        Return a dict with user PK as key and weight as value.
        """
        return self.get_weight_dict()

    def set_voters_from_dict(self, values: dict[int, int]):
        """
        Set voters exactly according to {user PK: weight}.
        Low-level — does not validate that users have meeting access.
        This is the only sanctioned way to update voter_data after creation.
        """
        if self.voter_data:
            raise ValueError("voter_data already set")
        self._allow_voter_data_write = True
        self.voter_data = {str(k): v for k, v in values.items()}
        self.save(update_fields=["voter_data"])

    def save(self, **kw):
        # A bit silly but better than nothing
        update_fields = kw.get("update_fields")
        if (
            self.pk is not None
            and update_fields is not None
            and "voter_data" in update_fields
            and not getattr(self, "_allow_voter_data_write", False)
        ):
            raise ValueError("voter_data is immutable; use set_voters_from_dict()")
        self._allow_voter_data_write = False
        super().save(**kw)

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
    polls: models.QuerySet
    meeting_id: int | None

    def __str__(self):
        return (
            f"{self.__class__.__name__}:{self.pk} with {len(self.voter_data)} voter(s)"
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
class Poll(BaseContent, MeetingContext, AgendaItemContext, MachineMixin):
    """
    A vote taken on a set of proposals within an agenda item.

    Lifecycle (``PollStateMachine``): ``private → upcoming → ongoing → finished``.
    The poll method (``method_name``) determines how votes are counted; methods
    are registered in the poll method registry and may carry a Pydantic settings
    schema (``settings_data``) and a result schema (``result_data``).

    ``electoral_register`` is the register used for counting. It may be updated
    during an ongoing poll if the ER policy regenerates it before closing.

    ``ballot_data`` and ``ballot_checksum`` (SHA-512) are written once when the poll
    closes and are immutable afterwards.
    """

    P_ORD_CHOICES = (("c", "Chronological"), ("a", "Alphabetical"), ("r", "Random"))
    PERM_CHANGE_STATE = f"poll.{PERM.CHANGE_STATE}_poll"

    name = "poll"
    state_machine_name = "voteit.poll.statemachines.PollStateMachine"
    state_machine_attr = "sm"
    sm: PollStateMachine
    state: str = models.CharField(
        default=PollStateMachine.initial_state.value,
        choices=[(s.value, str(s.name)) for s in PollStateMachine.states],
        max_length=20,
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

    def get_method_class(self) -> type[PollMethod]:
        """Fetch the poll method class, an adapter."""
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

    def cleanup_removed_from_er_votes(self) -> int | None:
        voter_pks = [int(k) for k in self.electoral_register.voter_data.keys()]
        if removed_votes := self.votes.exclude(user_id__in=voter_pks).delete()[0]:
            logger.info(
                "Removed %s votes from poll %s before calculating.",
                removed_votes,
                self.pk,
            )
            return removed_votes

    def finalize_vote_data(self) -> Counter:
        """
        Return JSON-serializable result counter.

        * Removes votes in case the electoral register changed for the poll. (Uncommon case with AlwaysAutomatic method)
        * Creates a serializable ballot package in preparation for count.
        * Calculates and stores ballot checksum.
        """
        if self.ballot_data is not None:
            raise PollError("Poll already finalized")
        if self.electoral_register is None:
            raise ElectoralRegisterMissing()
        weights = {int(k): v for k, v in self.electoral_register.voter_data.items()}
        counter = Counter()
        abstains = 0
        for v in self.votes.order_by("pk"):
            w = weights.get(v.user_id, 1)
            if v.abstain:
                abstains += w
            else:
                counter[v.vote_data] += w
        self.abstains = abstains
        self.ballot_data = dumps(counter)
        self.ballot_checksum = sha512(self.ballot_data.encode("utf-8")).hexdigest()
        logger.debug(
            "Finalized ballots for poll %s. Checksum: %s", self.pk, self.ballot_checksum
        )
        return counter

    def calculate_result(self) -> BaseModel | None:
        """
        Do the result calculation after ballots have been finalized.
        Delegates the actual calculation to the vote method.
        """
        if self.result_data is None:
            # Remove bad votes due to a change in electoral register during the poll.
            # This is probably not allowed in most meetings.
            counter = self.finalize_vote_data()
            result = self.method.calculate_result(counter)
            # Ensure vote count is same as the poll method uses, including vote weight.
            # Abstains aren't included here
            result.vote_count = sum(counter.values())
            self.result = result
        return self.result

    def _lock_proposals(self):
        for proposal in self.proposals.filter(
            state=ProposalStateMachine.published.value
        ).select_subclasses():
            with suppress(TransitionNotAllowed):
                proposal.lock_for_vote(force=True)
                proposal.save()

    def _publish_proposals(self):
        for proposal in self.proposals.filter(
            state=ProposalStateMachine.voting.value
        ).select_subclasses():
            with suppress(TransitionNotAllowed):
                proposal.publish(force=True)
                proposal.save()

    def set_proposals_from_result(self):
        approved_pks = set(self.result.approved)
        denied_pks = set(self.result.denied)
        for proposal in self.proposals.select_subclasses():
            with suppress(TransitionNotAllowed):
                if proposal.pk in approved_pks:
                    proposal.approved(force=True)
                elif proposal.pk in denied_pks:
                    proposal.denied(force=True)
                else:
                    proposal.publish(force=True)
                proposal.save()

    # Same methods as the old transitions in FSM but now delegated to SM.
    def upcoming(self, user=None, force=False):
        self.sm.send("make_upcoming", user=user, force=force)

    def ongoing(self, user=None, force=False):
        self.sm.send("make_ongoing", user=user, force=force)

    def close(self, user=None, force=False):
        self.sm.send("close", user=user, force=force)

    def cancel(self, user=None, force=False):
        self.sm.send("cancel", user=user, force=force)

    def unpublish(self, user=None, force=False):
        self.sm.send("unpublish", user=user, force=force)

    def publish_result(self, user=None, force=False):
        self.sm.send("publish_result", user=user, force=force)

    def withhold_result(self, user=None, force=False):
        self.sm.send("withhold_result", user=user, force=force)

    @property
    def is_ongoing(self) -> bool:
        return self.state == PollStateMachine.ongoing.value

    @property
    def is_private(self) -> bool:
        return self.state == PollStateMachine.private.value

    @property
    def is_upcoming(self) -> bool:
        return self.state == PollStateMachine.upcoming.value

    @property
    def is_finished(self) -> bool:
        return self.state in PollStateMachine.finished_states

    # Annotations
    objects: models.Manager
    votes: models.QuerySet
    meeting_id: int | None
    agenda_item_id: int | None

    def save(self, *args, **kwargs):
        if self._state.adding and self.meeting_id is None and self.agenda_item_id:
            self.meeting_id = self.agenda_item.meeting_id
        super().save(*args, **kwargs)


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
        if not er.has_voter(self.user_id):
            raise NotAllowedToVote()
        if self.abstain and self.vote_data is not None:
            self.vote_data = None
        super().save(**kw)

    objects: models.Manager


@auditlog.register(
    exclude_fields=["id"],
)
class VoteTransfer(MeetingContext, RulesModelMixin):
    """
    Delegates voting rights from one meeting participant (``source``) to another (``target``).

    Used when a participant cannot attend in person and wishes their vote weight
    to be carried by a proxy. The actual weight redistribution is applied by the
    electoral register policy when the register is (re)generated.
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
