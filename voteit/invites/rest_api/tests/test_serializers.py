from django.test import RequestFactory
from django.test import TestCase

from voteit.invites.models import MeetingInvite
from voteit.meeting.models import Meeting
from voteit.organisation.models import Organisation


class MeetingInviteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.organisation.meetings.create(title="Some meeting")
        cls.user = cls.meeting.participants.create(username="inviter")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
            roles=["participant"],
        )

    def setUp(self):
        self.invite.refresh_from_db()

    @property
    def _cut(self):
        from voteit.invites.rest_api.serializers import MeetingInviteSerializer

        return MeetingInviteSerializer

    def test_data(self):
        serializer = self._cut(self.invite)
        data = serializer.data
        self.assertEqual({"email": "hello@betahaus.net"}, data["user_data"])


class ExternalMeetingInviteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.organisation.meetings.create(title="Some meeting")
        cls.user = cls.meeting.participants.create(username="inviter")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
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
        self.assertEqual(self.organisation.host, data["organisation_host"])
        self.assertEqual(self.meeting.title, data["meeting_title"])
