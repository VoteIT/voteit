from __future__ import annotations

import math
from contextlib import suppress
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField
from django_fsm import transition
from pydantic.main import BaseModel

from voteit.agenda.models import AgendaItem
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.decorators import ensure_atomic
from voteit.core.fields import RolesField
from voteit.core.models import RoleContextMixin
from voteit.core.models import Roles
from voteit.core.permissions import NOT_ALLOWED
from voteit.core.role import Role
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.speaker.abcs import SpeakerSystemContext
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.permissions import SpeakerSystemPermissions
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.utils import get_list_method_registry
from voteit.speaker.workflows import SpeakerListWf
from voteit.speaker.workflows import SpeakerSystemWf
from voteit.room.models import Room

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation
    from voteit.speaker.abcs import ListMethod


__all__ = "SpeakerSystemRoles", "SpeakerListSystem", "Speaker", "SpeakerList"


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

    exporters = {"meeting": {"meeting_kw": "context__meeting"}}
    importers = {
        "meeting": {"remap_relations": {"speaker_system": "context"}},
        "organisation": {"remap_relations": {"speaker_system": "context"}},
    }

    def __str__(self):
        return f"{self.user} roles @ {self.context}"


class SpeakerListSystem(RoleContextMixin, MeetingContext, SpeakerSystemContext):
    """
    All speaker list things relate here, while this in turn might relate to a meeting.
    A list system has its own rules and moderators.
    """

    name = "speaker_system"
    state: str = FSMField(
        default=SpeakerSystemWf.initial,
        choices=SpeakerSystemWf.choices(),
        editable=False,
    )
    # SpeakerListSystem.objects.filter(title__iregex=r'^.{100,}$')
    # title: str | None = models.CharField(max_length=200, null=True)
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
    show_time: bool = models.BooleanField(
        verbose_name="Show time spoken for all", default=False
    )

    roles_cls = SpeakerSystemRoles
    exporters = {"meeting": {"ignore_fields": ("active_list",)}}
    importers = {"meeting": {}, "organisation": {}}

    def get_method_class(self) -> type[ListMethod]:
        """Fetch the poll method class, a django proxy model."""
        reg = get_list_method_registry()
        return reg[self.method_name]

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
        self.settings_data = data.dict()

    @property
    def organisation(self) -> Organisation:
        return self.meeting.organisation

    def no_active_speaker_guard(self) -> bool:
        if self.active_list:
            return not bool(self.active_list.current)
        return True

    @transition(
        field=state,
        source=SpeakerSystemWf.INACTIVE,
        target=SpeakerSystemWf.ACTIVE,
        permission=SpeakerSystemPermissions.CHANGE,
        custom={"title": _("Make active")},
    )
    def activate(self):
        """
        Set system as active
        """

    @transition(
        field=state,
        source=SpeakerSystemWf.ACTIVE,
        target=SpeakerSystemWf.INACTIVE,
        permission=SpeakerSystemPermissions.CHANGE,
        conditions=[no_active_speaker_guard],
        custom={"title": _("Inactivate")},
    )
    def inactivate(self):
        """
        Make system disabled and hidden for users. This is not a permission though,
        so users can still view the information if they dig around in the frontends source.
        """
        if self.active_list is not None:
            self.active_list = None
        self.save()

    @transition(
        field=state,
        target=SpeakerSystemWf.ARCHIVED,
        permission=NOT_ALLOWED,
        custom={"title": _("Archive")},
    )
    def archive(self):
        self.active_list = None
        for slist in self.speaker_lists.all():
            slist.stop_speaker()
            slist.speakers_in_queue().delete()
            slist.order_list = []
            slist.save()
        self.save()

    def save(self, **kw):
        # Will raise error if there's something bogus with settings or referenced method
        self.settings
        if (
            self.active_list_id
            and not self.speaker_lists.filter(pk=self.active_list_id).exists()
        ):
            raise IntegrityError("Active list belongs to another speaker system")
        # Add meeting on create if not specified
        if not self.pk and self.meeting_id is None and self.room_id is not None:
            if self.room.meeting_id:
                self.meeting_id = self.room.meeting_id
        # Make sure room and sls links to same meeting
        if not self.pk and self.room_id:
            if self.room.meeting_id != self.meeting_id:
                raise IntegrityError("SLS links to another meeting")
        super().save(**kw)

    @property
    def is_archived(self):
        return self.state == SpeakerSystemWf.ARCHIVED

    @property
    def is_active(self):
        return self.state == SpeakerSystemWf.ACTIVE

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


class Speaker(MeetingContext, SpeakerSystemContext):
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

    importers = {"organisation": {}}

    class Meta:
        constraints = []

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

    # Type hinting
    objects = models.Manager()
    user_id: int

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.pk}>"

    def __str__(self):
        return f"Speaker id {self.pk}"

    def save(self, **kwargs):
        new_obj = self.pk is None
        super().save(**kwargs)
        if new_obj:
            self.speaker_list.reorder()


class SpeakerList(AgendaItemContext, MeetingContext, SpeakerSystemContext):
    name = "speaker_list"
    title = models.CharField(max_length=200)
    state = FSMField(
        default=SpeakerListWf.initial, choices=SpeakerListWf.choices(), editable=False
    )
    current: Speaker | None = models.OneToOneField(
        Speaker,
        verbose_name="Current speaker, if any",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    speaker_system: SpeakerListSystem = models.ForeignKey(
        SpeakerListSystem, on_delete=models.CASCADE, related_name="speaker_lists"
    )
    agenda_item: AgendaItem | None = models.ForeignKey(
        AgendaItem, on_delete=models.CASCADE, null=True, related_name="speaker_lists"
    )
    speakers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=Speaker, related_name="speaker_lists"
    )
    order: str = models.TextField(
        verbose_name="Order of user PK, comma separated", default=""
    )
    exporters = {
        "meeting": {
            "meeting_kw": "speaker_system__meeting",
            "ignore_fields": ["current"],
        }
    }
    importers = {"meeting": {}, "organisation": {}}

    @property
    def meeting(self) -> Meeting | None:
        """
        While not directly related, it's still good to be able to do lookups this way
        """
        if self.speaker_system:
            return self.speaker_system.meeting

    @property
    def method(self) -> ListMethod:
        return self.speaker_system.method

    @property
    def is_active_list(self) -> bool:
        """Is this the currently active list?"""
        with suppress(SpeakerListSystem.DoesNotExist):
            return self.active_in_system is not None
        return False

    @property
    def order_list(self) -> list[int]:
        if not self.order:
            return []
        return [int(x) for x in self.order.split(",")]

    @order_list.setter
    def order_list(self, value: list[int | str]):
        [int(x) for x in value]
        self.order = ",".join(str(x) for x in value)

    @transition(
        field=state,
        source=SpeakerListWf.CLOSED,
        target=SpeakerListWf.OPEN,
        permission=SpeakerListPermissions.CHANGE,
        custom={"title": _("Open")},
    )
    def open(self):
        pass

    @transition(
        field=state,
        source=SpeakerListWf.OPEN,
        target=SpeakerListWf.CLOSED,
        permission=SpeakerListPermissions.CHANGE,
        custom={"title": _("Close")},
    )
    def close(self):
        pass

    @ensure_atomic
    def shuffle(self):
        """
        Randomize the order of the speakers. Run reorder afterwards to make sure any other priorities gets applied.
        """
        self.method.shuffle(self)
        self.reorder()

    def reorder(self):
        """
        Something have changed within the list that makes reordering necessary.
        Usually when a user is added or removed, but it can be triggered for attribute changes on users too.
        """
        order_list = self.order_list
        new_order = self.method.reorder(self)
        if order_list != new_order:
            self.order_list = new_order
            self.save()
        return new_order

    def speakers_in_queue(self) -> models.QuerySet[Speaker]:
        """
        Unsorted speaker models in queue. Normally there's no need to touch these.
        """
        return self.speaker_items.filter(seconds__isnull=True, started__isnull=True)

    def historic_speakers(self) -> models.QuerySet[Speaker]:
        return self.speaker_items.filter(seconds__isnull=False, started__isnull=False)

    def started_or_historic_speakers(self) -> models.QuerySet[Speaker]:
        return self.speaker_items.filter(started__isnull=False)

    def get_user_pk_in_queue_created_order(self) -> list[int]:
        return list(
            self.speakers_in_queue()
            .order_by("created")
            .values_list("user_id", flat=True)
        )

    @ensure_atomic
    def start_speaker(self, speaker: Speaker) -> None:
        """
        Start a specific user in the queue
        """
        order_list = self.order_list
        order_list.remove(speaker.user.pk)
        if speaker.started is None:
            self.stop_speaker()
            speaker.started = now()
            speaker.save()
            self.current = speaker
            self.order_list = order_list
            self.save()
        else:  # pragma: no coverage
            # FIXME: Something...?
            raise ValueError()

    @ensure_atomic
    def stop_speaker(self) -> None:
        """
        Stop current speaker and set spoken time
        """
        if speaker := self.current:
            end_td = now() - speaker.started
            speaker.seconds = min(
                math.ceil(end_td.total_seconds()) or 1, 32767
            )  # Max value of PosSmallIntField ~ 9 hours
            speaker.save()
            self.current = None
            self.save()
            # The end of the atomic transaction will trigger a speaker changed message here

    @ensure_atomic
    def undo_speaker(self) -> bool:
        """Move current speaker back to top of queue"""
        speaker = self.current
        if speaker is None:
            return False

        speaker.started = None
        speaker.save()
        self.current = None
        # The end of the atomic transaction will trigger a speaker changed message
        self.reorder()
        return True

    def save(self, **kw):
        if self.title is None:
            self.title = "list @ " + self.agenda_item.title
        with suppress(ObjectDoesNotExist):
            if (
                self.agenda_item_id
                and self.agenda_item.meeting_id
                and self.speaker_system.meeting_id != self.agenda_item.meeting_id
            ):
                raise IntegrityError(
                    "agenda item and list system attached to different meetings"
                )
        super().save(**kw)

    # Type hinting
    objects = models.Manager()
    speaker_items = models.QuerySet()

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.title[:50]}>"

    def __str__(self):
        if self.title:
            return self.title[:50]
        return f"Speaker list {self.pk}"
