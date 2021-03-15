from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from django.contrib.auth import get_user_model
from django.db import models

from voteit.core.models import BaseContent
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.reactions.mixins import Reactable

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from voteit.meeting.models import Meeting
    from voteit.meeting.models import MeetingGroup


User: AbstractUser = get_user_model()


class DiscussionPost(
    BaseContent,
    AgendaItemContext,
    MeetingContext,
    Reactable,
):
    name = "discussion_post"
    author: AbstractUser = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
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
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discussions",
    )

    @property
    def meeting(self) -> Optional[Meeting]:
        """ While not directly related, it still good to be able to do lookups this way"""
        if self.agenda_item:
            return self.agenda_item.meeting
