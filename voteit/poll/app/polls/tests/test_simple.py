from collections import Counter

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from voteit.poll.exceptions import NotAllowedToVote
from voteit.poll.exceptions import InvalidProposalCount


class SimpleTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(electoral_register=self.er)

    @property
    def Simple(self):
        from voteit.poll.app.polls.simple import Simple

        return Simple

    def test_generic_relation_from_poll(self):
        method = self.Simple.objects.create()
        self.poll.method = method
        self.assertEqual(self.poll.method, method)
        self.assertIsInstance(self.poll.method, method.__class__)

    def test_generic_relation_from_method(self):
        method = self.Simple.objects.create()
        method.poll = self.poll
        self.assertEqual(method.poll, self.poll)
        self.assertIsInstance(method.poll, self.poll.__class__)

    def test_start_check(self):
        from voteit.proposal.models import Proposal
        method = self.Simple.objects.create()
        method.poll = self.poll
        self.assertRaises(InvalidProposalCount, method.start_check)
        p1 = Proposal.objects.create()
        self.poll.proposals.add(p1)
        self.assertIsNone(method.start_check())
        p2 = Proposal.objects.create()
        self.poll.proposals.add(p2)
        self.assertRaises(InvalidProposalCount, method.start_check)

    def test_result(self):
        method = self.Simple.objects.create()
        method.poll = self.poll
        ua = User.objects.create(username="a")
        ub = User.objects.create(username="b")
        uc = User.objects.create(username="c")
        self.er.voters.set([ua, ub, uc])
        method.create_vote(choice=1, user=ua)
        method.create_vote(choice=1, user=ub)
        method.create_vote(choice=2, user=uc)
        self.assertEqual(Counter({1: 2, 2: 1}), method.get_result())


class SimpleVoteTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll, ElectoralRegister
        from voteit.poll.app.polls.simple import Simple

        self.user = User.objects.create(username="a")
        self.er = ElectoralRegister.objects.create()
        self.er.voters.add(self.user)
        self.poll = Poll.objects.create(electoral_register=self.er)
        self.method = Simple.objects.create()
        self.method.poll = self.poll

    @property
    def _cut(self):
        from voteit.poll.app.polls.simple import SimpleVote

        return SimpleVote

    def test_create_blocked_without_register(self):
        self.er.voters.remove(self.user)
        self.assertRaises(
            NotAllowedToVote,
            self._cut.objects.create,
            choice=1,
            user=self.user,
            method=self.method,
        )

    def test_ballot(self):
        obj = self._cut.objects.create(choice=1, user=self.user, method=self.method)
        self.assertEqual(1, obj.ballot())

    def test_poll_user_unique_together(self):
        self._cut.objects.create(choice=1, user=self.user, method=self.method)
        self.assertRaises(
            IntegrityError,
            self._cut.objects.create,
            choice=1,
            user=self.user,
            method=self.method,
        )
