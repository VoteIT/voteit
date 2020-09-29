from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional, Type

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.speaker.permissions import SpeakerListPermissions
from voteit.speaker.signals import list_updated
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

class SpeakerListSystem(models.Model):
    """ All speaker list things relate here, while this in turn might relate to a meeting.
        A list system has its own rules and moderators.
    """

    active: bool = models.BooleanField(
        verbose_name=_(
            "Is the system activated? If not it won't be visible to anyone."
        ),
        default=False,
    )
    meeting: Meeting = models.ForeignKey(
        Meeting, verbose_name=_("Related meeting"), on_delete=models.CASCADE, null=True
    )
    method_type: str = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True
    )
    method_id: int = models.PositiveIntegerField(null=True)
    method: ListMethod = GenericForeignKey("method_type", "method_id")
    moderators = models.ManyToManyField(
        User,
        verbose_name=_("Users who may moderate the speaker lists"),
        blank=True,
        related_name="moderator_in_list_systems",
        editable=False,
    )
    speakers = models.ManyToManyField(
        User,
        verbose_name=_(
            "Users who may ask to speak (i.e. enter a list) depending on if they're open or not"
        ),
        blank=True,
        related_name="speaker_in_list_systems",
        editable=False,
    )
    safe_positions = models.PositiveSmallIntegerField(
        verbose_name=_(
            "When a list is active, mark the top X positions as safe automatically. "
            "Safe speakers will never be moved down."
        ),
        choices=[(str(x), x) for x in range(3)],
        null=True,
    )
    active_list = models.ForeignKey(
        "SpeakerList",
        verbose_name=_("Currently active speaker list"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="active_list_system",
    )


class Speaker(models.Model):
    """ Information about a user who's entered a speaker list.
    """

    user: User = models.ForeignKey(User, on_delete=models.PROTECT)
    list: SpeakerList = models.ForeignKey(
        "SpeakerList", on_delete=models.CASCADE, related_name="speaker_items"
    )
    # Note: Created is also needed for "historic" positions within a speaker list in case they're rearranged.
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    order: int = models.PositiveSmallIntegerField(null=True)
    safe_pos: bool = models.BooleanField(default=False)
    started: datetime = models.DateTimeField(null=True)
    seconds: int = models.PositiveSmallIntegerField(null=True)

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
        """ We're guessing that this is the current speaker
            if it has a started timestamp and no recorded spoken seconds.
        """
        return self.started is not None and self.seconds is None

    def start(self):
        """ Remove from queue (order) and set a timestamp. """
        if self.started is None:
            self.order = None
            self.started = now()
            self.save()
        else:  # pragma: no coverage
            # FIXME: Something...?
            raise ValueError()


@receiver(post_save, sender=Speaker)
def set_initial_order(
    sender: Type[Speaker], instance: Speaker, created: bool, **kwargs
):
    """ 
    :param sender: Model
    :param instance: Speaker instance
    :param created: Is this a new db records? We only care about the newly created for this method.
    :param kwargs:
    """
    if created:
        sl = instance.list
        results = sl.speaker_items.filter(order__isnull=False).aggregate(
            models.Max("order")
        )
        current_order = results["order__max"]
        if current_order is None:
            order = 1
        else:
            order = current_order + 1
        instance.order = order
        instance.save()
        sl.reorder()


@receiver(post_delete, sender=Speaker)
def reorder_after_delete(sender: Type[Speaker], instance: Speaker, **kwargs):
    instance.list.reorder(force_signal=True)


class SpeakerList(models.Model):
    state = FSMField(
        default=SpeakerListWf.initial, choices=SpeakerListWf.choices(), editable=False
    )
    current: Optional[Speaker] = models.OneToOneField(
        Speaker,
        verbose_name=_("Current speaker, if any"),
        null=True,
        on_delete=models.CASCADE,
    )
    list_system: SpeakerListSystem = models.ForeignKey(
        SpeakerListSystem, on_delete=models.CASCADE, related_name="speaker_lists"
    )
    agenda_item: Optional[AgendaItem] = models.ForeignKey(
        AgendaItem, on_delete=models.CASCADE, null=True, related_name="speaker_lists"
    )
    speakers = models.ManyToManyField(
        User, through=Speaker, related_name="speaker_lists"
    )

    @property
    def method(self) -> ListMethod:
        return self.list_system.method

    @transition(
        field=state,
        source=SpeakerListWf.CLOSED,
        target=SpeakerListWf.OPEN,
        permission=SpeakerListPermissions.MODERATE,
    )
    def open(self):
        pass

    @transition(
        field=state,
        source=SpeakerListWf.OPEN,
        target=SpeakerListWf.CLOSED,
        permission=SpeakerListPermissions.MODERATE,
    )
    def close(self):
        pass

    def reorder(self, force_signal=False):
        """ Something have changed within the list that makes reordering necessary.
            Usually when a user is added or removed, but it can be triggered for attribute changes on users too.
        """
        current = self.current_order()
        with transaction.atomic():
            new_order = self.method.reorder(self)
            safe_updated = False
            # Check if a speaker should be moved to a safe position - only if the list is active.
            if self.active_list_system.exists():
                system = self.active_list_system.get()
                safe_pos = system.safe_positions
                if safe_pos and safe_pos > self.speaker_items.filter(order__isnull=False, safe_pos=True).count():
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
        list_updated.send(
            sender=self.__class__, instance=self, queue=self.current_order()
        )

    def current_order(self):
        """ Return an ordered list of primary keys for speaker items that are in the queue.
        """
        # FIXME: There's probably an optimisation to be done here :)
        return [x.pk for x in self.speakers_qs().all()]

    def safe_speakers_qs(self) -> models.QuerySet:
        return self.speaker_items.filter(order__isnull=False, safe_pos=True).order_by(
            "order"
        )

    def speakers_qs(self) -> models.QuerySet:
        """ Return an ordered queryset with the speakers in the current list.
        """
        return self.speaker_items.filter(order__isnull=False).order_by(
            "-safe_pos", "order"
        )

    def speakers_unsafe_created_qs(self) -> models.QuerySet:
        return self.speaker_items.filter(order__isnull=False, safe_pos=False).order_by("created")
