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
                "list_system": self.system.pk,
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
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.system = self.meeting.speaker_systems.create(method_name="simple")
        self.slist = self.system.speaker_lists.create(agenda_item=self.ai)
        self.user_one = self.slist.speakers.create(username="one")
        self.user_two = self.slist.speakers.create(username="two")
        for i in range(1, 4):
            self.slist.speaker_items.create(
                user=self.user_one,
                seconds=i * 5,
                # Make sure there's a diff between started, since it's sorted on that
                started=now() - timedelta(seconds=10 - i),
            )
        self.slist.speaker_items.create(user=self.user_two, seconds=11)

    @property
    def _cut(self):
        from voteit.speaker.rest_api.serializers import HistoricSpeakerListSerializer

        return HistoricSpeakerListSerializer

    def test_get(self):
        # Queue is not part of this
        serializer = self._cut(self.slist)
        data = serializer.data
        self.assertEqual(self.slist.pk, data["pk"])
        self.assertEqual(2, len(data["previous"]))
        previous = data["previous"]
        first = [x for x in previous if x[0] == self.user_one.pk][0]
        second = [x for x in previous if x[0] == self.user_two.pk][0]
        self.assertEqual([self.user_one.pk, [5, 10, 15]], first)
        self.assertEqual([self.user_two.pk, [11]], second)


class SpeakerListSystemSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        # self.ai = self.meeting.agenda_items.create(state="ongoing", title="Ongoing")
        self.system = self.meeting.speaker_systems.create(
            method_name="simple", active=True
        )
        self.slist = self.system.speaker_lists.create()

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
                "archived": False,
                "active_list": None,
                "active": True,
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
