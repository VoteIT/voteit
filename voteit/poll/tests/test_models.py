from django.contrib.auth.models import User
from django.test import TestCase
from voteit.poll.exceptions import (
    ElectoralRegisterMissing,
    ElectoralRegisterEmpty,
    InvalidProposalCount,
    InvalidPollMethod,
)


class PollMethodTests(TestCase):
    @property
    def _cut(self):
        from voteit.poll.models import PollMethod

        return PollMethod

    def test_registration(self):
        from voteit.core.component import Registry
        from voteit.poll.abcs import Vote

        poll_method = Registry(self._cut)

        class _Vote(Vote):
            class Meta:
                app_label = "poll"

        @poll_method
        class HelloMethod(self._cut):
            vote_model = _Vote
            title = "Hello"
            vote_set = object()  # Dummy too

            class Meta:
                app_label = "poll"

            def calculate_result(self, ballots):
                pass

            def get_result(self):
                pass

            def start_check(self):
                pass

        self.assertIn("hellomethod", poll_method)


class PollTests(TestCase):
    @property
    def Poll(self):
        from voteit.poll.models import Poll

        return Poll

    @property
    def ElectoralRegister(self):
        from voteit.poll.models import ElectoralRegister

        return ElectoralRegister

    @property
    def Proposal(self):
        from voteit.proposal.models import Proposal

        return Proposal

    def setUp(self):
        from voteit.poll.app.polls.simple import Simple

        self.method = Simple.objects.create()
        self.poll = self.Poll.objects.create(method=self.method)
        self.user = User.objects.create(username="1")
        self.user2 = User.objects.create(username="2")
        self.poll.electoral_register = self.er = self.ElectoralRegister.objects.create()
        self.er.voters.add(self.user, self.user2)
        self.poll.save()

    def test_method(self):
        self.assertIsInstance(self.poll.method, self.method.__class__)

    def test_start_check_no_electoral_register(self):
        self.poll.electoral_register = None
        self.assertRaises(ElectoralRegisterMissing, self.poll.start_check)

    def test_start_check_electoral_register_empty(self):
        self.er.voters.remove(self.user, self.user2)
        self.assertRaises(ElectoralRegisterEmpty, self.poll.start_check)

    def test_start_check_no_proposals(self):
        self.assertRaises(InvalidProposalCount, self.poll.start_check)

    def test_start_check(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.assertTrue(self.poll.start_check())

    def test_opening_poll_empty_poll(self):
        self.poll.electoral_register = None
        self.poll.upcoming()
        self.assertRaises(ElectoralRegisterMissing, self.poll.ongoing)

    def test_opening_poll(self):
        self.poll.upcoming()
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.assertIsNone(self.poll.ongoing())
        self.assertEqual("ongoing", self.poll.state)

    def test_assigning_bad_poll_method(self):
        self.poll.method = self.ElectoralRegister.objects.create()
        self.assertRaises(InvalidPollMethod, self.poll.save)

    def test_closing_poll(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.method.vote_set.create(user=self.user, choice=1)
        vote2 = self.method.vote_set.create(user=self.user2, choice=1)
        self.assertIn(vote1, self.method.get_votes())
        self.assertIn(vote2, self.method.get_votes())
        self.poll.close()
        self.assertEqual({"approve": 2, "deny": 0}, self.method.get_result())

    def test_votes_from_non_voters_removed_on_close(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.method.vote_set.create(user=self.user, choice=1)
        vote2 = self.method.vote_set.create(user=self.user2, choice=1)
        self.assertIn(vote1, self.method.get_votes())
        self.assertIn(vote2, self.method.get_votes())
        # Change ER
        self.poll.electoral_register = er2 = self.ElectoralRegister.objects.create()
        er2.voters.add(self.user)
        self.poll.save()
        self.poll.close()
        self.assertIn(vote1, self.method.get_votes())
        self.assertNotIn(vote2, self.method.get_votes())
        self.assertEqual({"approve": 1, "deny": 0}, self.method.get_result())

    def test_abstentions(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        self.method.vote_set.create(user=self.user, abstain=True)
        self.method.vote_set.create(user=self.user2, choice=1)
        self.poll.close()
        self.assertEqual({"approve": 1, "deny": 0}, self.poll.get_result())
        self.assertEqual(1, self.poll.abstains)

    def test_checksum(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        self.method.vote_set.create(user=self.user, choice=2)
        self.method.vote_set.create(user=self.user2, choice=1)
        self.poll.close()
        self.poll.save()
        self.assertEqual(
            "37f96aff28e9e4d862b8c4614329e61e2141a155b4367f9f7d69231d6d6d263d04c0e29"
            "4d2c474b44f288ba7415b61f8d96976611b47753da9f3886c2c90d3fb",
            self.poll.ballot_checksum,
        )
        self.assertEqual('{"2": 1, "1": 1}', self.poll.ballot_data)
        self.assertTrue(self.poll.verify_checksum())


class VoteWeightTests(TestCase):
    @property
    def Poll(self):
        from voteit.poll.models import Poll

        return Poll

    @property
    def ElectoralRegister(self):
        from voteit.poll.models import ElectoralRegister

        return ElectoralRegister

    @property
    def VoterWeight(self):
        from voteit.poll.models import VoterWeight

        return VoterWeight

    def setUp(self):
        from voteit.poll.app.polls.simple import Simple

        self.method = Simple.objects.create()
        self.er = self.ElectoralRegister.objects.create()
        self.poll = self.Poll.objects.create(method=self.method, electoral_register=self.er)
        self.user1 = User.objects.create(username='1')
        self.user2 = User.objects.create(username='2')
        self.user3 = User.objects.create(username='3')
        self.VoterWeight.objects.create(register=self.poll.electoral_register, user=self.user1)
        self.VoterWeight.objects.create(register=self.poll.electoral_register, user=self.user2)
        self.VoterWeight.objects.create(register=self.poll.electoral_register, user=self.user3, weight=3)

    def test_poll_result(self):
        from voteit.poll.app.polls.simple import SimpleVote
        from voteit.proposal.models import Proposal
        from voteit.proposal.workflows import ProposalWf
        self.poll.proposals.add(Proposal.objects.create(title='Abc123', body='I propose!'))
        self.poll.upcoming()
        self.poll.ongoing()
        self.method.vote_set.create(user=self.user1, choice=SimpleVote.APPROVE)
        self.method.vote_set.create(user=self.user2, choice=SimpleVote.APPROVE)
        self.method.vote_set.create(user=self.user3, choice=SimpleVote.DENY)
        self.poll.close()
        self.assertEqual(self.method.get_result(), {'approve': 2, 'deny': 3})
        # FIXME: Make this work :)
        # self.assertEqual(self.poll.proposals.first().state, ProposalWf.DENIED)

    def test_weight(self):
        self.assertEqual(self.er.get_voter_weight(self.user1), 1)
        self.assertEqual(self.er.get_voter_weight(self.user3), 3)
