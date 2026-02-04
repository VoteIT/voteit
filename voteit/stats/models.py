import datetime

from django.db import models

from voteit.organisation.models import Organisation


class HistoryLog(models.Model):
    """
    History Log entries, to be populated by nightly job for each organization.
    Contains anonymous usage data.
    """

    # Unique together
    date = models.DateField()
    org = models.ForeignKey(Organisation, on_delete=models.PROTECT)

    # Statistics fields
    user_online_count = models.IntegerField(
        default=0, verbose_name="Unique users online"
    )
    connection_count = models.IntegerField(
        default=0, verbose_name="Socket connections made"
    )
    action_count = models.IntegerField(default=0, verbose_name="Logged action count")
    action_types = models.JSONField(
        default=dict, verbose_name="Actions on different content types"
    )
    content_types = models.JSONField(
        default=dict, verbose_name="Total count of different content types"
    )
    online_duration = models.DurationField(
        default=datetime.timedelta, verbose_name="Total time online"
    )
    mean_online_duration = models.GeneratedField(
        db_persist=True,
        expression=models.Case(
            models.When(user_online_count=0, then=datetime.timedelta()),
            default=models.ExpressionWrapper(
                models.F("online_duration") / models.F("user_online_count"),
                output_field=models.DurationField(),
            ),
        ),
        output_field=models.DurationField(),
        verbose_name="Mean time online",
    )
    accepted_invitation_count = models.IntegerField(
        default=0, verbose_name="Accepted invitations"
    )
    login_count = models.IntegerField(default=0, verbose_name="User login count")
    spoken_duration = models.DurationField(
        default=datetime.timedelta, verbose_name="Total time spoken"
    )
    speaker_count = models.IntegerField(default=0, verbose_name="Unique speaker count")
    mean_spoken_duration = models.GeneratedField(
        db_persist=True,
        expression=models.Case(
            models.When(speaker_count=0, then=datetime.timedelta()),
            default=models.ExpressionWrapper(
                models.F("spoken_duration") / models.F("speaker_count"),
                output_field=models.DurationField(),
            ),
        ),
        output_field=models.DurationField(),
        verbose_name="Mean time spoken",
    )
    # Latest outcome of every changed proposal
    proposal_outcomes = models.JSONField(default=dict, verbose_name="Proposal outcomes")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["org", "date"], name="unique_org_date")
        ]
        ordering = ["-date"]
        verbose_name = "History Log"
        verbose_name_plural = "History Logs"

    def __str__(self):
        return f"{self.org} - {self.date}"
