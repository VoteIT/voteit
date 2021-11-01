from django.contrib.auth import get_user_model
from django.test import TestCase
from django_fsm import TransitionNotAllowed
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()


class AutoBeforePollTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
        from voteit.poll.app.er_policys import AutoBeforePoll

        cls.ABF = AutoBeforePoll

        cls.meeting: Meeting = Meeting.objects.create(er_policy_name=cls.ABF.name)
        cls.user1 = User.objects.create(username="one")
        cls.user2 = User.objects.create(username="two")
        cls.meeting.add_roles(cls.user1, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.user2, ROLE_POTENTIAL_VOTER)
        cls.poll = Poll.objects.create(meeting=cls.meeting, method_name="simple")

    def setUp(self):
        self.meeting.refresh_from_db()
        self.poll.refresh_from_db()

    @property
    def ElectoralRegister(self):
        from voteit.poll.models import ElectoralRegister

        return ElectoralRegister

    def test_new_er_on_upcoming(self):
        self.poll.upcoming()
        self.assertIsInstance(self.poll.electoral_register, self.ElectoralRegister)
        # Why self.assertQuerysetEqual() create object strings of some kind?
        self.assertEqual(
            {self.user1, self.user2}, set(self.poll.electoral_register.voters.all())
        )

    def test_new_er_on_start_if_new_users(self):
        first_er = self.meeting.er_policy.create_er(self.meeting)
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

        first_er = self.meeting.er_policy.create_er(self.meeting)
        self.poll.upcoming()
        prop = Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.ongoing()
        self.assertEqual(first_er, self.poll.electoral_register)
        self.assertEqual(first_er, self.meeting.get_latest_er())

    def test_changed_er_ref_on_poll(self):
        first_er = self.meeting.er_policy.create_er(self.meeting)
        self.poll.electoral_register = first_er
        user3 = User.objects.create(username="three")
        self.meeting.add_roles(user3, "potential_voter")
        self.poll.upcoming()
        self.assertNotEqual(first_er, self.poll.electoral_register)
        self.assertEqual(
            {self.user1, self.user2, user3},
            set(self.poll.electoral_register.voters.all()),
        )

    def test_initial_er_set_when_upcoming(self):
        self.poll.upcoming()
        self.poll.proposals.create()
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
        self.poll.proposals.create()
        self.assertRaises(TransitionNotAllowed, self.poll.ongoing)
        self.meeting.er_policy_name = self.ABF.name
        self.meeting.save()
        # FIX cache
        self.meeting.er_policy = self.meeting._er_policy()
        # We still need the meeting to have a policy
        self.assertRaises(TransitionNotAllowed, self.poll.ongoing)
        self.meeting.er_policy.create_er()
        self.poll.save()
        self.poll.meeting.refresh_from_db()
        self.poll.ongoing()
