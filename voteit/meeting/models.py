from __future__ import annotations
from typing import TYPE_CHECKING

from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _
from django_fsm import FSMField, transition

from voteit.core.models import BaseContent
from voteit.meeting.workflows import MeetingWf

if TYPE_CHECKING:
    from voteit.poll.models import ElectoralRegister


class Meeting(BaseContent):
    state = FSMField(
        default=MeetingWf.initial, choices=MeetingWf.choices(), editable=False
    )
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    participants = models.ManyToManyField(
        User, blank=True, related_name="participant_in_meetings", editable=False
    )
    potential_voters = models.ManyToManyField(
        User, blank=True, related_name="potential_voter_in_meetings", editable=False
    )
    er_policy_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, editable=False
    )
    er_policy_id = models.PositiveIntegerField(null=True, editable=False)
    er_policy = GenericForeignKey("er_policy_type", "er_policy_id")
    organisation = models.ForeignKey(
        "organisation.Organisation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="meetings",
    )

    def get_latest_er(self) -> ElectoralRegister:
        return (
            self.electoral_registers.filter(meeting=self).order_by("-created").first()
        )

    @transition(field=state, source=MeetingWf.ONGOING, target=MeetingWf.UPCOMING)
    def upcoming(self):
        pass

    @transition(
        field=state,
        source=[MeetingWf.UPCOMING, MeetingWf.CLOSED],
        target=MeetingWf.ONGOING,
    )
    def ongoing(self):
        self.start_time = timezone.now()

    @transition(field=state, source=MeetingWf.ONGOING, target=MeetingWf.CLOSED)
    def closed(self):
        self.end_time = timezone.now()

    @transition(field=state, source=MeetingWf.CLOSED, target=MeetingWf.ARCHIVED)
    def archived(self):
        pass
