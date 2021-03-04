from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

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


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class MeetingChannelSubscribedTests(TestCase):
    def setUp(self):
        from voteit.meeting.models import Meeting

        self.meeting: Meeting = Meeting.objects.create()
        self.user: User = self.meeting.participants.create(username="user")
        self.meeting.add_roles(self.user, "moderator")

    def test_roles_in_appstruct(self):
        from voteit.messaging.messages.channels import Subscribe
        from voteit.messaging.messages.channels import Subscribed

        msg = Subscribe(
            mm={"user_pk": self.user.pk, "consumer_name": "abc"},
            channel_type="meeting",
            pk=self.meeting.pk,
        )
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        added_meeting_roles = [
            x
            for x in response.data.app_state
            if x.t == "roles.added" and x.p["pk"] == self.meeting.pk
        ]
        self.assertEqual(1, len(added_meeting_roles))
        payload = added_meeting_roles[0].p
        self.assertEqual(set(payload["roles"]), {"participant", "moderator"})
        self.assertEqual(payload["user_pk"], self.user.pk)
        self.assertEqual(payload["model"], "meeting")
