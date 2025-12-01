from datetime import datetime
from datetime import timedelta
from datetime import timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.agenda.models import AgendaItem
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER
from voteit.meeting.roles import ROLE_PROPOSER
from voteit.speaker.models import Speaker
from voteit.speaker.models import SpeakerList
from voteit.speaker.models import SpeakerListSystem

User = get_user_model()


class SpeakerListSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.ai = cls.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.slist: SpeakerList = cls.system.speaker_lists.create(agenda_item=cls.ai)
        cls.participant = User.objects.get(username="participant")
        cls.moderator = User.objects.get(username="moderator")
        cls.participant_speaker = cls.slist.speaker_items.create(user=cls.participant)
        cls.moderator_speaker = cls.slist.speaker_items.create(user=cls.moderator)
        cls.participant_speaker.start()
        cls.participant_speaker.save()
        cls.slist.reorder()

    @property
    def _cut(self):
        from voteit.speaker.rest_api.serializers import SpeakerListSerializer

        return SpeakerListSerializer

    def test_get(self):
        # Queue is not part of this
        serializer = self._cut(self.slist)
        data = serializer.data
        self.assertEqual(
            {
                "pk": self.slist.pk,
                "title": "",
                "speaker_system": self.system.pk,
                "agenda_item": self.ai.pk,
                "state": "open",
                "queue": [self.participant.pk, self.moderator.pk],
                "current": self.participant.pk,
                "room": self.room.pk,
                "meeting": self.meeting.pk,
            },
            data,
        )

    def test_patch(self):
        serializer = self._cut(self.slist, {"title": "Hello"}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.slist.title, "Hello")


class HistoricSpeakerListSerializerTests(TestCase):
    @property
    def _cut(self):
        from voteit.speaker.rest_api.serializers import HistoricSpeakerListSerializer

        return HistoricSpeakerListSerializer

    def test_get(self):
        # Queue is not part of this
        serializer = self._cut(
            {
                "user": 1,
                "times_spoken": 3,
                "seconds_spoken": 200,
            }
        )
        data = serializer.data
        self.assertEqual(data["user"], 1)
        self.assertEqual(data["times_spoken"], 3)
        self.assertEqual(data["seconds_spoken"], 200)


class SpeakerListSystemSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        # self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.room = cls.meeting.rooms.create()
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", state="active", room=cls.room
        )
        cls.slist = cls.system.speaker_lists.create()

    @property
    def _cut(self):
        from voteit.speaker.rest_api.serializers import SpeakerListSystemSerializer

        return SpeakerListSystemSerializer

    def test_get(self):
        # Queue is not part of this
        serializer = self._cut(self.system)
        data = serializer.data
        self.assertEqual(
            {
                "pk": self.system.pk,
                "meeting": self.meeting.pk,
                "method_name": "simple",
                "settings": None,
                "safe_positions": None,
                "state": "active",
                "active_list": None,
                "meeting_roles_to_speaker": [],
                "room": self.room.pk,
                "show_time": False,
            },
            data,
        )

    def test_patch(self):
        serializer = self._cut(
            self.system,
            {"active_list": self.slist.pk},
            partial=True,
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.slist, self.system.active_list)

    def test_patch_meeting_roles_to_speaker_bad_roles(self):
        serializer = self._cut(
            self.system,
            data={"meeting_roles_to_speaker": ["Hello"]},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("meeting_roles_to_speaker", serializer.errors)

    def test_patch_meeting_roles_to_speaker(self):
        serializer = self._cut(
            self.system,
            data={"meeting_roles_to_speaker": [ROLE_POTENTIAL_VOTER, ROLE_PROPOSER]},
            partial=True,
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(
            self.system.meeting_roles_to_speaker, [ROLE_POTENTIAL_VOTER, ROLE_PROPOSER]
        )

    def test_patch_with_settings(self):
        serializer = self._cut(
            self.system,
            {"method_name": "priority", "settings": {"max_times": 3}},
            partial=True,
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.system.settings.max_times, 3)
        serializer = self._cut(self.system)
        self.assertEqual({"max_times": 3}, serializer.data["settings"])


class SpeakerExportSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.get(pk=1)
        cls.room = cls.meeting.rooms.create()
        cls.ai: AgendaItem = cls.meeting.agenda_items.create(
            state="ongoing", title="Ongoing"
        )
        cls.system: SpeakerListSystem = cls.meeting.speaker_systems.create(
            method_name="simple", room=cls.room
        )
        cls.slist1: SpeakerList = cls.system.speaker_lists.create(
            agenda_item=cls.ai, title="SpeakerList 1"
        )
        cls.slist2: SpeakerList = cls.system.speaker_lists.create(
            agenda_item=cls.ai, title="SpeakerList 2"
        )
        cls.slist3: SpeakerList = cls.system.speaker_lists.create(
            agenda_item=cls.ai, title="SpeakerList 3"
        )
        speaker_lists = [cls.slist1, cls.slist2, cls.slist3]
        cls.user_one: User = cls.slist1.speakers.create(
            username="one", first_name="One", last_name="Usersson"
        )
        cls.user_two: User = cls.slist1.speakers.create(
            username="two", first_name="Two", last_name="Usersson"
        )
        cls.user_three: User = cls.slist1.speakers.create(
            username="three", first_name="Three", last_name="Usersson"
        )
        cls.meeting.add_roles(cls.user_one, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.user_two, ROLE_PARTICIPANT)
        cls.meeting.add_roles(cls.user_three, ROLE_PARTICIPANT)
        users = [cls.user_one, cls.user_two, cls.user_three]
        ts = datetime(2025, 12, 1, 10, 0, tzinfo=timezone.utc)
        # Add spoken time
        for ui in range(3):
            user = users[ui]
            for i in range(1, 4):
                slist = speaker_lists[i - 1]
                slist.speaker_items.create(
                    user=user,
                    seconds=i + ui,
                    # Make sure there's a diff between started, since it's sorted on that
                    started=ts + timedelta(seconds=i * (ui + 1)),
                )

    @property
    def _cut(self):
        from voteit.speaker.rest_api.serializers import SpeakerExportSerializer

        return SpeakerExportSerializer

    def get_export_qs(self):
        return (
            Speaker.objects.filter(speaker_list__speaker_system=self.system)
            .exclude(seconds__isnull=True)
            .select_related("speaker_list", "user", "speaker_list__agenda_item")
            .order_by("started")
        )

    def test_data(self):
        serializer = self._cut(self.get_export_qs(), many=True)
        data = serializer.data
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 9)
        self.assertSetEqual(
            {
                "email",
                "agenda_item",
                "seconds",
                "last_name",
                "first_name",
                "started",
                "speaker_list",
                "created",
                "userid",
            },
            set(data[0]),
        )

        self.assertDictEqual(
            {
                "agenda_item": "Ongoing",
                "email": "",
                "first_name": "One",
                "last_name": "Usersson",
                "seconds": 1,
                "speaker_list": "SpeakerList 1",
                "started": "2025-12-01T11:00:01+01:00",
                "userid": None,
            },
            {k: v for k, v in data[0].items() if k not in ("created",)},
        )

    def test_n1(self):
        with self.assertNumQueries(1):
            serializer = self._cut(self.get_export_qs(), many=True)
            _ = serializer.data
