from django.contrib.auth.models import User
from django.test import TestCase
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER


class AutoBeforePollTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

        self.meeting = Meeting.objects.create(er_policy_name=self.ABF.name)
        self.user1 = User.objects.create(username="one")
        self.user2 = User.objects.create(username="two")
        self.meeting.add_roles(self.user1, ROLE_POTENTIAL_VOTER)
        self.meeting.add_roles(self.user2, ROLE_POTENTIAL_VOTER)
        self.poll = Poll.objects.create(meeting=self.meeting, method_name="simple")

    @property
    def ABF(self):
        from voteit.poll.app.er_policys import AutoBeforePoll

        return AutoBeforePoll

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
