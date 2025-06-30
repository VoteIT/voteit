from __future__ import annotations
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models

from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.models import User


class ParticipantTags(MeetingContext):
    user: User = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meeting_tags"
    )
    meeting: Meeting = models.ForeignKey(
        Meeting, on_delete=models.CASCADE, related_name="participant_tags"
    )
    tags = models.JSONField(default=dict)

    class Meta:
        unique_together = (("user", "meeting"),)

    objects: models.Manager
    user_id: int
    meeting_id: int
