from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from pydantic import ValidationError
from envelope.messages.errors import ValidationErrorMsg
from envelope.testing import testing_channel_layers_setting

from voteit.poll.app.polls.majority import MajorityVoteSchema
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.proposal.models import Proposal

User = get_user_model()


class MajorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.poll.app.polls.majority import Majority
        from voteit.proposal.models import Proposal

        cls.Majority = Majority
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter_a = User.objects.create(username="a")
        cls.voter_b = User.objects.create(username="b")
        cls.voter_c = User.objects.create(username="c")
        cls.er.set_voters_from_dict(
            {cls.voter_a.pk: 1, cls.voter_b.pk: 1, cls.voter_c.pk: 1}
        )
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
        self.poll.ongoing(force=True)
        vote = self.poll.votes.create(
            user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}'
        )
        self.assertIsInstance(vote.vote, MajorityVoteSchema)
        self.assertEqual(vote.vote.choice, self.prop1.pk)
        self.assertIsInstance(self.poll.method.vote_to_str(vote.vote), str)
        # And just test that a regular schema works
        MajorityVoteSchema(choice=1)

    def test_result_unanimous(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.close(force=True)
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
        self.assertEqual("approved", self.prop1.state)
        self.assertEqual("denied", self.prop2.state)

    def test_result_split(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.votes.create(user=self.voter_b, vote=f'{{"choice": {self.prop2.pk}}}')
        self.poll.close(force=True)
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
        self.assertEqual("published", self.prop1.state)
        self.assertEqual("published", self.prop2.state)

    def test_result_clear(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter_a, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.votes.create(user=self.voter_b, vote=f'{{"choice": {self.prop1.pk}}}')
        self.poll.votes.create(user=self.voter_c, vote=f'{{"choice": {self.prop2.pk}}}')
        self.poll.close(force=True)
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
        self.assertEqual("approved", self.prop1.state)
        self.assertEqual("denied", self.prop2.state)

    def test_close_without_votes(self):
        self.poll.votes.create(user=self.voter_a, abstain=True)
        self.poll.state = "ongoing"
        self.poll.save()
        self.poll.close(force=True)
        self.assertEqual("no_result", self.poll.state)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AddMajorityVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="a")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name="majority", state="ongoing"
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
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_add_msg(self):
        msg = self._mk_one(self.prop1.pk)
        msg.run_job()
        self.assertEqual(1, self.voter.vote_set.count())
        vote = self.voter.vote_set.first()
        self.assertEqual(self.prop1.pk, vote.vote.choice)

    def test_add_msg_obvious_bad_choice(self):
        # Handled by pydantic
        with self.assertRaises(ValidationError):
            self._mk_one(0)

    def test_add_msg_bad_proposal(self):
        bad_prop_pk = self.prop1.pk - 5
        msg = self._mk_one(bad_prop_pk)
        self.assertRaises(ValidationErrorMsg, msg.run_job)
