from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings
from voteit.messaging.testing import testing_channel_layers_setting
from voteit.organisation.channels import OrganisationChannel
from voteit.organisation.models import Organisation

from voteit.core.messages.user import InvalidateUserCache

User = get_user_model()


@override_settings(CHANNEL_LAYERS=testing_channel_layers_setting)
class UserChangedSignalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(title="Org")
        cls.user = User.objects.create(username="user", organisation=cls.organisation)

    def assert_invalidated(self, mock_method, user_pk):
        """One InvalidateUserCache, published to the user's own organisation."""
        self.assertTrue(mock_method.called)
        self.assertEqual(1, len(mock_method.mock_calls))
        # autospec keeps the receiving channel as the first argument, which is
        # the half of this that matters: it used to go to every open socket.
        channel, msg = mock_method.mock_calls[0].args
        self.assertIsInstance(msg, InvalidateUserCache)
        self.assertEqual(user_pk, msg.payload.pk)
        self.assertEqual(self.organisation.pk, channel.pk)

    @patch.object(OrganisationChannel, "sync_publish", autospec=True)
    def test_deleted(self, mock_method):
        user_pk = self.user.pk
        self.user.delete()
        self.assert_invalidated(mock_method, user_pk)

    @patch.object(OrganisationChannel, "sync_publish", autospec=True)
    def test_changed(self, mock_method):
        self.user.first_name = "Ivan"
        self.user.save()
        self.assert_invalidated(mock_method, self.user.pk)

    @patch.object(OrganisationChannel, "sync_publish", autospec=True)
    def test_created(self, mock_method):
        User.objects.create(username="new", organisation=self.organisation)
        self.assertFalse(mock_method.called)

    @patch.object(OrganisationChannel, "sync_publish", autospec=True)
    def test_without_organisation_publishes_nothing(self, mock_method):
        """The FK is nullable only to ease testing -- there is nowhere to send."""
        orgless = User.objects.create(username="orgless")
        orgless.first_name = "Ivan"
        orgless.save()
        self.assertFalse(mock_method.called)
