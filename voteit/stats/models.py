from __future__ import annotations
from datetime import timedelta
from datetime import date
from datetime import datetime
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from voteit.organisation.models import Organisation


class HistoryLog(models.Model):
    """
    History Log entries, to be populated by nightly job for each organization.
    Contains anonymous usage data.
    """

    # Unique together
    date: date = models.DateField()
    org: Organisation = models.ForeignKey(
        "organisation.Organisation", on_delete=models.PROTECT
    )

    # Statistics fields
    user_online_count: int = models.IntegerField(
        default=0, verbose_name="Unique users online"
    )
    connection_count: int = models.IntegerField(
        default=0, verbose_name="Socket connections made"
    )
    action_count: int = models.IntegerField(
        default=0, verbose_name="Logged action count"
    )
    action_types: dict = models.JSONField(
        default=dict, verbose_name="Actions on different content types"
    )
    content_types: dict = models.JSONField(
        default=dict, verbose_name="Total count of different content types"
    )
    online_duration: timedelta = models.DurationField(
        default=timedelta, verbose_name="Total time online"
    )
    mean_online_duration: timedelta = models.GeneratedField(
        db_persist=True,
        expression=models.Case(
            models.When(user_online_count=0, then=timedelta()),
            default=models.ExpressionWrapper(
                models.F("online_duration") / models.F("user_online_count"),
                output_field=models.DurationField(),
            ),
        ),
        output_field=models.DurationField(),
        verbose_name="Mean time online",
    )
    accepted_invitation_count: int = models.IntegerField(
        default=0, verbose_name="Accepted invitations"
    )
    login_count: int = models.IntegerField(default=0, verbose_name="User login count")
    spoken_duration: timedelta = models.DurationField(
        default=timedelta, verbose_name="Total time spoken"
    )
    speaker_count: int = models.IntegerField(
        default=0, verbose_name="Unique speaker count"
    )
    mean_spoken_duration: timedelta = models.GeneratedField(
        db_persist=True,
        expression=models.Case(
            models.When(speaker_count=0, then=timedelta()),
            default=models.ExpressionWrapper(
                models.F("spoken_duration") / models.F("speaker_count"),
                output_field=models.DurationField(),
            ),
        ),
        output_field=models.DurationField(),
        verbose_name="Mean time spoken",
    )
    # Latest outcome of every changed proposal
    proposal_outcomes: dict = models.JSONField(
        default=dict, verbose_name="Proposal outcomes"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "date"], name="unique_org_date")
        ]
        ordering = ["-date"]
        verbose_name = "History Log"
        verbose_name_plural = "History Logs"

    def __str__(self):
        return f"{self.org} - {self.date}"


class OrganisationPeriodStats(models.Model):
    """
    Unique counts for an organisation over a calendar month or year.
    Written by archive_auditlog before it deletes the log entries they come from,
    since unique counts can't be added up from daily HistoryLog rows.
    """

    MONTH = "month"
    YEAR = "year"
    PERIOD_CHOICES = [(MONTH, "Month"), (YEAR, "Year")]

    org: Organisation = models.ForeignKey(
        "organisation.Organisation", on_delete=models.PROTECT
    )
    period: str = models.CharField(max_length=5, choices=PERIOD_CHOICES)
    start: date = models.DateField()

    unique_online_users: int = models.IntegerField(
        default=0,
        verbose_name="Unique users online",
        help_text="From socket connections, only correct while those are kept.",
    )
    unique_logins: int = models.IntegerField(
        default=0, verbose_name="Unique users that logged in"
    )
    unique_actors: int = models.IntegerField(
        default=0, verbose_name="Unique users that did something"
    )
    active_meetings: int = models.IntegerField(
        default=0, verbose_name="Meetings with activity"
    )
    unique_participants: int = models.IntegerField(
        default=0, verbose_name="Unique participants in active meetings"
    )
    created: datetime = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "period", "start"], name="unique_org_period_start"
            )
        ]
        ordering = ["-start", "period"]
        verbose_name = "Organisation period stats"
        verbose_name_plural = "Organisation period stats"

    def __str__(self):
        return f"{self.org} - {self.period} {self.start}"


class MeetingStats(models.Model):
    """
    Lifetime numbers for a meeting, kept after the meeting and its log entries are gone.
    """

    # Not a FK, the row should outlive the meeting.
    meeting_id: int = models.BigIntegerField(unique=True)
    org: Organisation = models.ForeignKey(
        "organisation.Organisation", on_delete=models.PROTECT
    )
    title: str = models.CharField(max_length=255, blank=True)
    first_activity: datetime = models.DateTimeField()
    last_activity: datetime = models.DateTimeField()
    unique_participants: int = models.IntegerField(
        default=0, verbose_name="Unique participants"
    )
    unique_voters: int = models.IntegerField(default=0, verbose_name="Unique voters")
    poll_count: int = models.IntegerField(default=0)
    updated: datetime = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_activity"]
        verbose_name = "Meeting stats"
        verbose_name_plural = "Meeting stats"

    def __str__(self):
        return f"{self.title or self.meeting_id}"
