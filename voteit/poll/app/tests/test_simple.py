from collections import Counter

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase
from voteit.poll.exceptions import NotAllowedToVote
from voteit.poll.models import Poll, ElectoralRegister


class SimpleTests(TestCase):

    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(method_name='simple', electoral_register=self.er)

    @property
    def _cut(self):
        from voteit.poll.app.simple import Simple
        return Simple

    def test_result(self):
        method = self._cut(self.poll)
        ua = User.objects.create(username='a')
        ub = User.objects.create(username='b')
        uc = User.objects.create(username='c')
        self.er.voters.set([ua, ub, uc])
        method.create(choice=1, user=ua)
        method.create(choice=1, user=ub)
        method.create(choice=2, user=uc)

        self.assertEqual( Counter({1: 2, 2: 1}), method.get_result())


class SimpleVoteTests(TestCase):

    def setUp(self):
        self.user = User.objects.create(username='a')
        self.er = ElectoralRegister.objects.create()
        self.er.voters.add(self.user)
        self.poll = Poll.objects.create(method_name='simple', electoral_register=self.er)

    @property
    def _cut(self):
        from voteit.poll.app.simple import SimpleVote

        return SimpleVote

    def test_create_blocked_without_register(self):
        self.er.voters.remove(self.user)
        self.assertRaises(NotAllowedToVote, self._cut.objects.create, choice=1, poll=self.poll, user=self.user)

    def test_ballot(self):
        obj = self._cut.objects.create(choice=1, poll=self.poll, user=self.user)
        self.assertEqual(1, obj.ballot())

    def test_poll_user_unique_together(self):
        self._cut.objects.create(choice=1, poll=self.poll, user=self.user)
        self.assertRaises(IntegrityError, self._cut.objects.create, choice=1, poll=self.poll, user=self.user)
