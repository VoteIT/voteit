from json import loads
from os import environ
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from envelope.app.online_channel.channel import OnlineChannel
from envelope.models import Connection
from envelope.signals import client_connect
from envelope.utils import channel_layer
from voteit.core.messages.user import InvalidateUserCache

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@patch.dict(environ, {"FRONTEND_VERSION": "1.2.3"})
@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class FrontendVersionMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")
        cls.conn = Connection.objects.create(user=cls.user, channel_name="abc")

    def test_msg_sent(self):
        with patch.object(channel_layer, "send") as mock_method:
            client_connect.send(
                sender=None,
                user=self.user,
                consumer_name=self.conn.channel_name,
                connection=self.conn,
            )
            self.assertTrue(mock_method.called)
            self.assertEqual("abc", mock_method.mock_calls[0].args[0])
            self.assertEqual(
                {
                    "t": "s.frontend_version",
                    "p": {"version": "1.2.3"},
                    "i": None,
                    "s": None,
                },
                loads(mock_method.mock_calls[0].args[1].get("text_data")),
            )


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class UserChangedSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")

    @patch.object(OnlineChannel, "sync_publish")
    def test_deleted(self, mock_method):
        user_pk = self.user.pk
        self.user.delete()
        self.assertTrue(mock_method.called)
        self.assertEqual(1, len(mock_method.mock_calls))
        msg = mock_method.mock_calls[0].args[0]
        self.assertIsInstance(msg, InvalidateUserCache)
        self.assertEqual(user_pk, msg.data.pk)

    @patch.object(OnlineChannel, "sync_publish")
    def test_changed(self, mock_method):
        self.user.first_name = "Ivan"
        self.user.save()
        self.assertTrue(mock_method.called)
        self.assertEqual(1, len(mock_method.mock_calls))
        msg = mock_method.mock_calls[0].args[0]
        self.assertIsInstance(msg, InvalidateUserCache)
        self.assertEqual(self.user.pk, msg.data.pk)
