from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.meeting.channels import MeetingChannel

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RoleChangesPublishedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()
        self.user = User.objects.create(username="user")
        self.meeting.add_roles(self.user, "participant")

    @patch.object(MeetingChannel, "publish")
    def test_added(self, mock_publish):
        from voteit.core.messages import RolesAdded

        self.assertFalse(mock_publish.called)
        self.meeting.add_roles(self.user, "moderator")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesAdded)
        self.assertEqual(self.meeting.pk, msg.data.pk)
        self.assertEqual({"moderator"}, set(msg.data.roles))

    @patch.object(MeetingChannel, "publish")
    def test_removed(self, mock_publish):
        from voteit.core.messages import RolesRemoved

        self.assertFalse(mock_publish.called)
        self.meeting.remove_roles(self.user, "participant")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesRemoved)
        self.assertEqual(self.meeting.pk, msg.data.pk)
        self.assertEqual({"participant"}, set(msg.data.roles))
