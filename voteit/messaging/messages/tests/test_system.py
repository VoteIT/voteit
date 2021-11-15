from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class IncomingPingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="hi")

    async def test_ping(self):
        from channels.testing import WebsocketCommunicator
        from voteit.messaging.consumers import WebsocketDemuxConsumer
        from voteit.messaging.envelopes import IncomingEnvelope
        from voteit.messaging.envelopes import OutgoingEnvelope

        consumer = WebsocketDemuxConsumer.as_asgi()
        consumer.consumer_class.refresh_user = mock.AsyncMock(return_value=self.user)
        communicator = WebsocketCommunicator(consumer, "/testws/")
        connected, subprotocol = await communicator.connect()
        assert connected
        # Test sending text
        envelope = IncomingEnvelope(t="s.ping", i="123")
        await communicator.send_to(text_data=envelope.json())
        response = await communicator.receive_from()
        out_env = OutgoingEnvelope.parse_raw(response)
        self.assertEqual("s.pong", out_env.t)
        self.assertEqual("123", out_env.i)
        await communicator.disconnect()
