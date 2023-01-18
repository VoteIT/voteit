from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


class ActiveUser(MeetingContext):
    name = "active_user"
    meeting: Meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="active_users",
    )
    user: UserType = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="+"
    )
    created: datetime = models.DateTimeField(editable=False, default=now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_unique_per_meeting",
                fields=("meeting", "user"),
            ),
        ]

    # annotations
    user_id: int
    meeting_id: int
