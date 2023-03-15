from django.test import TestCase

from voteit.meeting.models import Meeting


class PresenceCheckSerializerTests(TestCase):
    def setUp(self):
        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.presence_check = self.meeting.presence_checks.create()

    @property
    def _cut(self):
        from voteit.presence.rest_api.serializers import PresenceCheckDetailSerializer

        return PresenceCheckDetailSerializer

    def test_get(self):
        serializer = self._cut(self.presence_check)
        data = serializer.data
        self.assertIsNotNone(data.pop("opened"))
        self.assertDictEqual(
            {
                "pk": self.presence_check.pk,
                "state": "open",
                "meeting": self.meeting.pk,
                "closed": None,
            },
            data,
        )

    def test_patch(self):
        serializer = self._cut(self.presence_check, {"state": "closed"}, partial=True)
        self.assertTrue(serializer.is_valid())  # Readonly, but still... DRF why why...
        serializer.save()
        self.assertEqual(self.presence_check.state, "open")


class PresenceCheckCreateSerializerTests(TestCase):
    def setUp(self):
        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )

    @property
    def _cut(self):
        from voteit.presence.rest_api.serializers import PresenceCheckCreateSerializer

        return PresenceCheckCreateSerializer

    def test_create(self):
        from voteit.presence.models import PresenceCheck

        serializer = self._cut(data={"meeting": self.meeting.pk})
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertIsInstance(instance, PresenceCheck)
        self.assertEqual(instance.meeting, self.meeting)
