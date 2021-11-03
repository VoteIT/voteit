from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.poll.exceptions import InvalidProposalCount

User = get_user_model()


class MajorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.app.polls import Majority
        from voteit.proposal.models import Proposal

        cls.Majority = Majority
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter_a = cls.er.voters.create(username="a")
        cls.voter_b = cls.er.voters.create(username="b")
        cls.voter_c = cls.er.voters.create(username="c")
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="majority"
        )
        cls.prop1: Proposal = cls.poll.proposals.create()
        cls.prop2: Proposal = cls.poll.proposals.create()

    def test_start_check(self):
        method = self.poll.method
        self.assertIsNone(method.start_check())
        self.prop2.delete()
        self.assertRaises(InvalidProposalCount, method.start_check)

    def test_vote_schema(self):
        from voteit.poll.app.polls.majority import MajorityVoteSchema

        self.poll.upcoming()
        self.poll.ongoing()
        vote = self.poll.votes.create(
            user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}'
        )
        self.assertIsInstance(vote.vote, MajorityVoteSchema)
        self.assertEqual(vote.vote.choice, self.prop1.pk)
        self.assertIsInstance(self.poll.method.vote_to_str(vote.vote), str)
        # And just test that a regular schema works
        MajorityVoteSchema(choice=1)

    def test_result_unanimous(self):
        from voteit.proposal.workflows import ProposalWf

        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.close()
        self.assertEqual(
            self.poll.result,
            {
                "results": [
                    {"proposal": self.prop1.pk, "votes": 1},
                ],
                "approved": [self.prop1.pk],
                "denied": [self.prop2.pk],
                "vote_count": 1,
            },
        )
        self.prop1.refresh_from_db()
        self.prop2.refresh_from_db()
        self.assertEqual(ProposalWf.APPROVED, self.prop1.state)
        self.assertEqual(ProposalWf.DENIED, self.prop2.state)

    def test_result_split(self):
        from voteit.proposal.workflows import ProposalWf

        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.votes.create(user=self.voter_b, vote=f'{{"choice": {self.prop2.pk}}}')
        self.poll.close()
        self.assertEqual(
            self.poll.result,
            {
                "results": [
                    {"proposal": self.prop1.pk, "votes": 1},
                    {"proposal": self.prop2.pk, "votes": 1},
                ],
                "approved": [],
                "denied": [],
                "vote_count": 2,
            },
        )
        self.prop1.refresh_from_db()
        self.prop2.refresh_from_db()
        self.assertEqual(ProposalWf.VOTING, self.prop1.state)
        self.assertEqual(ProposalWf.VOTING, self.prop2.state)

    def test_result_clear(self):
        from voteit.proposal.workflows import ProposalWf

        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.votes.create(user=self.voter_b, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.votes.create(user=self.voter_c, vote=f'{{"choice": {self.prop2.pk}}}')
        self.poll.close()
        self.assertEqual(
            self.poll.result,
            {
                "results": [
                    {"proposal": self.prop2.pk, "votes": 1},
                    {"proposal": self.prop1.pk, "votes": 2},
                ],
                "approved": [self.prop1.pk],
                "denied": [self.prop2.pk],
                "vote_count": 3,
            },
        )
        self.prop1.refresh_from_db()
        self.prop2.refresh_from_db()
        self.assertEqual(ProposalWf.APPROVED, self.prop1.state)
        self.assertEqual(ProposalWf.DENIED, self.prop2.state)
