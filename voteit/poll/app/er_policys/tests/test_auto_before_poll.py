from django.contrib.auth.models import User
from django.test import TestCase


class AutoBeforePollTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.meeting.models import Meeting
        from voteit.poll.app.polls.simple import Simple

        self.meeting = Meeting.objects.create()
        self.meeting.er_policy = self.ABF.objects.create()
        self.user1 = User.objects.create(username="one")
        self.user2 = User.objects.create(username="two")
        self.meeting.potential_voters.add(self.user1, self.user2)
        self.poll = Poll.objects.create(meeting=self.meeting)
        method = Simple.objects.create()
        method.poll = self.poll

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
        self.meeting.potential_voters.add(user3)
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
        self.meeting.potential_voters.add(user3)
        self.poll.upcoming()
        self.assertNotEqual(first_er, self.poll.electoral_register)
        self.assertEqual(
            {self.user1, self.user2, user3},
            set(self.poll.electoral_register.voters.all()),
        )
