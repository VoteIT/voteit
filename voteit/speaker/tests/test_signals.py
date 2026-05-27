from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from django.utils.timezone import now
from django_fsm import TransitionNotAllowed
from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed
from envelope.messages.common import Batch
from envelope.testing import ChannelMessageCatcher
from envelope.testing import MessageCatcher
from envelope.testing import testing_channel_layers_setting

from voteit.agenda.channels import AgendaItemChannel
from voteit.core.messages.role_updates import RolesAdded
from voteit.meeting.channels import MeetingChannel
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.workflows import MeetingWf
from voteit.room.channels import RoomChannel
from voteit.speaker.messages import SpeakerAdded
from voteit.speaker.messages import SpeakerChanged
from voteit.speaker.messages import SpeakerDeleted
from voteit.speaker.messages import SpeakerListAdded
from voteit.speaker.messages import SpeakerListChanged
from voteit.speaker.messages import SpeakerListDeleted
from voteit.speaker.messages import SpeakerSystemAdded
from voteit.speaker.messages import SpeakerSystemChanged
from voteit.speaker.messages import SpeakerSystemDeleted
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem
from voteit.speaker.roles import ROLE_LIST_MODERATOR
from voteit.speaker.roles import ROLE_SPEAKER
from voteit.speaker.workflows import SpeakerListWf
from voteit.speaker.workflows import SpeakerSystemWf

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class WFEffectsTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.moderator = User.objects.get(username="moderator")
        cls.meeting = Meeting.objects.get(pk=1)
        cls.meeting.ongoing()
        cls.meeting.save()
        cls.room = cls.meeting.rooms.create()
        cls.ai = cls.meeting.agenda_items.create()
        cls.system: SpeakerListSystem = SpeakerListSystem.objects.create(
            method_name="simple",
            room=cls.room,
        )
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai, title="Hello"
        )
        cls.speaker = cls.speaker_list.speaker_items.create(
            user=cls.moderator, started=now()
        )

    def test_ai(self):
        with self.assertRaises(TransitionNotAllowed) as cm:
            self.ai.close()
        self.assertEqual("Finish active speaker first", str(cm.exception))
        self.speaker.stop()
        self.speaker.save()
        self.ai.close()

    def test_meeting(self):
        with self.assertRaises(TransitionNotAllowed) as cm:
            self.meeting.close()
        self.assertEqual(
            "Finish active speaker on speaker list Hello first!", str(cm.exception)
        )
        self.speaker.stop()
        self.speaker.save()
        self.meeting.close()

    def test_close_lists_automatically_when_ai_closes(self):
        self.speaker.delete()
        self.system.active_list = self.speaker_list
        self.system.save()
        self.assertTrue(self.speaker_list.is_active_list)
        self.ai.close()
        self.system.refresh_from_db()
        self.speaker_list.refresh_from_db()
        self.assertFalse(self.speaker_list.is_active_list)
        self.assertEqual(SpeakerListWf.CLOSED, self.speaker_list.state)
        self.assertIsNone(self.system.active_list)

    def test_archive_meeting_archives_systems(self):
        self.meeting.archive()
        self.meeting.save()
        self.system.refresh_from_db()
        self.assertEqual(MeetingWf.ARCHIVED, self.meeting.state)
        self.assertEqual(SpeakerSystemWf.ARCHIVED, self.system.state)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class AppStateTests(TestCase):
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
        cls.system.add_roles(cls.participant, ROLE_SPEAKER)
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai, title="Hello"
        )
        cls.speaker = cls.speaker_list.speaker_items.create(user=cls.participant)
        for _ in range(4):
            cls.speaker_list.speaker_items.create(
                user=cls.participant, seconds=123, started=now()
            )

    def test_speakers_sent_to_room_if_active(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.room.pk,
            channel_type=RoomChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        self.assertEqual(self.speaker_list.speaker_items.count(), 5)
        self.assertEqual(sum(x.t == SpeakerAdded.name for x in msg.data.app_state), 0)
        self.system.active_list = self.speaker_list
        self.system.save()
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        self.assertEqual(sum(x.t == SpeakerAdded.name for x in msg.data.app_state), 5)

    def test_dont_kill_signal_when_room_changes(self):
        self.system.delete()
        self.room.refresh_from_db()
        self.room.save()
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.room.pk,
            channel_type=RoomChannel.name,
        )
        with MessageCatcher(Subscribed):
            command.run_job()

    def test_system_and_roles_sent_to_meeting(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.participant.pk},
            pk=self.meeting.pk,
            channel_type=MeetingChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        system_payload = [
            x.p for x in msg.data.app_state if x.t == SpeakerSystemAdded.name
        ]
        self.assertEqual(1, len(system_payload))
        self.assertEqual(
            {
                "active_list": None,
                "meeting": self.meeting.pk,
                "meeting_roles_to_speaker": [],
                "method_name": "simple",
                "pk": self.system.pk,
                "room": self.room.pk,
                "safe_positions": None,
                "settings": None,
                "show_time": False,
                "state": SpeakerSystemWf.ACTIVE,
            },
            system_payload[0],
        )
        speaker_roles_payload = [
            x.p
            for x in msg.data.app_state
            if x.t == RolesAdded.name and ROLE_SPEAKER in x.p["roles"]
        ]
        self.assertEqual(1, len(speaker_roles_payload))
        self.assertEqual(
            {
                "model": "speaker_system",
                "pk": self.system.pk,
                "roles": [ROLE_SPEAKER],
                "user_pk": self.participant.pk,
            },
            speaker_roles_payload[0],
        )

    def test_lists_sent_to_agenda_item(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.ai.pk,
            channel_type=AgendaItemChannel.name,
        )
        with MessageCatcher(Subscribed) as messages:
            command.run_job()
        self.assertEqual(1, len(messages))
        msg = messages[0]
        self.assertIsInstance(msg, Subscribed)
        self.assertEqual(
            sum(x.t == SpeakerListAdded.name for x in msg.data.app_state), 1
        )
        speaker_lists_added = [
            x.p for x in msg.data.app_state if x.t == SpeakerListAdded.name
        ]
        self.assertEqual(1, len(speaker_lists_added))
        self.assertEqual(
            {
                "speaker_system": self.system.pk,
                "agenda_item": self.ai.pk,
                "queue": [],
                "current": None,
                "state": SpeakerListWf.OPEN,
                "title": "Hello",
                "pk": self.speaker_list.pk,
                "room": self.room.pk,
                "meeting": self.meeting.pk,
            },
            speaker_lists_added[0],
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class SendStateChangesTestsTests(TestCase):
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
        cls.system.add_roles(cls.participant, ROLE_SPEAKER)
        cls.speaker_list: SpeakerList = SpeakerList.objects.create(
            speaker_system=cls.system, agenda_item=cls.ai, title="Hello"
        )
        cls.speaker = cls.speaker_list.speaker_items.create(user=cls.participant)

    def test_room_channel_receives_active_list_changed(self):
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            self.system.active_list = None
            self.system.save()
        self.assertFalse(messages)
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged, Batch) as messages:
            self.system.active_list = self.speaker_list
            self.system.save()
        self.assertEqual(2, len(messages))
        self.assertEqual(
            {
                "agenda_item": self.ai.pk,
                "pk": self.speaker_list.pk,
                "queue": [],
                "current": None,
                "speaker_system": self.system.pk,
                "state": "open",
                "title": "Hello",
                "room": self.room.pk,
                "meeting": self.meeting.pk,
            },
            messages[0].data.dict(),
        )
        self.assertDictEqual(
            {
                "t": SpeakerAdded.name,
                "payloads": [
                    {
                        "user": self.participant.pk,
                        "pk": self.speaker.pk,
                        "room": self.room.pk,
                        "started": None,
                        "seconds": None,
                        "speaker_list": self.speaker_list.pk,
                    }
                ],
            },
            messages[1].data.dict(),
        )
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            # Same list
            self.system.active_list = self.speaker_list
            self.system.save()
        self.assertEqual(0, len(messages))
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            # Same but with id
            self.system.active_list_id = self.speaker_list.pk
            self.system.save()
        self.assertEqual(0, len(messages))
        # and loaded from db
        system = self.meeting.speaker_systems.get(pk=self.system.pk)
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            # Same but with id
            system.active_list_id = self.speaker_list.pk
            system.save()
        self.assertEqual(0, len(messages))
        # With refresh
        self.system._initial_active_list_id = None
        self.system.refresh_from_db()
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            self.system.active_list_id = self.speaker_list.pk
            self.system.save()
        self.assertEqual(0, len(messages))
        # None can't generate any message
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            self.system.active_list_id = None
            self.system.save()
        self.assertEqual(0, len(messages))

    def test_meeting_channel_receives_system_added(self):
        new_room = self.meeting.rooms.create()
        with ChannelMessageCatcher(MeetingChannel, SpeakerSystemAdded) as messages:
            new_system = self.meeting.speaker_systems.create(
                method_name="simple", room=new_room, safe_positions=2
            )
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "active_list": None,
                "meeting": self.meeting.pk,
                "meeting_roles_to_speaker": [],
                "method_name": "simple",
                "pk": new_system.pk,
                "room": new_room.pk,
                "safe_positions": 2,
                "settings": None,
                "show_time": False,
                "state": SpeakerSystemWf.ACTIVE,
            },
            messages[0].data.dict(),
        )

    def test_meeting_channel_receives_system_changed(self):
        with ChannelMessageCatcher(MeetingChannel, SpeakerSystemChanged) as messages:
            self.system.save()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "active_list": None,
                "meeting": self.meeting.pk,
                "meeting_roles_to_speaker": [],
                "method_name": "simple",
                "pk": self.system.pk,
                "room": self.room.pk,
                "safe_positions": None,
                "settings": None,
                "show_time": False,
                "state": SpeakerSystemWf.ACTIVE,
            },
            messages[0].data.dict(),
        )

    def test_meeting_channel_receives_system_deleted(self):
        system_pk = self.system.pk
        with ChannelMessageCatcher(MeetingChannel, SpeakerSystemDeleted) as messages:
            self.system.delete()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "pk": system_pk,
            },
            messages[0].data.dict(),
        )

    def test_ai_channel_receives_list_added(self):
        with ChannelMessageCatcher(AgendaItemChannel, SpeakerListAdded) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                new_list = self.ai.speaker_lists.create(speaker_system=self.system)
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "agenda_item": self.ai.pk,
                "speaker_system": self.system.pk,
                "pk": new_list.pk,
                "state": SpeakerListWf.OPEN,
                "queue": [],
                "current": None,
                "title": "",
                "room": self.room.pk,
                "meeting": self.meeting.pk,
            },
            messages[0].data.dict(),
        )

    def test_ai_channel_receives_list_changed(self):
        with ChannelMessageCatcher(AgendaItemChannel, SpeakerListChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker_list.title = "Hello"
                self.speaker_list.save()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "speaker_system": self.system.pk,
                "pk": self.speaker_list.pk,
                "state": SpeakerListWf.OPEN,
                "title": "Hello",
                "agenda_item": self.ai.pk,
                "queue": [],
                "current": None,
                "room": self.room.pk,
                "meeting": self.meeting.pk,
            },
            messages[0].data.dict(),
        )

    def test_ai_channel_receives_list_deleted(self):
        list_pk = self.speaker_list.pk
        with ChannelMessageCatcher(AgendaItemChannel, SpeakerListDeleted) as messages:
            self.speaker_list.delete()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "pk": list_pk,
            },
            messages[0].data.dict(),
        )

    def test_room_channel_ignores_list_added(self):
        with ChannelMessageCatcher(RoomChannel, SpeakerListAdded) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.ai.speaker_lists.create(speaker_system=self.system)
        self.assertEqual(0, len(messages))

    def test_room_channel_receives_list_changed_if_active(self):
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker_list.title = "Hello"
                self.speaker_list.save()
        self.assertEqual(0, len(messages))
        self.system.active_list = self.speaker_list
        self.system.save()
        with ChannelMessageCatcher(RoomChannel, SpeakerListChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker_list.title = "Hello"
                self.speaker_list.save()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "speaker_system": self.system.pk,
                "pk": self.speaker_list.pk,
                "state": SpeakerListWf.OPEN,
                "title": "Hello",
                "agenda_item": self.ai.pk,
                "queue": [],
                "current": None,
                "room": self.room.pk,
                "meeting": self.meeting.pk,
            },
            messages[0].data.dict(),
        )

    def test_room_channel_receives_speaker_added_if_active(self):
        with ChannelMessageCatcher(RoomChannel, SpeakerAdded) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                speaker = self.speaker_list.speaker_items.create(user=self.moderator)
        self.assertEqual(0, len(messages))
        self.system.active_list = self.speaker_list
        self.system.save()
        speaker.delete()
        with ChannelMessageCatcher(RoomChannel, SpeakerAdded) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                speaker = self.speaker_list.speaker_items.create(user=self.moderator)
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "speaker_list": self.speaker_list.pk,
                "pk": speaker.pk,
                "seconds": None,
                "started": None,
                "user": self.moderator.pk,
                "room": self.room.pk,
            },
            messages[0].data.dict(),
        )

    def test_room_channel_receives_speaker_changed_if_active(self):
        with ChannelMessageCatcher(RoomChannel, SpeakerChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker.save()
        self.assertEqual(0, len(messages))
        self.system.active_list = self.speaker_list
        self.system.save()
        with ChannelMessageCatcher(RoomChannel, SpeakerChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker.save()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "speaker_list": self.speaker_list.pk,
                "pk": self.speaker.pk,
                "seconds": None,
                "started": None,
                "user": self.participant.pk,
                "room": self.room.pk,
            },
            messages[0].data.dict(),
        )

    def test_room_channel_receives_speaker_deleted_if_active(self):
        speaker = self.speaker_list.speaker_items.create(user=self.moderator)
        with ChannelMessageCatcher(RoomChannel, SpeakerDeleted) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                speaker.delete()
        self.assertEqual(0, len(messages))
        self.system.active_list = self.speaker_list
        self.system.save()
        speaker_pk = self.speaker.pk
        with ChannelMessageCatcher(RoomChannel, SpeakerDeleted) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker.delete()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "pk": speaker_pk,
            },
            messages[0].data.dict(),
        )

    def test_ai_channel_receives_speaker_changed_if_active(self):
        with ChannelMessageCatcher(AgendaItemChannel, SpeakerChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker.save()
        self.assertEqual(0, len(messages))
        self.system.active_list = self.speaker_list
        self.system.save()
        with ChannelMessageCatcher(RoomChannel, SpeakerChanged) as messages:
            with self.captureOnCommitCallbacks(execute=True):
                self.speaker.save()
        self.assertEqual(1, len(messages))
        self.assertEqual(
            {
                "speaker_list": self.speaker_list.pk,
                "pk": self.speaker.pk,
                "seconds": None,
                "started": None,
                "user": self.participant.pk,
                "room": self.room.pk,
            },
            messages[0].data.dict(),
        )


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
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
        self.assertFalse(self.meeting.get_roles(self.user))

        self.system.add_roles(self.user, "speaker")
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.user))

    def test_adding_moderator(self):
        self.system.add_roles(self.user, ROLE_LIST_MODERATOR)
        self.assertEqual({ROLE_PARTICIPANT}, self.meeting.get_roles(self.user))
