from json import loads
from os import environ
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from envelope.app.online_channel.channel import OnlineChannel
from envelope.async_signals import consumer_connected
from envelope.tests.helpers import mk_consumer

from voteit.core.messages.user import InvalidateUserCache

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@patch.dict(environ, {"FRONTEND_VERSION": "1.2.3"})
@override_settings(
    CHANNEL_LAYERS=_channel_layers_setting,
    ENVELOPE_CONNECTIONS_QUEUE=None,
)
class FrontendVersionMessageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="user")

    async def test_msg_sent(self):
        consumer = mk_consumer(user=self.user)
        with patch.object(consumer, "send") as mock_method:
            await consumer_connected.send(sender=consumer.__class__, consumer=consumer)
            self.assertIn(
                {
                    "t": "s.frontend_version",
                    "p": {"version": "1.2.3"},
                    "i": None,
                    "s": None,
                },
                [loads(x[2]["text_data"]) for x in mock_method.mock_calls],
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
