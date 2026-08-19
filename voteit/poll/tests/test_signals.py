from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.test import override_settings

from voteit.messaging.channels import UserChannel
from voteit.messaging.state import AppState
from voteit.messaging.testing import action_of
from voteit.messaging.testing import build_app_state
from voteit.messaging.testing import ChannelMessageCatcher
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.messages import VoteTransferChanged
from voteit.poll.messages import VoteTransferDeleted
from voteit.poll.models import ElectoralRegister
from voteit.poll.registries import er_policy
from voteit.poll.registries import vote_transfer_policies
from voteit.poll.testing import UnrestrictedVoteTransferER
from voteit.poll.testing import UnrestrictedVoteTransferPolicy

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class MeetingSubscribedTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.meeting.er_policy_name = None
        cls.ai = cls.meeting.agenda_items.create()
        cls.er = ElectoralRegister.objects.create(meeting=cls.meeting)
        cls.poll = cls.meeting.polls.create(
            method_name="simple", electoral_register=cls.er, state="upcoming"
        )
        cls.poll2 = cls.meeting.polls.create(
            method_name="simple", electoral_register=cls.er, state="ongoing"
        )
        cls.poll_private = cls.meeting.polls.create(
            method_name="simple", electoral_register=cls.er
        )
        cls.user = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.er.set_voters_from_dict({cls.user.pk: 1, cls.moderator.pk: 1})
        # Props
        cls.prop1 = cls.poll.proposals.create(agenda_item=cls.ai)
        cls.prop2 = cls.poll2.proposals.create(agenda_item=cls.ai)
        cls.prop3 = cls.poll_private.proposals.create(agenda_item=cls.ai)
        # Create votes
        cls.vote = cls.poll.votes.create(user=cls.user, vote="yes")
        cls.vote2 = cls.poll2.votes.create(user=cls.user, vote="yes")
        cls.vote_private = cls.poll_private.votes.create(user=cls.user, vote="yes")

    def setUp(self):
        # Clear cached stuff
        self.meeting = Meeting.objects.get(pk=1)
        self.er.refresh_from_db()
        self.poll.refresh_from_db()

    @property
    def _fut(self):
        from voteit.poll.signals import meeting_subscribed

        return meeting_subscribed

    def test_app_state_sent_participants_poll_added(self):
        app_state = build_app_state(
            ParticipantsChannel.name, self.meeting.pk, self.user.pk
        )
        batched_payload = [
            x.payload.items for x in app_state if x.action == "poll.changed.batch"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual({self.poll.pk, self.poll2.pk}, {x.pk for x in payloads})

    def test_app_state_sent_moderators(self):
        app_state = build_app_state(
            ModeratorsChannel.name, self.meeting.pk, self.moderator.pk
        )
        batched_payload = [
            x.payload.items for x in app_state if x.action == "poll.changed.batch"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual(
            {self.poll.pk, self.poll_private.pk, self.poll2.pk},
            {x.pk for x in payloads},
        )

    def test_app_state_sent_votes(self):
        app_state = build_app_state(MeetingChannel.name, self.meeting.pk, self.user.pk)
        pks = {x.payload.pk for x in app_state if x.action == "vote.changed"}
        self.assertEqual({self.vote.pk, self.vote2.pk, self.vote_private.pk}, pks)

    def test_app_state_sent_latest_er(self):
        app_state = build_app_state(MeetingChannel.name, self.meeting.pk, self.user.pk)
        pks = {x.payload.pk for x in app_state if x.action == "er.changed"}
        self.assertEqual({self.er.pk}, pks)

    def test_app_state_doesnt_break_without_er(self):
        self.er.delete()
        app_state = build_app_state(MeetingChannel.name, self.meeting.pk, self.user.pk)
        self.assertFalse([x for x in app_state if x.action == "er.changed"])

    def test_n1_problem(self):
        app_state = AppState()
        with self.assertNumQueries(3):
            self._fut(self.meeting, app_state, self.user)

    def test_withheld_result_participant(self):
        self.meeting.er_policy_name = AutoAlways.name
        self.meeting.save()
        self.meeting.add_roles(self.user, ROLE_POTENTIAL_VOTER)
        self.poll.withheld_result = True
        self.poll.ongoing(force=True)
        self.poll.close(force=True)
        self.poll.save()
        self.assertEqual("withheld", self.poll.state)
        app_state = build_app_state(
            ParticipantsChannel.name, self.meeting.pk, self.user.pk
        )
        batched_payload = [
            x.payload.items for x in app_state if x.action == "poll.changed.batch"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual(2, len(payloads))
        for payload in payloads:
            if payload.pk == self.poll.pk:
                break
        else:
            self.fail("Poll pk wasn't found in payload")
        self.assertEqual(None, payload.result)

    def test_withheld_result_moderator(self):
        self.meeting.er_policy_name = AutoAlways.name
        self.meeting.save()
        self.meeting.add_roles(self.user, ROLE_POTENTIAL_VOTER)
        self.poll.withheld_result = True
        self.poll.ongoing(force=True)
        self.poll.close(force=True)
        self.poll.save()
        self.assertEqual("withheld", self.poll.state)
        app_state = build_app_state(
            ModeratorsChannel.name, self.meeting.pk, self.moderator.pk
        )
        batched_payload = [
            x.payload.items for x in app_state if x.action == "poll.changed.batch"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual(3, len(payloads))
        for payload in payloads:
            if payload.pk == self.poll.pk:
                break
        else:
            self.fail("Poll pk wasn't found in payload")
        self.assertEqual(
            {
                "no": 0,
                "yes": 1,
                "denied": [],
                "approved": [self.prop1.pk],
                "vote_count": 1,
            },
            payload.result,
        )

    def test_app_state_ongoing_poll(self):
        app_state = build_app_state("meeting", self.meeting.pk, self.user.pk)
        message = [x for x in app_state if x.action.endswith(".batch")][0]
        self.assertEqual(1, len(message.payload.items))
        self.assertEqual(
            {"pk": self.poll2.pk, "voted": 1, "total": 2},
            message.payload.items[0].model_dump(),
        )

    def test_app_state_multiple_ongoing_poll(self):
        self.poll.state = "ongoing"
        self.poll.save()
        self.poll.votes.create(user=self.moderator, vote="yes")
        self.poll2.votes.create(user=self.moderator, vote="yes")
        # Build after the mutations: build_app_state runs the receivers now,
        # where the old Subscribe message was only evaluated on run_job().
        app_state = build_app_state("meeting", self.meeting.pk, self.user.pk)
        message = [x for x in app_state if x.action.endswith(".batch")][0]
        dict_payloads = [x.model_dump() for x in message.payload.items]
        self.assertIn({"pk": self.poll.pk, "voted": 2, "total": 2}, dict_payloads)
        self.assertIn({"pk": self.poll2.pk, "voted": 2, "total": 2}, dict_payloads)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class PollChangedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.er = ElectoralRegister.objects.create()
        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.poll = cls.meeting.polls.create(
            method_name="simple", electoral_register=cls.er
        )
        cls.poll_pk = cls.poll.pk
        cls.poll.upcoming(force=True)
        cls.poll.save()
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT)

    def setUp(self):
        self.poll = self.meeting.polls.get(pk=self.poll_pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_added_participants(self, mock_publish):
        self.meeting.polls.create(method_name="simple", electoral_register=self.er)
        self.assertFalse(mock_publish.called)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_added_moderators(self, mock_publish):
        from voteit.poll.messages import PollChanged

        self.assertFalse(mock_publish.called)
        with self.captureOnCommitCallbacks(execute=True):
            poll = self.meeting.polls.create(
                method_name="simple", electoral_register=self.er
            )
            poll.proposals.add(self.prop)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollChanged)
        self.assertEqual(poll.pk, msg.payload.pk)
        self.assertEqual([self.prop.pk], msg.payload.proposals)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_changed_participants(self, mock_publish):
        from voteit.poll.messages import PollChanged
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        with self.captureOnCommitCallbacks(execute=True):
            self.poll.title = "Hello"
            self.poll.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollChanged)
        self.assertEqual(self.poll.pk, msg.payload.pk)
        mock_publish.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            self.poll.unpublish(force=True)
            self.poll.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(self.poll.pk, msg.payload.pk)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        poll_pk = self.poll.pk
        self.poll.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(poll_pk, msg.payload.pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_deleted(self, mock_publish):
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        poll_pk = self.poll.pk
        self.poll.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(poll_pk, msg.payload.pk)
        # Creating a new private poll
        poll = self.meeting.polls.create(
            method_name="simple", electoral_register=self.er
        )
        mock_publish.reset_mock()
        poll.delete()
        # Poll was private, so no message sent
        self.assertFalse(mock_publish.called)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class PrivateAIPublishedTests(TestCase):
    def setUp(self):
        self.er = ElectoralRegister.objects.create()
        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.poll = self.meeting.polls.create(
            method_name="simple", electoral_register=self.er, agenda_item=self.ai
        )
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, ROLE_PARTICIPANT)
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, ROLE_MODERATOR)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_ai_made_public_private_poll(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged

        self.ai.make_upcoming(user=self.moderator)
        self.ai.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaChanged)
        self.assertEqual(1, len(mock_publish.mock_calls))

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_ai_made_public_visible_poll(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged
        from voteit.poll.messages import PollChanged

        self.poll.upcoming(force=True)
        self.poll.save()
        mock_publish.reset_mock()
        self.ai.make_upcoming(user=self.moderator)
        self.ai.save()
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len([x for x in messages if isinstance(x, AgendaChanged)]))
        self.assertEqual(1, len([x for x in messages if isinstance(x, PollChanged)]))


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class NewERSentToMeetingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(er_policy_name="manual", state="ongoing")
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)

    @patch.object(MeetingChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.poll.messages import ElectoralRegisterChanged

        er = self.meeting.er_policy.create_er(weight_dict={self.user.pk: 5})
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], ElectoralRegisterChanged)
        ]
        msg = messages[0]
        self.assertEqual(er.pk, msg.payload.pk)
        self.assertEqual([{"user": self.user.pk, "weight": 5}], msg.payload.weights)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class VoteSignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(
            er_policy_name=AutoAlways.name, state="ongoing"
        )
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.poll = cls.meeting.polls.create(method_name="simple")
        cls.poll.proposals.add(cls.prop)
        cls.poll.ongoing(force=True)
        cls.poll.save()

    @patch.object(UserChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.poll.messages import GenericVoteResponse

        with self.captureOnCommitCallbacks(execute=True):
            self.poll.votes.create(user=self.user, vote="yes")

        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], GenericVoteResponse)
        ]
        msg = messages[0]
        self.assertEqual({"choice": "yes"}, msg.payload.vote)

    @patch.object(UserChannel, "sync_publish")
    def test_changed(self, mock_publish):
        from voteit.poll.messages import GenericVoteResponse

        with self.captureOnCommitCallbacks(execute=True):
            vote = self.poll.votes.create(user=self.user, vote="yes")
        mock_publish.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            vote.vote = "no"
            vote.save()

        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], GenericVoteResponse)
        ]
        msg = messages[0]
        self.assertEqual({"choice": "no"}, msg.payload.vote)

    @patch("voteit.poll.signals.schedule_poll_status_publish")
    def test_count_sent_to_meeting_ch(self, mock_schedule):
        with self.captureOnCommitCallbacks(execute=True):
            self.poll.votes.create(user=self.user, vote="yes")
        mock_schedule.assert_called_once_with(self.poll.pk)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
@patch.dict(
    vote_transfer_policies,
    {UnrestrictedVoteTransferPolicy.name: UnrestrictedVoteTransferPolicy},
)
@patch.dict(
    er_policy,
    {UnrestrictedVoteTransferER.name: UnrestrictedVoteTransferER},
)
class VoteTransferSignalsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.get(pk=1)
        cls.meeting.er_policy_name = UnrestrictedVoteTransferER.name
        cls.meeting.save()
        cls.participant = cls.meeting.participants.get(username="participant")
        cls.other = cls.meeting.participants.create(username="other")
        cls.moderator = cls.meeting.participants.get(username="moderator")
        cls.transfer = cls.meeting.vote_transfers.create(
            source=cls.moderator, target=cls.participant
        )

    def test_cleanup_target(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.meeting.roles.filter(user=self.moderator).delete()
        with self.assertRaises(ObjectDoesNotExist):
            self.transfer.refresh_from_db()

    def test_cleanup_source(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.meeting.roles.filter(user=self.participant).delete()
        with self.assertRaises(ObjectDoesNotExist):
            self.transfer.refresh_from_db()

    def test_add_message_sent(self):
        self.transfer.delete()
        with ChannelMessageCatcher(MeetingChannel) as messages:
            transfer = self.meeting.vote_transfers.create(
                source=self.moderator, target=self.participant
            )
        msg = messages[0]
        self.assertIsInstance(msg, VoteTransferChanged)
        self.assertEqual(
            {
                "meeting": self.meeting.pk,
                "pk": transfer.pk,
                "source": self.moderator.pk,
                "target": self.participant.pk,
            },
            msg.payload.model_dump(),
        )

    def test_change_message_sent(self):
        with ChannelMessageCatcher(MeetingChannel) as messages:
            self.transfer.target = self.other
            self.transfer.save()
        msg = messages[0]
        self.assertIsInstance(msg, VoteTransferChanged)
        self.assertEqual(
            {
                "meeting": self.meeting.pk,
                "pk": self.transfer.pk,
                "source": self.moderator.pk,
                "target": self.other.pk,
            },
            msg.payload.model_dump(),
        )

    def test_delete_message_sent(self):
        transfer_pk = self.transfer.pk
        with ChannelMessageCatcher(MeetingChannel) as messages:
            self.transfer.delete()
        msg = messages[0]
        self.assertIsInstance(msg, VoteTransferDeleted)
        self.assertEqual({"pk": transfer_pk}, msg.payload.model_dump())

    def test_subscribe_message_sent(self):
        command = build_app_state(
            MeetingChannel.name, self.meeting.pk, self.participant.pk
        )

        app_state = command
        payloads = []
        for x in app_state:
            if x.action == f"{action_of(VoteTransferChanged)}.batch":
                payloads = x.payload.items
                break
        self.assertEqual(1, len(payloads))
        self.assertDictEqual(
            {
                "meeting": self.meeting.pk,
                "pk": self.transfer.pk,
                "source": self.moderator.pk,
                "target": self.participant.pk,
            },
            payloads[0].dict(),
        )

    def test_subscribe_message_not_sent_if_not_active(self):
        self.meeting.er_policy_name = AutoAlways.name
        self.meeting.save()
        command = build_app_state(
            MeetingChannel.name, self.meeting.pk, self.participant.pk
        )

        app_state = command
        self.assertEqual(
            [],
            [
                x
                for x in app_state
                if x.action.endswith(".batch")
                and x.payload.action == action_of(VoteTransferChanged)
            ],
        )
