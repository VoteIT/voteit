from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError
from voteit.messaging.errors import ValidationErrorMsg

from voteit.poll.exceptions import InvalidProposalCount

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class MajorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.app.polls.majority import Majority
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


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddMajorityVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.app.polls.majority import Majority
        from voteit.proposal.models import Proposal
        from voteit.poll.workflows import PollWf

        cls.Majority = Majority
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = cls.er.voters.create(username="a")
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="majority", state=PollWf.ONGOING
        )
        cls.prop1: Proposal = cls.poll.proposals.create()
        cls.prop2: Proposal = cls.poll.proposals.create()

    @property
    def _cut(self):
        from voteit.poll.app.polls.majority import AddMajorityVote

        return AddMajorityVote

    def _mk_one(self, choice, **kw):
        kw.setdefault("vote", {"choice": choice})
        kw.setdefault("poll", self.poll.pk)
        return self._cut({"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_add_msg(self):
        msg = self._mk_one(self.prop1.pk)
        msg.run_job()
        self.assertEqual(1, self.voter.vote_set.count())
        vote = self.voter.vote_set.first()
        self.assertEqual(self.prop1.pk, vote.vote.choice)

    def test_add_msg_obvious_bad_choice(self):
        # Handled by pydantic
        self.assertRaises(ValidationError, self._mk_one, 0)

    def test_add_msg_bad_proposal(self):
        bad_prop_pk = self.prop1.pk - 5
        msg = self._mk_one(bad_prop_pk)
        self.assertRaises(ValidationErrorMsg, msg.run_job)
