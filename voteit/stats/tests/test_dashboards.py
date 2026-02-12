from datetime import timedelta

from django.test import RequestFactory
from django.test import TestCase
from django.utils import timezone

from voteit.core.models import User
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.organisation.models import Organisation
from voteit.poll.models import Poll
from voteit.stats.dashboards import DailyOrgVoteChart


class DashboardTests(TestCase):
    fixtures = ["meeting_test_fixture", "agenda_test_fixture", "full_ai_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.outsider = User.objects.create(username="outsider")
        cls.participant = User.objects.get(username="participant")
        cls.poll = Poll.objects.get()

    def test_daily_org_votes(self):
        yesterday = timezone.now() - timedelta(days=1)
        self.poll.votes.update(created=yesterday)
        other_org = Organisation.objects.create(title="Other")
        other_user = other_org.users.create(username="other_user")
        other_poll = (
            other_org.meetings.create(
                title="First meeting ever", er_policy_name="auto_always"
            )
            .agenda_items.create(title="First on agenda")
            .polls.create(title="Vote me!", method_name="simple")
        )
        other_poll.proposals.create(
            body="First proposal ever", agenda_item=other_poll.agenda_item
        )
        other_poll.meeting.add_roles(other_user, ROLE_POTENTIAL_VOTER)
        other_poll.ongoing()
        other_poll.save()
        other_poll.votes.create(user=other_user, created=yesterday)
        request = RequestFactory().get("/")
        chart = DailyOrgVoteChart(request=request)
        self.assertEqual(chart.top_orgs.count(), 2)
        self.assertEqual(chart.legend[0].title, "Testfixture organisation")
        self.assertEqual(chart.series[0][-1], 2)
        self.assertEqual(chart.legend[1].title, "Other")
        self.assertEqual(chart.series[1][-1], 1)
