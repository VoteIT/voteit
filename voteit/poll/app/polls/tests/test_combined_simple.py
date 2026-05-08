from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.poll.app.polls.combined_simple import CombinedSimpleVoteSchema
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.proposal.models import Proposal
from voteit.proposal.workflows import ProposalWf

User = get_user_model()


class SimpleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(
            electoral_register=cls.er, method_name="combined_simple"
        )

    @property
    def CombinedSimple(self):
        from voteit.poll.app.polls.combined_simple import CombinedSimple

        return CombinedSimple

    def test_start_check(self):
        method = self.poll.method
        self.assertRaises(InvalidProposalCount, method.start_check)
        p1 = Proposal.objects.create()
        self.poll.proposals.add(p1)
        self.assertIsNone(method.start_check())
        p2 = Proposal.objects.create()
        self.poll.proposals.add(p2)
        self.assertIsNone(method.start_check())

    def test_vote_schema(self):
        self.poll.upcoming()
        proposal = self.poll.proposals.create()
        proposal2 = self.poll.proposals.create()
        voter = User.objects.create(username="a")
        self.er.add_voter(voter)
        self.poll.ongoing()
        vote = self.poll.votes.create(
            user=voter, vote=f'{{"yes": [{proposal2.pk},{proposal.pk}]}}'
        )
        self.assertIsInstance(vote.vote, CombinedSimpleVoteSchema)
        self.assertEqual(vote.vote.yes, [proposal.pk, proposal2.pk])
        self.assertIsInstance(self.poll.method.vote_to_str(vote.vote), str)
        with self.assertRaises(ValueError):
            CombinedSimpleVoteSchema(yes=["bad"])

    def test_result(self):
        self.poll.upcoming()
        prop = self.poll.proposals.create()
        prop2 = self.poll.proposals.create()
        ua = User.objects.create(username="a")
        ub = User.objects.create(username="b")
        uc = User.objects.create(username="c")
        self.er.set_voters_from_dict({u.pk: 1 for u in [ua, ub, uc]})
        self.poll.ongoing()
        self.poll.votes.create(
            user=ua, vote=f'{{"yes": [{prop.pk}], "no": [{prop2.pk}]}}'
        )
        self.poll.votes.create(user=ub, vote=f'{{"yes": [{prop.pk}]}}')
        self.poll.votes.create(user=uc, vote=f'{{"no": [{prop.pk},{prop2.pk}]}}')
        self.poll.close()
        self.assertEqual(
            self.poll.result,
            {
                "results": {
                    prop.pk: {"abstain": 0, "yes": 2, "no": 1},
                    prop2.pk: {"abstain": 1, "yes": 0, "no": 2},
                },
                "approved": [prop.pk],
                "denied": [prop2.pk],
                "vote_count": 3,
            },
        )
        self.assertEqual(self.poll.proposals.get(pk=prop.pk).state, ProposalWf.APPROVED)
        self.assertEqual(self.poll.proposals.get(pk=prop2.pk).state, ProposalWf.DENIED)
