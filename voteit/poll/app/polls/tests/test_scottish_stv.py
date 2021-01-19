from django.test import TestCase
from django_fsm import TransitionNotAllowed

from voteit.poll.exceptions import InvalidProposalCount


class ScottishTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(
            electoral_register=self.er, method_name="scottish_stv"
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
        self.assertRaises(TransitionNotAllowed, self.poll.upcoming)

    def test_vote_schema(self):
        from voteit.poll.app.polls.scottish_stv import STVVoteSchema
        self.poll.settings = dict(winners=2)
        one = self.poll.proposals.create()
        two = self.poll.proposals.create()
        self.poll.proposals.create()
        self.poll.upcoming()
        self.poll.ongoing()
        vote = self.poll.votes.create(user=self.voter, vote=f"{one.pk},{two.pk}")
        vote_data = vote.vote
        self.assertIsInstance(vote_data, STVVoteSchema)
        self.assertEquals(vote_data.ranking, [one.pk, two.pk])

    def test_random_votes_result(self):
        from random import sample, randint

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
        self.assertEquals(len(result.winners), 3)
