from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from voteit.organisation.admin import TermsOfServiceAdmin
from voteit.organisation.models import GlobalTermsOfService
from voteit.organisation.models import Organisation
from voteit.organisation.models import TermsOfService
from voteit.organisation.utils import accept_tos


class TermsOfServiceAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create(title="One", host="one.example.com")
        cls.other = Organisation.objects.create(title="Two", host="two.example.com")
        cls.admin = cls.org.users.create(
            username="admin", is_staff=True, is_superuser=True
        )
        cls.old = cls.org.tos.create(version=now() - timedelta(days=2))
        GlobalTermsOfService.objects.create(required_from=now().date())

    def setUp(self):
        self.client.force_login(self.admin)

    def test_changelists(self):
        for name in ("globaltermsofservice", "termsofservice", "useraccept"):
            response = self.client.get(reverse(f"admin:organisation_{name}_changelist"))
            self.assertEqual(200, response.status_code, name)

    def test_accepts_count(self):
        accept_tos(self.admin)
        accept_tos(self.other.users.create(username="elsewhere"))
        new = self.org.tos.create()
        qs = TermsOfServiceAdmin(TermsOfService, None).get_queryset(None)
        counts = {x.pk: x.accepts__count for x in qs}
        self.assertEqual(1, counts[self.old.pk])
        self.assertEqual(0, counts[new.pk])
