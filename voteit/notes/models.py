from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from voteit.core.abcs import MeetingContext
from voteit.core.fields import RichTextField
from voteit.core.utils import strict_clean_html
from voteit.meeting.models import Meeting
from voteit.notes import NoteIntent
from voteit.proposal.models import Proposal

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


class Note(MeetingContext):
    name = "note"
    meeting: Meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="notes",
        editable=False,
    )
    proposal: Proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="+",
    )
    user: UserType = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="notes",
    )
    body: str = RichTextField(blank=True, default="", html_cleaner=strict_clean_html)
    intent: str = models.CharField(
        max_length=1,
        blank=True,
        choices=NoteIntent,
        default=NoteIntent.BLANK,
    )
    created: datetime = models.DateTimeField(
        editable=False,
        default=now,
    )

    def __str__(self):  # pragma: no cover
        return f"Note {self.pk}"

    class Meta:
        ordering = ("created",)
        constraints = [
            models.UniqueConstraint(
                name="%(app_label)s_%(class)s_unique",
                fields=("proposal", "user"),
            ),
        ]

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.meeting_id = self.proposal.agenda_item.meeting_id
        super().save(*args, **kwargs)

    # annotations
    user_id: int
    meeting_id: int
    proposal_id: int
    objects: models.Manager
