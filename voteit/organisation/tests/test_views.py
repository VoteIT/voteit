from django.test import Client
from django.test import TestCase
from django.test import override_settings

from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.backends import IDProxyOAuth2
from voteit.organisation.models import Organisation
from voteit.organisation.testing import DUMMY_PROVIDER
from voteit.organisation.testing import dummy_backend_enabled

ID_HOST = "https://id.example.com"


@dummy_backend_enabled()
@override_settings(
    ID_HOST=ID_HOST,
    SOCIAL_AUTH_IDPROXY_AUTHORIZATION_URL=IDProxyOAuth2.AUTHORIZATION_URL,
)
class BeginViewTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)
        cls.org.host = "testserver"
        cls.org.save()
        cls.org.providers.create(
            provider_id=DUMMY_PROVIDER,
            scope="",
            client_id="voteit",
            client_secret="s3cret",
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def post(self, backend=IDPROXY_PROVIDER, **headers):
        return self.client.post(f"/login/{backend}/", headers=headers)

    def test_login_origins(self):
        provider = self.org.get_provider(IDPROXY_PROVIDER)
        self.assertEqual({ID_HOST}, IDProxyOAuth2.get_login_origins(provider))

    def test_id_host_may_post_without_token(self):
        response = self.post(origin=ID_HOST)
        self.assertEqual(302, response.status_code)
        self.assertTrue(
            response["Location"].startswith(IDProxyOAuth2.AUTHORIZATION_URL)
        )

    def test_other_or_no_origin_is_rejected(self):
        self.assertEqual(403, self.post(origin="https://evil.example.com").status_code)
        self.assertEqual(403, self.post().status_code)

    def test_origin_only_trusted_for_its_own_backend(self):
        self.assertEqual(403, self.post(DUMMY_PROVIDER, origin=ID_HOST).status_code)

    def test_origin_not_trusted_without_provider(self):
        self.org.get_provider(IDPROXY_PROVIDER).delete()
        self.assertEqual(403, self.post(origin=ID_HOST).status_code)

    def test_origin_not_trusted_for_other_organisation(self):
        response = self.client.post(
            f"/login/{IDPROXY_PROVIDER}/",
            headers={"origin": ID_HOST},
            HTTP_HOST="elsewhere.voteit.se",
        )
        self.assertEqual(403, response.status_code)

    def test_same_origin_post_with_token(self):
        token = "a" * 32
        self.client.cookies["csrftoken"] = token
        response = self.client.post(
            f"/login/{IDPROXY_PROVIDER}/",
            {"csrfmiddlewaretoken": token},
            headers={"origin": "http://testserver"},
        )
        self.assertEqual(302, response.status_code)
