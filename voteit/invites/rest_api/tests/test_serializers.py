from django.test import RequestFactory
from django.test import TestCase


# class CreateMeetingInviteSerializerTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.organisation.models import Organisation
#         from voteit.meeting.models import Meeting
#
#         cls.organisation = Organisation.objects.create()
#         cls.meeting: Meeting = cls.organisation.meetings.create(title="Some meeting")
#         cls.user = cls.meeting.participants.create(username="inviter")
#
#     @property
#     def _cut(self):
#         from voteit.invites.rest_api.serializers import (
#             CreateMeetingInviteSerializer,
#         )
#
#         return CreateMeetingInviteSerializer
#
#     def _mk_request(self):
#         request = RequestFactory().request()
#         # "Login"
#         request.user = self.user
#         return request
#
#     def test_create(self):
#         data = {
#             "meeting": self.meeting.pk,
#             "invite_data": {"email": "hello@betahaus.net"},
#         }
#         serializer = self._cut(data=data, context={"request": self._mk_request()})
#         serializer.is_valid()
#         self.assertFalse(serializer.errors)
#         instance = serializer.save()
#         self.assertEqual(self.user, instance.created_by)
#
#     def test_validate_bogus_email_invite_data(self):
#         data = {
#             "meeting": self.meeting.pk,
#             "invite_data": {"email": "not really"},
#         }
#         serializer = self._cut(data=data, context={"request": self._mk_request()})
#         serializer.is_valid()
#         self.assertIn("invite_data", serializer.errors)
#
#     def test_validate_bogus_key_invite_data(self):
#         data = {
#             "meeting": self.meeting.pk,
#             "invite_data": {"404": "not really"},
#         }
#         serializer = self._cut(data=data, context={"request": self._mk_request()})
#         serializer.is_valid()
#         self.assertIn("invite_data", serializer.errors)


class MeetingInviteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation
        from voteit.meeting.models import Meeting
        from voteit.invites.models import MeetingInvite

        cls.organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.organisation.meetings.create(title="Some meeting")
        cls.user = cls.meeting.participants.create(username="inviter")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            created_by=cls.user,
            invite_data="hello@betahaus.net",
            roles=["participant"],
        )

    def setUp(self):
        self.invite.refresh_from_db()

    @property
    def _cut(self):
        from voteit.invites.rest_api.serializers import MeetingInviteSerializer

        return MeetingInviteSerializer

    def test_get(self):
        serializer = self._cut(self.invite)
        data = serializer.data
        self.assertEqual(self.user.pk, data["created_by"])

    def test_update(self):
        serializer = self._cut(
            self.invite,
            data={"invite_data": "another@betahaus.net"},
            partial=True,
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        serializer.save()

    def test_validate_bogus_email_invite_data(self):
        data = {
            "meeting": self.meeting.pk,
            "invite_data": "not really",
        }
        serializer = self._cut(self.invite, data=data)
        serializer.is_valid()
        self.assertIn("invite_data", serializer.errors)


class ExternalMeetingInviteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation
        from voteit.meeting.models import Meeting
        from voteit.invites.models import MeetingInvite

        cls.organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.organisation.meetings.create(title="Some meeting")
        cls.user = cls.meeting.participants.create(username="inviter")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            created_by=cls.user,
            invite_data="hello@betahaus.net",
            roles=["participant"],
        )

    @property
    def _cut(self):
        from voteit.invites.rest_api.serializers import (
            ExternalMeetingInviteSerializer,
        )

        return ExternalMeetingInviteSerializer

    def test_get(self):
        serializer = self._cut(self.invite)
        data = serializer.data
        self.assertEqual(self.organisation.pk, data["organisation_pk"])
        self.assertEqual(self.meeting.title, data["meeting_title"])
        self.assertEqual(self.user.pk, data["created_by"])
