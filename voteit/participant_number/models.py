from __future__ import annotations

from datetime import datetime
from typing import Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from voteit.meeting.models import Meeting


class ParticipantNumber(models.Model):
    """
    A specific number for a specific user within a meeting.
    This works as an alias in situations where it would be impractical to use usernames,
    for instance a plenary debate with bad internet connections. Speakers (users)
    could then have signs with a number on that the moderator simply enters to queue them.
    """

    name = "participant_number"

    number: int = models.PositiveSmallIntegerField(blank=True)
    user: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    pns: PNSystem = models.ForeignKey(
        "PNSystem", on_delete=models.CASCADE, related_name="numbers"
    )
    created: datetime = models.DateTimeField(editable=False, auto_now_add=True)

    importers = {"organisation": {"remap_relations": {"pnsystem": {"pns"}}}}

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "pns"],
                name="%(app_label)s_%(class)s_unique_check_for_user",
            ),
            models.UniqueConstraint(
                fields=["pns", "number"],
                name="%(app_label)s_%(class)s_unique_check_for_number",
            ),
        ]

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.number}>"

    def __str__(self):
        return f"{self.user}: PN-{self.number}"

    def save(self, **kwargs):
        if self.number is None:
            pn = self.pns.numbers.order_by("-number").first()
            if pn is None:
                self.number = 1
            else:
                self.number = pn.number + 1
        super().save(**kwargs)


class PNSystem(models.Model):
    """
    The Participant number system has a 1-1 relation to a meeting.

    Most of the permission checks for this system is delegated to the related meeting,
    so there's no separate role.
    """

    name = "pnsystem"

    meeting: Optional[Meeting] = models.OneToOneField(
        Meeting, on_delete=models.CASCADE, null=True, related_name="pn_system"
    )

    importers = {"organisation": {}}

    def get_user(self, pn: int, default=None) -> Optional[AbstractUser]:
        for pn_obj in self.numbers.filter(number=pn).all().prefetch_related("user"):
            return pn_obj.user
        return default

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.meeting}>"

    def __str__(self):
        return f"PN: {self.meeting}"

    # Annotations
    numbers: models.QuerySet
    objects: models.Manager
