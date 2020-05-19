from django.contrib.auth.models import User
from django.test import TestCase
from voteit.poll.exceptions import InvalidProposalCount


class SimpleTests(TestCase):
    def setUp(self):
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister

        self.er = ElectoralRegister.objects.create()
        self.poll = Poll.objects.create(electoral_register=self.er)

    @property
    def ScottishSTV(self):
        from voteit.poll.app.polls.scottish_stv import ScottishSTV
        return ScottishSTV

    def test_method_creation(self):
        method = self.ScottishSTV.objects.create(winners=3)
        self.poll.method = method
        self.poll.save()
        self.assertRaises(InvalidProposalCount, method.start_check)

    def test_random_votes_result(self):
        from random import sample, randint
        method = self.ScottishSTV.objects.create(winners=3)
        self.poll.method = method
        self.poll.save()
        for n in range(10):
            self.poll.proposals.create()
        self.assertIsNone(method.start_check())
        proposal_pks = list(self.poll.proposals.values_list('pk', flat=True))
        for n in range(20):
            self.er.voters.create(username=f'voter-{n}')
        for voter in self.er.voters.all():
            method.vote_set.create(
                user=voter,
                ranking=','.join(str(pk) for pk in sample(proposal_pks, randint(3, 10)))
            )
        result = method.get_result()
        self.assertIsInstance(result, dict)
        self.assertEquals(len(result.get('winners')), 3)
