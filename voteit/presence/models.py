from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now
from rules.contrib.models import RulesModelMixin

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting


class Presence(MeetingContext):
    """
    A registered presence for a specific user.
    It's only possible to create/delete this if the presence_check is open.
    As an object, there's no usecase to allow change since it implies tampering with the system.
    """

    name = "presence"

    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT
    )
    presence_check: PresenceCheck = models.ForeignKey(
        "PresenceCheck", on_delete=models.CASCADE, related_name="presences"
    )
    created: datetime = models.DateTimeField(editable=False, default=now)

    @property
    def meeting(self) -> Meeting | None:
        """
        Find meeting from this instance
        """
        return self.presence_check.meeting

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "presence_check"],
                name="%(app_label)s_%(class)s_unique_check_for_user",
            )
        ]

    def __str__(self):
        return f"Presence ({self.pk})"

    # Type hinting
    objects: models.Manager


class PresenceCheck(RulesModelMixin, MeetingContext):
    """
    This models handles lists of users who are present.
    Only one presence check should be open at a time.
    It enforces a relation to the PresenceSystem.

    Closing it causes it to be write protected,
    and no related objects should be changed after that.

    It should be okay to delete the whole PresenceSystem though,
    since deleting is better than tampering :)
    """

    name = "presence_check"

    state: str = models.CharField(max_length=30, editable=False)
    present_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through=Presence, related_name="presences"
    )
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="presence_checks"
    )
    opened: datetime = models.DateTimeField(editable=False, default=now)
    closed: datetime | None = models.DateTimeField(
        editable=False, null=True, blank=True
    )

    def present_user_pks(self) -> list[int]:
        return list(self.presences.values_list("user_id"))

    def __str__(self):
        return f"Presence check ({self.pk})"

    presences: models.QuerySet
