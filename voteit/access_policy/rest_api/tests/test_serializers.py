from django.test import TestCase

from voteit.access_policy.app.policies import AutomaticAccess
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_PARTICIPANT


class AutomaticAccessSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        meeting: Meeting = Meeting.objects.create()
        cls.ap: AutomaticAccess = AutomaticAccess.objects.create(
            meeting=meeting, active=True, roles_given=[ROLE_PARTICIPANT]
        )

    @property
    def _cut(self):
        from voteit.access_policy.rest_api.serializers import AutomaticAccessSerializer

        return AutomaticAccessSerializer

    def test_serializer(self):
        data = self._cut(self.ap).data
        self.assertEqual(self.ap.pk, data["pk"])
        self.assertEqual(self.ap.name, data["name"])


# class ModeratorApprovedAccessSerializerTests(TestCase):
#     def setUp(self):
#         from voteit.meeting.models import Meeting
#         from voteit.access_policy.app.policies import ModeratorApprovedAccess
#
#         meeting = Meeting.objects.create()
#         self.ap = ModeratorApprovedAccess.objects.create(meeting=meeting, active=True)
#
#     @property
#     def _cut(self):
#         from voteit.access_policy.rest_api.serializers import (
#             ModeratorApprovedAccessSerializer,
#         )
#
#         return ModeratorApprovedAccessSerializer
#
#     def test_serializer(self):
#         data = self._cut(self.ap).data
#         self.assertEqual(self.ap.pk, data["pk"])
#         self.assertEqual(self.ap.name, data["name"])


class MeetingAccessPoliciesSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.ap_aa: AutomaticAccess = AutomaticAccess.objects.create(
            meeting=cls.meeting, active=True, roles_given=[ROLE_PARTICIPANT]
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
