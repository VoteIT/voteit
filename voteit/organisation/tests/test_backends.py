from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import TestCase
from social_django.storage import BaseDjangoStorage
from social_django.strategy import DjangoStrategy

from voteit.organisation.models import Organisation

User = get_user_model()


# @override_settings(ID_HOST_BACKEND="https://localhost")
class IDProxyBackendTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.org.provider.scope = "hello world identity"
        cls.org.provider.save()
        cls.org.host = "testserver"
        # cls.org.provider = cls.provider
        cls.org.save()
        cls.user = User.objects.create(username="user")

    @property
    def _cut(self):
        from voteit.organisation.backends import IDProxyOAuth2

        return IDProxyOAuth2

    def test_get_scopes(self):
        request = RequestFactory().get("/")
        request.session = self.client.session
        strategy = DjangoStrategy(BaseDjangoStorage, request=request)
        backend = self._cut(strategy=strategy)
        self.assertEqual(["hello", "identity", "world"], backend.get_scope())
