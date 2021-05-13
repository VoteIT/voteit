from django.test import TestCase, override_settings


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
        response = await msg.run(None)
        self.assertIsInstance(response, AllTransitions)
        self.assertIn("meeting", response.data.transitions)
