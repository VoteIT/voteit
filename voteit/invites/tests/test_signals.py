from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from envelope.messages.channels import Subscribe
from voteit.core.testing import FakeCommit
from voteit.invites.channels import MeetingInvitesChannel
from voteit.invites.models import MeetingInvite
from voteit.meeting.models import Meeting

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
            roles=["discusser", "potential_voter"],
        )

    def test_auto_use(self):
        with FakeCommit():
            self.meeting.add_roles(self.user, "participant")
        self.assertEqual(
            {"participant", "discusser", "potential_voter"},
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
        cls.meeting.add_roles(cls.moderator, "moderator")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"}
        )

    def test_app_state_sent(self):
        command = Subscribe(
            mm={"consumer_name": "abc", "user_pk": self.moderator.pk},
            pk=self.meeting.pk,
            channel_type="invites",
        )
        msg = command.run_job()
        pks = {x.p["pk"] for x in msg.data.app_state if x.t == "meeting_invite.added"}
        self.assertEqual({self.invite.pk}, pks)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingInviteSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.meeting: Meeting = Meeting.objects.create()
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting.add_roles(cls.moderator, "moderator")
        cls.invite: MeetingInvite = cls.meeting.invites.create(
            user_data={"email": "hello@betahaus.net"},
        )

    def setUp(self):
        self.invite.refresh_from_db()

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.invites.messages import MeetingInviteAdded

        self.assertFalse(mock_publish.called)
        with FakeCommit():
            invite = self.meeting.invites.create(
                user_data={"email": "hello@betahaus.net"}
            )
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteAdded)
        self.assertEqual(invite.pk, msg.data.pk)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_changed(self, mock_publish):
        from voteit.invites.messages import MeetingInviteChanged

        self.assertFalse(mock_publish.called)
        with FakeCommit():
            self.invite.roles = ["participant", "moderator"]
            self.invite.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteChanged)
        self.assertEqual(self.invite.pk, msg.data.pk)
        self.assertEqual(self.invite.roles, msg.data.roles)

    @patch.object(MeetingInvitesChannel, "sync_publish")
    def test_deleted_diff_participants(self, mock_publish):
        from voteit.invites.messages import MeetingInviteDeleted

        self.assertFalse(mock_publish.called)
        invite_pk = self.invite.pk
        self.invite.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteDeleted)
        self.assertEqual(invite_pk, msg.data.pk)
