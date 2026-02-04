import datetime

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from envelope.models import Connection

from voteit.core.decorators import schedule_job
from voteit.organisation.models import Organisation
from voteit.stats.models import HistoryLog

User = get_user_model()


@schedule_job("0 4 * * *")
def populate_history_log(date: datetime.datetime = None):
    """
    Creates HistoryLog entry for a date (default yesterday) for each organization.
    """
    if date is None:
        date = timezone.now() - datetime.timedelta(days=1)

    datetime_gte = date.replace(hour=0, minute=0, second=0, microsecond=0)
    datetime_lt = datetime_gte + datetime.timedelta(days=1)
    connection_filter = {
        "last_action__gte": datetime_gte,
        "last_action__lt": datetime_lt,
    }

    for org in Organisation.objects.all():
        HistoryLog.objects.create(
            date=date,
            org=org,
            user_online_count=org.users.annotate(
                conn=models.Exists(
                    Connection.objects.filter(
                        user=models.OuterRef("id"), **connection_filter
                    )
                )
            )
            .filter(conn=True)
            .count(),
            connection_count=Connection.objects.filter(
                user__organisation=org, **connection_filter
            ).count(),
            action_count=LogEntry.objects.filter(
                actor__organisation=org,
                timestamp__gte=datetime_gte,
                timestamp__lt=datetime_lt,
            ).count(),
            # FIXME fields below
            action_types={},
            content_types={},
            online_duration=datetime.timedelta(hours=1),
            spoken_duration=datetime.timedelta(hours=1),
            speaker_count=1,
            accepted_invitation_count=0,
            login_count=0,
            proposal_outcomes={},
        )
