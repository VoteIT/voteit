from collections import Counter
from random import randint
from random import sample
from random import seed

from django.test import TestCase
from pydantic import ValidationError
from envelope.messages.errors import ValidationErrorMsg

from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.models import Poll
from voteit.poll.models import ElectoralRegister
from voteit.poll.schemas import RankingSchema
from voteit.poll.workflows import PollWf
from voteit.proposal.workflows import ProposalWf


class IRVTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="irv")
        cls.voter = cls.er.voters.create(username="a_voter")

    @property
    def IRV(self):
        from voteit.poll.app.polls.irv import IRV

        return IRV

    def test_start_check(self):
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)

    def test_vote_schema(self):
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        self.poll.proposals.create()
        self.poll.upcoming()
        self.poll.ongoing()
        vote = self.poll.votes.create(user=self.voter, vote=f"{one.pk},{two.pk}")
        vote_data = vote.vote
        self.assertIsInstance(vote_data, RankingSchema)
        self.assertEqual(vote_data.ranking, [one.pk, two.pk])

    def test_random_votes_result(self):
        seed(1337)
        for n in range(10):
            self.poll.proposals.create()
        self.assertIsNone(self.poll.method.start_check())
        proposal_pks = list(self.poll.proposals.values_list("pk", flat=True))
        for n in range(20):
            self.er.voters.create(username=f"voter-{n}")
        self.poll.upcoming()
        self.poll.ongoing()
        for voter in self.er.voters.all():
            self.poll.votes.create(
                user=voter,
                vote_data=",".join(
                    str(pk) for pk in sample(proposal_pks, randint(3, 10))
                ),
            )
        self.poll.close()
        result = self.poll.result
        self.assertEqual(len(result.approved), 1)
        self.assertEqual(len(result.denied), 9)
        for state, count in (
            (ProposalWf.VOTING, 0),
            (ProposalWf.APPROVED, 1),
            (ProposalWf.DENIED, 9),
        ):
            self.assertEqual(self.poll.proposals.filter(state=state).count(), count)

    def test_result(self):
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        three = self.poll.proposals.create()
        counter = Counter()
        counter[f"{one.pk},{two.pk},{three.pk}"] = 5
        counter[f"{one.pk},{three.pk}"] = 2
        counter[f"{three.pk},{two.pk}"] = 3
        result = self.poll.method.calculate_result(counter)
        self.assertEqual([one.pk], result.approved)
        self.assertIsInstance(result.json(), str)

    def test_no_majority(self):
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        three = self.poll.proposals.create()
        result = self.poll.method.calculate_result(
            {
                str(one.pk): 1,
                str(two.pk): 1,
                str(three.pk): 1,
            }
        )
        self.assertIs(result.complete, False)

    def test_close_without_votes(self):
        self.poll.proposals.create()
        self.poll.proposals.create()
        self.poll.state = PollWf.ONGOING
        self.poll.save()
        self.poll.close()
        self.assertEqual(PollWf.NO_RESULT, self.poll.state)


class AddVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.voter = cls.er.voters.create(username="voter")
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="irv")
        cls.prop1 = cls.poll.proposals.create()
        cls.prop2 = cls.poll.proposals.create()
        cls.prop3 = cls.poll.proposals.create()
        cls.poll.upcoming()
        cls.poll.ongoing()
        cls.poll.save()

    @property
    def _cut(self):
        from voteit.poll.app.polls.irv import AddIRVVote

        return AddIRVVote

    def _mk_one(self, **kw):
        kw.setdefault(
            "vote", {"ranking": [self.prop1.pk, self.prop2.pk, self.prop3.pk]}
        )
        kw.setdefault("poll", self.poll.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_add(self):
        msg = self._mk_one()
        msg.run_job()
        vote = self.poll.votes.filter(user=self.voter).first()
        self.assertIsNotNone(vote)
        self.assertEqual(
            f"{self.prop1.pk},{self.prop2.pk},{self.prop3.pk}", vote.vote_data
        )

    def test_add_bad_vote(self):
        msg = self._mk_one(vote={"ranking": [-1, self.prop2.pk]})
        self.assertRaises(ValidationErrorMsg, msg.run_job)


class RepeatedIRVTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(
            electoral_register=er,
            method_name="repeated_irv",
            settings={"winners": 2},
        )
        cls.voter = er.voters.create(username="a_voter")

    @property
    def RepeatedIRV(self):
        from voteit.poll.app.polls.irv import RepeatedIRV

        return RepeatedIRV

    def test_one_winner(self):
        from voteit.poll.models import Poll

        with self.assertRaises(ValidationError):
            Poll.objects.create(
                electoral_register=self.er,
                method_name="repeated_irv",
                settings={"winners": 1},
            )

    def test_start_check(self):
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)

    def test_vote_schema(self):
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        self.poll.proposals.create()
        self.poll.upcoming()
        self.poll.ongoing()
        vote = self.poll.votes.create(user=self.voter, vote=f"{one.pk},{two.pk}")
        vote_data = vote.vote
        self.assertIsInstance(vote_data, RankingSchema)
        self.assertEqual(vote_data.ranking, [one.pk, two.pk])

    def test_random_votes_result(self):
        seed(1337)
        for n in range(10):
            self.poll.proposals.create()
        self.assertIsNone(self.poll.method.start_check())
        proposal_pks = list(self.poll.proposals.values_list("pk", flat=True))
        for n in range(20):
            self.er.voters.create(username=f"voter-{n}")
        self.poll.upcoming()
        self.poll.ongoing()
        for voter in self.er.voters.all():
            self.poll.votes.create(
                user=voter,
                vote_data=",".join(
                    str(pk) for pk in sample(proposal_pks, randint(3, 10))
                ),
            )
        self.poll.close()
        result = self.poll.result
        self.assertEqual(len(result.approved), 2)
        self.assertEqual(len(result.denied), 8)
        for state, count in (
            (ProposalWf.VOTING, 0),
            (ProposalWf.APPROVED, 2),
            (ProposalWf.DENIED, 8),
        ):
            self.assertEqual(self.poll.proposals.filter(state=state).count(), count)

    def test_result(self):
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        three = self.poll.proposals.create()
        counter = Counter()
        counter[f"{one.pk},{two.pk},{three.pk}"] = 5
        counter[f"{one.pk},{three.pk}"] = 2
        counter[f"{three.pk},{two.pk}"] = 4
        result = self.poll.method.calculate_result(counter)
        self.assertEqual([one.pk, three.pk], result.approved)
        self.assertIsInstance(result.json(), str)

    def test_no_majority(self):
        result = self.poll.method.calculate_result(
            {str(self.poll.proposals.create().pk): 1 for _ in range(3)}
        )
        self.assertIs(result.complete, False)

    def test_one_reaches_quota(self):
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        three = self.poll.proposals.create()
        counter = Counter()
        counter[str(one.pk)] = 5
        counter[f"{one.pk},{three.pk}"] = 2
        counter[f"{three.pk},{two.pk}"] = 2
        result = self.poll.method.calculate_result(counter)
        self.assertEqual([one.pk], result.approved)
        self.assertIsInstance(result.json(), str)
        self.assertIs(result.complete, False)
