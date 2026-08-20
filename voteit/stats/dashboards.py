from datetime import timedelta

from auditlog.models import LogEntry
from controlcenter import Dashboard
from controlcenter import widgets
from django.contrib.auth import get_user_model
from django.db.models import Case
from django.db.models import CharField
from django.db.models import Count
from django.db.models import IntegerField
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When
from django.db.models.fields.json import KeyTransform
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.functional import cached_property
from voteit.messaging.models import GOING_AWAY
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import Connection
from sql_util.aggregates import SubquerySum

from ..organisation.models import Organisation
from .models import HistoryLog

User = get_user_model()


class DailyChart(widgets.LineChart):
    days = 10

    class Chartist:
        options = {
            "reverseData": False,
            "onlyInteger": True,
        }

    @property
    def start_date(self):
        return timezone.now().date() - timedelta(days=self.days)

    @property
    def start_time(self):
        """00:00:00 at start of first day"""
        return self.start_today - timedelta(days=self.days)

    @property
    def start_today(self):
        """00:00:00 at start of current day"""
        return timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def iter_dates(self):
        today = timezone.now().date()
        for n in reversed(range(1, self.days + 1)):
            yield today - timedelta(days=n)

    def labels(self):
        return [d.strftime("%d %b") for d in self.iter_dates()]


class ActiveOrgs[T](DailyChart):
    default_value: T = 0
    field = "action_count"
    title = "Organisation activity (logged actions)"

    @staticmethod
    def convert_value(value: T) -> int | float:
        # Override to support timedelta
        return value

    @property
    def top_orgs(self):
        return (
            Organisation.objects.annotate(
                sum=SubquerySum(
                    f"historylog__{self.field}",
                    filter=Q(date__gte=self.start_date),
                )
            )
            .exclude(sum=self.default_value)  # No need to show these
            .order_by("-sum")[:5]
        )

    def get_queryset(self):
        return HistoryLog.objects.filter(
            org__in=self.top_orgs, date__gte=self.start_date
        ).values("date", "org", self.field)

    def series(self):
        data = self.get_queryset()
        lookup = {
            org: {
                entry["date"]: entry[self.field]
                for entry in data
                if entry["org"] == org.id
            }
            for org in self.top_orgs
        }
        return [
            [
                self.convert_value(lookup[org].get(date, self.default_value))
                for date in self.iter_dates()
            ]
            for org in self.top_orgs
        ]

    def legend(self):
        return list(self.top_orgs)


class ActiveOrgsOnline(ActiveOrgs):
    default_value = timedelta()
    field = "online_duration"
    title = "Organisation activity (hours online)"

    @staticmethod
    def convert_value(value: timedelta):
        return round(value.total_seconds() / 3600, 1)


class ActionsLast24(widgets.LineChart):
    title = "Actions last 24 hours"

    class Chartist:
        options = {
            "onlyInteger": True,
        }

    @property
    def start_time(self):
        return self.start_this_hour - timedelta(hours=24)

    @property
    def start_this_hour(self):
        return timezone.now().replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def iter_hours():
        this_hour = timezone.now().hour
        for n in range(24):
            yield (this_hour - n) % 24

    def get_queryset(self):
        return (
            LogEntry.objects.filter(
                timestamp__gte=self.start_time, timestamp__lt=self.start_this_hour
            )
            .values("timestamp__hour")
            .annotate(sum=Count("pk"))
            .order_by("timestamp__hour")
        )

    def labels(self):
        return [f"{h:02d}" for h in self.iter_hours()]

    def series(self):
        lookup = {
            entry["timestamp__hour"]: entry["sum"] for entry in self.get_queryset()
        }
        return [[lookup.get(hour, 0) for hour in self.iter_hours()]]


class DailyVoteChart(DailyChart):
    title = "Total votes per day"

    def get_queryset(self):
        return (
            HistoryLog.objects.filter(date__gte=self.start_date)
            .values("date")
            .annotate(
                sum=Sum(
                    Cast(
                        KeyTransform("poll.vote:create", "action_types"),
                        output_field=IntegerField(),
                    )
                )
            )
            .order_by("date")
        )

    def series(self):
        lookup = {entry["date"]: entry["sum"] or 0 for entry in self.get_queryset()}
        return [[lookup.get(day, 0) for day in self.iter_dates()]]


class DailyOrgVoteChart(DailyChart):
    title = "Organisations, votes per day"

    vote_create_field = Cast(
        KeyTransform("poll.vote:create", "action_types"),
        output_field=IntegerField(),
    )

    @cached_property
    def top_orgs(self):
        # Note: There must be a better way, but this should be fast enough
        # First get org ids for the organisations with the most votes during this period
        top_org_ids = (
            HistoryLog.objects.filter(date__gte=self.start_date)
            .values("org")
            .annotate(vote_count=Sum(self.vote_create_field))
            .exclude(vote_count=0)
            .order_by("-vote_count")[:5]
            .values_list("org", flat=True)
        )
        # Return the actual Organisation objects for these orgs
        return Organisation.objects.filter(id__in=top_org_ids)

    def get_queryset(self):
        return (
            HistoryLog.objects.filter(date__gte=self.start_date, org__in=self.top_orgs)
            .annotate(vote_count=Sum(self.vote_create_field))
            .order_by()
        )

    def series(self):
        data = self.get_queryset()
        lookup = {
            org.id: {
                entry.date: entry.vote_count or 0
                for entry in data
                if entry.org_id == org.id
            }
            for org in self.top_orgs
        }
        return [
            [lookup[org.id].get(date, 0) for date in self.iter_dates()]
            for org in self.top_orgs
        ]

    def legend(self):
        return list(self.top_orgs)


class OnlineYesterdayChart(widgets.BarChart):
    """
    Skips organizations with less than one hour online time
    """

    title = "Online time yesterday (>1h)"

    @property
    def yesterday(self):
        return timezone.now().date() - timedelta(days=1)

    @property
    def orgs(self):
        return (
            Organisation.objects.annotate(
                duration=Subquery(
                    HistoryLog.objects.filter(
                        org=OuterRef("pk"), date=self.yesterday
                    ).values("online_duration")
                )
            )
            .exclude(duration__lt=timedelta(hours=1))
            .order_by("title")
        )

    def labels(self):
        return [o.title for o in self.orgs]

    def series(self):
        return [[o.duration.total_seconds() / 3600 for o in self.orgs]]


class OnlineUserChart(widgets.BarChart):
    action_time = timedelta(minutes=20)
    title = "Online users (last 20 min)"

    class Chartist:
        options = {
            "onlyInteger": True,
        }

    @cached_property
    def top_orgs(self):
        return (
            Organisation.objects.filter(
                users__pk__in=Connection.objects.online(self.action_time).user_ids()
            )
            .annotate(conns=Count("users", distinct=True))
            .order_by("-conns")
        )

    def labels(self):
        return ["All", *(o.title for o in self.top_orgs)]

    def series(self):
        return [
            [
                Connection.objects.online(self.action_time)
                .values("user_id")
                .distinct()
                .count(),
                *(o.conns for o in self.top_orgs),
            ]
        ]


class HourlyChart(widgets.LineChart):
    """Counts per hour over the last 24, bucketed on an hour lookup.

    Same shape as ActionsLast24 -- the codebase uses ``__hour`` rather than
    TruncHour throughout.
    """

    field = "timestamp"

    class Chartist:
        options = {
            "onlyInteger": True,
        }

    @property
    def start_this_hour(self):
        return timezone.now().replace(minute=0, second=0, microsecond=0)

    @property
    def start_time(self):
        return self.start_this_hour - timedelta(hours=24)

    @staticmethod
    def iter_hours():
        this_hour = timezone.now().hour
        for n in range(24):
            yield (this_hour - n) % 24

    def labels(self):
        return [f"{h:02d}" for h in self.iter_hours()]

    def series(self):
        lookup = {
            entry[f"{self.field}__hour"]: entry["sum"] for entry in self.get_queryset()
        }
        return [[lookup.get(hour, 0) for hour in self.iter_hours()]]


class ConnectionsStartedLast24(HourlyChart):
    title = "Websocket connections opened last 24 hours"
    field = "connected_at"

    def get_queryset(self):
        return (
            Connection.objects.filter(
                connected_at__gte=self.start_time, connected_at__lt=self.start_this_hour
            )
            .order_by()
            .values("connected_at__hour")
            .annotate(sum=Count("pk"))
        )


class ClosedLast24Mixin:
    """Connections that reported a close code during the last 24 hours."""

    @property
    def start_time(self):
        return timezone.now() - timedelta(hours=24)

    def closed_qs(self):
        return Connection.objects.filter(
            code__isnull=False, last_action__gte=self.start_time
        )


class SessionLengthChart(ClosedLast24Mixin, widgets.BarChart):
    """How long finished sessions lasted.

    Only as accurate as last_action, which is throttled to one write per
    VOTEIT_CONNECTION_UPDATE_INTERVAL -- so treat the shortest bucket as
    "a minute or less" rather than a precise figure.
    """

    title = "Session length, closed last 24h"

    # Ordered shortest first; the last entry is the catch-all.
    buckets = (
        ("< 1 min", timedelta(minutes=1)),
        ("1-5 min", timedelta(minutes=5)),
        ("5-15 min", timedelta(minutes=15)),
        ("15-60 min", timedelta(hours=1)),
        ("1-4 h", timedelta(hours=4)),
        ("> 4 h", None),
    )

    class Chartist:
        options = {
            "onlyInteger": True,
        }

    def bucket_case(self):
        return Case(
            *(
                When(duration__lt=upper, then=Value(label))
                for label, upper in self.buckets
                if upper is not None
            ),
            default=Value(self.buckets[-1][0]),
            output_field=CharField(),
        )

    def get_queryset(self):
        return (
            self.closed_qs()
            .with_duration()
            .annotate(bucket=self.bucket_case())
            # order_by() clears Meta.ordering, which would otherwise join
            # last_action into the GROUP BY and give one row per connection.
            .order_by()
            .values_list("bucket")
            .annotate(sum=Count("pk"))
        )

    def labels(self):
        return [label for label, _ in self.buckets]

    def series(self):
        lookup = dict(self.get_queryset())
        return [[lookup.get(label, 0) for label, _ in self.buckets]]


class CloseCodeChart(ClosedLast24Mixin, widgets.BarChart):
    """Which close codes sockets reported, plus how many never reported one.

    A large "still open" bar next to a small live-user count means dangling
    rows are accumulating -- see close_stale_connections.
    """

    title = "Close codes last 24h"

    code_labels = {
        NORMAL_CLOSURE: f"{NORMAL_CLOSURE} normal",
        GOING_AWAY: f"{GOING_AWAY} going away",
        ABNORMAL_CLOSURE: f"{ABNORMAL_CLOSURE} abnormal",
    }

    class Chartist:
        options = {
            "onlyInteger": True,
        }

    @cached_property
    def rows(self):
        counts = list(
            self.closed_qs()
            .order_by()
            .values_list("code")
            .annotate(sum=Count("pk"))
            .order_by("-sum")
        )
        still_open = (
            Connection.objects.open().filter(connected_at__gte=self.start_time).count()
        )
        if still_open:
            counts.append((None, still_open))
        return counts

    def labels(self):
        return [
            self.code_labels.get(code, "still open" if code is None else str(code))
            for code, _ in self.rows
        ]

    def series(self):
        return [[count for _, count in self.rows]]


class LatestStats(Dashboard):
    title = "Recent"
    widgets = (
        ActiveOrgs,
        ActiveOrgsOnline,
        DailyVoteChart,
        DailyOrgVoteChart,
        OnlineYesterdayChart,
    )


class NowStats(Dashboard):
    title = "Now"
    widgets = (
        OnlineUserChart,
        ActionsLast24,
    )


class SocketStats(Dashboard):
    title = "Sockets"
    widgets = (
        OnlineUserChart,
        ConnectionsStartedLast24,
        SessionLengthChart,
        CloseCodeChart,
    )
