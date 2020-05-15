from collections import Counter

from django.contrib.auth.models import User
from django.test import TestCase
from voteit.poll.exceptions import (
    ElectoralRegisterMissing,
    ElectoralRegisterEmpty,
    InvalidProposalCount,
    InvalidPollMethod,
)


class PollMethodTests(TestCase):
    @property
    def _cut(self):
        from voteit.poll.models import PollMethod

        return PollMethod

    def test_registration(self):
        from voteit.core.component import FactoryRegistry
        from voteit.poll.abcs import Vote

        poll_method = FactoryRegistry(self._cut)

        class _Vote(Vote):
            class Meta:
                app_label = "poll"

        @poll_method
        class HelloMethod(self._cut):
            Vote = _Vote
            title = "Hello"

            class Meta:
                app_label = "poll"

            def start_check(self):  # pragma: no coverage
                pass

        self.assertIn("hellomethod", poll_method)


class PollTests(TestCase):
    @property
    def Poll(self):
        from voteit.poll.models import Poll

        return Poll

    @property
    def ElectoralRegister(self):
        from voteit.poll.models import ElectoralRegister

        return ElectoralRegister

    @property
    def Proposal(self):
        from voteit.proposal.models import Proposal

        return Proposal

    def setUp(self):
        from voteit.poll.app.polls.simple import Simple

        self.method = Simple.objects.create()
        self.poll = self.Poll.objects.create(method=self.method)
        self.user = User.objects.create(username="a")

    def test_method(self):
        self.assertIsInstance(self.poll.method, self.method.__class__)

    def test_start_check_no_electoral_register(self):
        self.assertRaises(ElectoralRegisterMissing, self.poll.start_check)

    def test_start_check_electoral_register_empty(self):
        self.poll.electoral_register = self.ElectoralRegister.objects.create()
        self.assertRaises(ElectoralRegisterEmpty, self.poll.start_check)

    def test_start_check_no_proposals(self):
        self.poll.electoral_register = er = self.ElectoralRegister.objects.create()
        er.voters.add(self.user)
        self.assertRaises(InvalidProposalCount, self.poll.start_check)

    def test_start_check(self):
        self.poll.electoral_register = er = self.ElectoralRegister.objects.create()
        er.voters.add(self.user)
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.assertIsNone(self.poll.start_check())

    def test_opening_poll_empty_poll(self):
        self.poll.upcoming()
        self.assertRaises(
            ElectoralRegisterMissing,
            self.poll.ongoing,
        )

    def test_opening_poll(self):
        self.poll.upcoming()
        self.poll.electoral_register = er = self.ElectoralRegister.objects.create()
        er.voters.add(self.user)
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.assertIsNone(
            self.poll.ongoing()
        )
        self.assertEqual('ongoing', self.poll.state)

    def test_assigning_bad_poll_method(self):
        self.poll.method = self.ElectoralRegister.objects.create()
        self.assertRaises(InvalidPollMethod, self.poll.save)

    def test_votes_from_non_voters_removed_on_close(self):
        from voteit.poll.app.polls.simple import SimpleVote
        self.poll.electoral_register = er = self.ElectoralRegister.objects.create()
        self.poll.save()
        user2 = User.objects.create(username='2')
        er.voters.add(self.user, user2)
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = SimpleVote.objects.create(user=self.user, method=self.method, choice=1)
        vote2 = SimpleVote.objects.create(user=user2, method=self.method, choice=1)
        self.assertEqual(Counter({1: 2}), self.method.get_result())
        self.assertIn(vote1, self.method.get_votes())
        self.assertIn(vote2, self.method.get_votes())
        self.poll.electoral_register = er2 = self.ElectoralRegister.objects.create()
        er2.voters.add(self.user)
        self.poll.save()
        self.poll.close()
        self.assertIn(vote1, self.method.get_votes())
        self.assertNotIn(vote2, self.method.get_votes())
