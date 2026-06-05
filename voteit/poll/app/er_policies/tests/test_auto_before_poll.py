from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from voteit.active.components import ActiveUsersComponent
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll
from voteit.proposal.models import Proposal

User = get_user_model()


class AutoBeforePollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=AutoBeforePoll.name, state="ongoing"
        )
        cls.ai = cls.meeting.agenda_items.create()
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()

    def test_no_er_on_upcoming(self):
        self.poll.upcoming(force=True)
        self.assertIsNone(self.poll.electoral_register)

    def test_new_er_on_ongoing(self):
        self.poll.proposals.create(agenda_item=self.ai)
        self.poll.ongoing(force=True)
        self.assertIsInstance(self.poll.electoral_register, ElectoralRegister)
        self.assertEqual(
            {self.user1.pk, self.user2.pk},
            {int(k) for k in self.poll.electoral_register.voter_data.keys()},
        )

    def test_new_er_on_start_if_new_users(self):
        first_er = self.meeting.er_policy.create_er()
        user3 = User.objects.create(username="three")
        self.meeting.add_roles(user3, ROLE_POTENTIAL_VOTER)
        self.poll.proposals.create(agenda_item=self.ai)
        self.poll.ongoing(force=True)
        self.assertNotEqual(first_er, self.poll.electoral_register)
        self.assertEqual(
            {self.user1.pk, self.user2.pk, user3.pk},
            {int(k) for k in self.poll.electoral_register.voter_data.keys()},
        )

    def test_same_er_on_start_if_no_new_users(self):
        first_er = self.meeting.er_policy.create_er()
        prop = Proposal.objects.create(agenda_item=self.ai)
        self.poll.proposals.add(prop)
        self.poll.ongoing(force=True)
        self.assertEqual(first_er, self.poll.electoral_register)
        self.assertEqual(first_er, self.meeting.get_latest_er())

    def test_changed_er_ref_on_poll(self):
        first_er = self.meeting.er_policy.create_er()
        self.poll.electoral_register = first_er
        user3 = User.objects.create(username="three")
        self.meeting.add_roles(user3, ROLE_POTENTIAL_VOTER)
        self.poll.proposals.create(agenda_item=self.ai)
        self.poll.ongoing(force=True)
        self.assertNotEqual(first_er, self.poll.electoral_register)
        self.assertEqual(
            {self.user1.pk, self.user2.pk, user3.pk},
            {int(k) for k in self.poll.electoral_register.voter_data.keys()},
        )

    def test_er_updated_when_ongoing(self):
        self.poll.proposals.create(agenda_item=self.ai)
        first_er = self.poll.electoral_register
        user3 = User.objects.create(username="three")
        self.meeting.add_roles(user3, ROLE_POTENTIAL_VOTER)
        self.poll.ongoing(force=True)
        self.assertNotEqual(self.poll.electoral_register, first_er)

    def test_er_set_at_wrong_time(self):
        self.meeting.er_policy_name = None
        self.meeting.save()
        self.poll.proposals.create(agenda_item=self.ai)
        self.assertRaises(ValidationError, self.poll.ongoing, force=True)
        self.meeting.er_policy_name = AutoBeforePoll.name
        self.meeting.save()
        self.poll.meeting.refresh_from_db()
        self.poll.ongoing(force=True)

    def test_active_users_respected(self):
        self.meeting.components.create(
            component_name=ActiveUsersComponent.name, enabled=True
        )
        self.meeting.active_users.create(user=self.user1)
        self.poll.proposals.create(agenda_item=self.ai)
        self.poll.ongoing(force=True)
        self.assertEqual(
            {self.user1.pk},
            {int(k) for k in self.poll.electoral_register.voter_data.keys()},
        )
