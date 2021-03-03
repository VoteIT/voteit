from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from django.db import models

from voteit.core.models import BaseContent
from voteit.core.abcs import AgendaItemContext
from voteit.core.abcs import MeetingContext
from voteit.reactions.mixins import Reactable

if TYPE_CHECKING:
    from voteit.meeting.models import Meeting


class DiscussionPost(
    BaseContent,
    AgendaItemContext,
    MeetingContext,
    Reactable,
):
    name = "discussion_post"
    agenda_item = models.ForeignKey(
        "agenda.AgendaItem",
        on_delete=models.CASCADE,
        null=True,
        related_name="discussions",
    )

    @property
    def meeting(self) -> Optional[Meeting]:
        """ While not directly related, it still good to be able to do lookups this way"""
        if self.agenda_item:
            return self.agenda_item.meeting
