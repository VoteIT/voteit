from django.test import TestCase
from django.test import RequestFactory

from voteit.invites.models import MeetingInvite
from voteit.invites.utils import get_invite_adapter_registry
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.organisation.models import Organisation


class MeetingInviteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.organisation.meetings.create(title="Some meeting")
        cls.user = cls.meeting.participants.create(username="inviter")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
            roles=[ROLE_PARTICIPANT],
        )
        cls.group = cls.meeting.groups.create()
        cls.invite.group_annotations.create(meeting_group=cls.group)
        cls.reg = get_invite_adapter_registry()

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

    def test_annotations_not_prepped(self):
        serializer = self._cut(self.meeting.invites.all(), many=True)
        first = serializer.data[0]
        # Rather testing that it doesn't die
        self.assertFalse(first["has_annotations"])

    def test_annotations(self):
        qs = self.reg.prep_invites_qs_for_subscribe(self.meeting.invites.all())
        serializer = self._cut(qs, many=True)
        first = serializer.data[0]
        self.assertTrue(first["has_annotations"])

    def test_annotations_single_instance(self):
        serializer = self._cut(self.invite)
        self.assertTrue(serializer.data["has_annotations"])

    def _mk_bulk_serializer(self, **kwargs):
        from ..serializers import InviteBulkSerializer

        request = RequestFactory().get("/")
        request.user = self.user

        serializer = InviteBulkSerializer(
            context={"request": request},
            data={"invites": [self.invite.pk], "meeting": self.meeting.id, **kwargs},
        )
        serializer.is_valid()
        return serializer

    def test_bulk_serializer_no_meeting(self):
        self.meeting.roles.filter(user=self.user).update(
            assigned=[ROLE_MODERATOR, ROLE_PARTICIPANT]
        )
        serializer = self._mk_bulk_serializer(meeting=None)
        self.assertEqual(
            serializer.errors["meeting"][0].code,
            "null",
        )

    def test_bulk_serializer_valid(self):
        self.meeting.roles.filter(user=self.user).update(
            assigned=[ROLE_MODERATOR, ROLE_PARTICIPANT]
        )
        serializer = self._mk_bulk_serializer()
        self.assertEqual(serializer.validated_data["meeting"], self.meeting)

    def test_bulk_serializer_no_moderator(self):
        serializer = self._mk_bulk_serializer()
        self.assertEqual(
            serializer.errors["meeting"][0].code,
            "does_not_exist",
        )

    def test_bulk_serializer_archived(self):
        self.meeting.roles.filter(user=self.user).update(
            assigned=[ROLE_MODERATOR, ROLE_PARTICIPANT]
        )
        self.meeting.state = "archived"
        self.meeting.save()
        serializer = self._mk_bulk_serializer()
        self.assertEqual(
            serializer.errors["meeting"][0].code,
            "does_not_exist",
        )

    def test_bulk_serializer_bad_invite(self):
        self.meeting.roles.filter(user=self.user).update(
            assigned=[ROLE_MODERATOR, ROLE_PARTICIPANT]
        )
        serializer = self._mk_bulk_serializer(invites=[0])
        self.assertEqual(
            serializer.errors["invites"][0].code,
            "invalid",
        )


class ExternalMeetingInviteSerializerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create()
        cls.meeting: Meeting = cls.organisation.meetings.create(title="Some meeting")
        cls.user = cls.meeting.participants.create(username="inviter")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
            roles=[ROLE_PARTICIPANT],
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
