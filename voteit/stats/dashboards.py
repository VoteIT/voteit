from datetime import timedelta

from auditlog.models import LogEntry
from controlcenter import Dashboard
from controlcenter import widgets
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import Q
from django.db.models import Subquery
from django.utils import timezone
from django.utils.functional import cached_property
from envelope.models import Connection
from sql_util.aggregates import SubqueryCount
from sql_util.aggregates import SubquerySum

from ..organisation.models import Organisation
from ..poll.models import Vote
from .models import HistoryLog

User = get_user_model()


def format_wo_seconds(duration: timedelta):
    return str(duration).rsplit(":", 1)[0]


class DailyChart(widgets.LineChart):
    days = 10

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
        for n in range(1, self.days + 1):
            yield today - timedelta(days=n)

    def labels(self):
        return list(self.iter_dates())


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
            .order_by("-sum")[:10]
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
            Vote.objects.filter(
                created__gte=self.start_time, created__lt=self.start_today
            )
            .values("created__date")
            .annotate(sum=Count("pk"))
            .order_by("created__date")
        )

    def series(self):
        lookup = {entry["created__date"]: entry["sum"] for entry in self.get_queryset()}
        return [[lookup.get(day, 0) for day in self.iter_dates()]]


class DailyOrgVoteChart(DailyChart):
    title = "Organisations, votes per day"

    @cached_property
    def top_orgs(self):
        return (
            Organisation.objects.annotate(
                vote_count=SubqueryCount(
                    "users__vote",
                    filter=Q(
                        created__gte=self.start_time, created__lt=self.start_today
                    ),
                ),
            )
            .exclude(vote_count=0)  # No need to show orgs with no votes
            .order_by("-vote_count")[:10]
        )

    def get_queryset(self):
        return (
            Vote.objects.filter(
                created__gte=self.start_time, created__lt=self.start_today
            )
            .values("created__date", "user__organisation")
            .annotate(count=Count("pk"))
            .order_by("created__date", "user__organisation")
        )

    def series(self):
        data = self.get_queryset()
        lookup = {
            org.id: {
                entry["created__date"]: entry["count"]
                for entry in data
                if entry["user__organisation"] == org.id
            }
            for org in self.top_orgs
        }
        return [
            [lookup[org.id].get(date, 0) for date in self.iter_dates()]
            for org in self.top_orgs
        ]

    def legend(self):
        return list(self.top_orgs)


class OnlineYesterdayChart(widgets.PieChart):
    """
    Skips organizations with less than one hou online time
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
        return [f"{o.title}: {format_wo_seconds(o.duration)}" for o in self.orgs]

    def series(self):
        return [o.duration.total_seconds() for o in self.orgs]


class OnlineUserChart(widgets.BarChart):
    action_time = timedelta(minutes=20)
    title = "Online users (last 20 min)"

    @property
    def recent_qs(self):
        return Connection.objects.filter(
            online=True,
            last_action__gt=timezone.now() - self.action_time,
        )

    @property
    def top_orgs(self):
        return (
            Organisation.objects.annotate(
                conns=SubqueryCount(
                    "users", distinct=True, filter=Q(connections__in=self.recent_qs)
                )
            )
            .exclude(conns=0)
            .order_by("-conns")
        )

    def labels(self):
        return ["All", *(o.title for o in self.top_orgs)]

    def series(self):
        return [
            [
                self.recent_qs.distinct("user").count(),
                *(o.conns for o in self.top_orgs),
            ]
        ]


class LatestStats(Dashboard):
    widgets = (
        OnlineUserChart,
        OnlineYesterdayChart,
        ActiveOrgs,
        ActiveOrgsOnline,
        DailyVoteChart,
        DailyOrgVoteChart,
        ActionsLast24,
    )
