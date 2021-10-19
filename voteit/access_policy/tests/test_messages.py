from __future__ import annotations
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.access_policy.channels import MeetingInvitesChannel

if TYPE_CHECKING:
    from voteit.access_policy.messages import AddInvites

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class AddInvitesTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @property
    def _cut(self):
        from voteit.access_policy.messages import AddInvites

        return AddInvites

    def _mk_one(self, user_pk: int = None, **kw) -> AddInvites:
        if user_pk is None:
            user_pk = 1  # Moderator from fixture
        kw.setdefault("meeting", 1)  # from fixture
        return self._cut({"consumer_name": "abc", "user_pk": user_pk}, **kw)

    @patch.object(MeetingInvitesChannel, "publish")
    def test_add(self, mock_publish):
        from voteit.access_policy.messages import MeetingInviteAdded

        data = []
        for name in ["one", "two", "three"]:
            data.append({"email": f"{name}@betahaus.net"})
        msg = self._mk_one(roles=["participant"], invite_data=data)
        response = msg.run_job()
        self.assertTrue(mock_publish.called)
        self.assertEqual(3, len(mock_publish.mock_calls))
        # Check response
        self.assertEqual(3, len(response.data.added))
        self.assertEqual(0, len(response.data.changed))
        self.assertEqual(0, response.data.skipped_count)

        # Check pushes
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingInviteAdded)
        self.assertEqual({"email": "one@betahaus.net"}, msg.data.invite_data)


# @override_settings(CHANNEL_LAYERS=_channel_layers_setting)
# class MeetingInviteSignalTests(TestCase):
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.meeting.models import Meeting
#         from voteit.access_policy.models import MeetingInvite
#
#         cls.meeting: Meeting = Meeting.objects.create()
#         cls.moderator = User.objects.create(username="moderator")
#         cls.meeting.add_roles(cls.moderator, "moderator")
#         cls.invite: MeetingInvite = cls.meeting.invites.create(
#             data={"email": "hello@betahaus.net"},
#             created_by=cls.moderator,
#         )
#
#     def setUp(self):
#         self.invite.refresh_from_db()
#
#     @patch.object(MeetingInvitesChannel, "publish")
#     def test_added(self, mock_publish):
#         from voteit.access_policy.messages import MeetingInviteAdded
#
#         self.assertFalse(mock_publish.called)
#         invite = self.meeting.invites.create(
#             data={"email": "hello@betahaus.net"}, created_by=self.moderator
#         )
#         self.assertTrue(mock_publish.called)
#         msg = mock_publish.mock_calls[0].args[0]
#         self.assertIsInstance(msg, MeetingInviteAdded)
#         self.assertEqual(invite.pk, msg.data.pk)
#
#     @patch.object(MeetingInvitesChannel, "publish")
#     def test_changed(self, mock_publish):
#         from voteit.access_policy.messages import MeetingInviteChanged
#
#         self.assertFalse(mock_publish.called)
#         self.invite.roles = ["participant", "moderator"]
#         self.invite.save()
#         self.assertTrue(mock_publish.called)
#         msg = mock_publish.mock_calls[0].args[0]
#         self.assertIsInstance(msg, MeetingInviteChanged)
#         self.assertEqual(self.invite.pk, msg.data.pk)
#         self.assertEqual(self.invite.roles, msg.data.roles)
#
#     @patch.object(MeetingInvitesChannel, "publish")
#     def test_deleted_diff_participants(self, mock_publish):
#         from voteit.access_policy.messages import MeetingInviteDeleted
#
#         self.assertFalse(mock_publish.called)
#         invite_pk = self.invite.pk
#         self.invite.delete()
#         self.assertTrue(mock_publish.called)
#         msg = mock_publish.mock_calls[0].args[0]
#         self.assertIsInstance(msg, MeetingInviteDeleted)
#         self.assertEqual(invite_pk, msg.data.pk)
