from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.channels import OnlineChannel
from voteit.messaging.testing import testing_channel_layers_setting

from voteit.core.messages.user import InvalidateUserCache

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
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
        self.assertEqual(user_pk, msg.payload.pk)

    @patch.object(OnlineChannel, "sync_publish")
    def test_changed(self, mock_method):
        self.user.first_name = "Ivan"
        self.user.save()
        self.assertTrue(mock_method.called)
        self.assertEqual(1, len(mock_method.mock_calls))
        msg = mock_method.mock_calls[0].args[0]
        self.assertIsInstance(msg, InvalidateUserCache)
        self.assertEqual(self.user.pk, msg.payload.pk)
