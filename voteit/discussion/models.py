from __future__ import annotations

from typing import TYPE_CHECKING

from auditlog.registry import auditlog
from django.conf import settings
from django.db import models

from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.core.models import BaseContent
from voteit.reactions.mixins import Reactable
from voteit.stats.registry import history_log

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.meeting.models import Meeting
    from voteit.meeting.models import MeetingGroup


@history_log("agenda_item__meeting__organisation")
@auditlog.register(
    include_fields=[
        "agenda_item",
        "author",
        "meeting_group",
        "as_group",
        "body",
    ],
)
class DiscussionPost(
    BaseContent,
    AgendaItemContext,
    MeetingContext,
    Reactable,
):
    name = "discussion_post"
    author: AbstractUser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="discussions",
    )
    agenda_item = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        null=True,
        related_name="discussions",
    )
    meeting_group: MeetingGroup = models.ForeignKey(
        "meeting.MeetingGroup",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="discussions",
    )
    as_group: bool = models.BooleanField(
        verbose_name="Posted as group rather than author", default=False
    )

    @property
    def meeting(self) -> Meeting | None:
        """While not directly related, it still good to be able to do lookups this way"""
        if self.agenda_item:
            return self.agenda_item.meeting

    def save(self, **kwargs):
        if self.as_group and not self.meeting_group_id:
            self.as_group = False
        super().save(**kwargs)

    # Annotations
    objects: models.Manager
    meeting_group_id: None | int
    agenda_item_id: None | int
    author_id: None | int
