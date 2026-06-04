from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.poll.app.polls.simple import SimpleVoteSchema
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.workflows import PollWf
from voteit.proposal.models import Proposal

User = get_user_model()


class SimpleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="simple"
        )

    @property
    def Simple(self):
        from voteit.poll.app.polls.simple import Simple

        return Simple

    def test_start_check(self):
        method = self.poll.method
        self.assertRaises(InvalidProposalCount, method.start_check)
        p1 = Proposal.objects.create()
        self.poll.proposals.add(p1)
        self.assertIsNone(method.start_check())
        p2 = Proposal.objects.create()
        self.poll.proposals.add(p2)
        self.assertRaises(InvalidProposalCount, method.start_check)

    def test_vote_schema(self):
        self.poll.upcoming()
        self.poll.proposals.create()
        voter = User.objects.create(username="a")
        self.er.set_voters_from_dict({voter.pk: 1})
        self.poll.ongoing()
        vote = self.poll.votes.create(user=voter, vote="yes")
        self.assertIsInstance(vote.vote, SimpleVoteSchema)
        self.assertEqual(vote.vote.choice, "yes")
        with self.assertRaises(ValueError):
            SimpleVoteSchema(choice="abstain")

    def test_result(self):
        self.poll.upcoming()
        prop = self.poll.proposals.create()
        ua = User.objects.create(username="a")
        ub = User.objects.create(username="b")
        uc = User.objects.create(username="c")
        self.er.set_voters_from_dict({u.pk: 1 for u in [ua, ub, uc]})
        self.poll.ongoing()
        self.poll.votes.create(user=ua, vote="yes")
        self.poll.votes.create(user=ub, vote="yes")
        self.poll.votes.create(user=uc, vote="no")
        self.poll.close()
        self.assertEqual(
            self.poll.result,
            {
                "yes": 2,
                "no": 1,
                "approved": [prop.pk],
                "denied": [],
                "vote_count": 3,
            },
        )
        self.assertEqual(self.poll.proposals.get().state, "approved")

    def test_close_without_votes(self):
        self.poll.proposals.create()
        self.poll.state = PollWf.ONGOING
        self.poll.save()
        self.poll.close()
        self.assertEqual(PollWf.NO_RESULT, self.poll.state)
