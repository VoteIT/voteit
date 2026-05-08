from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError

from envelope.messages.errors import ValidationErrorMsg
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.workflows import PollWf

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class DuttTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.app.polls.dutt import Dutt
        from voteit.proposal.models import Proposal

        cls.Dutt = Dutt
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter_a = User.objects.create(username="a")
        cls.voter_b = User.objects.create(username="b")
        cls.voter_c = User.objects.create(username="c")
        cls.er.set_voters_from_dict({cls.voter_a.pk: 1, cls.voter_b.pk: 1, cls.voter_c.pk: 1})
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="dutt"
        )
        cls.prop1: Proposal = cls.poll.proposals.create()
        cls.prop2: Proposal = cls.poll.proposals.create()

    def test_start_check(self):
        method = self.poll.method
        self.assertIsNone(method.start_check())
        self.prop2.delete()
        self.assertRaises(InvalidProposalCount, method.start_check)

    def test_vote_schema(self):
        from voteit.poll.app.polls.dutt import DuttVoteSchema

        self.poll.upcoming()
        self.poll.ongoing()
        vote = self.poll.votes.create(user=self.voter_a, vote=f"[{self.prop1.pk}]")
        self.assertIsInstance(vote.vote, DuttVoteSchema)
        self.assertEqual(vote.vote.choices, [self.prop1.pk])
        self.assertIsInstance(self.poll.method.vote_to_str(vote.vote), str)
        # And just test that a regular schema works
        DuttVoteSchema(choices=[self.prop1.pk])

    def test_result_split(self):
        from voteit.proposal.workflows import ProposalWf

        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.voter_a, vote=f"[{self.prop1.pk}]")
        self.poll.votes.create(user=self.voter_b, vote=f"[{self.prop2.pk}]")
        self.poll.close()
        self.assertEqual(
            self.poll.result.dict(),
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

    def test_close_without_votes(self):
        self.poll.state = PollWf.ONGOING
        self.poll.save()
        self.poll.votes.create(user=self.voter_a, abstain=True)
        self.poll.close()
        self.assertEqual(PollWf.NO_RESULT, self.poll.state)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddDuttVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.app.polls.dutt import Dutt
        from voteit.proposal.models import Proposal
        from voteit.poll.workflows import PollWf

        cls.Dutt = Dutt
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="a")
        cls.er.add_voter(cls.voter)
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name=Dutt.name, state=PollWf.ONGOING
        )
        cls.prop1: Proposal = cls.poll.proposals.create()
        cls.prop2: Proposal = cls.poll.proposals.create()

    @property
    def _cut(self):
        from voteit.poll.app.polls.dutt import AddDuttVote

        return AddDuttVote

    def _mk_one(self, choices, **kw):
        kw.setdefault("vote", {"choices": choices})
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_add_msg(self):
        msg = self._mk_one([self.prop1.pk])
        msg.run_job()
        self.assertEqual(1, self.voter.vote_set.count())
        vote = self.voter.vote_set.first()
        self.assertEqual([self.prop1.pk], vote.vote.choices)

    def test_add_msg_obvious_bad_choice(self):
        # Handled by pydantic
        with self.assertRaises(ValidationError):
            msg = self._mk_one([0])

    def test_add_msg_bad_proposal(self):
        bad_prop_pk = self.prop1.pk - 5
        msg = self._mk_one([bad_prop_pk])
        self.assertRaises(ValidationErrorMsg, msg.run_job)
