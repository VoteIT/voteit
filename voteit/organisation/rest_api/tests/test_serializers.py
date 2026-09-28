from django.test import TestCase
from django.test import override_settings

from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import Organisation
from voteit.organisation.testing import ALT_DUMMY_PROVIDER
from voteit.organisation.testing import DUMMY_PROVIDER
from voteit.organisation.testing import dummy_backend_enabled


@dummy_backend_enabled()
@override_settings(
    LANGUAGE_CODE="en-us",
    ID_HOST="https://idproxy",
)
class OrganisationSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.get(pk=1)

    @property
    def _cut(self):
        from voteit.organisation.rest_api.serializers import OrganisationSerializer

        return OrganisationSerializer

    def test_get(self):
        serializer = self._cut(self.org)
        data = serializer.data
        self.assertEqual(data.pop("pk"), self.org.pk)
        self.assertEqual(data.pop("title"), self.org.title)
        self.assertEqual(
            [
                {
                    "provider_id": IDPROXY_PROVIDER,
                    "title": "VoteIT ID",
                    "login_url": "https://idproxy/login-to/testserver",
                    "profile_url": "https://idproxy/",
                    "logout_url": "https://idproxy/log-out",
                    "scope": ["email"],
                }
            ],
            [dict(x) for x in data.pop("providers")],
        )
        self.assertIsNotNone(data.pop("page_title"))
        self.assertIsNotNone(data.pop("body"))
        self.assertIsInstance(data.pop("components"), list)
        self.assertEqual(data.pop("active"), True)
        self.assertEqual(data.pop("help_info"), "")
        self.assertFalse(data, "Not everything was checked")

    def test_get_without_providers(self):
        self.org.providers.all().delete()
        self.assertEqual([], self._cut(self.org).data["providers"])

    def _add(self, provider_id, **kwargs):
        return self.org.providers.create(
            provider_id=provider_id,
            scope="one two",
            client_id="cid",
            client_secret="secret",
            **kwargs,
        )

    def _titles(self):
        return [x["title"] for x in self._cut(self.org).data["providers"]]

    def test_get_several_providers(self):
        self._add(DUMMY_PROVIDER)
        data = self._cut(self.org).data
        self.assertEqual(
            [
                {
                    "provider_id": DUMMY_PROVIDER,
                    "title": "Dummy login",
                    "login_url": "/login/dummy/",
                    "profile_url": "https://dummy.example/testserver/account/",
                    "logout_url": "https://dummy.example/logout/",
                    "scope": ["one", "two"],
                },
                {
                    "provider_id": IDPROXY_PROVIDER,
                    "title": "VoteIT ID",
                    "login_url": "https://idproxy/login-to/testserver",
                    "profile_url": "https://idproxy/",
                    "logout_url": "https://idproxy/log-out",
                    "scope": ["email"],
                },
            ],
            [dict(x) for x in data["providers"]],
        )

    def test_providers_sort_by_title_case_insensitively(self):
        self._add(DUMMY_PROVIDER)
        self._add(ALT_DUMMY_PROVIDER)
        # Raw string order would put "VoteIT ID" before "alpha login".
        self.assertEqual(["alpha login", "Dummy login", "VoteIT ID"], self._titles())

    def test_primary_provider_comes_first(self):
        self._add(DUMMY_PROVIDER)
        self._add(ALT_DUMMY_PROVIDER)
        self.org.providers.filter(provider_id=IDPROXY_PROVIDER).update(primary=True)
        self.assertEqual(["VoteIT ID", "alpha login", "Dummy login"], self._titles())

    def test_several_primaries_stay_sorted_among_themselves(self):
        self._add(DUMMY_PROVIDER, primary=True)
        self._add(ALT_DUMMY_PROVIDER, primary=True)
        self.assertEqual(["alpha login", "Dummy login", "VoteIT ID"], self._titles())

    def test_hidden_providers_are_omitted(self):
        self._add(DUMMY_PROVIDER, hidden=True)
        self.assertEqual(["VoteIT ID"], self._titles())

    def test_hidden_wins_over_primary(self):
        self._add(DUMMY_PROVIDER, primary=True, hidden=True)
        self.assertEqual(["VoteIT ID"], self._titles())

    def test_get_skips_provider_without_enabled_backend(self):
        self.org.providers.create(
            provider_id="retired-backend",
            scope="email",
            client_id="cid",
            client_secret="secret",
        )
        data = self._cut(self.org).data
        self.assertEqual(
            [IDPROXY_PROVIDER], [x["provider_id"] for x in data["providers"]]
        )

    def test_patch(self):
        serializer = self._cut(self.org, {"body": "Bye!"}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.org.body, "Bye!")


# class IDOrganisationSerializerTests(TestCase):
#     fixtures = ["meeting_test_fixture"]
#
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.organisation.models import Organisation
#
#         cls.org = Organisation.objects.get(pk=1)
#
#     @property
#     def _cut(self):
#         from voteit.organisation.rest_api.serializers import IDOrganisationSerializer
#
#         return IDOrganisationSerializer
#
#     def test_get(self):
#         serializer = self._cut(self.org)
#         data = serializer.data
#         self.assertEqual(data.pop("pk"), self.org.pk)
#         self.assertEqual(data.pop("title"), self.org.title)
#
#     def test_patch(self):
#         serializer = self._cut(self.org, {"body": "Bye!"}, partial=True)
#         self.assertTrue(serializer.is_valid())
#         serializer.save()
#         self.assertEqual(self.org.body, "Bye!")
#
#
# class IDProviderSerializerTests(TestCase):
#     fixtures = ["meeting_test_fixture"]
#
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.organisation.models import OAuth2Provider
#
#         cls.provider = OAuth2Provider.objects.get(pk=1)
#
#     @property
#     def _cut(self):
#         from voteit.organisation.rest_api.serializers import IDProviderSerializer
#
#         return IDProviderSerializer
#
#     def test_get(self):
#         serializer = self._cut(self.provider)
#         data = serializer.data
#         self.assertEqual(data.pop("pk"), self.provider.pk)
#         self.assertNotIn("client_id", data)
#         self.assertNotIn("client_secret", data)
#
#
# class IDProviderUpdateSerializerTests(TestCase):
#     fixtures = ["meeting_test_fixture"]
#
#     @classmethod
#     def setUpTestData(cls):
#         from voteit.organisation.models import OAuth2Provider
#
#         cls.provider = OAuth2Provider.objects.get(pk=1)
#
#     @property
#     def _cut(self):
#         from voteit.organisation.rest_api.serializers import IDProviderUpdateSerializer
#
#         return IDProviderUpdateSerializer
#
#     def test_patch(self):
#         serializer = self._cut(self.provider, {"client_id": "hello"}, partial=True)
#         self.assertTrue(serializer.is_valid())
#         serializer.save()
#         self.assertEqual(self.provider.client_id, "hello")
#
#     def test_patch_bad_provider_id(self):
#         serializer = self._cut(self.provider, {"provider_id": "hello"}, partial=True)
#         serializer.is_valid()
#         self.assertIn("provider_id", serializer.errors)
#
#     def test_create(self):
#         serializer = self._cut(
#             self.provider,
#             {
#                 "title": "Hello world",
#                 "client_id": "hello",
#                 "client_secret": "very_secret",
#             },
#         )
#         serializer.is_valid()
#         self.assertFalse(serializer.errors)
#         instance = serializer.create(serializer.validated_data)
#         self.assertEqual("very_secret", instance.client_secret)


# class TOSSerializerTests(TestCase):
#     def setUp(self):
#         from voteit.organisation.models import Organisation
#
#         self.org = Organisation.objects.create(title="Test org")
#         self.tos = self.org.tos.create(
#             title="Some terms", body="Very important", required=1
#         )
#
#     @property
#     def _cut(self):
#         from voteit.organisation.rest_api.serializers import TOSSerializer
#
#         return TOSSerializer
#
#     def test_get(self):
#         serializer = self._cut(self.tos)
#         data = serializer.data
#         self.assertEqual(data.pop("pk"), self.tos.pk)
#         self.assertEqual(data.pop("title"), self.tos.title)
#         self.assertEqual(data.pop("body"), self.tos.body)
#
#     def test_patch(self):
#         serializer = self._cut(self.tos, {"body": "Bye!"}, partial=True)
#         self.assertTrue(serializer.is_valid())
#         serializer.save()
#         self.assertEqual(self.tos.body, "Bye!")
#
#
# class TOSCreateSerializerTests(TestCase):
#     def setUp(self):
#         from voteit.organisation.models import Organisation
#
#         self.org = Organisation.objects.create(title="Test org")
#         self.tos = self.org.tos.create(
#             title="Some terms", body="Very important", required=1
#         )
#         self.user = self.org.users.create(username="orguser")
#
#     @property
#     def _cut(self):
#         from voteit.organisation.rest_api.serializers import TOSCreateSerializer
#
#         return TOSCreateSerializer
#
#     def test_create(self):
#         request = RequestFactory().request()
#         # "login"
#         request.user = self.user
#         serializer = self._cut(
#             data={"title": "Important", "organisation": self.org.pk},
#             context={"request": request},
#         )
#         serializer.is_valid()
#         self.assertFalse(serializer.errors)
#         instance = serializer.save()
#         self.assertEqual("Important", instance.title)
#
#
# class UserConsentSerializerTests(TestCase):
#     def setUp(self):
#         from voteit.organisation.models import Organisation
#         from voteit.organisation.models import UserConsent
#
#         self.org = Organisation.objects.create(title="Test org")
#         self.tos = self.org.tos.create(
#             title="Some terms", body="Very important", required=1
#         )
#         self.user = self.org.users.create(username="orguser")
#         self.user_consent: UserConsent = self.tos.consents.create(user=self.user)
#
#     @property
#     def _cut(self):
#         from voteit.organisation.rest_api.serializers import UserConsentSerializer
#
#         return UserConsentSerializer
#
#     def test_get(self):
#         serializer = self._cut(self.user_consent)
#         data = serializer.data
#         self.assertEqual(data.pop("pk"), self.user_consent.pk)
#         self.assertIsInstance(data.pop("created"), str)
#         self.assertEqual(data.pop("revoked"), self.user_consent.revoked)
#         self.assertIsNone(self.user_consent.revoked)
#
#
# class UserConsentCreateSerializerTests(TestCase):
#     def setUp(self):
#         from voteit.organisation.models import Organisation
#
#         self.org = Organisation.objects.create(title="Test org")
#         self.tos = self.org.tos.create(
#             title="Some terms", body="Very important", required=1
#         )
#         self.user = self.org.users.create(username="orguser")
#
#     @property
#     def _cut(self):
#         from voteit.organisation.rest_api.serializers import UserConsentCreateSerializer
#
#         return UserConsentCreateSerializer
#
#     def test_create(self):
#         request = RequestFactory().request()
#         # "login"
#         request.user = self.user
#         serializer = self._cut(
#             data={"tos": self.tos.pk},
#             context={"request": request},
#         )
#         serializer.is_valid()
#         self.assertFalse(serializer.errors)
#         instance = serializer.save()
#         self.assertIsInstance(instance.created, datetime)
