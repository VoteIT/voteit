from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase

from voteit.poll.exceptions import ElectoralRegisterEmpty
from voteit.poll.exceptions import ElectoralRegisterMissing
from voteit.poll.exceptions import InvalidPollMethod
from voteit.poll.exceptions import InvalidProposalCount
from voteit.poll.exceptions import NotAllowedToVote
from voteit.poll.models import ElectoralRegister
from voteit.proposal.workflows import ProposalWf


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
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.agenda.models import AgendaItem
        from voteit.poll.models import Poll
        from voteit.poll.models import ElectoralRegister
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.poll: Poll = cls.ai.polls.create(method_name="simple")
        cls.prop = cls.poll.proposals.create(agenda_item=cls.ai)
        cls.moderator = User.objects.get(username="moderator")
        cls.participant = User.objects.get(username="participant")
        cls.meeting.add_roles(cls.moderator, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.participant, ROLE_POTENTIAL_VOTER)
        cls.er: ElectoralRegister = cls.meeting.er_policy.create_er()

    def setUp(self):
        self.poll.refresh_from_db()
        self.er.refresh_from_db()

    def test_method(self):
        from voteit.poll.app.polls.simple import Simple

        self.assertIsInstance(self.poll.method, Simple)

    def test_start_check_no_electoral_register_no_meeting(self):
        self.poll.meeting = None
        self.poll.save()
        self.assertTrue(self.poll.electoral_register_empty_guard())

    def test_start_check_no_electoral_register_checked_against_meeting(self):
        self.assertTrue(self.poll.electoral_register_missing_guard())
        self.er.delete()
        self.assertFalse(self.poll.electoral_register_missing_guard())

    def test_start_check_electoral_register_empty(self):
        self.assertTrue(self.poll.electoral_register_empty_guard())
        self.er.voters.remove(self.participant, self.moderator)
        self.assertFalse(self.poll.electoral_register_empty_guard())

    def test_start_check_no_proposals(self):
        self.assertTrue(self.poll.no_proposals_guard())
        self.poll.proposals.all().delete()
        self.assertFalse(self.poll.no_proposals_guard())

    def test_opening_poll(self):
        self.poll.upcoming()
        self.assertIsNone(self.poll.ongoing())
        self.assertEqual("ongoing", self.poll.state)

    def test_assigning_bad_poll_method(self):
        self.poll.method_name = "jeff"
        self.assertRaises(InvalidPollMethod, self.poll.save)

    def test_closing_poll(self):
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.poll.votes.create(user=self.participant, vote="yes")
        vote2 = self.poll.votes.create(user=self.moderator, vote="yes")
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertIn(vote2, votes)
        self.poll.close()
        self.assertEqual(
            self.poll.result.dict(),
            {
                "yes": 2,
                "no": 0,
                "approved": [self.prop.pk],
                "denied": [],
                "vote_count": 2,
            },
        )

    def test_closing_de_facto_empty_poll(self):
        # Add bad votes and close it
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.poll.votes.create(user=self.participant, vote="yes")
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        # Change ER
        self.poll.electoral_register.voters.remove(self.participant)
        self.poll.close()
        self.assertFalse(self.poll.votes.count())
        self.assertEqual("failed", self.poll.state)

    def test_votes_from_non_voters_removed_on_close(self):
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.poll.votes.create(user=self.participant, vote="yes")
        vote2 = self.poll.votes.create(user=self.moderator, vote="yes")
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertIn(vote2, votes)
        # Change ER
        self.poll.electoral_register.voters.remove(self.moderator)
        self.poll.close()
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertNotIn(vote2, votes)
        self.assertEqual(
            self.poll.result.dict(),
            {
                "yes": 1,
                "no": 0,
                "approved": [self.prop.pk],
                "denied": [],
                "vote_count": 1,
            },
        )

    def test_abstentions(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.moderator, abstain=True)
        self.poll.votes.create(user=self.participant, vote="yes")
        self.poll.close()
        self.assertEqual(
            self.poll.result.dict(),
            {
                "yes": 1,
                "no": 0,
                "approved": [self.prop.pk],
                "denied": [],
                "vote_count": 1,
            },
        )
        self.assertEqual(1, self.poll.abstains)

    def test_checksum(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.moderator, vote="no")
        self.poll.votes.create(user=self.participant, vote="yes")
        self.poll.close()
        self.poll.save()
        self.assertEqual(
            self.poll.ballot_checksum,
            "062cb36e77dd5f6c5d7fb29b96b43d2c54a7f993d37c1887e987acb47f3b03d80dd3e95a30e4197946264234595bd503782114deb1ce2d84aca0e674ab68d76f",
        )
        self.assertEqual('{"no": 1, "yes": 1}', self.poll.ballot_data)
        self.assertTrue(self.poll.verify_checksum())

    def test_proposal_state_exceptions(self):
        from voteit.proposal.workflows import ProposalWf

        self.prop.unhandled()
        self.prop.save()
        # Must not cause exception
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.moderator, vote="no")
        # Must not cause exception
        self.poll.close()
        self.poll.save()
        self.assertEqual(
            self.poll.proposals.get().state,
            ProposalWf.UNHANDLED,
            "Proposal state must not cause an exception if it can't change.",
        )

    def test_cancel_resets_locked_proposals(self):
        self.poll.upcoming()
        self.poll.ongoing()
        self.prop.refresh_from_db()
        self.prop2 = self.poll.proposals.create(
            agenda_item=self.ai, state=ProposalWf.APPROVED
        )
        self.assertEqual(ProposalWf.VOTING, self.prop.state)
        self.poll.votes.create(user=self.moderator, vote="no")
        self.poll.votes.create(user=self.participant, vote="yes")
        self.poll.cancel()
        self.poll.save()
        self.prop.refresh_from_db()
        self.assertEqual(ProposalWf.PUBLISHED, self.prop.state)
        self.assertEqual(ProposalWf.APPROVED, self.prop2.state)

    def test_private_resets_proposals(self):
        self.poll.upcoming()
        self.prop.refresh_from_db()
        self.assertEqual(ProposalWf.VOTING, self.prop.state)
        self.poll.unpublish()
        self.prop.refresh_from_db()
        self.assertEqual(ProposalWf.PUBLISHED, self.prop.state)

    def test_proposal_from_another_meeting(self):
        from voteit.proposal.models import Proposal

        other_prop = Proposal.objects.create()
        with self.assertRaises(IntegrityError):
            self.poll.proposals.add(other_prop)

    def test_poll_from_another_meeting(self):
        from voteit.proposal.models import Proposal

        other_prop = Proposal.objects.create()
        with self.assertRaises(IntegrityError):
            other_prop.polls.add(self.poll)


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
        prop = self.poll.proposals.create(body="I propose!")
        self.poll.upcoming()
        self.poll.ongoing()
        self.poll.votes.create(user=self.user1, vote_data="yes")
        self.poll.votes.create(user=self.user2, vote_data="yes")
        self.poll.votes.create(user=self.user3, vote_data="no")
        self.poll.close()
        self.assertEqual(
            self.poll.result.dict(),
            {
                "yes": 2,
                "no": 3,
                "approved": [],
                "denied": [prop.pk],
                "vote_count": 5,
            },
        )

    def test_get_voter_weight(self):
        self.assertEqual(self.er.get_voter_weight(self.user1), 1)
        self.assertEqual(self.er.get_voter_weight(self.user3), 3)

    def test_get_total_vote_weight(self):
        self.assertEqual(5, self.er.get_total_vote_weight())


class ElectoralRegisterTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting = Meeting.objects.get(pk=1)
        # cls.meeting.save()
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting.add_roles(cls.participant, "potential_voter")
        cls.meeting.add_roles(cls.moderator, "potential_voter")
        cls.er: ElectoralRegister = cls.meeting.er_policy.create_er()
        wv_participant = cls.er.voterweight_set.get(user=cls.participant)
        wv_participant.weight = 4
        wv_participant.save()
        wv_moderator = cls.er.voterweight_set.get(user=cls.moderator)
        wv_moderator.weight = 2
        wv_moderator.save()

    def setUp(self):
        # Clear cached things
        self.er: ElectoralRegister = ElectoralRegister.objects.get(pk=self.er.pk)

    def test_get_voter_weight(self):
        self.assertEqual(2, self.er.get_voter_weight(self.moderator))

    def test_get_total_vote_weight(self):
        self.assertEqual(6, self.er.get_total_vote_weight())

    def test_weight_dict(self):
        self.assertEqual(
            {self.moderator.pk: 2, self.participant.pk: 4},
            self.er.weight_dict,
        )

    def test_set_voters_from_dict(self):
        self.er.set_voters_from_dict({self.moderator.pk: 3})
        self.assertEqual({self.moderator.pk: 3}, self.er.weight_dict)


class ElectoralRegisterManagerTests(TestCase):
    def _mk_meeting_user(self, _id: int):
        from voteit.meeting.models import Meeting
        from voteit.meeting import roles
        from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll
        from voteit.poll.app.polls.simple import Simple

        meeting = Meeting.objects.create(
            title="Test meeting",
            er_policy_name=AutoBeforePoll.name,
        )
        meeting.ongoing()
        meeting.save()
        user = User.objects.create(username=f"user-{_id}")
        meeting.add_roles(user, roles.ROLE_POTENTIAL_VOTER)

        ai = meeting.agenda_items.create(title="Test agenda item")
        ai.ongoing()
        ai.save()

        poll = ai.polls.create(
            title="Simple test poll",
            method_name=Simple.name,
        )
        poll.proposals.add(ai.proposals.create(author=user))
        poll.upcoming()
        poll.ongoing()
        poll.save()
        return meeting, user

    def test_manager(self):
        from voteit.poll.models import ElectoralRegister

        meeting1, user1 = self._mk_meeting_user(1)
        meeting2, _ = self._mk_meeting_user(2)
        self.assertEqual(ElectoralRegister.objects.for_user(user1).count(), 1)
        self.assertEqual(
            ElectoralRegister.objects.for_user(user1).get().meeting, meeting1
        )
        self.assertNotEqual(
            ElectoralRegister.objects.for_user(user1).get().meeting, meeting2
        )


class VoteTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.agenda.models import AgendaItem
        from voteit.poll.models import Poll

        # from voteit.poll.models import ElectoralRegister
        from voteit.meeting.models import Meeting
        from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.poll: Poll = cls.ai.polls.create(method_name="simple")
        cls.prop = cls.poll.proposals.create(agenda_item=cls.ai)
        # cls.moderator = User.objects.get(username="moderator")
        cls.voter = User.objects.get(username="participant")
        cls.meeting.add_roles(cls.voter, ROLE_POTENTIAL_VOTER)
        # cls.er: ElectoralRegister = cls.meeting.new_electoral_register()
        cls.poll.upcoming()
        cls.poll.ongoing()
        cls.poll.save()

    def setUp(self):
        self.poll.refresh_from_db()

    def test_add_vote(self):
        self.poll.votes.create(user=self.voter, vote="yes")

    def test_add_abstain_clears_vote(self):
        vote = self.poll.votes.create(user=self.voter, vote="yes")
        self.assertIsNotNone(vote.vote_data)
        vote.abstain = True
        vote.save()
        self.assertIsNone(vote.vote_data)

    def test_lacking_er(self):
        self.poll.electoral_register = None
        self.poll.save()
        self.assertRaises(
            ElectoralRegisterMissing,
            self.poll.votes.create,
            user=self.voter,
            vote="yes",
        )

    def test_not_in_er(self):
        self.poll.electoral_register.voters.remove(self.voter)
        self.assertRaises(
            NotAllowedToVote,
            self.poll.votes.create,
            user=self.voter,
            vote="yes",
        )
