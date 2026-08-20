from datetime import timedelta

from auditlog.context import set_actor
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.messaging.models import ABNORMAL_CLOSURE
from voteit.messaging.models import NORMAL_CLOSURE
from voteit.messaging.models import Connection
from voteit.organisation.models import Organisation
from voteit.stats.dashboards import CloseCodeChart
from voteit.stats.dashboards import ConnectionsStartedLast24
from voteit.stats.dashboards import DailyOrgVoteChart
from voteit.stats.dashboards import SessionLengthChart
from voteit.stats.jobs import populate_history_log


class DashboardTests(TestCase):
    def test_daily_org_votes(self):
        for n, name in enumerate(("One", "Other"), 1):
            org = Organisation.objects.create(title=name)
            poll = (
                org.meetings.create(
                    title="First meeting ever",
                    er_policy_name="auto_always",
                    state="ongoing",
                )
                .agenda_items.create(title="First on agenda", state="ongoing")
                .polls.create(title="Vote me!", method_name="simple")
            )
            poll.proposals.create(
                body="First proposal ever", agenda_item=poll.agenda_item
            )
            users = [org.users.create(username=f"{name}-user-{n}") for n in range(n)]
            for user in users:
                poll.meeting.add_roles(user, ROLE_POTENTIAL_VOTER)
            poll.ongoing(force=True)
            poll.save()
            for user in users:
                with set_actor(user):
                    poll.votes.create(user=user)
        # Logentries needs to be set to yesterday
        LogEntry.objects.update(timestamp=timezone.now() - timedelta(days=1))
        populate_history_log()
        request = RequestFactory().get("/")
        chart = DailyOrgVoteChart(request=request)
        self.assertEqual(chart.top_orgs.count(), 2)
        self.assertEqual(chart.legend[0].title, "One")
        self.assertEqual(chart.series[0][-1], 1)
        self.assertEqual(chart.legend[1].title, "Other")
        self.assertEqual(chart.series[1][-1], 2)


class SocketWidgetTests(TestCase):
    @staticmethod
    def _mk(*, ago_minutes, duration, code=None):
        last_action = timezone.now() - timedelta(minutes=ago_minutes)
        return Connection.objects.create(
            user_id=1,
            channel_name=f"c{ago_minutes}-{duration}",
            connected_at=last_action - duration,
            last_action=last_action,
            code=code,
        )

    @staticmethod
    def _chart(cls):
        return cls(request=RequestFactory().get("/"))

    def test_connections_started_labels_and_series_align(self):
        chart = self._chart(ConnectionsStartedLast24)
        self.assertEqual(24, len(chart.labels))
        self.assertEqual(24, len(chart.series[0]))

    def test_connections_started_counts_the_current_hour_out(self):
        # Two opened over an hour ago, one opened right now. Zero duration on
        # the last one keeps it inside the running hour however close to the
        # hour boundary the suite happens to run.
        self._mk(ago_minutes=90, duration=timedelta(minutes=1))
        self._mk(ago_minutes=95, duration=timedelta(minutes=1))
        self._mk(ago_minutes=0, duration=timedelta())
        chart = self._chart(ConnectionsStartedLast24)
        # The running hour is incomplete and excluded, as in ActionsLast24.
        self.assertEqual(2, sum(chart.series[0]))

    def test_session_length_buckets(self):
        self._mk(ago_minutes=5, duration=timedelta(seconds=30), code=NORMAL_CLOSURE)
        self._mk(ago_minutes=5, duration=timedelta(minutes=3), code=NORMAL_CLOSURE)
        self._mk(ago_minutes=5, duration=timedelta(hours=6), code=ABNORMAL_CLOSURE)
        # Still open, so not a finished session.
        self._mk(ago_minutes=5, duration=timedelta(minutes=3))
        chart = self._chart(SessionLengthChart)
        counts = dict(zip(chart.labels, chart.series[0]))
        self.assertEqual(
            {"< 1 min": 1, "1-5 min": 1, "> 4 h": 1},
            {label: count for label, count in counts.items() if count},
        )

    def test_session_length_ignores_older_than_24h(self):
        self._mk(
            ago_minutes=60 * 30, duration=timedelta(minutes=3), code=NORMAL_CLOSURE
        )
        chart = self._chart(SessionLengthChart)
        self.assertEqual(0, sum(chart.series[0]))

    def test_dashboard_page_renders(self):
        """The Chartist templates are only exercised by the real view."""
        self._mk(ago_minutes=5, duration=timedelta(minutes=1), code=NORMAL_CLOSURE)
        self._mk(ago_minutes=5, duration=timedelta(minutes=1))
        admin_user = get_user_model().objects.create_superuser(username="admin")
        self.client.force_login(admin_user)
        response = self.client.get(reverse("controlcenter:dashboard", args=["sockets"]))
        self.assertEqual(200, response.status_code)
        self.assertIn("Close codes last 24h", response.content.decode())

    def test_close_codes(self):
        self._mk(ago_minutes=5, duration=timedelta(minutes=1), code=NORMAL_CLOSURE)
        self._mk(ago_minutes=6, duration=timedelta(minutes=1), code=NORMAL_CLOSURE)
        self._mk(ago_minutes=7, duration=timedelta(minutes=1), code=ABNORMAL_CLOSURE)
        self._mk(ago_minutes=8, duration=timedelta(minutes=1))
        chart = self._chart(CloseCodeChart)
        self.assertEqual(
            {
                f"{NORMAL_CLOSURE} normal": 2,
                f"{ABNORMAL_CLOSURE} abnormal": 1,
                "still open": 1,
            },
            dict(zip(chart.labels, chart.series[0])),
        )
