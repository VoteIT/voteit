from __future__ import annotations

from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django_fsm import FSMField, transition

from voteit.bug_reports.workflows import BugReportWf
from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting


User = get_user_model()


class BugReport(MeetingContext):
    meeting = models.ForeignKey(Meeting, models.CASCADE)
    user = models.ForeignKey(User, models.CASCADE)
    user_roles: list[str] = ArrayField(models.CharField(max_length=20, default=tuple))
    user_platform: dict = models.JSONField(
        encoder=DjangoJSONEncoder
    )  # navigator.userAgent, etc
    function: str = models.CharField(max_length=20, null=True, blank=True)
    description: str = models.TextField()
    state: str = FSMField(default=BugReportWf.initial, choices=BugReportWf.choices())
    created: datetime = models.DateTimeField(auto_now_add=True)
    updated: datetime = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bug report"
        verbose_name_plural = "Bug reports"
        ordering = ("-created",)

    def __str__(self):
        return f"Report by {self.user} from {self.user.organisation}"

    @transition(
        field=state,
        source="+",
        target=BugReportWf.UNRESOLVED,
    )
    def back_to_unresolved(self):
        pass

    @transition(
        field=state,
        source="+",
        target=BugReportWf.IGNORED,
    )
    def ignore(self):
        pass

    @transition(
        field=state,
        source="+",
        target=BugReportWf.RESOLVED,
    )
    def resolve(self):
        pass

    objects: models.Manager
