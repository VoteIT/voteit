from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from envelope.app.user_channel.channel import UserChannel
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.channels.models import AppState
from envelope.testing import MessageCatcher
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.meeting.channels import ParticipantsChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.messages import PollStatus
from voteit.poll.models import ElectoralRegister
from voteit.poll.workflows import PollWf

User = get_user_model()


_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
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
        cls.er.voters.add(cls.user, cls.moderator)
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
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=ParticipantsChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        batched_payload = [
            x.p["payloads"]
            for x in msg.data.app_state
            if x.t == "s.batch" and x.p.get("t") == "poll.added"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual({self.poll.pk, self.poll2.pk}, {x.pk for x in payloads})

    def test_app_state_sent_moderators(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.meeting.pk,
            channel_type=ModeratorsChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        batched_payload = [
            x.p["payloads"]
            for x in msg.data.app_state
            if x.t == "s.batch" and x.p.get("t") == "poll.added"
        ]
        self.assertEqual(1, len(batched_payload))
        payloads = batched_payload[0]
        self.assertEqual(
            {self.poll.pk, self.poll_private.pk, self.poll2.pk},
            {x.pk for x in payloads},
        )

    def test_app_state_sent_votes(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        pks = {x.p["pk"] for x in msg.data.app_state if x.t == "vote.added"}
        self.assertEqual({self.vote.pk, self.vote2.pk, self.vote_private.pk}, pks)

    def test_app_state_sent_latest_er(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        pks = {x.p["pk"] for x in msg.data.app_state if x.t == "er.added"}
        self.assertEqual({self.er.pk}, pks)

    def test_app_state_doesnt_break_without_er(self):
        self.er.delete()
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertFalse([x for x in msg.data.app_state if x.t == "er.added"])

    def test_n1_problem(self):
        app_state = AppState()
        with self.assertNumQueries(4):
            self._fut(self.meeting, app_state, self.user)

    def test_withheld_result_participant(self):
        self.meeting.er_policy_name = AutoAlways.name
        self.meeting.save()
        self.meeting.add_roles(self.user, ROLE_POTENTIAL_VOTER)
        self.poll.withheld_result = True
        self.poll.ongoing()
        self.poll.close()
        self.poll.save()
        self.assertEqual(PollWf.WITHHELD, self.poll.state)
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type=ParticipantsChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        batched_payload = [
            x.p["payloads"]
            for x in msg.data.app_state
            if x.t == "s.batch" and x.p.get("t") == "poll.added"
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
        self.poll.ongoing()
        self.poll.close()
        self.poll.save()
        self.assertEqual(PollWf.WITHHELD, self.poll.state)
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.meeting.pk,
            channel_type=ModeratorsChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        batched_payload = [
            x.p["payloads"]
            for x in msg.data.app_state
            if x.t == "s.batch" and x.p.get("t") == "poll.added"
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
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="meeting",
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        messages = [x.p for x in msg.data.app_state if x.t == PollStatus.name]
        self.assertEqual(1, len(messages))
        payload = messages[0]
        self.assertEqual({"pk": self.poll2.pk, "voted": 1, "total": 2}, payload)

    def test_app_state_multiple_ongoing_poll(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.user.pk},
            pk=self.meeting.pk,
            channel_type="meeting",
        )
        self.poll.state = PollWf.ONGOING
        self.poll.save()
        self.poll.votes.create(user=self.moderator, vote="yes")
        self.poll2.votes.create(user=self.moderator, vote="yes")
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        messages = [x.p for x in msg.data.app_state if x.t == PollStatus.name]
        self.assertEqual(2, len(messages))
        self.assertIn({"pk": self.poll.pk, "voted": 2, "total": 2}, messages)
        self.assertIn({"pk": self.poll2.pk, "voted": 2, "total": 2}, messages)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
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
        cls.poll.upcoming()
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
        from voteit.poll.messages import PollAdded

        self.assertFalse(mock_publish.called)
        with self.captureOnCommitCallbacks(execute=True):
            poll = self.meeting.polls.create(
                method_name="simple", electoral_register=self.er
            )
            poll.proposals.add(self.prop)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollAdded)
        self.assertEqual(poll.pk, msg.data.pk)
        self.assertEqual([self.prop.pk], msg.data.proposals)

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
        self.assertEqual(self.poll.pk, msg.data.pk)
        mock_publish.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            self.poll.unpublish()
            self.poll.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(self.poll.pk, msg.data.pk)

    @patch.object(ModeratorsChannel, "sync_publish")
    def test_deleted_moderators(self, mock_publish):
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        poll_pk = self.poll.pk
        self.poll.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(poll_pk, msg.data.pk)

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_deleted(self, mock_publish):
        from voteit.poll.messages import PollDeleted

        self.assertFalse(mock_publish.called)
        poll_pk = self.poll.pk
        self.poll.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PollDeleted)
        self.assertEqual(poll_pk, msg.data.pk)
        # Creating a new private poll
        poll = self.meeting.polls.create(
            method_name="simple", electoral_register=self.er
        )
        mock_publish.reset_mock()
        poll.delete()
        # Poll was private, so no message sent
        self.assertFalse(mock_publish.called)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
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

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_ai_made_public_private_poll(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged

        self.ai.upcoming()
        self.ai.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, AgendaChanged)
        self.assertEqual(1, len(mock_publish.mock_calls))

    @patch.object(ParticipantsChannel, "sync_publish")
    def test_ai_made_public_visible_poll(self, mock_publish):
        from voteit.agenda.messages import AgendaChanged
        from voteit.poll.messages import PollAdded

        self.poll.upcoming()
        self.poll.save()
        mock_publish.reset_mock()
        self.ai.upcoming()
        self.ai.save()
        self.assertTrue(mock_publish.called)
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(1, len([x for x in messages if isinstance(x, AgendaChanged)]))
        self.assertEqual(1, len([x for x in messages if isinstance(x, PollAdded)]))


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class NewERSentToMeetingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(er_policy_name="manual")
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)

    @patch.object(MeetingChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.poll.messages import ElectoralRegisterAdded

        er = self.meeting.er_policy.create_er(weight_dict={self.user.pk: 5})
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], ElectoralRegisterAdded)
        ]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertEqual(er.pk, msg.data.pk)
        self.assertEqual([{"user": self.user.pk, "weight": 5}], msg.data.weights)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class VoteSignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create(er_policy_name=AutoAlways.name)
        cls.user = User.objects.create(username="user")
        cls.meeting.add_roles(cls.user, ROLE_PARTICIPANT, ROLE_POTENTIAL_VOTER)
        cls.ai = cls.meeting.agenda_items.create()
        cls.prop = cls.ai.proposals.create()
        cls.poll = cls.meeting.polls.create(method_name="simple")
        cls.poll.proposals.add(cls.prop)
        cls.poll.upcoming()
        cls.poll.ongoing()
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
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertEqual({"choice": "yes"}, msg.data.vote)

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
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertEqual({"choice": "no"}, msg.data.vote)

    @patch.object(MeetingChannel, "sync_publish")
    def test_count_sent_to_meeting_ch(self, mock_publish):
        from voteit.poll.messages import PollStatus

        with self.captureOnCommitCallbacks(execute=True):
            self.poll.votes.create(user=self.user, vote="yes")
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if isinstance(x.args[0], PollStatus)
        ]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertEqual(1, msg.data.voted)
