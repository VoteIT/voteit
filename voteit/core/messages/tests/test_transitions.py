from unittest import mock

from django.test import TestCase, override_settings
from envelope.testing import mk_consumer
from envelope.testing import testing_channel_layers_setting


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class GetAllTransitionsTests(TestCase):
    @property
    def _cut(self):
        from voteit.core.messages.transitions import GetAllTransitions

        return GetAllTransitions

    async def test_get_transitions(self):
        from voteit.core.messages.transitions import AllTransitions

        msg = self._cut(mm={"consumer_name": "abc"})

        consumer = mk_consumer()
        consumer.send_ws_message = mock.AsyncMock()
        response = await msg.run(consumer=consumer)
        self.assertIsInstance(response, AllTransitions)
        # Meeting and proposal use python-statemachine (not django-fsm)
        self.assertNotIn("meeting", response.data.transitions)
        self.assertNotIn("proposal", response.data.transitions)
        self.assertTrue(consumer.send_ws_message.called)
