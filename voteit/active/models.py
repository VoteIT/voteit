from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.conf import settings
from django.db import models
from django.utils.timezone import now
from rules.contrib.models import RulesModelMixin

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


@auditlog.register(
    include_fields=[
        "meeting",
        "user",
    ],
)
class ActiveUser(RulesModelMixin, MeetingContext):
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

    def __str__(self):
        if self.user.userid:
            return f"ActiveUser ({self.user.userid})"
        return f"ActiveUser [{self.user.username}]"

    # annotations
    user_id: int
    meeting_id: int
