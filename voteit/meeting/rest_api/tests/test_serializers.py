from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles

User = get_user_model()


class MeetingSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import MeetingSerializer

        return MeetingSerializer

    def _mk_request(self, user):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        return request

    def test_roles_moderator(self):
        moderator = User.objects.get(username="moderator")
        request = self._mk_request(moderator)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual(
            {"participant", "moderator"}, set(serializer.data["current_user_roles"])
        )

    def test_participant(self):
        participant = User.objects.get(username="participant")
        request = self._mk_request(participant)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual({"participant"}, set(serializer.data["current_user_roles"]))

    def test_create(self):
        participant = User.objects.get(username="participant")
        request = self._mk_request(participant)
        serializer = self._cut(data={"title": "Hello"}, context={"request": request})
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, Meeting)


class MeetingRolesSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import MeetingRolesSerializer

        return MeetingRolesSerializer

    def test_moderator(self):
        instance = MeetingRoles.objects.get(pk=1)
        serializer = self._cut(instance)
        data = serializer.data
        self.assertEqual({"participant", "moderator"}, set(data["assigned"]))
        self.assertEqual(
            {
                "pk": 1,
                "username": "moderator",
                "first_name": "Moderator",
                "full_name": "Moderator",
                "last_name": "",
                "organisation": 1,
            },
            dict(data["user"]),
        )
        self.assertEqual(1, data["meeting"])
        self.assertEqual(1, data["pk"])
