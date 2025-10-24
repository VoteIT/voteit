from django.contrib.auth import get_user_model
from django.test import TestCase

from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation

User = get_user_model()


class OAuth2ProviderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def test_title_no_org(self):
        provider = OAuth2Provider.objects.create()
        self.assertEqual(f"Provider {provider.pk}", provider.title)
