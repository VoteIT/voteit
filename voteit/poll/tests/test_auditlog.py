from auditlog.context import set_actor
from auditlog.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()


class AuditlogIntegrationTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.state = "ongoing"
        cls.meeting.save()
        cls.moderator = User.objects.get(username="moderator")
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()

    def test_create(self):
        with set_actor(self.moderator):
            poll = self.ai.polls.create(method_name="simple", meeting=self.meeting)
        entry = LogEntry.objects.get_for_object(poll).last()
        self.assertEqual(
            {
                "meeting": ["None", f"{self.meeting.pk}"],
                "agenda_item": ["None", f"{self.ai.pk}"],
                "method_name": ["None", "simple"],
                "p_ord": ["None", "c"],
                "state": ["None", "private"],
                "title": ["None", ""],
                "withheld_result": ["None", "False"],
            },
            entry.changes_dict,
        )

    def test_create_vote(self):
        with set_actor(self.moderator):
            self.meeting.add_roles(self.moderator, ROLE_POTENTIAL_VOTER)
            poll = self.ai.polls.create(method_name="simple")
            poll.proposals.add(self.prop)
            poll.upcoming(force=True)
            poll.ongoing(force=True)
            poll.save()
            vote = poll.votes.create(vote_data="", user=self.moderator)
        entry = LogEntry.objects.get_for_object(vote).last()
        self.assertDictEqual(
            {
                "poll": ["None", f"{poll.pk}"],
                "user": ["None", f"{self.moderator.pk}"],
                "abstain": ["*", "*"],
                "vote_data": ["*", "*"],
            },
            entry.changes_dict,
        )
