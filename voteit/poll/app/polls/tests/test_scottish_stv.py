from collections import Counter

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.models import ElectoralRegister
from voteit.poll.models import Poll
from voteit.poll.schemas import RankingSchema

User = get_user_model()


class ScottishTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(
            electoral_register=cls.er,
            method_name="scottish_stv",
            settings={"winners": 2},
        )
        cls.voter = User.objects.create(username="a_voter")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})

    @property
    def ScottishSTV(self):
        from voteit.poll.app.polls.scottish_stv import ScottishSTV

        return ScottishSTV

    def test_start_check(self):
        self.poll.settings = dict(winners=3)
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)

    def test_without_settings(self):
        self.poll.settings_data = None
        self.assertRaises(ValidationError, self.poll.upcoming, force=True)

    def test_vote_schema(self):
        from voteit.poll.schemas import RankingSchema

        self.poll.settings = dict(winners=2)
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        self.poll.proposals.create()
        self.poll.ongoing(force=True)
        vote = self.poll.votes.create(user=self.voter, vote=f"{one.pk},{two.pk}")
        vote_data = vote.vote
        self.assertIsInstance(vote_data, RankingSchema)
        self.assertEqual(vote_data.ranking, [one.pk, two.pk])

    def test_random_votes_result(self):
        from random import sample, randint

        self.poll.settings = dict(winners=3)
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
        for voter in User.objects.filter(pk__in=self.er.voter_data.keys()):
            self.poll.votes.create(
                user=voter,
                vote_data=",".join(
                    str(pk) for pk in sample(proposal_pks, randint(3, 10))
                ),
            )
        self.poll.close(force=True)
        result = self.poll.result
        self.assertEqual(len(result.approved), 3)
        self.assertEqual(len(result.denied), 7)
        for state, count in (
            ("voting", 0),
            ("approved", 3),
            ("denied", 7),
        ):
            self.assertEqual(self.poll.proposals.filter(state=state).count(), count)

    def test_result(self):
        self.poll.settings = {"winners": 2}
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        three = self.poll.proposals.create()
        counter = Counter()
        counter[f"{one.pk},{two.pk},{three.pk}"] = 5
        counter[f"{one.pk},{three.pk}"] = 2
        counter[f"{three.pk},{two.pk}"] = 3
        result = self.poll.method.calculate_result(counter)
        self.assertEqual([one.pk, three.pk], result.approved)
        self.assertIsInstance(result.json(), str)

    def test_close_without_votes(self):
        self.poll.state = "ongoing"
        self.poll.save()
        self.poll.close(force=True)
        self.assertEqual("no_result", self.poll.state)


class ValidateVoteTests(TestCase):
    """
    Unit-level coverage of ScottishSTV.validate_vote - the extra method-specific
    validation run by VoteAddSerializer before a vote is stored (rest_api/serializers.py).
    """

    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.voter = User.objects.create(username="voter")
        cls.er.set_voters_from_dict({cls.voter.pk: 1})
        cls.poll = Poll.objects.create(
            electoral_register=cls.er,
            method_name="scottish_stv",
            settings={"winners": 2},
        )
        cls.prop1 = cls.poll.proposals.create()
        cls.prop2 = cls.poll.proposals.create()
        cls.prop3 = cls.poll.proposals.create()
        cls.poll.ongoing(force=True)
        cls.poll.save()

    def test_valid_ranking(self):
        vote = RankingSchema(ranking=[self.prop1.pk, self.prop2.pk, self.prop3.pk])
        self.assertIsNone(self.poll.method.validate_vote(vote))

    def test_bad_proposal(self):
        vote = RankingSchema(ranking=[-1, self.prop2.pk])
        self.assertRaises(ValidationError, self.poll.method.validate_vote, vote)
