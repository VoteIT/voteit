from collections import Counter
from collections.abc import Iterator
from datetime import datetime
from datetime import timedelta

from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.functions import Concat
from django.utils import timezone
from envelope.models import Connection

from voteit.core.decorators import schedule_job
from voteit.stats.models import HistoryLog
from voteit.stats.registry import history_content_type_registry

User = get_user_model()


def mk_daterange_filter(field_name: str, start: datetime = None) -> dict:
    """
    Creates a date range filter for named DateTimeField. Faster than filtering on <field_name>__date.

    >>> mk_daterange_filter("created", datetime(2020, 1, 1, 12, 34))
    {'created__gte': datetime.datetime(2020, 1, 1, 0, 0), 'created__lt': datetime.datetime(2020, 1, 2, 0, 0)}
    """
    if start is None:
        start = timezone.now()
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        f"{field_name}__gte": start,
        f"{field_name}__lt": start + timedelta(days=1),
    }


def translate_action_keys(counter: Counter[str]) -> Iterator[tuple[str, int]]:
    """
    Translates a Counter of strings like agenda.agendaitem:0 -> agenda.agendaitem:create.
    Use to create a dict.

    >>> dict(translate_action_keys(Counter(["agenda.agendaitem:0", "agenda.agendaitem:1", "agenda.agendaitem:1"])))
    {'agenda.agendaitem:create': 1, 'agenda.agendaitem:update': 2}
    """
    lookup = dict(LogEntry.Action.choices)
    for key, count in counter.items():
        model, action = key.split(":")
        yield f"{model}:{lookup[int(action)]}", count


@schedule_job("0 4 * * *")
def populate_history_log(
    date: datetime = None,
):
    """
    Creates HistoryLog entry for a date (default yesterday) for each organization.
    """
    # Circular import funzies
    from voteit.invites.models import MeetingInvite
    from voteit.organisation.models import Organisation
    from voteit.proposal.statemachines import ProposalStateMachine
    from voteit.speaker.models import Speaker

    if date is None:
        date = timezone.now() - timedelta(days=1)
    proposal_ct = ContentType.objects.get_by_natural_key("proposal", "proposal")
    user_ct = ContentType.objects.get_for_model(User)

    logentry_exists = LogEntry.objects.filter(
        actor__organisation_id=models.OuterRef("pk"),
        **mk_daterange_filter("timestamp", date),
    )

    connection_exists = Connection.objects.filter(
        user__organisation_id=models.OuterRef("pk"),
        **mk_daterange_filter("online_at", date),
    )

    # HistoryLog already exists
    history_exists = HistoryLog.objects.filter(
        org_id=models.OuterRef("pk"),
        date=date,
    )

    for org in Organisation.objects.filter(
        (models.Exists(logentry_exists) | models.Exists(connection_exists))
        & ~models.Exists(history_exists)
    ):
        org_logentries = LogEntry.objects.filter(
            actor__organisation=org, **mk_daterange_filter("timestamp", date)
        )

        # Last proposal outcome for all proposal with changed state
        proposal_outcome_counter = Counter(
            org_logentries.filter(
                action=LogEntry.Action.UPDATE,
                changes__has_key="state",
                content_type=proposal_ct,
            )
            .order_by("object_id", "-timestamp")
            .distinct("object_id")
            .values_list("changes__state__1", flat=True)
        )
        # Published not an outcome
        proposal_outcome_counter.pop(ProposalStateMachine.published.value, None)

        HistoryLog.objects.create(
            date=date,
            org=org,
            # Data fields
            accepted_invitation_count=MeetingInvite.objects.filter(
                used_by__organisation=org, **mk_daterange_filter("used_at", date)
            ).count(),
            action_count=org_logentries.count(),
            # Different types of actions from auditlog
            action_types=dict(
                translate_action_keys(
                    Counter(
                        org_logentries.annotate(
                            key=Concat(
                                "content_type__app_label",
                                models.Value("."),
                                "content_type__model",
                                models.Value(":"),
                                "action",
                                output_field=models.CharField(),
                            )
                        ).values_list("key", flat=True)
                    )
                )
            ),
            # Total connections made (WebSocket)
            connection_count=Connection.objects.filter(
                user__organisation=org, **mk_daterange_filter("last_action", date)
            ).count(),
            # Count of different kinds of content types
            content_types={
                cta.label: cta.get_organisation_count(org)
                for cta in history_content_type_registry
            },
            # Unique users that logged in
            login_count=org_logentries.filter(
                action=LogEntry.Action.UPDATE,
                content_type=user_ct,
                changes__has_key="last_login",
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
            proposal_outcomes=proposal_outcome_counter,
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
                        **mk_daterange_filter("online_at", date),
                    )
                )
            )
            .filter(conn=True)
            .count(),
        )
