from __future__ import annotations

import math
from contextlib import suppress
from datetime import datetime
from datetime import timedelta
from itertools import chain
from random import sample
from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError
from django.db import models
from django.utils.timezone import now
from pydantic.main import BaseModel
from voteit.core.statemachines import StateMachineModelMixin
from rules.contrib.models import RulesModelMixin

from voteit.agenda.models import AgendaItem
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.decorators import ensure_atomic
from voteit.core.fields import RolesField
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles
from voteit.core.role import Role
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.speaker.abcs import SpeakerSystemContext
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.statemachines import SpeakerSystemStateMachine
from voteit.speaker.utils import get_list_method_registry
from voteit.room.models import Room
from voteit.stats.registry import history_log

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation
    from voteit.speaker.abcs import ListMethod


__all__ = (
    "SpeakerSystemRoles",
    "SpeakerListSystem",
    "Speaker",
    "SpeakerList",
)


@auditlog.register(
    exclude_fields=["id"],
)
class SpeakerSystemRoles(Roles, MeetingContext):
    name = "speaker_roles"
    valid_roles = {
        ROLE_LIST_MODERATOR: ROLE_LIST_MODERATOR,
        ROLE_SPEAKER: ROLE_SPEAKER,
    }
    context: SpeakerListSystem = models.ForeignKey(
        "SpeakerListSystem", on_delete=models.CASCADE
    )
    assigned: str = RolesField(role_choices=valid_roles.values(), max_length=30)

    @property
    def meeting(self) -> Meeting | None:
        return self.context.meeting

    class Meta:
        verbose_name = verbose_name_plural = "Speaker system roles"

    def __str__(self):
        return f"{self.user} roles @ {self.context}"


@history_log("meeting__organisation")
@auditlog.register(
    include_fields=[
        "state",
        "room",
        "meeting",
        "method_name",
        "settings_data",
        "safe_positions",
        "meeting_roles_to_speaker",
    ],
)
class SpeakerListSystem(
    RulesModelMixin,
    RoleContextMixin,
    MeetingContext,
    SpeakerSystemContext,
    StateMachineModelMixin,
):
    """
    All speaker list things relate here, while this in turn might relate to a meeting.
    A list system has its own rules and moderators.
    """

    name = "speaker_system"
    state_machine_name = "voteit.speaker.statemachines.SpeakerSystemStateMachine"
    sm: SpeakerSystemStateMachine
    state: str = models.CharField(
        default=SpeakerSystemStateMachine.initial_state.value,
        choices=[(s.value, str(s.name)) for s in SpeakerSystemStateMachine.states],
        max_length=20,
    )
    room: Room = models.OneToOneField(
        Room,
        verbose_name="Room",
        on_delete=models.RESTRICT,
        related_name="sls",
    )
    meeting: Meeting = models.ForeignKey(
        Meeting,
        verbose_name="Related meeting",
        on_delete=models.CASCADE,
        related_name="speaker_systems",
    )
    method_name: str = models.CharField(max_length=20)
    settings_data: dict = models.JSONField(
        verbose_name="JSON-serialized settings data",
        editable=False,
        null=True,
        encoder=DjangoJSONEncoder,
    )
    safe_positions: int | None = models.PositiveSmallIntegerField(
        verbose_name=(
            "When a list is active, mark the top X positions as safe automatically. "
            "Safe speakers will never be moved down."
        ),
        choices=[(x, str(x)) for x in range(3)],
        null=True,
        blank=True,
    )
    active_list: SpeakerList | None = models.OneToOneField(
        "SpeakerList",
        verbose_name="Currently active speaker list",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_in_system",
    )
    meeting_roles_to_speaker: list[Role] = RolesField(
        role_choices=MeetingRoles.valid_roles.values(), max_length=60
    )
    # FIXME: This is on room too, remove one of them
    show_time: bool = models.BooleanField(
        verbose_name="Show time spoken for all", default=False
    )

    roles_cls = SpeakerSystemRoles

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_active_list_id = self.active_list_id
        self._initial_method_name = self.method_name

    def get_method_class(self) -> type[ListMethod]:
        """Fetch the poll method class, a django proxy model."""
        reg = get_list_method_registry()
        return reg[self.method_name]

    @property
    def active_list_changed(self) -> bool:
        return self.active_list_id != self._initial_active_list_id

    @property
    def method_name_changed(self) -> bool:
        return self.method_name != self._initial_method_name

    @property
    def speaker_system(self) -> SpeakerListSystem:
        """
        Fulfilling SpeakerSystemContext
        """
        return self

    @property
    def method(self) -> ListMethod:
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
    def settings(self, value: dict | BaseModel):
        schema = self.method.settings_schema
        if schema is None:
            raise ValueError(f"Method {self.method.name} has no settings_schema")
        if isinstance(value, dict):
            data = schema(**value)
        elif isinstance(value, schema):
            data = value
        else:  # pragma: no cover
            raise ValueError(f"{value} is not a settings schema or a dict")
        self.settings_data = data.model_dump()

    @property
    def organisation(self) -> Organisation:
        return self.meeting.organisation

    def activate(self, user):
        self.sm.send("activate", user=user)

    def inactivate(self, user):
        self.sm.send("inactivate", user=user)

    @ensure_atomic
    def archive(self):
        self.state = SpeakerSystemStateMachine.archived.value
        self.active_list = None
        Speaker.objects.filter(
            speaker_list__speaker_system=self, seconds__isnull=True
        ).delete()
        for slist in self.speaker_lists.exclude(order=""):
            slist.order = ""
            slist.save()

    def signal_active_list_changed(self):
        from voteit.speaker.signals import active_list_changed

        active_list_changed.send(sender=self.__class__, instance=self)

    def signal_list_method_added(self, force=False):
        from voteit.speaker.signals import list_method_added

        if (self.method_name_changed or force) and self.method_name:
            list_method_added.send(sender=self.get_method_class(), instance=self)

    def signal_list_method_removed(self, force=False):
        from voteit.speaker.signals import list_method_removed

        if (self.method_name_changed or force) and self._initial_method_name:
            reg = get_list_method_registry()
            if method_class := reg.get(self._initial_method_name):
                list_method_removed.send(sender=method_class, instance=self)

    def refresh_from_db(self, **kwargs):
        super().refresh_from_db(**kwargs)
        self._initial_active_list_id = self.active_list_id
        self._initial_method_name = self.method_name

    def save(self, **kw):
        # Add meeting on create if not specified
        adding = False
        if self._state.adding:
            adding = True
            if self.meeting_id is None and self.room_id is not None:
                if self.room.meeting_id:
                    self.meeting_id = self.room.meeting_id
            # Make sure room and sls links to same meeting
            if self.room.meeting_id != self.meeting_id:
                raise IntegrityError("SLS links to another meeting")
        super().save(**kw)
        if self.active_list_changed:
            if self.active_list_id:
                self.active_list.is_active_list = True  # Update cached value
            self.signal_active_list_changed()
        self._initial_active_list_id = self.active_list_id
        if self.method_name_changed:
            self.signal_list_method_removed()
            self.signal_list_method_added()
        elif adding:
            self.signal_list_method_added(force=True)
        self._initial_method_name = self.method_name

    @property
    def is_archived(self):
        return self.state == SpeakerSystemStateMachine.archived.value

    @property
    def is_active(self):
        return self.state == SpeakerSystemStateMachine.active.value

    # Type hinting
    objects: models.Manager
    speaker_lists: models.QuerySet
    room: Room
    room_id: int | None
    meeting_id: int | None
    active_list_id: int | None

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.pk}>"

    def __str__(self):
        if self.room_id and self.room.title:
            return self.room.title[:30]
        return f"SLS {self.pk}"


@history_log("user__organisation")
class Speaker(RulesModelMixin, MeetingContext, SpeakerSystemContext):
    """
    Information about a user who's entered a speaker list.
    """

    name = "speaker"
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT
    )
    speaker_list: SpeakerList = models.ForeignKey(
        "SpeakerList", on_delete=models.CASCADE, related_name="speaker_items"
    )
    # Note: Created is also needed for "historic" positions within a speaker list in case they're rearranged.
    created: datetime = models.DateTimeField(editable=False, default=now)
    started: datetime | None = models.DateTimeField(null=True)
    seconds: int | None = models.PositiveSmallIntegerField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                "speaker_list",
                condition=models.Q(started__isnull=False, seconds__isnull=True),
                name="only_one_ongoing_speaker",
            ),
            models.UniqueConstraint(
                "user",
                "speaker_list",
                condition=models.Q(seconds__isnull=True),
                name="only_unique_users_in_queue",
            ),
        ]

    def start(self) -> datetime | None:
        # Validation before this function
        if self.started is None:
            self.started = now()
            return self.started

    def stop(self) -> int | None:
        # Validation before this function
        if self.seconds is None:
            end_td = now() - self.started
            self.seconds = min(
                math.ceil(end_td.total_seconds()) or 1, 32767
            )  # Max value of PosSmallIntField ~ 9 hours. But must at least be 1.
            return self.seconds

    def undo(self) -> bool:
        if self.started and self.seconds is None:
            self.started = None
            return True
        return False  # Pragma: no coverage

    @property
    def ended(self) -> datetime | None:
        if self.seconds is not None and isinstance(self.started, datetime):
            return self.started + timedelta(seconds=self.seconds)

    @property
    def current(self) -> bool:
        """
        We're guessing that this is the current speaker
        if it has a started timestamp and no recorded spoken seconds.
        """
        return self.started is not None and self.seconds is None

    @property
    def in_queue(self) -> bool:
        """
        The definition of being in the queue is that started isn't set.
        """
        return self.started is None

    @property
    def meeting(self) -> Meeting | None:
        return self.speaker_list.meeting

    @property
    def speaker_system(self) -> SpeakerListSystem:
        return self.speaker_list.speaker_system

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.pk}>"

    def __str__(self):
        return f"Speaker id {self.pk}"

    # Type hinting
    objects: models.Manager
    user_id: int
    speaker_list_id: int


@history_log("meeting__organisation")
@auditlog.register(
    include_fields=[
        "title",
        "state",
        "speaker_system",
        "meeting",
        "room",
    ],
)
class SpeakerList(
    RulesModelMixin, AgendaItemContext, MeetingContext, SpeakerSystemContext
):
    name = "speaker_list"
    _active_speaker: Speaker | None
    title = models.CharField(max_length=200)
    is_open: bool = models.BooleanField(default=True)
    speaker_system: SpeakerListSystem = models.ForeignKey(
        SpeakerListSystem, on_delete=models.CASCADE, related_name="speaker_lists"
    )
    agenda_item: AgendaItem | None = models.ForeignKey(
        AgendaItem, on_delete=models.CASCADE, null=True, related_name="speaker_lists"
    )
    meeting: Meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="+",
        editable=False,
    )
    room: Room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="+",
        editable=False,
    )
    speakers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=Speaker, related_name="speaker_lists"
    )
    order: str = models.TextField(
        verbose_name="Order of user PK, comma separated", default=""
    )

    @property
    def method(self) -> ListMethod:
        return self.speaker_system.method

    @property
    def is_active_list(self) -> bool:
        """Is this the currently active list?"""
        if hasattr(self, "_is_active_list"):
            return self._is_active_list
        self._is_active_list = False
        with suppress(SpeakerListSystem.DoesNotExist):
            self._is_active_list = bool(self.active_in_system)
        return self._is_active_list

    @is_active_list.setter
    def is_active_list(self, value: bool):
        self._is_active_list = value

    @is_active_list.deleter
    def is_active_list(self):
        if hasattr(self, "_is_active_list"):
            delattr(self, "_is_active_list")

    @property
    def order_list(self) -> list[int]:
        if not self.order:
            return []
        return [int(x) for x in self.order.split(",")]

    @order_list.setter
    def order_list(self, value: list[int | str]):
        [int(x) for x in value]
        self.order = ",".join(str(x) for x in value)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def active_speaker(self, refresh=False) -> Speaker | None:
        if refresh or not hasattr(self, "_active_speaker"):
            self._active_speaker = self.speaker_items.filter(
                started__isnull=False, seconds__isnull=True
            ).first()
        return self._active_speaker

    @ensure_atomic
    def shuffle(self):
        """
        Randomize the order of the speakers. Run reorder after to make sure any other priorities gets applied.
        This method should lock speaker list first via queryset.select_for_update()
        """
        self.reorder(sample(self.order_list, len(self.order_list)))

    @ensure_atomic
    def reorder(self, order_list: list[int] = None):
        """
        Something have changed within the list that makes reordering necessary.
        Usually when a user is added or removed, but it can be triggered for attribute changes on users too.
        """
        if order_list is None:
            order_list = self.order_list

        def order_key(speaker: Speaker) -> tuple[int, datetime]:
            try:
                index = order_list.index(speaker.user_id)
            except ValueError:
                # Anything not in the order_list will get same index and get ordered by created
                index = len(order_list)
            return index, speaker.created

        incoming_order = sorted(self.method.get_queryset(self), key=order_key)
        safe_positions = self.speaker_system.safe_positions or 0  # Must not be None
        # If current speaker is in safe position, reserve one more position as safe.
        if any(speaker.started for speaker in incoming_order[:safe_positions]):
            safe_positions += 1
        safe_speakers = incoming_order[:safe_positions]
        speakers_to_order = incoming_order[safe_positions:]
        new_order = [
            s.user_id
            for s in chain(
                safe_speakers, self.method.reorder(safe_speakers, speakers_to_order)
            )
        ]
        if self.order_list != new_order:
            self.order_list = new_order
            self.save()
        return new_order

    def speakers_in_queue_or_speaking(self) -> models.QuerySet[Speaker]:
        return self.speaker_items.filter(seconds__isnull=True)

    def speakers_in_queue(self) -> models.QuerySet[Speaker]:
        """
        Unsorted speaker models in queue. Normally there's no need to touch these.
        """
        return self.speaker_items.filter(seconds__isnull=True, started__isnull=True)

    def refresh_from_db(self, **kwargs):
        super().refresh_from_db(**kwargs)
        del self.is_active_list
        if hasattr(self, "_active_speaker"):
            delattr(self, "_active_speaker")

    def save(self, **kw):
        if self._state.adding:
            with suppress(ObjectDoesNotExist):
                if (
                    self.agenda_item_id
                    and self.agenda_item.meeting_id
                    and self.speaker_system.meeting_id != self.agenda_item.meeting_id
                ):
                    raise IntegrityError(
                        "agenda item and list system attached to different meetings"
                    )
            self.room_id = self.speaker_system.room_id
            self.meeting_id = self.speaker_system.meeting_id
        super().save(**kw)

    # Type hinting
    meeting_id: int
    room_id: int
    agenda_item_id: int | None
    objects: models.Manager
    speaker_items: models.QuerySet[Speaker]
    # Accessing will raise ObjectNotFound if None, so use is_active_list
    active_in_system: SpeakerListSystem | None

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.title[:50]}>"

    def __str__(self):
        if self.title:
            return self.title[:50]
        return f"Speaker list {self.pk}"
