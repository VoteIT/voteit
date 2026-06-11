from datetime import timedelta

from auditlog.context import set_actor
from auditlog.models import LogEntry
from django.test import RequestFactory
from django.test import TestCase
from django.utils import timezone

from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.organisation.models import Organisation
from voteit.stats.dashboards import DailyOrgVoteChart
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
