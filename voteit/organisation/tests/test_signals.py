from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from envelope.channels.messages import Subscribe
from envelope.channels.messages import Subscribed

from ..channels import OrganisationChannel

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class OrganisationChangedTests(TestCase):
    def setUp(self):
        from ..models import Organisation

        self.org = Organisation.objects.create(title="Test org")

    # We don't handle added right now
    @patch.object(OrganisationChannel, "sync_publish")
    def test_changed(self, mock_publish):
        from ..messages import OrganisationChanged

        self.assertFalse(mock_publish.called)
        self.org.body = "Hello"
        self.org.save()
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, OrganisationChanged)
        self.assertEqual(self.org.pk, msg.data.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class OrganisationChannelSubscribedTests(TestCase):
    def setUp(self):
        from ..models import Organisation

        self.org: Organisation = Organisation.objects.create(title="Test org")
        self.user: User = self.org.users.create(username="user")
        self.org.add_roles(self.user, "org_manager")

    def test_roles_in_app_state(self):
        msg = Subscribe(
            mm={"user_pk": self.user.pk, "consumer_name": "abc"},
            channel_type="organisation",
            pk=self.org.pk,
        )
        response = msg.run_job()
        self.assertIsInstance(response, Subscribed)
        added_org_roles = [
            x
            for x in response.data.app_state
            if x.t == "roles.added" and x.p["pk"] == self.org.pk
        ]
        self.assertEqual(1, len(added_org_roles))
        payload = added_org_roles[0].p
        self.assertEqual(set(payload["roles"]), {"org_manager"})
        self.assertEqual(payload["user_pk"], self.user.pk)
        self.assertEqual(payload["model"], "organisation")


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class RoleChangesPublishedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation

        cls.org: Organisation = Organisation.objects.create()
        cls.user = cls.org.users.create(username="user")
        cls.org.add_roles(cls.user, "org_manager")

    @patch.object(OrganisationChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.core.messages.role_updates import RolesAdded

        self.assertFalse(mock_publish.called)
        self.org.add_roles(self.user, "meeting_creator")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesAdded)
        self.assertEqual(self.org.pk, msg.data.pk)
        self.assertEqual(msg.data.model, "organisation")
        self.assertEqual({"meeting_creator"}, set(msg.data.roles))

    @patch.object(OrganisationChannel, "sync_publish")
    def test_removed(self, mock_publish):
        from voteit.core.messages.role_updates import RolesRemoved

        self.assertFalse(mock_publish.called)
        self.org.remove_roles(self.user, "org_manager")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesRemoved)
        self.assertEqual(self.org.pk, msg.data.pk)
        self.assertEqual(msg.data.model, "organisation")
        self.assertEqual({"org_manager"}, set(msg.data.roles))
