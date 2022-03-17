from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.app.user_channel.channel import UserChannel

from voteit.presence.channels import PresenceCheckChannel

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class SignalsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.presence.models import PresenceSystem
        from voteit.presence.models import PresenceCheck
        from voteit.meeting.models import Meeting

        cls.user = User.objects.create(username="creeper")
        cls.moderator = User.objects.create(username="moderator")
        cls.meeting = Meeting.objects.create()
        cls.meeting.add_roles(cls.user, "participant")
        cls.meeting.add_roles(cls.moderator, "moderator")
        cls.system = PresenceSystem.objects.create(meeting=cls.meeting)
        cls.check = PresenceCheck.objects.create(meeting=cls.meeting)

    def _mk_presence(self):
        from voteit.presence.models import Presence

        return Presence.objects.create(user=self.user, presence_check=self.check)

    @patch.object(UserChannel, "sync_publish")
    def test_presence_add_user_channel(self, mock_publish):
        from voteit.presence.messages import PresenceAdded

        presence = self._mk_presence()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceAdded)
        self.assertEqual(msg.data.user, self.user.pk)
        self.assertEqual(msg.data.pk, presence.pk)

    @patch.object(PresenceCheckChannel, "sync_publish")
    def test_presence_add_presence_channel(self, mock_publish):
        from voteit.presence.messages import PresenceCheckStatus

        self._mk_presence()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceCheckStatus)
        self.assertEqual(msg.data.present, 1)
        self.assertEqual(msg.data.pk, self.check.pk)

    @patch.object(UserChannel, "sync_publish")
    def test_presence_deleted_user_channel(self, mock_publish):
        from voteit.presence.messages import PresenceDeleted

        presence = self._mk_presence()
        presence_pk = presence.pk
        mock_publish.reset_mock()
        presence.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceDeleted)
        self.assertEqual(msg.data.pk, presence_pk)

    @patch.object(PresenceCheckChannel, "sync_publish")
    def test_presence_deleted_presence_channel(self, mock_publish):
        from voteit.presence.messages import PresenceCheckStatus

        presence = self._mk_presence()
        mock_publish.reset_mock()
        presence.delete()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, PresenceCheckStatus)
        self.assertEqual(msg.data.present, 0)
        self.assertEqual(msg.data.pk, self.check.pk)
