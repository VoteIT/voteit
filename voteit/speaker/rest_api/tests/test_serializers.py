from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now


class SpeakerListSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.system = self.meeting.speaker_systems.create(method_name="simple")
        self.slist = self.system.speaker_lists.create(agenda_item=self.ai)

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
        serializer = self._cut({
            "user": 1,
            "times_spoken": 3,
            "seconds_spoken": 200,
        })
        data = serializer.data
        self.assertEqual(data["user"], 1)
        self.assertEqual(data["times_spoken"], 3)
        self.assertEqual(data["seconds_spoken"], 200)


class SpeakerListSystemSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        # self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        cls.system = cls.meeting.speaker_systems.create(
            method_name="simple", state="active"
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
                "title": None,
                "meeting": self.meeting.pk,
                "method_name": "simple",
                "settings": None,
                "safe_positions": None,
                "state": "active",
                "active_list": None,
                "meeting_roles_to_speaker": [],
            },
            data,
        )

    def test_patch(self):
        serializer = self._cut(
            self.system,
            {"title": "Hello", "active_list": self.slist.pk},
            partial=True,
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.system.title, "Hello")
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
            data={"meeting_roles_to_speaker": ["potential_voter", "proposer"]},
            partial=True,
        )
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(
            self.system.meeting_roles_to_speaker, ["potential_voter", "proposer"]
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
