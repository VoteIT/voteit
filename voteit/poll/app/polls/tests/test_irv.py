from collections import Counter
from random import randint
from random import sample

from django.contrib.auth import get_user_model
from django.test import TestCase
from pydantic import ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from voteit.core.testing import SetSeed
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.models import Poll
from voteit.poll.models import ElectoralRegister
from voteit.poll.schemas import RankingSchema

User = get_user_model()


class IRVTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(electoral_register=cls.er, method_name="irv")
        cls.voter = User.objects.create(username="a_voter")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})

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
        self.poll.ongoing(force=True)
        vote = self.poll.votes.create(user=self.voter, vote=f"{one.pk},{two.pk}")
        vote_data = vote.vote
        self.assertIsInstance(vote_data, RankingSchema)
        self.assertEqual(vote_data.ranking, [one.pk, two.pk])

    def test_random_votes_result(self):
        for n in range(10):
            self.poll.proposals.create()
        self.assertIsNone(self.poll.method.start_check())
        proposal_pks = list(self.poll.proposals.values_list("pk", flat=True))
        new_voters = [User.objects.create(username=f"voter-{n}") for n in range(20)]
        self.er.voter_data = {}  # To allow reset
        self.er.set_voters_from_dict(
            {**self.er.voter_data, **{u.pk: 1 for u in new_voters}}
        )
        self.poll.ongoing(force=True)
        with SetSeed():
            for voter in User.objects.filter(pk__in=self.er.voter_data.keys()):
                self.poll.votes.create(
                    user=voter,
                    vote_data=",".join(
                        str(pk) for pk in sample(proposal_pks, randint(3, 10))
                    ),
                )
            self.poll.close(force=True)
        result = self.poll.result

        self.assertEqual(len(result.approved), 1)
        self.assertEqual(len(result.denied), 9)
        for state, count in (
            ("voting", 0),
            ("approved", 1),
            ("denied", 9),
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
        self.poll.state = "ongoing"
        self.poll.save()
        self.poll.close(force=True)
        self.assertEqual("no_result", self.poll.state)


class ValidateVoteTests(TestCase):
    """
    Unit-level coverage of IRV/RepeatedIRV.validate_vote - the extra method-specific
    validation run by VoteAddSerializer before a vote is stored (rest_api/serializers.py).
    """

    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="voter")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.irv_poll = Poll.objects.create(electoral_register=cls.er, method_name="irv")
        cls.repeated_irv_poll = Poll.objects.create(
            electoral_register=cls.er,
            method_name="repeated_irv",
            settings={"winners": 2},
        )
        cls.prop1 = cls.irv_poll.proposals.create()
        cls.prop2 = cls.irv_poll.proposals.create()
        cls.prop3 = cls.irv_poll.proposals.create()
        cls.repeated_irv_poll.proposals.add(cls.prop1, cls.prop2, cls.prop3)
        for poll in (cls.irv_poll, cls.repeated_irv_poll):
            poll.ongoing(force=True)
            poll.save()

    def test_bad_ranking(self):
        vote = RankingSchema(ranking=[-1, self.prop2.pk])
        self.assertRaises(DRFValidationError, self.irv_poll.method.validate_vote, vote)

    def test_min(self):
        settings = self.repeated_irv_poll.settings.dict()
        settings["min"] = 2
        self.repeated_irv_poll.settings = settings
        self.repeated_irv_poll.save()
        method = self.repeated_irv_poll.method
        method.validate_vote(RankingSchema(ranking=[self.prop1.pk, self.prop2.pk]))
        with self.assertRaises(DRFValidationError) as cm:
            method.validate_vote(RankingSchema(ranking=[self.prop1.pk]))
        self.assertEqual({"ranking": "Too few selected"}, cm.exception.detail)

    def test_max(self):
        settings = self.repeated_irv_poll.settings.dict()
        settings["max"] = 2
        self.repeated_irv_poll.settings = settings
        self.repeated_irv_poll.save()
        method = self.repeated_irv_poll.method
        method.validate_vote(RankingSchema(ranking=[self.prop1.pk, self.prop2.pk]))
        with self.assertRaises(DRFValidationError) as cm:
            method.validate_vote(
                RankingSchema(ranking=[self.prop1.pk, self.prop2.pk, self.prop3.pk])
            )
        self.assertEqual({"ranking": "Too many selected"}, cm.exception.detail)


class RepeatedIRVTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(
            electoral_register=er,
            method_name="repeated_irv",
            settings={"winners": 2},
        )
        cls.voter = User.objects.create(username="a_voter")
        er.set_voters_from_dict({cls.voter.pk: 1})
        cls.prop_one = cls.poll.proposals.create()
        cls.prop_two = cls.poll.proposals.create()
        cls.prop_three = cls.poll.proposals.create()

    @property
    def RepeatedIRV(self):
        from voteit.poll.app.polls.irv import RepeatedIRV

        return RepeatedIRV

    def test_one_winner(self):
        with self.assertRaises(ValidationError):
            Poll.objects.create(
                electoral_register=self.er,
                method_name="repeated_irv",
                settings={"winners": 1},
            )

    def test_start_check(self):
        self.assertIsNone(self.poll.method.start_check())
        self.prop_three.delete()
        with self.assertRaises(InvalidProposalCount):
            self.poll.method.start_check()

    def test_vote_schema(self):
        self.poll.ongoing(force=True)
        vote = self.poll.votes.create(
            user=self.voter, vote=f"{self.prop_one.pk},{self.prop_two.pk}"
        )
        vote_data = vote.vote
        self.assertIsInstance(vote_data, RankingSchema)
        self.assertEqual(vote_data.ranking, [self.prop_one.pk, self.prop_two.pk])

    def test_random_votes_result(self):
        for n in range(7):  # 3 exist already
            self.poll.proposals.create()
        self.assertIsNone(self.poll.method.start_check())
        proposal_pks = list(self.poll.proposals.values_list("pk", flat=True))
        new_voters = [User.objects.create(username=f"voter-{n}") for n in range(20)]
        self.er.voter_data = {}  # To allow reset
        self.er.set_voters_from_dict(
            {**self.er.voter_data, **{u.pk: 1 for u in new_voters}}
        )
        self.poll.ongoing(force=True)
        with SetSeed():
            for voter in User.objects.filter(pk__in=self.er.voter_data.keys()):
                self.poll.votes.create(
                    user=voter,
                    vote_data=",".join(
                        str(pk) for pk in sample(proposal_pks, randint(3, 10))
                    ),
                )
            self.poll.close(force=True)
        result = self.poll.result
        self.assertEqual(len(result.approved), 2)
        self.assertEqual(len(result.denied), 8)
        for state, count in (
            ("voting", 0),
            ("approved", 2),
            ("denied", 8),
        ):
            self.assertEqual(self.poll.proposals.filter(state=state).count(), count)

    def test_result(self):
        counter = Counter()
        counter[f"{self.prop_one.pk},{self.prop_two.pk},{self.prop_three.pk}"] = 5
        counter[f"{self.prop_one.pk},{self.prop_three.pk}"] = 2
        counter[f"{self.prop_three.pk},{self.prop_two.pk}"] = 4
        result = self.poll.method.calculate_result(counter)
        self.assertEqual([self.prop_one.pk, self.prop_three.pk], result.approved)
        self.assertIsInstance(result.json(), str)

    def test_no_majority(self):
        result = self.poll.method.calculate_result(
            {str(self.poll.proposals.create().pk): 1 for _ in range(3)}
        )
        self.assertIs(result.complete, False)

    def test_one_reaches_quota(self):
        counter = Counter()
        counter[str(self.prop_one.pk)] = 5
        counter[f"{self.prop_one.pk},{self.prop_three.pk}"] = 2
        counter[f"{self.prop_three.pk},{self.prop_two.pk}"] = 2
        result = self.poll.method.calculate_result(counter)
        self.assertEqual([self.prop_one.pk], result.approved)
        self.assertIsInstance(result.json(), str)
        self.assertIs(result.complete, False)
