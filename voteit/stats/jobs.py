from collections import Counter
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
    proposal_ct = ContentType.objects.get_by_natural_key("proposal", "proposal")
    user_ct = ContentType.objects.get_for_model(User)

    for org in Organisation.objects.all():
        org_logentries = LogEntry.objects.filter(
            actor__organisation=org, **mk_daterange_filter("timestamp", date)
        )
        HistoryLog.objects.create(
            date=date,
            org=org,
            # Data fields
            accepted_invitation_count=MeetingInvite.objects.filter(
                used_by__organisation=org, **mk_daterange_filter("used_at", date)
            ).count(),
            action_count=org_logentries.count(),
            # Unique users that logged in
            login_count=org_logentries.filter(
                action=LogEntry.Action.UPDATE,
                content_type=user_ct,
                changes__has_key="last_login",
            ).count(),
            # Total connections made (WebSocket)
            connection_count=Connection.objects.filter(
                user__organisation=org, **mk_daterange_filter("last_action", date)
            ).count(),
            # Estimated online time for all users
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
            # Last proposal outcome for all proposal with changed state
            proposal_outcomes=Counter(
                org_logentries.filter(
                    action=LogEntry.Action.UPDATE,
                    changes__has_key="state",
                    content_type=proposal_ct,
                )
                .order_by("object_id", "-timestamp")
                .distinct("object_id")
                .values_list("changes__state__1", flat=True)
            ),
            # Unique speakers
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
            # Unique users that made a connection
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
            action_types={},
            content_types={},
        )
