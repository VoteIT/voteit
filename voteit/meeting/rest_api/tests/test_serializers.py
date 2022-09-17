from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase

from voteit.meeting.models import Meeting
from voteit.meeting.models import MeetingRoles
from voteit.poll.app.er_policies.auto_always import AutoAlways
from voteit.poll.app.polls.simple import Simple

User = get_user_model()


class MeetingSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)
        self.participant = User.objects.get(username="participant")
        self.moderator = User.objects.get(username="moderator")

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
        request = self._mk_request(self.moderator)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual(
            {"participant", "moderator"}, set(serializer.data["current_user_roles"])
        )

    def test_participant(self):
        request = self._mk_request(self.participant)
        serializer = self._cut(self.meeting, context={"request": request})
        self.assertEqual({"participant"}, set(serializer.data["current_user_roles"]))


class MeetingDetailSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    def setUp(self):
        self.meeting = Meeting.objects.get(pk=1)
        self.participant = User.objects.get(username="participant")
        self.moderator = User.objects.get(username="moderator")

    @property
    def _cut(self):
        from voteit.meeting.rest_api.serializers import MeetingDetailSerializer

        return MeetingDetailSerializer

    def _mk_request(self, user):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = user
        return request

    def test_create(self):
        request = self._mk_request(self.participant)
        serializer = self._cut(
            data={"title": "Hello", "er_policy_name": AutoAlways.name},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance, Meeting)

    def test_update_er_policy(self):
        request = self._mk_request(self.participant)
        serializer = self._cut(
            self.meeting,
            data={"title": "Hello", "er_policy_name": AutoAlways.name},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()
        # breakpoint()
        self.assertEqual(AutoAlways.name, self.meeting.er_policy_name)

    def test_update_er_policy_ongoing_polls(self):
        self.meeting.polls.create(state="ongoing", method_name=Simple.name)
        request = self._mk_request(self.participant)
        serializer = self._cut(
            self.meeting,
            data={"title": "Hello", "er_policy_name": AutoAlways.name},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertIn("er_policy_name", serializer.errors)


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
                "userid": "moderator",
                "email": "moderator@voteit.se",
                "first_name": "Moderator",
                "full_name": "Moderator",
                "last_name": "",
                "img_url": None,
                "organisation": 1,
                "state": "incomplete",
            },
            dict(data["user"]),
        )
        self.assertEqual(1, data["meeting"])
        self.assertEqual(1, data["pk"])

    def test_prefetch(self):
        qs = MeetingRoles.objects.prefetch_related("user")
        serializer = self._cut(instance=qs, many=True)
        with self.assertNumQueries(2):
            data = serializer.data
