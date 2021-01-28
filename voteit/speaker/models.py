from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, Type, Dict, Union

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition
from pydantic.main import BaseModel

from voteit.agenda.models import AgendaItem
from voteit.core.abcs import MeetingContext
from voteit.core.models import Roles, RoleContextMixin
from voteit.meeting.models import Meeting
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.utils import get_list_method_registry
from voteit.speaker.workflows import SpeakerListWf

if TYPE_CHECKING:
    from voteit.speaker.abcs import ListMethod

# FIXME:
# Då gör jag ett system som heter "talarprioritering" som har möjligheten
# att begränsa antalet gånger en talare ska prioriteras.
# Voila så har vi "antal talarlistor" på ett begripligt sätt.
# Som standard så finns ingen sådan begränsning då
# och ett system som bara sätter upp talaren utan att göra något

# FIXME: SpeakerListSystems (SLS) should be able to relate to another SLS, causing all settings
# to be shared between them.


__all__ = "SpeakerSystemRoles", "SpeakerListSystem", "Speaker", "SpeakerList"


class SpeakerSystemRoles(Roles, MeetingContext):
    context: SpeakerListSystem = models.ForeignKey(
        "SpeakerListSystem", on_delete=models.CASCADE
    )

    @property
    def meeting(self) -> Optional[Meeting]:
        return self.context.meeting


class SpeakerListSystem(RoleContextMixin, MeetingContext):
    """All speaker list things relate here, while this in turn might relate to a meeting.
    A list system has its own rules and moderators.
    """

    active: bool = models.BooleanField(
        verbose_name=_(
            "Is the system activated? If not it won't be visible to anyone."
        ),
        default=False,
    )
    title = models.CharField(max_length=200, null=True)
    meeting: Optional[Meeting] = models.ForeignKey(
        Meeting,
        verbose_name=_("Related meeting"),
        on_delete=models.CASCADE,
        null=True,
        related_name="speaker_systems",
    )
    method_name: str = models.CharField(max_length=20)
    settings_data: Dict = models.JSONField(
        verbose_name=_("JSON-serialized settings data"),
        editable=False,
        null=True,
        encoder=DjangoJSONEncoder,
    )
    safe_positions = models.PositiveSmallIntegerField(
        verbose_name=_(
            "When a list is active, mark the top X positions as safe automatically. "
            "Safe speakers will never be moved down."
        ),
        choices=[(x, str(x)) for x in range(3)],
        null=True,
        blank=True,
    )
    active_list = models.OneToOneField(
        "SpeakerList",
        verbose_name=_("Currently active speaker list"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_in_system",
    )

    roles_cls = SpeakerSystemRoles

    def get_method_class(self) -> Type[ListMethod]:
        """Fetch the poll method class, a django proxy model."""
        reg = get_list_method_registry()
        return reg[self.method_name]

    @cached_property
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
    def settings(self, value: Union[Dict, BaseModel]):
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

    def save(self, **kw):
        # Will raise error if there's something bogus with settings or referenced method
        self.settings
        super(SpeakerListSystem, self).save(**kw)

    # Type hinting
    objects = models.Manager()


class Speaker(models.Model):
    """Information about a user who's entered a speaker list."""

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    list: SpeakerList = models.ForeignKey(
        "SpeakerList", on_delete=models.CASCADE, related_name="speaker_items"
    )
    # Note: Created is also needed for "historic" positions within a speaker list in case they're rearranged.
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    order: Optional[int] = models.PositiveSmallIntegerField(null=True)
    safe_pos: bool = models.BooleanField(default=False)
    started: Optional[datetime] = models.DateTimeField(null=True)
    seconds: Optional[int] = models.PositiveSmallIntegerField(null=True)

    class Meta:
        constraints = [
            # Save doesn't work with this when we reorder. Really?
            # models.UniqueConstraint(
            #     fields=["list", "order"],
            #     name="%(app_label)s_%(class)s_speakers_position_unique",
            # )
        ]

    @property
    def ended(self) -> Optional[datetime]:
        if self.seconds is not None and isinstance(self.started, datetime):
            return self.started + timedelta(seconds=self.seconds)

    @property
    def current(self) -> bool:
        """We're guessing that this is the current speaker
        if it has a started timestamp and no recorded spoken seconds.
        """
        return self.started is not None and self.seconds is None

    @property
    def in_queue(self) -> bool:
        """ The definition of being in the queue is that order is set to a number"""
        return self.order is not None

    # def start(self):
    #     """ Remove from queue (order) and set a timestamp. """
    #     if self.started is None:
    #         if self.list.current is not None:
    #             self.list.current.stop()
    #         self.order = None
    #         self.started = now()
    #         self.save()
    #         self.list.current = self
    #         self.list.save()
    #     else:  # pragma: no coverage
    #         # FIXME: Something...?
    #         raise ValueError()

    # def stop(self):
    #     """End this speaker."""
    #     if self.list.current == self and self.started is not None:
    #         end_td = now() - self.started
    #         end_secs = end_td.seconds
    #         if not end_secs:
    #             end_secs = 1
    #         self.seconds = end_secs
    #         self.save()
    #         self.list.current = None
    #         self.list.save()

    # Type hinting
    objects = models.Manager()


class SpeakerList(models.Model):
    title = models.CharField(max_length=200, null=True)
    state = FSMField(
        default=SpeakerListWf.initial, choices=SpeakerListWf.choices(), editable=False
    )
    current: Optional[Speaker] = models.OneToOneField(
        Speaker,
        verbose_name=_("Current speaker, if any"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )
    list_system: SpeakerListSystem = models.ForeignKey(
        SpeakerListSystem, on_delete=models.CASCADE, related_name="speaker_lists"
    )
    agenda_item: Optional[AgendaItem] = models.ForeignKey(
        AgendaItem, on_delete=models.CASCADE, null=True, related_name="speaker_lists"
    )
    speakers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=Speaker, related_name="speaker_lists"
    )

    @property
    def method(self) -> ListMethod:
        return self.list_system.method

    @property
    def is_active_list(self) -> bool:
        """ Is this the currently active list? """
        return self.list_system.active_list == self

    @transition(
        field=state,
        source=SpeakerListWf.CLOSED,
        target=SpeakerListWf.OPEN,
        permission=SpeakerListPermissions.CHANGE,
    )
    def open(self):
        pass

    @transition(
        field=state,
        source=SpeakerListWf.OPEN,
        target=SpeakerListWf.CLOSED,
        permission=SpeakerListPermissions.CHANGE,
    )
    def close(self):
        pass

    def reorder(self, force_signal=False):
        """Something have changed within the list that makes reordering necessary.
        Usually when a user is added or removed, but it can be triggered for attribute changes on users too.
        """
        current = self.current_order()
        with transaction.atomic():
            new_order = self.method.reorder(self)
            safe_updated = False
            # Check if a speaker should be moved to a safe position - only if the list is active.
            if self.is_active_list:
                system = self.list_system
                safe_pos = system.safe_positions
                if (
                    safe_pos
                    and safe_pos
                    > self.speaker_items.filter(
                        order__isnull=False, safe_pos=True
                    ).count()
                ):
                    # FIXME: Do something smarter
                    for speaker in self.speakers_qs()[:safe_pos]:
                        if not speaker.safe_pos:
                            speaker.safe_pos = True
                            speaker.save()
                            safe_updated = True
        # Outside of transaction block, the save must be done first!
        if current != new_order or safe_updated or force_signal:
            self.signal_list_updated()
        return new_order

    def signal_list_updated(self):
        # Circular import :(
        from voteit.speaker.signals import list_updated

        list_updated.send(sender=self.__class__, instance=self)

    def current_order(self):
        """Return an ordered list of primary keys for speaker items that are in the queue."""
        # FIXME: There's probably an optimisation to be done here :)
        return [x.pk for x in self.speakers_qs().all()]

    def safe_speakers_qs(self) -> models.QuerySet:
        return self.speaker_items.filter(order__isnull=False, safe_pos=True).order_by(
            "order"
        )

    def speakers_qs(self) -> models.QuerySet:
        """Return an ordered queryset with the speakers in the current list."""
        return self.speaker_items.filter(order__isnull=False).order_by(
            "-safe_pos", "order"
        )

    def speakers_unsafe_created_qs(self) -> models.QuerySet:
        return self.speaker_items.filter(order__isnull=False, safe_pos=False).order_by(
            "created"
        )

    def start_speaker(self, speaker: Speaker) -> None:
        """ Start a a specific user in the queue, or first user
        """
        if speaker := speaker or self.speakers_qs().first():
            if speaker.started is None:
                self.stop_speaker()
                speaker.order = None
                speaker.started = now()
                speaker.save()
                self.current = speaker
                self.save()
            else:  # pragma: no coverage
                # FIXME: Something...?
                raise ValueError()

    def stop_speaker(self) -> None:
        """ Stop current speaker and set spoken time
        """
        if speaker := self.current:
            end_td = now() - speaker.started
            speaker.seconds = end_td.seconds or 1
            speaker.save()
            self.current = None
            self.save()

    # Type hinting
    objects = models.Manager()
