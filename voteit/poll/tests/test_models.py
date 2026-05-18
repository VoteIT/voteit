from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings
from envelope.testing import testing_channel_layers_setting

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.workflows import MeetingWf
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.app.er_policies.auto_before_poll import AutoBeforePoll
from voteit.poll.app.polls.simple import Simple
from voteit.poll.exceptions import (
    ElectoralRegisterMissing,
    InvalidPollMethod,
    NotAllowedToVote,
)
from voteit.poll.models import ElectoralRegister, Poll
from voteit.poll.registries import er_policy, vote_transfer_policies
from voteit.poll.testing import (
    UnrestrictedVoteTransferER,
    UnrestrictedVoteTransferPolicy,
)
from voteit.poll.workflows import PollWf
from voteit.proposal.models import Proposal
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

    def test_broken_er_name_checked(self):
        self.assertTrue(self.poll.valid_er_policy_guard())
        self.poll.meeting.er_policy_name = "broken"
        self.poll.meeting.save()
        self.assertFalse(self.poll.valid_er_policy_guard())

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
        # Change ER - remove participant
        er = self.poll.electoral_register
        er.voter_data = {}  # To allow reset
        er.set_voters_from_dict(
            {k: v for k, v in er.get_weight_dict().items() if k != self.participant.pk}
        )
        self.poll.close()
        self.assertFalse(self.poll.votes.count())
        self.assertEqual(PollWf.NO_RESULT, self.poll.state)

    def test_votes_from_non_voters_removed_on_close(self):
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.poll.votes.create(user=self.participant, vote="yes")
        vote2 = self.poll.votes.create(user=self.moderator, vote="yes")
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertIn(vote2, votes)
        # Change ER - remove moderator
        er = self.poll.electoral_register
        new_vals = {
            k: v for k, v in er.get_weight_dict().items() if k != self.moderator.pk
        }
        er.voter_data = {}  # To allow set_voters_from_dict
        er.set_voters_from_dict(new_vals)
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

    def test_no_er_causes_poll_to_have_no_result(self):
        self.poll.upcoming()
        self.poll.ongoing()
        vote1 = self.poll.votes.create(user=self.participant, vote="yes")
        vote2 = self.poll.votes.create(user=self.moderator, vote="yes")
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertIn(vote2, votes)
        self.poll.electoral_register = None
        self.poll.close()
        self.poll.save()
        votes = self.poll.votes.all()
        self.assertIn(vote1, votes)
        self.assertIn(vote2, votes)
        self.assertEqual(PollWf.NO_RESULT, self.poll.state)

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
        other_prop = Proposal.objects.create()
        with self.assertRaises(IntegrityError):
            self.poll.proposals.add(other_prop)

    def test_poll_from_another_meeting(self):
        other_prop = Proposal.objects.create()
        with self.assertRaises(IntegrityError):
            other_prop.polls.add(self.poll)


class VoteWeightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.poll = Poll.objects.create(method_name="simple", electoral_register=cls.er)
        cls.user1 = User.objects.create(username="1")
        cls.user2 = User.objects.create(username="2")
        cls.user3 = User.objects.create(username="3")
        cls.er.set_voters_from_dict({cls.user1.pk: 1, cls.user2.pk: 1, cls.user3.pk: 3})

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
        cls.meeting = Meeting.objects.get(pk=1)
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting.add_roles(cls.participant, ROLE_POTENTIAL_VOTER)
        cls.meeting.add_roles(cls.moderator, ROLE_POTENTIAL_VOTER)
        cls.er: ElectoralRegister = cls.meeting.er_policy.create_er()
        cls.er.voter_data = {}  # To allow reset
        cls.er.set_voters_from_dict({cls.participant.pk: 4, cls.moderator.pk: 2})

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
        self.er.voter_data = {}  # To allow reset
        self.er.set_voters_from_dict({self.moderator.pk: 3})
        self.assertEqual({self.moderator.pk: 3}, self.er.weight_dict)

    def test_create_er_on_closed_meeting(self):
        self.meeting.state = MeetingWf.CLOSED
        self.meeting.save()
        self.meeting.remove_roles(self.participant, ROLE_POTENTIAL_VOTER)
        self.assertFalse(self.meeting.er_policy.new_er_needed())
        self.assertEqual(self.er, self.meeting.er_policy.create_er())

    def test_create_empty_er_on_blank_meeting(self):
        self.meeting.electoral_registers.all().delete()
        self.meeting.roles.all().delete()
        self.assertIsNone(None, self.meeting.latest_er)
        self.assertIsNone(None, self.meeting.er_policy.create_er())

    def test_create_empty_er_on_blank_meeting_er_method_poll_change(self):
        self.meeting.electoral_registers.all().delete()
        self.meeting.roles.all().delete()
        self.meeting.er_policy_name = AutoAlways.name
        self.meeting.save()
        self.assertIsNone(None, self.meeting.latest_er)
        er = self.meeting.er_policy.create_er()
        self.assertIsInstance(er, ElectoralRegister)
        self.assertEqual({}, er.weight_dict)

    def test_create_empty_er_when_last_has_voters(self):
        self.meeting.roles.all().delete()
        er = self.meeting.er_policy.create_er()
        self.assertEqual({}, er.weight_dict)


class ElectoralRegisterManagerTests(TestCase):
    def _mk_meeting_user(self, _id: int):
        meeting = Meeting.objects.create(
            title="Test meeting",
            er_policy_name=AutoBeforePoll.name,
        )
        meeting.ongoing()
        meeting.save()
        user = User.objects.create(username=f"user-{_id}")
        meeting.add_roles(user, ROLE_POTENTIAL_VOTER)

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
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai: AgendaItem = cls.meeting.agenda_items.create()
        cls.poll: Poll = cls.ai.polls.create(method_name="simple")
        cls.prop = cls.poll.proposals.create(agenda_item=cls.ai)
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
        er = self.poll.electoral_register
        er.voter_data = {}  # To allow set_voters_from_dict
        er.set_voters_from_dict(
            {k: v for k, v in er.get_weight_dict().items() if k != self.voter.pk}
        )
        self.assertRaises(
            NotAllowedToVote,
            self.poll.votes.create,
            user=self.voter,
            vote="yes",
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
@patch.dict(
    vote_transfer_policies,
    {UnrestrictedVoteTransferPolicy.name: UnrestrictedVoteTransferPolicy},
)
@patch.dict(
    er_policy,
    {UnrestrictedVoteTransferER.name: UnrestrictedVoteTransferER},
)
class VoteTransferTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.meeting.er_policy_name = UnrestrictedVoteTransferER.name
        cls.meeting.save()
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.other_participant = cls.meeting.participants.create(username="other")
        cls.moderator = cls.meeting.participants.get(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_POTENTIAL_VOTER)
        cls.transfer = cls.meeting.vote_transfers.create(
            source=cls.moderator, target=cls.participant
        )

    def test_trigger_er(self):
        er = self.meeting.er_policy.create_er()
        self.assertEqual({self.participant.pk: 1}, er.weight_dict)
        self.transfer.delete()
        er = self.meeting.er_policy.create_er()
        self.assertEqual({self.moderator.pk: 1}, er.weight_dict)

    def test_duplicate_source(self):
        with self.assertRaises(IntegrityError):
            self.meeting.vote_transfers.create(
                source=self.moderator, target=self.other_participant
            )
