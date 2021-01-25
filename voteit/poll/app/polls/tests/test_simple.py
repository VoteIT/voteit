from django.contrib.auth.models import User
from django.test import TestCase

from voteit.poll.exceptions import InvalidProposalCount


class SimpleTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(electoral_register=self.er, method_name="simple")

    @property
    def Simple(self):
        from voteit.poll.app.polls.simple import Simple

        return Simple

    def test_start_check(self):
        from voteit.proposal.models import Proposal
        method = self.poll.method
        self.assertRaises(InvalidProposalCount, method.start_check)
        p1 = Proposal.objects.create()
        self.poll.proposals.add(p1)
        self.assertIsNone(method.start_check())
        p2 = Proposal.objects.create()
        self.poll.proposals.add(p2)
        self.assertRaises(InvalidProposalCount, method.start_check)

    def test_vote_schema(self):
        from voteit.poll.app.polls.simple import SimpleVoteSchema
        self.poll.upcoming()
        self.poll.proposals.create()
        voter = self.er.voters.create(username="a")
        self.poll.ongoing()
        vote = self.poll.votes.create(user=voter, vote="yes")
        self.assertIsInstance(vote.vote, SimpleVoteSchema)
        self.assertEqual(vote.vote.choice, "yes")

    def test_result(self):
        from voteit.proposal.workflows import ProposalWf
        self.poll.upcoming()
        prop = self.poll.proposals.create()
        ua = User.objects.create(username="a")
        ub = User.objects.create(username="b")
        uc = User.objects.create(username="c")
        self.er.voters.set([ua, ub, uc])
        self.poll.ongoing()
        self.poll.votes.create(user=ua, vote="yes")
        self.poll.votes.create(user=ub, vote="yes")
        self.poll.votes.create(user=uc, vote="no")
        self.poll.close()
        self.assertEqual(
            self.poll.result,
            {"yes": 2, "no": 1, "approved": [prop.pk], "denied": []}
        )
        self.assertEqual(
            self.poll.proposals.get().state,
            ProposalWf.APPROVED
        )
