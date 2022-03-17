from collections import Counter

from django.test import TestCase
from django_fsm import TransitionNotAllowed

from envelope.messages.errors import ValidationErrorMsg
from voteit.poll.exceptions import InvalidProposalCount


class ScottishTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(
            electoral_register=self.er,
            method_name="scottish_stv",
            settings={"winners": 2},
        )
        self.voter = self.er.voters.create(username="a_voter")

    @property
    def ScottishSTV(self):
        from voteit.poll.app.polls.scottish_stv import ScottishSTV

        return ScottishSTV

    def test_start_check(self):
        self.poll.settings = dict(winners=3)
        self.assertRaises(InvalidProposalCount, self.poll.method.start_check)

    def test_without_settings(self):
        self.poll.settings_data = None
        self.assertRaises(TransitionNotAllowed, self.poll.upcoming)

    def test_vote_schema(self):
        from voteit.poll.schemas import RankingSchema

        self.poll.settings = dict(winners=2)
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        self.poll.proposals.create()
        self.poll.upcoming()
        self.poll.ongoing()
        vote = self.poll.votes.create(user=self.voter, vote=f"{one.pk},{two.pk}")
        vote_data = vote.vote
        self.assertIsInstance(vote_data, RankingSchema)
        self.assertEquals(vote_data.ranking, [one.pk, two.pk])

    def test_random_votes_result(self):
        from random import sample, randint
        from voteit.proposal.workflows import ProposalWf

        self.poll.settings = dict(winners=3)
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
        self.assertEqual(len(result.approved), 3)
        self.assertEqual(len(result.denied), 7)
        for state, count in (
            (ProposalWf.VOTING, 0),
            (ProposalWf.APPROVED, 3),
            (ProposalWf.DENIED, 7),
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


class AddVoteTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll = Poll.objects.create(
            electoral_register=self.er,
            method_name="scottish_stv",
            settings={"winners": 2},
        )
        self.prop1 = self.poll.proposals.create()
        self.prop2 = self.poll.proposals.create()
        self.prop3 = self.poll.proposals.create()
        self.poll.settings = {"winners": 2}
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()

    @property
    def _cut(self):
        from voteit.poll.app.polls.scottish_stv import AddSTVVote

        return AddSTVVote

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


class ChangeVoteTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.voter = self.er.voters.create(username="voter")
        self.poll = Poll.objects.create(
            electoral_register=self.er,
            method_name="scottish_stv",
            settings={"winners": 2},
        )
        self.prop1 = self.poll.proposals.create()
        self.prop2 = self.poll.proposals.create()
        self.prop3 = self.poll.proposals.create()
        self.poll.settings = {"winners": 2}
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.save()
        self.vote = self.poll.votes.create(
            user=self.voter, vote_data=f"{self.prop3.pk},{self.prop2.pk}"
        )

    @property
    def _cut(self):
        from voteit.poll.app.polls.scottish_stv import ChangeSTVVote

        return ChangeSTVVote

    def _mk_one(self, **kw):
        kw.setdefault("vote", {"ranking": [self.prop1.pk, self.prop2.pk]})
        kw.setdefault("pk", self.vote.pk)
        return self._cut(mm={"user_pk": self.voter.pk, "consumer_name": "abc"}, **kw)

    def test_change(self):
        msg = self._mk_one()
        msg.run_job()
        self.vote.refresh_from_db()
        self.assertEqual(f"{self.prop1.pk},{self.prop2.pk}", self.vote.vote_data)

    def test_change_bad_vote(self):
        msg = self._mk_one(vote={"ranking": [-1, self.prop2.pk]})
        self.assertRaises(ValidationErrorMsg, msg.run_job)
