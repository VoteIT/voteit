from datetime import datetime

from django.test import RequestFactory
from django.test import TestCase


class OrganisationSerializerTests(TestCase):
    fixtures = ["meeting_test_fixture"]

    @classmethod
    def setUpTestData(cls):
        from voteit.organisation.models import Organisation

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
        self.assertEqual(data.pop("login_url"), "/begin-auth/1/")
        self.assertEqual(data.pop("scopes"), ["email"])

    def test_get_with_provider(self):
        from voteit.organisation.models import OAuth2Provider

        OAuth2Provider(organisation=self.org)
        serializer = self._cut(self.org)
        data = serializer.data
        self.assertEqual(data.pop("login_url"), f"/begin-auth/{self.org.pk}/")

    def test_patch(self):
        serializer = self._cut(self.org, {"body": "Bye!"}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.org.body, "Bye!")


class TOSSerializerTests(TestCase):
    def setUp(self):
        from voteit.organisation.models import Organisation

        self.org = Organisation.objects.create(title="Test org")
        self.tos = self.org.tos.create(
            title="Some terms", body="Very important", required=1
        )

    @property
    def _cut(self):
        from voteit.organisation.rest_api.serializers import TOSSerializer

        return TOSSerializer

    def test_get(self):
        serializer = self._cut(self.tos)
        data = serializer.data
        self.assertEqual(data.pop("pk"), self.tos.pk)
        self.assertEqual(data.pop("title"), self.tos.title)
        self.assertEqual(data.pop("body"), self.tos.body)

    def test_patch(self):
        serializer = self._cut(self.tos, {"body": "Bye!"}, partial=True)
        self.assertTrue(serializer.is_valid())
        serializer.save()
        self.assertEqual(self.tos.body, "Bye!")


class TOSCreateSerializerTests(TestCase):
    def setUp(self):
        from voteit.organisation.models import Organisation

        self.org = Organisation.objects.create(title="Test org")
        self.tos = self.org.tos.create(
            title="Some terms", body="Very important", required=1
        )
        self.user = self.org.users.create(username="orguser")

    @property
    def _cut(self):
        from voteit.organisation.rest_api.serializers import TOSCreateSerializer

        return TOSCreateSerializer

    def test_create(self):
        request = RequestFactory().request()
        # "login"
        request.user = self.user
        serializer = self._cut(
            data={"title": "Important", "organisation": self.org.pk},
            context={"request": request},
        )
        serializer.is_valid()
        # breakpoint()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        # data = serializer.data
        self.assertEqual("Important", instance.title)


class UserConsentSerializerTests(TestCase):
    def setUp(self):
        from voteit.organisation.models import Organisation
        from voteit.organisation.models import UserConsent

        self.org = Organisation.objects.create(title="Test org")
        self.tos = self.org.tos.create(
            title="Some terms", body="Very important", required=1
        )
        self.user = self.org.users.create(username="orguser")
        self.user_consent: UserConsent = self.tos.consents.create(user=self.user)

    @property
    def _cut(self):
        from voteit.organisation.rest_api.serializers import UserConsentSerializer

        return UserConsentSerializer

    def test_get(self):
        serializer = self._cut(self.user_consent)
        data = serializer.data
        self.assertEqual(data.pop("pk"), self.user_consent.pk)
        self.assertIsInstance(data.pop("created"), str)
        self.assertEqual(data.pop("revoked"), self.user_consent.revoked)
        self.assertIsNone(self.user_consent.revoked)


class UserConsentCreateSerializerTests(TestCase):
    def setUp(self):
        from voteit.organisation.models import Organisation

        self.org = Organisation.objects.create(title="Test org")
        self.tos = self.org.tos.create(
            title="Some terms", body="Very important", required=1
        )
        self.user = self.org.users.create(username="orguser")

    @property
    def _cut(self):
        from voteit.organisation.rest_api.serializers import UserConsentCreateSerializer

        return UserConsentCreateSerializer

    def test_create(self):
        request = RequestFactory().request()
        # "login"
        request.user = self.user
        serializer = self._cut(
            data={"tos": self.tos.pk},
            context={"request": request},
        )
        serializer.is_valid()
        self.assertFalse(serializer.errors)
        instance = serializer.save()
        self.assertIsInstance(instance.created, datetime)
