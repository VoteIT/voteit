from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.channels.messages import Subscribe

from voteit.core.testing import FakeCommit
from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.messages import MeetingInviteAdded
from voteit.invites.messages import MeetingInviteChanged
from voteit.invites.messages import MeetingInviteDeleted
from voteit.invites.models import MeetingInvite
from voteit.meeting.models import Meeting
from voteit.meeting.roles import ROLE_DISCUSSER
from voteit.meeting.roles import ROLE_MODERATOR
from voteit.meeting.roles import ROLE_PARTICIPANT
from voteit.meeting.roles import ROLE_POTENTIAL_VOTER

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


class AutoUseInviteTests(TestCase):
    def setUp(self):
        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a", email="a@betahaus.net")
        self.inv1: MeetingInvite = MeetingInvite.objects.create(
            meeting=self.meeting,
            user_data={"email": "a@betahaus.net"},
            roles=[ROLE_DISCUSSER, ROLE_POTENTIAL_VOTER],
        )

    def test_auto_use(self):
        with FakeCommit():
            self.meeting.add_roles(self.user, ROLE_PARTICIPANT)
        self.assertEqual(
            {ROLE_PARTICIPANT, ROLE_DISCUSSER, ROLE_POTENTIAL_VOTER},
            set(self.meeting.get_roles(self.user)),
        )


class InvitesExpireWhenMeetingArchivedTests(TestCase):
    def setUp(self):
        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="a")
        self.inv1 = MeetingInvite.objects.create(
            meeting=self.meeting,
            user_data={"email": "a@betahaus.net"},
        )

    def test_expire(self):
        from voteit.invites.workflows import InviteWf

        self.assertEqual(InviteWf.OPEN, self.inv1.state)
        self.meeting.archive()
        self.inv1.refresh_from_db()
        self.assertEqual(InviteWf.EXPIRED, self.inv1.state)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
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
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.meeting.pk,
            channel_type="invites",
        )
        msg = command.run_job()
        batch_msg_payloads = [
            x.p
            for x in msg.data.app_state
            if x.t == "s.batch" and x.p["t"] == "meeting_invite.added"
        ]
        self.assertEqual(1, len(batch_msg_payloads))
        payloads = batch_msg_payloads[0]["payloads"]
        self.assertEqual(2, len(payloads))
        self.assertEqual({self.invite.pk, self.invite2.pk}, {x.pk for x in payloads})
        self.assertEqual({True, False}, {x.has_annotations for x in payloads})


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
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
        with FakeCommit():
            invite = self.meeting.invites.create(
                user_data={"email": "bye@betahaus.net"}
            )
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteAdded)
        self.assertEqual(invite.pk, msg.data.pk)
        self.assertEqual(False, msg.data.has_annotations)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_changed(self, mock_publish):
        self.assertFalse(mock_publish.called)
        with FakeCommit():
            self.invite.roles = [ROLE_PARTICIPANT, ROLE_MODERATOR]
            self.invite.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteChanged)
        self.assertEqual(self.invite.pk, msg.data.pk)
        self.assertEqual(self.invite.roles, msg.data.roles)
        self.assertEqual(True, msg.data.has_annotations)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_deleted_diff_participants(self, mock_publish):
        self.assertFalse(mock_publish.called)
        invite_pk = self.invite.pk
        self.invite.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteDeleted)
        self.assertEqual(invite_pk, msg.data.pk)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_accepted_removes_annotation(self, mock_publish):
        user = User.objects.create(username="accepter")
        with self.captureOnCommitCallbacks(execute=True):
            self.invite.accept(user)
            self.invite.save()
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteChanged)
        self.assertEqual(False, msg.data.has_annotations)
