from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.statemachines import PollStateMachine
from voteit.proposal.models import Proposal

User = get_user_model()


class PollSMTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.meeting.state = "ongoing"
        cls.meeting.save()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.poll: Poll = cls.ai.polls.create(method_name="simple")
        cls.prop = cls.poll.proposals.create(agenda_item=cls.ai)
        cls.voter = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting.add_roles(cls.voter, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.moderator, ROLE_POTENTIAL_VOTER)
        cls.er: ElectoralRegister = cls.meeting.er_policy.create_er()

    def setUp(self):
        self.poll.refresh_from_db()

    def _prop_state(self):
        return Proposal.objects.get(pk=self.prop.pk).state

    def test_initial_state(self):
        self.assertEqual(PollStateMachine.private.value, self.poll.state)

    def test_private_to_upcoming(self):
        self.poll.upcoming(force=True)
        self.assertEqual("upcoming", self.poll.state)
        self.assertEqual("voting", self._prop_state())

    def test_upcoming_to_private(self):
        self.poll.upcoming(force=True)
        self.poll.unpublish(force=True)
        self.assertEqual("private", self.poll.state)

    def test_private_to_ongoing(self):
        self.poll.ongoing(force=True)
        self.assertEqual("ongoing", self.poll.state)
        self.assertIsNotNone(self.poll.started)
        self.assertIsNotNone(self.poll.electoral_register)
        self.assertEqual("voting", self._prop_state())

    def test_ongoing_to_canceled(self):
        self.poll.ongoing(force=True)
        self.poll.cancel(force=True)
        self.assertEqual("canceled", self.poll.state)
        self.assertIsNotNone(self.poll.closed)
        self.assertEqual("published", self._prop_state())

    def test_close_with_votes_goes_to_finished(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter, vote="yes")
        self.poll.close(force=True)
        self.assertEqual("finished", self.poll.state)
        self.assertIsNotNone(self.poll.closed)
        self.assertIsNotNone(self.poll.result)

    def test_close_with_votes_withheld_goes_to_withheld(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter, vote="yes")
        self.poll.withheld_result = True
        self.poll.save()
        self.poll.close(force=True)
        self.assertEqual("withheld", self.poll.state)
        self.assertIsNotNone(self.poll.closed)
        self.assertIsNotNone(self.poll.result)

    def test_close_without_votes_goes_to_no_result(self):
        self.poll.ongoing(force=True)
        self.poll.close(force=True)
        self.assertEqual("no_result", self.poll.state)
        self.assertIsNotNone(self.poll.closed)

    def test_withheld_to_finished(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter, vote="yes")
        self.poll.withheld_result = True
        self.poll.save()
        self.poll.close(force=True)
        self.assertEqual("withheld", self.poll.state)
        # proposals still locked in voting while result is withheld
        self.assertEqual("voting", self._prop_state())
        self.poll.publish_result(force=True)
        self.assertEqual("finished", self.poll.state)
        self.assertFalse(self.poll.withheld_result)
        # voter said yes and is the only voter, so proposal is approved
        self.assertEqual("approved", self._prop_state())

    def test_finished_to_withheld(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter, vote="yes")
        self.poll.close(force=True)
        self.assertEqual("finished", self.poll.state)
        self.poll.withhold_result(force=True)
        self.assertEqual("withheld", self.poll.state)
        self.assertTrue(self.poll.withheld_result)
