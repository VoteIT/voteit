from json import loads
from os import environ
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from envelope.models import Connection
from envelope.async_signals import consumer_connected
from envelope.tests.helpers import mk_consumer

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
