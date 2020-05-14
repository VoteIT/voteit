from django.contrib.auth.models import User
from django.test import TestCase


class RulesTests(TestCase):

    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.app.polls.simple import Simple
        from voteit.proposal.models import Proposal
        prop1 = Proposal.objects.create()
        self.poll = Poll.objects.create(method=Simple.objects.create())
        self.poll.proposals.add(prop1)
        self.poll.save()
        self.er = ElectoralRegister.objects.create()
        self.user = User.objects.create(username="a")

    def test_is_voter(self):
        from voteit.poll.rules import is_voter
        self.assertFalse(is_voter(self.user, self.poll))
        # Add er
        self.poll.electoral_register = self.er
        self.poll.save()
        self.assertFalse(is_voter(self.user, self.poll))
        # Add user to er
        self.er.voters.add(self.user)
        self.er.save()
        self.assertTrue(is_voter(self.user, self.poll))

    def test_can_vote_now(self):
        from voteit.poll.rules import can_vote_now
        self.assertFalse(can_vote_now(self.user, self.poll))
        self.er.voters.add(self.user)
        self.er.save()
        self.poll.electoral_register = self.er
        self.poll.save()
        self.assertFalse(can_vote_now(self.user, self.poll))
        self.poll.upcoming()
        self.assertFalse(can_vote_now(self.user, self.poll))
        self.poll.ongoing()
        self.assertTrue(can_vote_now(self.user, self.poll))
        self.poll.close()
        self.assertFalse(can_vote_now(self.user, self.poll))
