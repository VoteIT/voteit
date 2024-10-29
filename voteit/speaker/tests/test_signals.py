from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from django_fsm import TransitionNotAllowed
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.channels.models import ContextChannel
from envelope.testing import MessageCatcher

from voteit.agenda.channels import AgendaItemChannel
from voteit.core.testing import FakeCommit
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.speaker.channels import SpeakerListSystemChannel
from voteit.speaker.messages import SpeakerListAdded
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.workflows import SpeakerListWf
from voteit.speaker.workflows import SpeakerSystemWf

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SpeakerListSystemAppStateTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple",
            room=cls.room,
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai, title="Hello"
        )
        cls.speaker = cls.speaker_list.speaker_items.create(user=cls.participant)
        for _ in range(4):
            cls.speaker_list.speaker_items.create(
                user=cls.participant, seconds=123, started=now()
            )

    def test_stopped_speakers_sent(self):
        self.system.active_list = self.speaker_list
        self.system.save()
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.system.pk,
            channel_type=SpeakerListSystemChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        self.assertEqual(self.speaker_list.historic_speakers().count(), 4)
        self.assertEqual(
            sum(x.t == "speaker.added" for x in msg.data.app_state),
            4,
        )


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalListChangeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system = SpeakerListSystem.objects.create(
            method_name="simple", room=cls.room
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
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
        self.speaker_list.title = "Hej"
        self.speaker_list.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        data = msg.data
        self.assertEqual(
            [self.user_one.pk, self.user_two.pk, self.user_three.pk], data.queue
        )
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertIsNone(data.current)

    @patch.object(SpeakerListSystemChannel, "sync_publish")
    def test_sls_gets_active_list(self, mock_publish):
        self.system.active_list = self.speaker_list
        self.system.save()
        mock_publish.reset_mock()  # Remove above calls
        self.speaker_list.title = "Hello"
        self.speaker_list.save()
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
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[-1].args[0]
        data = msg.data
        self.assertEqual([self.user_one.pk, self.user_two.pk], data.queue)
        self.assertEqual(self.speaker_list.pk, data.pk)
        self.assertEqual(self.user_three.pk, data.current)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalListChangesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", room=cls.room
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai, title="Hello"
        )
        cls.speaker = cls.speaker_list.speaker_items.create(user=cls.participant)
        cls.speaker_moderator = cls.speaker_list.speaker_items.create(
            user=cls.moderator
        )

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

    @patch.object(AgendaItemChannel, "sync_publish")
    def test_ai_gets_active_list_changed(self, mock_publish):
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

    @patch.object(SpeakerListSystemChannel, "sync_publish")
    def test_system_gets_active_list_changed(self, mock_publish):
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

    def test_system_get_speaker_order(self):
        self.system.active_list = self.speaker_list
        self.system.save()
        self.speaker_list.start_speaker(self.speaker_moderator)
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.participant.pk},
            pk=self.system.pk,
            channel_type=SpeakerListSystemChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        changed_message = list(
            m for m in msg.data.app_state if m.t == SpeakerListAdded.name
        )
        self.assertTrue(
            changed_message, "There should be a speaker_list.changed message"
        )
        msg = changed_message[0]
        self.assertEqual(
            msg.p["current"],
            self.moderator.pk,
            "Participant is currently speaking",
        )
        self.assertEqual(
            msg.p["queue"],
            [self.participant.pk],
            "Participant is in queue",
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_list_deleted(self, mock_publish):
        from voteit.speaker.messages import SpeakerListDeleted

        list_pk = self.speaker_list.pk
        self.speaker_list.delete()
        self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if x.args[0].name == SpeakerListDeleted.name
        ]
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, SpeakerListDeleted)
        self.assertEqual(list_pk, msg.data.pk)

    @patch.object(ContextChannel, "sync_publish")  # All of them here
    def test_list_deleted_event_order(self, mock_publish):
        from voteit.speaker.messages import SpeakerListChanged
        from voteit.speaker.messages import SpeakerListDeleted

        self.speaker_list.start_speaker(self.speaker)
        mock_publish.reset_mock()
        with self.captureOnCommitCallbacks(execute=True):
            self.speaker_list.delete()
            self.assertTrue(mock_publish.called)
        messages = [
            x.args[0]
            for x in mock_publish.mock_calls
            if x.args[0].name.startswith("speaker")
        ]
        changed_positions = [
            messages.index(x) for x in messages if isinstance(x, SpeakerListChanged)
        ]
        deleted_positions = [
            messages.index(x) for x in messages if isinstance(x, SpeakerListDeleted)
        ]
        self.assertEqual(1, len(deleted_positions))
        deleted_pos = deleted_positions[0]
        for pos in changed_positions:
            self.assertLess(pos, deleted_pos)

    def test_exception_when_trying_to_close_ai_with_active_speaker(self):
        self.speaker_list.start_speaker(self.speaker)
        with self.assertRaises(TransitionNotAllowed):
            self.ai.close()

    def test_close_lists_automatically_when_ai_closes(self):
        self.system.active_list = self.speaker_list
        self.assertTrue(self.speaker_list.is_active_list)
        self.system.save()
        self.ai.close()
        self.speaker_list.refresh_from_db()
        self.assertFalse(self.speaker_list.is_active_list)
        self.assertEqual(SpeakerListWf.CLOSED, self.speaker_list.state)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalSystemChangesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple", room=cls.room
        )

    @patch.object(MeetingChannel, "sync_publish")
    def test_system_changed(self, mock_publish):
        from voteit.speaker.messages import SpeakerSystemChanged

        self.system.safe_positions = 5
        self.system.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, SpeakerSystemChanged)
        data = msg.data
        self.assertEqual(self.system.pk, data.pk)
        self.assertEqual(self.meeting.pk, data.meeting)
        self.assertEqual(self.system.safe_positions, data.safe_positions)

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

        list_one: SpeakerList = self.system.speaker_lists.create()
        mock_publish.reset_mock()
        self.system.active_list = list_one
        with FakeCommit():
            self.system.save()
        messages = [x.args[0] for x in mock_publish.mock_calls]
        message_names = [x.name for x in messages]
        self.assertIn(SpeakerSystemChanged.name, message_names)
        self.assertEqual(list_one.pk, messages[0].data.active_list)
        self.assertIn(SpeakerListChanged.name, message_names)
        self.assertEqual(list_one.pk, messages[1].data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class ChannelSubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.ai.upcoming()
        cls.ai.save()
        cls.system = SpeakerListSystem.objects.create(
            method_name="simple",
            meeting=cls.meeting,
            state=SpeakerSystemWf.ACTIVE,
            room=cls.room,
        )
        # Create lists
        cls.other_list = cls.system.speaker_lists.create(agenda_item=cls.ai)
        cls.active_list = cls.system.speaker_lists.create(agenda_item=cls.ai)
        cls.system.active_list = cls.active_list
        cls.system.save()
        # Create speakers
        cls.user_one = User.objects.create(username="one")
        cls.user_two = User.objects.create(username="two")
        cls.speaker_one = cls.active_list.speaker_items.create(user=cls.user_one)
        cls.speaker_two = cls.active_list.speaker_items.create(user=cls.user_two)
        # Start speaker
        cls.active_list.start_speaker(cls.speaker_one)
        # Moderator
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_PARTICIPANT)
        cls.system.add_roles(cls.moderator, ROLE_LIST_MODERATOR)

    def _mk_one(self, pk, channel_type):
        return Subscribe(
            mm={"user_pk": self.moderator.pk, "consumer_name": "abc"},
            pk=pk,
            channel_type=channel_type,
        )

    def test_subscribe_meeting(self):
        command = self._mk_one(self.meeting.pk, "meeting")
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        response = messages[0]
        self.assertIsInstance(response, Subscribed)
        appstates = {x.t: x.p for x in response.data.app_state}
        self.assertIn("speaker_system.added", appstates)
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
        command = self._mk_one(self.ai.pk, "agenda_item")
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        response = messages[0]
        self.assertIsInstance(response, Subscribed)
        payloads = [
            x.p for x in response.data.app_state if x.t == SpeakerListAdded.name
        ]
        self.assertEqual(2, len(payloads))
        self.assertEqual(
            {self.active_list.pk, self.other_list.pk}, {x["pk"] for x in payloads}
        )

    def test_subscribe_speaker_list_system(self):
        command = self._mk_one(self.system.pk, SpeakerListSystemChannel.name)
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        response = messages[0]
        self.assertIsInstance(response, Subscribed)
        speaker_payloads = [
            x.p for x in response.data.app_state if x.t == "speaker.added"
        ]
        self.assertEqual(1, len(speaker_payloads))
        data = speaker_payloads[0]
        self.assertEqual(self.speaker_one.pk, data.pop("pk"))
        self.assertEqual(self.active_list.pk, data.pop("speaker_list"))
        self.assertIsInstance(data.pop("started"), datetime)
        self.assertIsNone(data.pop("seconds"))
        self.assertEqual(self.user_one.pk, data.pop("user"))
        self.assertEqual(self.system.pk, data.pop("sls"))
        self.assertFalse(data)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RolesRelationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.user = User.objects.create(username="jane")

    def test_removing_participant_removes_system_roles(self):
        self.meeting.add_roles(self.user, ROLE_PARTICIPANT)
        self.system.add_roles(self.user, "speaker")
        self.meeting.remove_roles(self.user, ROLE_PARTICIPANT)
        self.assertFalse(self.system.get_roles(self.user))

    def test_adding_system_roles_adds_participant(self):
        self.system.add_roles(self.user, "speaker")
        self.assertTrue(self.meeting.get_roles(self.user))


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SpeakerSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple",
            meeting=cls.meeting,
            room=cls.room,
            state=SpeakerSystemWf.ACTIVE,
        )
        cls.active_speaker_list = cls.system.speaker_lists.create()
        cls.system.active_list = cls.active_speaker_list
        cls.system.save()
        cls.inactive_speaker_list = cls.system.speaker_lists.create()
        cls.user = User.objects.create(username="le_speaker")
        cls.active_speaker = cls.active_speaker_list.speaker_items.create(user=cls.user)
        cls.inactive_speaker = cls.inactive_speaker_list.speaker_items.create(
            user=cls.user
        )

    @patch.object(SpeakerListSystemChannel, "sync_publish")
    def test_speaker_changed_nothing_special(self, mock_publish):
        with FakeCommit():
            self.inactive_speaker.save()
        self.assertFalse(mock_publish.called)

        with FakeCommit():
            # All updates are sent for active lists
            self.active_speaker.save()
        self.assertTrue(mock_publish.called)

    @patch.object(SpeakerListSystemChannel, "sync_publish")
    def test_speaker_changed_and_started(self, mock_publish):
        with FakeCommit():
            self.inactive_speaker.started = now()
            self.inactive_speaker.save()
        self.assertFalse(mock_publish.called)
        with FakeCommit():
            self.active_speaker.started = now()
            self.active_speaker.save()
        self.assertTrue(mock_publish.called)
        self.assertIn(
            "speaker.changed", [x.args[0].name for x in mock_publish.mock_calls]
        )

    @patch.object(SpeakerListSystemChannel, "sync_publish")
    def test_speaker_deleted(self, mock_publish):
        self.inactive_speaker.delete()
        self.assertFalse(mock_publish.called)
        self.active_speaker.delete()
        self.assertTrue(mock_publish.called)
        self.assertIn(
            "speaker.deleted", [x.args[0].name for x in mock_publish.mock_calls]
        )

    @patch.object(SpeakerListSystemChannel, "sync_publish")
    def test_previous_speaker_changed(self, mock_publish):
        self.inactive_speaker.seconds = 10
        self.inactive_speaker.started = now()
        self.inactive_speaker.save()
        self.active_speaker.seconds = 10
        self.active_speaker.started = now()
        self.active_speaker.save()
        mock_publish.reset_mock()

        with FakeCommit():
            self.inactive_speaker.seconds = 1
            self.inactive_speaker.save()
        self.assertFalse(mock_publish.called)
        with FakeCommit():
            self.active_speaker.seconds = 2
            self.active_speaker.save()
        self.assertTrue(mock_publish.called)
        self.assertIn(
            "speaker.changed", [x.args[0].name for x in mock_publish.mock_calls]
        )
