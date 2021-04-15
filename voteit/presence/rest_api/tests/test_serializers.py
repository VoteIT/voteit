from django.test import TestCase


class PresenceCheckSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.presence.models import PresenceSystem

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.system: PresenceSystem = PresenceSystem.objects.create(
            meeting=self.meeting
        )
        self.presence_check = self.meeting.presence_checks.create()

    @property
    def _cut(self):
        from voteit.presence.rest_api.serializers import PresenceCheckDetailSerializer

        return PresenceCheckDetailSerializer

    def test_get(self):
        serializer = self._cut(self.presence_check)
        data = serializer.data
        self.assertDictEqual(
            {
                "pk": self.presence_check.pk,
                "state": "open",
                "meeting": self.meeting.pk,
                "opened": self.presence_check.opened.isoformat()[:-6] + "Z",
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
        from voteit.meeting.models import Meeting
        from voteit.presence.models import PresenceSystem

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.system: PresenceSystem = PresenceSystem.objects.create(
            meeting=self.meeting
        )

    @property
    def _cut(self):
        from voteit.presence.rest_api.serializers import PresenceCheckDetailSerializer

        return PresenceCheckDetailSerializer

    def test_create(self):
        from voteit.presence.models import PresenceCheck

        serializer = self._cut(data={"meeting": self.meeting.pk})
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertIsInstance(instance, PresenceCheck)
        self.assertEqual(instance.meeting, self.meeting)


class PresenceSystemSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.presence.models import PresenceSystem

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )
        self.system: PresenceSystem = PresenceSystem.objects.create(
            meeting=self.meeting
        )

    @property
    def _cut(self):
        from voteit.presence.rest_api.serializers import PresenceSystemDetailSerializer

        return PresenceSystemDetailSerializer

    def test_get(self):
        # Queue is not part of this
        serializer = self._cut(self.system)
        data = serializer.data
        self.assertEqual(
            {"pk": self.system.pk, "meeting": self.meeting.pk},
            data,
        )

    def test_patch(self):
        serializer = self._cut(
            self.system,
            {"meeting": -1},
            partial=True,
        )
        self.assertTrue(serializer.is_valid())  # Since DRF throws away meeting...
        serializer.save()
        self.system.refresh_from_db(fields=["meeting"])
        self.assertEqual(self.meeting, self.system.meeting)


class PresenceSystemCreateSerializer(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create(
            title="Test meeting", state="ongoing"
        )

    @property
    def _cut(self):
        from voteit.presence.rest_api.serializers import PresenceSystemCreateSerializer

        return PresenceSystemCreateSerializer

    def test_create(self):
        from voteit.presence.models import PresenceSystem

        serializer = self._cut(data={"meeting": self.meeting.pk})
        self.assertTrue(serializer.is_valid())
        instance = serializer.save()
        self.assertIsInstance(instance, PresenceSystem)
        self.assertEqual(self.meeting, instance.meeting)
