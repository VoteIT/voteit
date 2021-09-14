from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

User = get_user_model()

_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class DeferredJobTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="helloer")

    def test_translation(self):
        from voteit.messaging.messages.testing import HelloResponse
        from voteit.messaging.jobs import run_job

        HelloResponse.from_message = mocked = mock.MagicMock()
        run_job(
            {},
            {"language": "sv", "type": "testing.hello", "user_pk": self.user.pk},
            incoming=True,
            atomic=False,
        )

        self.assertTrue(mocked.called)
        self.assertEqual("Hej helloer!", mocked.mock_calls[0].kwargs.get("greeting"))
