from django.contrib.auth import get_user_model
from django.test import TestCase
from voteit.poll.exceptions import (
    ElectoralRegisterMissing,
    ElectoralRegisterEmpty,
    InvalidProposalCount,
    InvalidPollMethod,
)


User = get_user_model()


class PollMethodTests(TestCase):
    @property
    def _cut(self):
        from voteit.poll.abcs import PollMethod

        return PollMethod

    def test_registration(self):
        from voteit.core.component import Registry

        poll_method = Registry(self._cut)

        @poll_method
        class HelloMethod(self._cut):
            title = "Hello"
            name = "hello"
            result_schema = None
            vote_schema = None

            class Meta:
                app_label = "poll"

            def vote_to_str(self, data):
                pass

            def vote_to_obj(self, text):
                pass

            def calculate_result(self, counter):
                pass

        self.assertIn("hello", poll_method)


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
        self.poll = self.Poll.objects.create(method_name="simple")
        self.user = User.objects.create(username="1")
        self.user2 = User.objects.create(username="2")
        self.poll.electoral_register = self.er = self.ElectoralRegister.objects.create()
        self.er.voters.add(self.user, self.user2)
        self.poll.save()

    def test_method(self):
        from voteit.poll.app.polls.simple import Simple

        self.assertIsInstance(self.poll.method, Simple)

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
        self.poll.method_name = "jeff"
        self.assertRaises(InvalidPollMethod, self.poll.save)

    def test_closing_poll(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.poll.votes.create(user=self.user, vote="yes")
        vote2 = self.poll.votes.create(user=self.user2, vote="yes")
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertIn(vote2, votes)
        self.poll.close()
        self.assertEqual(
            self.poll.result.dict(),
            {"yes": 2, "no": 0, "approved": [prop.pk], "denied": []}
        )

    def test_votes_from_non_voters_removed_on_close(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.poll.votes.create(user=self.user, vote="yes")
        vote2 = self.poll.votes.create(user=self.user2, vote="yes")
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertIn(vote2, votes)
        # Change ER
        self.poll.electoral_register = er2 = self.ElectoralRegister.objects.create()
        er2.voters.add(self.user)
        self.poll.save()
        self.poll.close()
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertNotIn(vote2, votes)
        self.assertEqual(
            self.poll.result.dict(),
            {"yes": 1, "no": 0, "approved": [prop.pk], "denied": []}
        )

    def test_abstentions(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.user, abstain=True)
        self.poll.votes.create(user=self.user2, vote="yes")
        self.poll.close()
        self.assertEqual(
            self.poll.result.dict(),
            {"yes": 1, "no": 0, "approved": [prop.pk], "denied": []}
        )
        self.assertEqual(1, self.poll.abstains)

    def test_checksum(self):
        prop = self.Proposal.objects.create()
        self.poll.proposals.add(prop)
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.user, vote="no")
        self.poll.votes.create(user=self.user2, vote="yes")
        self.poll.close()
        self.poll.save()
        self.assertEqual(
            # "81567db4add4931106515ce10f9c5c6025765de626c1c13d60bf550d428e2fdf66e48b06a62b4462c50abe5eff1e1dc99f3dd440687a3d3b9ea375201e094e30",
            self.poll.ballot_checksum,
            "062cb36e77dd5f6c5d7fb29b96b43d2c54a7f993d37c1887e987acb47f3b03d80dd3e95a30e4197946264234595bd503782114deb1ce2d84aca0e674ab68d76f"
        )
        self.assertEqual('{"no": 1, "yes": 1}', self.poll.ballot_data)
        self.assertTrue(self.poll.verify_checksum())

    def test_proposal_state_exceptions(self):
        from voteit.proposal.workflows import ProposalWf
        prop = self.poll.proposals.create()
        prop.approved()
        prop.save()
        # Must not cause exception
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.user, vote="no")
        # Must not cause exception
        self.poll.close()
        self.poll.save()
        self.assertEqual(
            self.poll.proposals.get().state,
            ProposalWf.APPROVED,
            "Proposal state must not have changed automatically from approved."
        )


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
        self.er = self.ElectoralRegister.objects.create()
        self.poll = self.Poll.objects.create(
            method_name="simple", electoral_register=self.er
        )
        self.user1 = User.objects.create(username="1")
        self.user2 = User.objects.create(username="2")
        self.user3 = User.objects.create(username="3")
        self.VoterWeight.objects.create(
            register=self.poll.electoral_register, user=self.user1
        )
        self.VoterWeight.objects.create(
            register=self.poll.electoral_register, user=self.user2
        )
        self.VoterWeight.objects.create(
            register=self.poll.electoral_register, user=self.user3, weight=3
        )

    def test_poll_result(self):
        prop = self.poll.proposals.create(
            title="Abc123", body="I propose!"
        )
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.user1, vote_data="yes")
        self.poll.votes.create(user=self.user2, vote_data="yes")
        self.poll.votes.create(user=self.user3, vote_data="no")
        self.poll.close()
        self.assertEqual(
            self.poll.result.dict(),
            {"yes": 2, "no": 3, "approved": [], "denied": [prop.pk]}
        )

    def test_get_voter_weight(self):
        self.assertEqual(self.er.get_voter_weight(self.user1), 1)
        self.assertEqual(self.er.get_voter_weight(self.user3), 3)

    def test_get_total_vote_weight(self):
        self.assertEqual(5, self.er.get_total_vote_weight())
