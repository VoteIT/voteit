from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from voteit.poll.app.polls.dutt import Dutt
from voteit.poll.app.polls.dutt import DuttVoteSchema
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.proposal.models import Proposal

User = get_user_model()


class DuttTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.Dutt = Dutt
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter_a = User.objects.create(username="a")
        cls.voter_b = User.objects.create(username="b")
        cls.voter_c = User.objects.create(username="c")
        cls.er.set_voters_from_dict(
            {cls.voter_a.pk: 1, cls.voter_b.pk: 1, cls.voter_c.pk: 1}
        )
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
        self.poll.ongoing(force=True)
        vote = self.poll.votes.create(user=self.voter_a, vote=f"[{self.prop1.pk}]")
        self.assertIsInstance(vote.vote, DuttVoteSchema)
        self.assertEqual(vote.vote.choices, [self.prop1.pk])
        self.assertIsInstance(self.poll.method.vote_to_str(vote.vote), str)
        # And just test that a regular schema works
        DuttVoteSchema(choices=[self.prop1.pk])

    def test_result_split(self):
        self.poll.ongoing(force=True)
        self.poll.votes.create(user=self.voter_a, vote=f"[{self.prop1.pk}]")
        self.poll.votes.create(user=self.voter_b, vote=f"[{self.prop2.pk}]")
        self.poll.close(force=True)
        self.assertEqual(
            self.poll.result.model_dump(),
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

    def test_close_without_votes(self):
        self.poll.state = "ongoing"
        self.poll.save()
        self.poll.votes.create(user=self.voter_a, abstain=True)
        self.poll.close(force=True)
        self.assertEqual("no_result", self.poll.state)


class ValidateVoteTests(TestCase):
    """
    Unit-level coverage of Dutt.validate_vote - the extra method-specific
    validation run by VoteAddSerializer before a vote is stored (rest_api/serializers.py).
    """

    @classmethod
    def setUpTestData(cls):
        cls.er: ElectoralRegister = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="a")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.poll: Poll = Poll.objects.create(
            electoral_register=cls.er, method_name=Dutt.name, state="ongoing"
        )
        cls.prop1: Proposal = cls.poll.proposals.create()
        cls.prop2: Proposal = cls.poll.proposals.create()

    def test_valid_choice(self):
        vote = DuttVoteSchema(choices=[self.prop1.pk])
        self.assertIsNone(self.poll.method.validate_vote(vote))

    def test_bad_proposal(self):
        bad_prop_pk = self.prop1.pk - 5
        vote = DuttVoteSchema(choices=[bad_prop_pk])
        self.assertRaises(ValidationError, self.poll.method.validate_vote, vote)

    def test_too_few(self):
        self.poll.settings = {"min": 2}
        self.poll.save()
        vote = DuttVoteSchema(choices=[self.prop1.pk])
        self.assertRaises(ValidationError, self.poll.method.validate_vote, vote)

    def test_too_many(self):
        self.poll.settings = {"max": 1}
        self.poll.save()
        vote = DuttVoteSchema(choices=[self.prop1.pk, self.prop2.pk])
        self.assertRaises(ValidationError, self.poll.method.validate_vote, vote)
