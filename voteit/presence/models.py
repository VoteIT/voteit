from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now
from django_fsm import FSMField
from django_fsm import transition

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting
from voteit.presence.workflows import PresenceCheckWf


class Presence(models.Model):
    """
    A registered presence for a specific user.
    It's only possible to create/delete this if the presence_check is open.
    As an object, there's no usecase to allow change since it implies tampering with the system.
    """

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    presence_check: PresenceCheck = models.ForeignKey(
        "PresenceCheck", on_delete=models.CASCADE, related_name="presences"
    )
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "presence_check"],
                name="%(app_label)s_%(class)s_unique_check_for_user",
            )
        ]

    def __str__(self):
        return f"Presence ({self.pk})"

    objects = models.Manager()  # Type hinting


class PresenceCheck(models.Model):
    """
    This models handles lists of users who are present.
    Only one presence check should be open at a time.
    It enforces a relation to the PresenceSystem.

    Closing it causes it to be write protected,
    and no related objects should be changed after that.

    It should be okay to delete the whole PresenceSystem though,
    since deleting is better than tampering :)
    """

    state: str = FSMField(
        default=PresenceCheckWf.initial,
        choices=PresenceCheckWf.choices(),
        protected=True,
    )
    present_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=Presence, related_name="presences"
    )
    presence_system: PresenceSystem = models.ForeignKey(
        "PresenceSystem", on_delete=models.CASCADE, related_name="presence_checks"
    )
    opened: datetime = models.DateTimeField(editable=False, auto_now_add=True)
    closed: Optional[datetime] = models.DateTimeField(
        editable=False, null=True, blank=True
    )

    @transition(field=state, source=PresenceCheckWf.OPEN, target=PresenceCheckWf.CLOSED)
    def close(self) -> None:
        self.closed = now()

    def __str__(self):
        return f"Presence check ({self.pk})"

    objects = models.Manager()  # Type hinting


class PresenceSystem(MeetingContext):
    """
    The presence system has a 1-1 relation to a meeting.
    It acts as a container for all other objects.
    It should be possible to safely delete it and thus
    remove all data related to presence for the related meeting.

    Most of the permission checks for this system is delegated to the related meeting,
    so there's no separate role to run presence checks.
    """

    meeting: Optional[Meeting] = models.OneToOneField(
        Meeting, on_delete=models.CASCADE, null=True
    )

    def __str__(self):
        return f"Presence system ({self.pk})"

    objects = models.Manager()  # Type hinting
