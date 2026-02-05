from datetime import datetime, timedelta

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from envelope.models import Connection

from voteit.core.decorators import schedule_job
from voteit.invites.models import MeetingInvite
from voteit.organisation.models import Organisation
from voteit.speaker.models import Speaker
from voteit.stats.models import HistoryLog

User = get_user_model()


def mk_daterange_filter(field_name: str, start: datetime = None) -> dict:
    """
    Creates a date range filter for named DateTimeField. Faster than filtering on field_name__date.
    """
    if start is None:
        start = timezone.now()
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        f"{field_name}__gte": start,
        f"{field_name}__lt": start + timedelta(days=1),
    }


@schedule_job("0 4 * * *")
def populate_history_log(date: datetime = None):
    """
    Creates HistoryLog entry for a date (default yesterday) for each organization.
    """
    if date is None:
        date = timezone.now() - timedelta(days=1)

    for org in Organisation.objects.all():
        HistoryLog.objects.create(
            date=date,
            org=org,
            # Data fields
            accepted_invitation_count=MeetingInvite.objects.filter(
                used_by__organisation=org, **mk_daterange_filter("used_at", date)
            ).count(),
            action_count=LogEntry.objects.filter(
                actor__organisation=org, **mk_daterange_filter("timestamp", date)
            ).count(),
            login_count=LogEntry.objects.filter(
                actor__organisation=org,
                **mk_daterange_filter("timestamp", date),
                action=LogEntry.Action.UPDATE,
                content_type=ContentType.objects.get_for_model(User),
                changes__has_key="last_login",
            ).count(),
            connection_count=Connection.objects.filter(
                user__organisation=org, **mk_daterange_filter("last_action", date)
            ).count(),
            online_duration=Connection.objects.filter(
                user__organisation=org, **mk_daterange_filter("last_action", date)
            )
            .annotate(
                duration=models.ExpressionWrapper(
                    models.F("last_action") - models.F("online_at"),
                    output_field=models.DurationField(),
                )
            )
            .aggregate(total=models.Sum("duration"))["total"]
            or timedelta(0),
            speaker_count=org.users.annotate(
                spoken=models.Exists(
                    Speaker.objects.filter(
                        user=models.OuterRef("id"),
                        **mk_daterange_filter("started", date),
                    )
                )
            )
            .filter(spoken=True)
            .count(),
            spoken_duration=timedelta(
                seconds=Speaker.objects.filter(
                    user__organisation=org, **mk_daterange_filter("started", date)
                ).aggregate(secs=models.Sum("seconds"))["secs"]
                or 0
            ),
            user_online_count=org.users.annotate(
                conn=models.Exists(
                    Connection.objects.filter(
                        user=models.OuterRef("id"),
                        **mk_daterange_filter("last_action", date),
                    )
                )
            )
            .filter(conn=True)
            .count(),
            # FIXME fields below
            proposal_outcomes={},
            action_types={},
            content_types={},
        )
