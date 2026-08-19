from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import action_of
from voteit.messaging.testing import build_app_state
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.messages import MeetingInviteChanged
from voteit.invites.messages import MeetingInviteDeleted
from voteit.invites.models import MeetingInvite
from voteit.invites.statemachines import InviteStateMachine
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()


@override_settings(
    CHANNEL_LAYERS=testing_channel_layers_setting,
)
class InviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting = Meeting.objects.create()
        cls.user = User.objects.create(username="a", email="a@betahaus.net")
        cls.inv1: MeetingInvite = MeetingInvite.objects.create(
            meeting=cls.meeting,
            user_data={"email": "a@betahaus.net"},
            roles=[ROLE_DISCUSSER, ROLE_POTENTIAL_VOTER],
        )

    def test_auto_use(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.meeting.add_roles(self.user, ROLE_PARTICIPANT)
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_POTENTIAL_VOTER},
            set(self.meeting.get_roles(self.user)),
        )

    def test_kicking_user_removes_invite(self):
        self.inv1.accept(self.user)
        self.inv1.save()
        self.meeting.remove_roles(self.user, ROLE_PARTICIPANT)
        self.assertIsNone(self.meeting.get_roles(self.user))
        with self.assertRaises(MeetingInvite.DoesNotExist):
            self.inv1.refresh_from_db()


class InvitesExpireWhenMeetingArchivedTests(TestCase):
    def setUp(self):
        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")
        self.inv1 = MeetingInvite.objects.create(
            meeting=self.meeting,
            user_data={"email": "a@betahaus.net"},
        )

    def test_expire(self):
        self.assertEqual(InviteStateMachine.open.id, self.inv1.state)
        self.meeting.archive()
        self.inv1.refresh_from_db()
        self.assertEqual(InviteStateMachine.expired.id, self.inv1.state)


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class InvitesSubscribedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.group = cls.meeting.groups.create()
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"}
        )
        cls.invite2: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "bye@betahaus.net"}
        )
        cls.invite.group_annotations.create(meeting_group=cls.group)

    def test_app_state_sent(self):
        command = build_app_state("invites", self.meeting.pk, self.moderator.pk)
        app_state = command
        batch = None
        for item in app_state:
            if item.action == f"{action_of(MeetingInviteChanged)}.batch":
                batch = item
        payloads = batch.payload.items
        self.assertEqual({self.invite.pk, self.invite2.pk}, {x.pk for x in payloads})
        self.assertEqual({True, False}, {x.has_annotations for x in payloads})
        data = {}
        for item in payloads:
            if item.pk == self.invite.pk:
                data = item.dict(exclude={"pk", "has_annotations"})
                break
        self.assertEqual(self.meeting.pk, data.pop("meeting"))
        self.assertEqual({"email": "hello@betahaus.net"}, data.pop("user_data"))
        self.assertEqual([], data.pop("roles"))
        self.assertEqual(None, data.pop("used_by"))
        self.assertEqual("open", data.pop("state"))
        self.assertFalse(data.keys())


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class MeetingInviteSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, ROLE_MODERATOR)
        cls.group = cls.meeting.groups.create()
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
        )
        cls.invite.group_annotations.create(meeting_group=cls.group)

    def setUp(self):
        self.invite.refresh_from_db()

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_added(self, mock_publish):
        self.assertFalse(mock_publish.called)
        with self.captureOnCommitCallbacks(execute=True):
            invite = self.meeting.invites.create(
                user_data={"email": "bye@betahaus.net"}
            )
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteChanged)
        self.assertEqual(invite.pk, msg.payload.pk)
        self.assertEqual(False, msg.payload.has_annotations)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_changed(self, mock_publish):
        self.assertFalse(mock_publish.called)
        with self.captureOnCommitCallbacks(execute=True):
            self.invite.roles = [ROLE_PARTICIPANT, ROLE_MODERATOR]
            self.invite.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteChanged)
        self.assertEqual(self.invite.pk, msg.payload.pk)
        self.assertEqual(self.invite.roles, msg.payload.roles)
        self.assertEqual(True, msg.payload.has_annotations)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_deleted_diff_participants(self, mock_publish):
        self.assertFalse(mock_publish.called)
        invite_pk = self.invite.pk
        self.invite.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteDeleted)
        self.assertEqual(invite_pk, msg.payload.pk)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_accepted_removes_annotation(self, mock_publish):
        user = User.objects.create(username="accepter")
        with self.captureOnCommitCallbacks(execute=True):
            self.invite.accept(user)
            self.invite.save()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteChanged)
        self.assertEqual(False, msg.payload.has_annotations)
