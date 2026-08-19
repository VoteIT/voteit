from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from voteit.messaging.testing import build_app_state

from voteit.organisation.channels import OrganisationChannel
from voteit.organisation.models import Organisation

User = get_user_model()
_channel_layers_setting = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class OrganisationChangedTests(TestCase):
    def setUp(self):
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
        self.assertEqual(self.org.pk, msg.payload.pk)


@override_settings(CHANNEL_LAYERS=_channel_layers_setting)
class OrganisationChannelSubscribedTests(TestCase):
    def setUp(self):
        self.org: Organisation = Organisation.objects.create(title="Test org")
        self.user: User = self.org.users.create(username="user")
        self.org.add_roles(self.user, "org_manager")

    def test_roles_in_app_state(self):
        msg = build_app_state("organisation", self.org.pk, self.user.pk)
        app_state = msg
        added_org_roles = [
            x
            for x in app_state
            if x.action == "roles.changed" and x.payload.pk == self.org.pk
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
        cls.org: Organisation = Organisation.objects.create()
        cls.user = cls.org.users.create(username="user")
        cls.org.add_roles(cls.user, "org_manager")

    @patch.object(OrganisationChannel, "sync_publish")
    def test_added(self, mock_publish):
        from voteit.core.messages.role_updates import RolesChanged

        self.assertFalse(mock_publish.called)
        self.org.add_roles(self.user, "meeting_creator")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesChanged)
        self.assertEqual(self.org.pk, msg.payload.pk)
        self.assertEqual(msg.payload.model, "organisation")
        self.assertEqual({"meeting_creator"}, set(msg.payload.roles))

    @patch.object(OrganisationChannel, "sync_publish")
    def test_removed(self, mock_publish):
        from voteit.core.messages.role_updates import RolesRemoved

        self.assertFalse(mock_publish.called)
        self.org.remove_roles(self.user, "org_manager")
        self.assertTrue(mock_publish.called)
        msg = mock_publish.mock_calls[0].args[0]
        self.assertIsInstance(msg, RolesRemoved)
        self.assertEqual(self.org.pk, msg.payload.pk)
        self.assertEqual(msg.payload.model, "organisation")
        self.assertEqual({"org_manager"}, set(msg.payload.roles))
