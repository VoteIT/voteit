from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from voteit.organisation.models import GlobalTermsOfService
from voteit.organisation.models import Organisation


class GlobalTermsOfServiceAdminTests(TestCase):
    changelist_url = reverse("admin:organisation_globaltermsofservice_changelist")

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="One", host="one.example.com")
        cls.admin = cls.org.users.create(
            username="admin", is_staff=True, is_superuser=True
        )
        cls.published = GlobalTermsOfService.objects.create(
            body="Published",
            version=now() - timedelta(days=1),
            required_from=now().date(),
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def _create_org_tos(self, gtos):
        return self.client.post(
            self.changelist_url,
            {"action": "create_org_tos", "_selected_action": [gtos.pk]},
            follow=True,
        )

    def test_create_org_tos(self):
        response = self._create_org_tos(self.published)
        self.assertContains(response, "Created ToS for 1 organisation(s)")
        self.assertTrue(self.org.tos.filter(based_on=self.published).exists())

    def test_create_org_tos_ignores_newer_draft(self):
        GlobalTermsOfService.objects.create(body="Draft")
        response = self._create_org_tos(self.published)
        self.assertContains(response, "Created ToS for 1 organisation(s)")

    def test_create_org_tos_refuses_draft(self):
        draft = GlobalTermsOfService.objects.create(body="Draft")
        response = self._create_org_tos(draft)
        self.assertContains(response, "Set required from before using it")
        self.assertFalse(self.org.tos.exists())

    def test_create_org_tos_refuses_older(self):
        GlobalTermsOfService.objects.create(body="Newer", required_from=now().date())
        response = self._create_org_tos(self.published)
        self.assertContains(response, "Only the latest version can be used")
        self.assertFalse(self.org.tos.exists())
