from unittest import mock

from django.test import TestCase, override_settings

from envelope.consumers.websocket import WebsocketConsumer

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class GetAllTransitionsTests(TestCase):
    @property
    def _cut(self):
        from voteit.core.messages import GetAllTransitions

        return GetAllTransitions

    async def test_get_transitions(self):
        from voteit.core.messages import AllTransitions

        msg = self._cut(mm={"consumer_name": "abc"})
        consumer = WebsocketConsumer()
        consumer.send_ws_message = mock.AsyncMock()
        response = await msg.run(consumer=consumer)
        self.assertIsInstance(response, AllTransitions)
        self.assertIn("meeting", response.data.transitions)
        self.assertTrue(consumer.send_ws_message.called)
