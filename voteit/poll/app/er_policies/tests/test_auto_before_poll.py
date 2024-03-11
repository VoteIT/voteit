from django.contrib.auth import get_user_model
from django.test import TestCase
from django_fsm import TransitionNotAllowed

from voteit.active.components import ActiveUsersComponent
from voteit.core.workflows import EnabledWf
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll

User = get_user_model()


class AutoBeforePollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            er_policy_name=AutoBeforePoll.name
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

    def test_new_er_on_upcoming(self):
        self.poll.upcoming()
        self.assertIsInstance(self.poll.electoral_register, ElectoralRegister)
        # Why self.assertQuerysetEqual() create object strings of some kind?
        self.assertEqual(
            {self.user1, self.user2}, set(self.poll.electoral_register.voters.all())
        )

    def test_new_er_on_start_if_new_users(self):
        first_er = self.meeting.er_policy.create_er()
        user3 = User.objects.create(username="three")
        self.meeting.add_roles(user3, ROLE_POTENTIAL_VOTER)
        self.poll.upcoming()
        self.assertNotEqual(first_er, self.poll.electoral_register)
        self.assertEqual(
            {self.user1, self.user2, user3},
            set(self.poll.electoral_register.voters.all()),
        )

    def test_same_er_on_start_if_no_new_users(self):
        from voteit.proposal.models import Proposal

        first_er = self.meeting.er_policy.create_er()
        self.poll.upcoming()
        prop = Proposal.objects.create(agenda_item=self.ai)
        self.poll.proposals.add(prop)
        self.poll.ongoing()
        self.assertEqual(first_er, self.poll.electoral_register)
        self.assertEqual(first_er, self.meeting.get_latest_er())

    def test_changed_er_ref_on_poll(self):
        first_er = self.meeting.er_policy.create_er()
        self.poll.electoral_register = first_er
        user3 = User.objects.create(username="three")
        self.meeting.add_roles(user3, ROLE_POTENTIAL_VOTER)
        self.poll.upcoming()
        self.assertNotEqual(first_er, self.poll.electoral_register)
        self.assertEqual(
            {self.user1, self.user2, user3},
            set(self.poll.electoral_register.voters.all()),
        )

    def test_initial_er_set_when_upcoming(self):
        self.poll.upcoming()
        self.poll.proposals.create(agenda_item=self.ai)
        first_er = self.poll.electoral_register
        user3 = User.objects.create(username="three")
        self.meeting.add_roles(user3, ROLE_POTENTIAL_VOTER)
        self.poll.ongoing()
        self.assertEqual(
            self.poll.initial_electoral_register, self.poll.electoral_register
        )
        self.assertNotEqual(self.poll.initial_electoral_register, first_er)

    def test_er_set_at_wrong_time(self):
        self.meeting.er_policy_name = None
        self.meeting.save()
        self.poll.upcoming()
        self.poll.proposals.create(agenda_item=self.ai)
        self.assertRaises(TransitionNotAllowed, self.poll.ongoing)
        self.meeting.er_policy_name = AutoBeforePoll.name
        self.meeting.save()
        # We still need the meeting to have a policy
        self.assertRaises(TransitionNotAllowed, self.poll.ongoing)
        self.meeting.er_policy.create_er()
        self.poll.save()
        self.poll.meeting.refresh_from_db()
        self.poll.ongoing()

    def test_active_users_respected(self):
        self.meeting.components.create(
            component_name=ActiveUsersComponent.name, state=EnabledWf.ON
        )
        self.meeting.active_users.create(user=self.user1)
        self.poll.upcoming()
        self.assertEqual(
            {self.user1},
            set(self.poll.electoral_register.voters.all()),
        )
