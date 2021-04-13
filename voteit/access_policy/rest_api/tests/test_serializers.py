from django.test import RequestFactory
from django.test import TestCase


class AutomaticAccessSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.access_policy.app.policies import AutomaticAccess

        meeting = Meeting.objects.create()
        self.ap = AutomaticAccess.objects.create(
            meeting=meeting, active=True, roles_given=["participant"]
        )

    @property
    def _cut(self):
        from voteit.access_policy.rest_api.serializers import AutomaticAccessSerializer

        return AutomaticAccessSerializer

    def test_serializer(self):
        data = self._cut(self.ap).data
        self.assertEqual(self.ap.pk, data["pk"])
        self.assertEqual(self.ap.name, data["name"])


class ModeratorApprovedAccessSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.access_policy.app.policies import ModeratorApprovedAccess

        meeting = Meeting.objects.create()
        self.ap = ModeratorApprovedAccess.objects.create(meeting=meeting, active=True)

    @property
    def _cut(self):
        from voteit.access_policy.rest_api.serializers import (
            ModeratorApprovedAccessSerializer,
        )

        return ModeratorApprovedAccessSerializer

    def test_serializer(self):
        data = self._cut(self.ap).data
        self.assertEqual(self.ap.pk, data["pk"])
        self.assertEqual(self.ap.name, data["name"])


class MeetingAccessPoliciesSerializerTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting
        from voteit.access_policy.app.policies import AutomaticAccess

        self.meeting = Meeting.objects.create()
        self.ap_aa = AutomaticAccess.objects.create(
            meeting=self.meeting, active=True, roles_given=["participant"]
        )

    @property
    def _cut(self):
        from voteit.access_policy.rest_api.serializers import (
            MeetingAccessPoliciesSerializer,
        )

        return MeetingAccessPoliciesSerializer

    def test_serializer(self):
        data = self._cut(self.meeting).data
        self.assertEqual(self.meeting.pk, data["pk"])
        self.assertEqual(1, len(data["policies"]))


# class InviteQuerySerializerTests(TestCase):
#     @property
#     def _cut(self):
#         from voteit.access_policy.rest_api.serializers import InviteQuerySerializer
#
#         return InviteQuerySerializer
#
#     def test_multiple_query(self):
#         data = [
#             {
#                 "scope": "email",
#                 "data": "hello@betahaus.net",
#                 "validated": "2021-03-24T15:56:00.043000Z",
#             }
#         ]


class MeetingInviteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.meeting.models import Meeting

        cls.meeting = Meeting.objects.create()
        cls.user = cls.meeting.participants.create(username="inviter")

    @property
    def _cut(self):
        from voteit.access_policy.rest_api.serializers import MeetingInviteSerializer

        return MeetingInviteSerializer

    def _mk_request(self):
        request = RequestFactory().request()
        # "Login"
        request.user = self.user
        return request

    def test_create(self):
        data = {
            "meeting": self.meeting.pk,
            "data": {"email": "hello@betahaus.net"},
        }
        serializer = self._cut(data=data, context={"request": self._mk_request()})
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertEqual(self.user, instance.created_by)

    def test_validate_bogus_email_invite_data(self):
        data = {
            "meeting": self.meeting.pk,
            "data": {"email": "not really"},
        }
        serializer = self._cut(data=data, context={"request": self._mk_request()})
        serializer.is_valid()
        self.assertIn("data", serializer.errors)

    def test_validate_bogus_key_invite_data(self):
        data = {
            "meeting": self.meeting.pk,
            "data": {"404": "not really"},
        }
        serializer = self._cut(data=data, context={"request": self._mk_request()})
        serializer.is_valid()
        self.assertIn("data", serializer.errors)
