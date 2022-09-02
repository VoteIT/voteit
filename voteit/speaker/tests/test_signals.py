from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils import timezone
from pytz import UTC

from envelope.messages.channels import Subscribe
from envelope.messages.channels import Subscribed

from voteit.agenda.channels import AgendaItemChannel
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.channels import ModeratorsChannel
from voteit.speaker.messages import SpeakerStopped

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalListOrderChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):

        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        from voteit.meeting.models import Meeting

        cls.meeting = Meeting.objects.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system = SpeakerListSystem.objects.create(
            method_name="simple", meeting=cls.meeting
        )
        cls.speaker_list = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai
        )
        cls.user_one = User.objects.create(username="one")
        cls.user_two = User.objects.create(username="two")
        cls.user_three = User.objects.create(username="three")
        cls.speaker_one = cls.speaker_list.speaker_items.create(user=cls.user_one)
        cls.speaker_two = cls.speaker_list.speaker_items.create(user=cls.user_two)
        cls.speaker_three = cls.speaker_list.speaker_items.create(user=cls.user_three)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_agenda_gets_list_change(self, mock_publish):
        self.speaker_list.signal_list_updated()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk], data.queue
        )
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertIsNone(data.current)

    @patch.object(MeetingChannel, "sync_publish")
    def test_meeting_gets_active_list(self, mock_publish):
        self.system.active_list = self.speaker_list
        self.system.save()
        mock_publish.reset_mock()  # Remove above calls
        self.speaker_list.signal_list_updated()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk], data.queue
        )
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertIsNone(data.current)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_agenda_with_active_speaker(self, mock_publish):
        self.speaker_list.start_speaker(self.speaker_three)
        self.speaker_list.signal_list_updated()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[-1].args[0]
        data = msg.data
        self.assertEqual([self.user_one.pk, self.user_two.pk], data.queue)
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertEqual(self.user_three.pk, data.current)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalStartedStoppedTests(TestCase):
    def setUp(self):

        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList
        from voteit.speaker.models import Speaker

        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        # self.ai = self.meeting.agenda_items.create()
        self.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", meeting=self.meeting
        )
        self.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=self.system, title="Hello"  # agenda_item=self.ai
        )
        self.system.active_list = self.speaker_list
        self.system.save()
        self.user: User = self.meeting.participants.create(username="user")
        self.speaker: Speaker = self.speaker_list.speaker_items.create(user=self.user)

    @patch.object(MeetingChannel, "sync_publish")
    def test_start_speaker(self, mock_publish):
        from voteit.speaker.messages import SpeakerStarted

        self.speaker_list.start_speaker(self.speaker)
        self.assertTrue(mock_publish.called)
        msg = None
        for mcall in mock_publish.mock_calls:
            if isinstance(mcall.args[0], SpeakerStarted):
                msg = mcall.args[0]
                break
        self.assertIsNotNone(msg, "SpeakerStarted never found in meeting channel")
        data = msg.data
        self.assertEqual(self.speaker.pk, data.pk)
        self.assertEqual(self.speaker.started, data.started)
        self.assertIsNone(data.seconds)

    @patch.object(MeetingChannel, "sync_publish")
    def test_stop_speaker(self, mock_publish):
        from voteit.speaker.messages import SpeakerStopped

        self.speaker_list.start_speaker(self.speaker)
        mock_publish.reset_mock()
        self.speaker_list.stop_speaker()
        self.assertTrue(mock_publish.called)
        msg = None
        for mcall in mock_publish.mock_calls:
            if isinstance(mcall.args[0], SpeakerStopped):
                msg = mcall.args[0]
                break
        self.assertIsNotNone(msg, "SpeakerStopped never found in meeting channel")
        data = msg.data
        self.assertEqual(self.speaker.pk, data.pk)
        self.assertEqual(self.speaker.started, data.started)
        self.assertEqual(1, data.seconds)  # Minimum 1!


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalListChangesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):

        from voteit.speaker.models import SpeakerListSystem
        from voteit.speaker.models import SpeakerList

        from voteit.meeting.models import Meeting

        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.ai = cls.meeting.agenda_items.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", meeting=cls.meeting
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai, title="Hello"
        )
        cls.speaker = cls.speaker_list.speaker_items.create(user=cls.participant)

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_agenda_gets_list_changed(self, mock_publish):
        from voteit.speaker.messages import SpeakerListAdded

        speaker_list = self.system.speaker_lists.create(agenda_item=self.ai)
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, SpeakerListAdded)
        data = msg.data
        self.assertEqual("open", data.state)
        self.assertEqual(self.system.pk, data.speaker_system)
        self.assertEqual(speaker_list.pk, data.pk)
        self.assertEqual(self.ai.pk, data.agenda_item)

    @patch.object(MeetingChannel, "sync_publish")
    def test_meeting_gets_active_list_changed(self, mock_publish):
        from voteit.speaker.messages import SpeakerListChanged

        self.system.active_list = self.speaker_list
        self.system.save()
        mock_publish.reset_mock()  # Above lines will have caused calls
        self.speaker_list.title = "world"
        self.speaker_list.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertIsInstance(msg, SpeakerListChanged)
        self.assertEqual(self.system.pk, data.speaker_system)
        self.assertEqual(self.ai.pk, data.agenda_item)
        self.assertEqual(self.speaker_list.title, data.title)

    def test_moderators_get_stopped_speakers(self):
        self.system.active_list = self.speaker_list
        self.system.save()
        for _ in range(4):
            self.speaker_list.speaker_items.create(user=self.participant, seconds=123)
        msg = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.meeting.pk,
            channel_type=ModeratorsChannel.name,
        ).run_job()
        self.assertEqual(self.speaker_list.history_qs().count(), 4)
        self.assertEqual(
            sum(x.t == "speaker.stopped" for x in msg.data.app_state),
            3,
            "Only 3 latest are sent automatically. Other fetched by REST call.",
        )

    def test_meeting_get_speaker_order(self):
        self.system.active_list = self.speaker_list
        self.system.save()
        for _ in range(4):
            self.speaker_list.speaker_items.create(user=self.participant)
            self.speaker_list.start_speaker()
        msg = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.participant.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        ).run_job()
        order_message = next(
            m for m in msg.data.app_state if m.t == "speaker_list.order"
        )
        self.assertTrue(order_message, "There should be a speaker_list.order message")
        self.assertEqual(
            order_message.p["times_spoken"],
            [[self.participant.pk, 3]],
            "Participant spoke 3 times already",
        )
        self.assertEqual(
            order_message.p["current"],
            self.participant.pk,
            "Participant is currently speaking",
        )
        self.assertEqual(
            order_message.p["queue"],
            [self.participant.pk],
            "Participant is in queue",
        )

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_list_deleted(self, mock_publish):
        from voteit.speaker.messages import SpeakerListDeleted

        list_pk = self.speaker_list.pk
        self.speaker_list.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertIsInstance(msg, SpeakerListDeleted)
        self.assertEqual(list_pk, data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalSystemChangesTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", meeting=self.meeting, title="We speak in order"
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_meeting_gets_added(self, mock_publish):
        from voteit.speaker.messages import SpeakerSystemAdded
        from voteit.speaker.models import SpeakerListSystem

        SpeakerListSystem.objects.create(method_name="simple")
        self.assertFalse(mock_publish.called)
        SpeakerListSystem.objects.create(method_name="simple", meeting=self.meeting)
        self.assertTrue(mock_publish.called)

        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, SpeakerSystemAdded)

    @patch.object(MeetingChannel, "sync_publish")
    def test_system_changed(self, mock_publish):
        from voteit.speaker.messages import SpeakerSystemChanged

        self.system.title = "Group 1"
        self.system.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, SpeakerSystemChanged)
        data = msg.data
        self.assertEqual(self.system.pk, data.pk)
        self.assertEqual(self.meeting.pk, data.meeting)
        self.assertEqual(self.system.title, data.title)

    @patch.object(MeetingChannel, "sync_publish")
    def test_system_deleted(self, mock_publish):
        from voteit.speaker.messages import SpeakerSystemDeleted

        system_pk = self.system.pk
        self.system.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, SpeakerSystemDeleted)
        data = msg.data
        self.assertEqual(system_pk, data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_system_changes_active_list(self, mock_publish):
        from voteit.speaker.messages import SpeakerSystemChanged
        from voteit.speaker.messages import SpeakerListChanged
        from voteit.speaker.messages import SpeakerListOrder

        list_one = self.system.speaker_lists.create()
        list_two = self.system.speaker_lists.create()
        user = User.objects.create(username="user")
        list_one.speaker_items.create(user=user)
        list_two.speaker_items.create(user=user)
        mock_publish.reset_mock()
        self.system.active_list = list_one
        self.system.save()
        messages = [x.args[0] for x in mock_publish.mock_calls]
        message_names = [x.name for x in messages]
        self.assertIn(SpeakerSystemChanged.name, message_names)
        self.assertIn(SpeakerListChanged.name, message_names)
        self.assertIn(SpeakerListOrder.name, message_names)
        self.assertEqual(list_one.pk, messages[1].data.pk)
        self.assertEqual([user.pk], messages[2].data.queue)
        mock_publish.reset_mock()
        self.system.active_list = list_two
        self.system.save()
        messages = [x.args[0] for x in mock_publish.mock_calls]
        self.assertEqual(list_two.pk, messages[1].data.pk)

    @patch.object(MeetingChannel, "sync_publish")
    def test_system_changes_active_list_pushes_last_spoken(self, mock_publish):
        list_one = self.system.speaker_lists.create()
        user_one = User.objects.create(username="one")
        user_two = User.objects.create(username="two")
        list_one.speaker_items.create(
            user=user_one, seconds=1, started=datetime(1971, 1, 1, tzinfo=UTC)
        )
        list_one.speaker_items.create(
            user=user_two, seconds=2, started=datetime(1972, 1, 1, tzinfo=UTC)
        )
        list_one.speaker_items.create(
            user=user_one, seconds=3, started=datetime(1973, 1, 1, tzinfo=UTC)
        )
        list_one.speaker_items.create(
            user=user_two, seconds=4, started=datetime(1974, 1, 1, tzinfo=UTC)
        )
        mock_publish.reset_mock()
        self.system.active_list = list_one
        self.system.save()
        messages = [x.args[0] for x in mock_publish.mock_calls]
        message_names = [x.name for x in messages]
        self.assertIn(SpeakerStopped.name, message_names)
        stopped_messages = [x for x in messages if x.name == "speaker.stopped"]
        self.assertEqual(3, len(stopped_messages))
        self.assertEqual(4, stopped_messages[0].data.seconds)
        self.assertEqual(3, stopped_messages[1].data.seconds)
        self.assertEqual(2, stopped_messages[2].data.seconds)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ChannelSubscribedTests(TestCase):
    def setUp(self):
        from voteit.speaker.models import SpeakerListSystem
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.ai = self.meeting.agenda_items.create()
        self.ai.upcoming()
        self.ai.save()
        self.system = SpeakerListSystem.objects.create(
            method_name="simple", meeting=self.meeting, title="We speak in order"
        )
        # Create lists
        self.other_list = self.system.speaker_lists.create(agenda_item=self.ai)
        self.active_list = self.system.speaker_lists.create(agenda_item=self.ai)
        self.system.active_list = self.active_list
        self.system.save()
        # Create speakers
        self.user_one = User.objects.create(username="one")
        self.user_two = User.objects.create(username="two")
        self.speaker_one = self.active_list.speaker_items.create(user=self.user_one)
        self.speaker_two = self.active_list.speaker_items.create(user=self.user_two)
        # Start speaker
        self.active_list.start_speaker(self.speaker_one)
        # Moderator
        self.moderator = User.objects.create(username="moderator")
        self.meeting.add_roles(self.moderator, "participant")
        self.system.add_roles(self.moderator, "list_moderator")

    def _mk_one(self, pk, channel_type):
        return Subscribe(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"},
            pk=pk,
            channel_type=channel_type,
        )

    def test_subscribe_meeting(self):
        msg = self._mk_one(self.meeting.pk, "meeting")
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        appstates = dict((x.t, x.p) for x in response.data.app_state)
        self.assertIn("speaker_system.added", appstates)
        self.assertIn("speaker_list.added", appstates)
        self.assertEqual(
            1,
            sum([1 for x in response.data.app_state if x.t == "speaker_list.added"]),
        )
        self.assertEqual(
            1,
            sum([1 for x in response.data.app_state if x.t == "speaker_list.order"]),
        )
        self.assertEqual(
            1,
            sum([1 for x in response.data.app_state if x.t == "speaker.started"]),
        )
        self.assertEqual(
            [self.user_two.pk],
            appstates["speaker_list.order"]["queue"],
        )

        added_system_roles = [
            x
            for x in response.data.app_state
            if x.t == "roles.added" and x.p["pk"] == self.system.pk
        ]
        self.assertEqual(1, len(added_system_roles))
        payload = added_system_roles[0].p
        self.assertEqual(set(payload["roles"]), {"list_moderator"})
        self.assertEqual(payload["user_pk"], self.moderator.pk)
        self.assertEqual(payload["model"], "speaker_system")

    def test_subscribe_ai(self):
        msg = self._mk_one(self.ai.pk, "agenda_item")
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        appstates = dict((x.t, x.p) for x in response.data.app_state)
        self.assertIn("speaker_list.added", appstates)
        # The active list has already been transmitted
        self.assertEqual(
            1,
            sum([1 for x in response.data.app_state if x.t == "speaker_list.added"]),
        )
        list_added = appstates["speaker_list.added"]
        self.assertEqual(self.other_list.pk, list_added["pk"])
        self.assertEqual(
            1,
            sum([1 for x in response.data.app_state if x.t == "speaker_list.order"]),
        )
        self.assertEqual(
            [],
            appstates["speaker_list.order"]["queue"],
        )


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RolesRelationsTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create()
        self.system = self.meeting.speaker_systems.create(method_name="simple")
        self.user = User.objects.create(username="jane")

    def test_removing_participant_removes_system_roles(self):
        self.meeting.add_roles(self.user, "participant")
        self.system.add_roles(self.user, "speaker")
        self.meeting.remove_roles(self.user, "participant")
        self.assertFalse(self.system.get_roles(self.user))

    def test_adding_system_roles_adds_participant(self):
        self.system.add_roles(self.user, "speaker")
        self.assertTrue(self.meeting.get_roles(self.user))
