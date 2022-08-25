from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django_fsm import FSMField, transition

from voteit.bug_reports.workflows import BugReportWf
from voteit.core.abcs import MeetingContext
from voteit.meeting.models import Meeting

if TYPE_CHECKING:
    from voteit.core.models import User as UserType


__all__ = ("BugReport",)


class BugReport(MeetingContext):
    name = "bug_report"
    meeting: Meeting = models.ForeignKey(Meeting, models.CASCADE)
    user: UserType = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
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
