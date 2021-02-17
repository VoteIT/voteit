from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from voteit.meeting.channels import MeetingChannel

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingChangedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting = Meeting.objects.create()

    # We don't handle added right now
    @patch.object(MeetingChannel, "publish")
    def test_changed(self, mock_publish):
        from voteit.meeting.messages import MeetingChanged

        self.assertFalse(mock_publish.called)
        self.meeting.title = "Hello"
        self.meeting.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, MeetingChanged)
        self.assertEqual(self.meeting.pk, msg.data.pk)
