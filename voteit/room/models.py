from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.utils.timezone import now

from voteit.agenda.models import AgendaItem
from voteit.core.abcs import MeetingContext
from voteit.core.fields import RichTextField
from voteit.core.utils import relaxed_clean_html
from voteit.meeting.models import Meeting
from voteit.poll.models import Poll
from voteit.proposal.models import Proposal

if TYPE_CHECKING:
    from voteit.core.models import User as UserType
    from voteit.speaker.models import SpeakerListSystem


class Room(MeetingContext):
    _initial_poll_value = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_poll_value = self.poll
        self._initial_show_ballot = self.show_ballot

    name = "room"
    open: bool = models.BooleanField(
        verbose_name="Is it open for participants?", default=False
    )
    handler: UserType | None = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Who's in the drivers seat?",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    title: str = models.CharField(
        verbose_name="Title",
        max_length=100,
        default="",
        blank=True,
    )
    body: str = RichTextField(
        verbose_name="Body", blank=True, default="", html_cleaner=relaxed_clean_html
    )
    created: datetime = models.DateTimeField(editable=False, default=now)
    meeting: Meeting = models.ForeignKey(
        Meeting,
        on_delete=models.CASCADE,
        related_name="rooms",
    )
    agenda_item: AgendaItem = models.ForeignKey(
        AgendaItem,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    poll: Poll = models.ForeignKey(
        Poll,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    show_ballot: bool = models.BooleanField(
        verbose_name="Show the ballot", default=False
    )
    # Auto set speaker list from active agenda?
    send_sls: bool = models.BooleanField(
        verbose_name="Send Speaker lists?", default=False
    )
    send_proposals: bool = models.BooleanField(
        verbose_name="Send proposals?", default=False
    )
    show_time: bool = models.BooleanField(
        verbose_name="Show time?",
        default=True,
    )

    @property
    def highlighted_proposal_pks(self):
        return (
            self.highlighted_proposals.all()
            .order_by("order")
            .values_list("proposal", flat=True)
        )

    def save(self, **kwargs):
        if self.poll != self._initial_poll_value and self._initial_show_ballot:
            self.show_ballot = False
        super().save(**kwargs)

    def __str__(self):
        return f"Room {self.title} for meeting {self.meeting.pk}"

    # annotations
    meeting_id: int
    sls: SpeakerListSystem | None
    poll_id: int | None
    highlighted_proposals: models.Manager
    objects: models.Manager


class HighlightProposal(models.Model):
    proposal: Proposal = models.ForeignKey(
        Proposal, on_delete=models.CASCADE, related_name="highlighted_in"
    )
    room: Room = models.ForeignKey(
        Room, on_delete=models.CASCADE, related_name="highlighted_proposals"
    )
    order: int = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["room", "proposal"],
                name="unique_room_prop",
            )
        ]

    def save(self, **kwargs):
        if not self.pk and not self.order:
            max_order = self.room.highlighted_proposals.aggregate(
                max_order=models.Max("order")
            )["max_order"]
            if max_order is None:
                self.order = 1
            else:
                self.order = max_order + 1
        super().save(**kwargs)

    # annotations
    objects: models.Manager
    proposal_id: int
    room_id: int
    order: int
