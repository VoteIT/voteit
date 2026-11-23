from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from voteit.organisation import IDPROXY_PROVIDER
from voteit.organisation.models import OAuth2Provider
from voteit.organisation.models import Organisation
from voteit.organisation.testing import DUMMY_PROVIDER
from voteit.organisation.testing import dummy_backend_enabled

User = get_user_model()


class OAuth2ProviderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()

    def test_organisation_is_required(self):
        with self.assertRaises(IntegrityError):
            OAuth2Provider.objects.create()

    def test_title_with_org(self):
        provider = OAuth2Provider.objects.create(organisation=self.org)
        self.assertEqual(f"{self.org.title} (idproxy)", provider.title)

    def test_get_provider(self):
        provider = OAuth2Provider.objects.create(
            organisation=self.org, provider_id=DUMMY_PROVIDER
        )
        self.assertEqual(provider, self.org.get_provider(DUMMY_PROVIDER))

    def test_get_provider_missing(self):
        with self.assertRaises(OAuth2Provider.DoesNotExist):
            self.org.get_provider(DUMMY_PROVIDER)

    def test_several_providers_per_organisation(self):
        OAuth2Provider.objects.create(organisation=self.org)
        OAuth2Provider.objects.create(organisation=self.org, provider_id=DUMMY_PROVIDER)
        self.assertEqual(
            [DUMMY_PROVIDER, IDPROXY_PROVIDER],
            sorted(self.org.providers.values_list("provider_id", flat=True)),
        )

    def test_one_row_per_backend_and_organisation(self):
        OAuth2Provider.objects.create(organisation=self.org)
        with self.assertRaises(IntegrityError):
            OAuth2Provider.objects.create(organisation=self.org)

    def test_clean_rejects_unknown_backend(self):
        provider = OAuth2Provider(organisation=self.org, provider_id="nope")
        with self.assertRaises(ValidationError) as cm:
            provider.clean()
        self.assertIn("provider_id", cm.exception.message_dict)

    def test_clean_accepts_an_enabled_backend(self):
        provider = OAuth2Provider(organisation=self.org, provider_id=DUMMY_PROVIDER)
        with dummy_backend_enabled():
            provider.clean()

    def test_backend_is_none_when_not_enabled(self):
        provider = OAuth2Provider(organisation=self.org, provider_id=DUMMY_PROVIDER)
        self.assertIsNone(provider.backend)
        with dummy_backend_enabled():
            self.assertEqual(DUMMY_PROVIDER, provider.backend.name)


class UserSocialAuthAuditlogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = Organisation.objects.create()
        cls.user = cls.org.users.create(username="kim")

    def _entries(self, social):
        from auditlog.models import LogEntry

        return LogEntry.objects.get_for_object(social)

    def test_connect_is_logged_without_extra_data(self):
        from social_django.models import UserSocialAuth

        social = UserSocialAuth.objects.create(
            user=self.user,
            provider="scoutid",
            uid="1234567",
            extra_data={"access_token": "secret"},
        )
        entry = self._entries(social).get()
        self.assertEqual(
            {
                "provider": ["None", "scoutid"],
                "uid": ["None", "1234567"],
                "user": ["None", str(self.user.pk)],
            },
            entry.changes_dict,
        )
        self.assertEqual({"o": self.org.pk}, entry.additional_data)

    def test_extra_data_changes_are_not_logged(self):
        from social_django.models import UserSocialAuth

        social = UserSocialAuth.objects.create(
            user=self.user, provider="scoutid", uid="1234567"
        )
        social.set_extra_data({"access_token": "new"})
        self.assertEqual(1, self._entries(social).count())

    def test_transfer_between_accounts_is_logged(self):
        from social_django.models import UserSocialAuth

        from voteit.organisation.pipeline import _transfer_social_auths

        other = self.org.users.create(username="kim2")
        social = UserSocialAuth.objects.create(
            user=self.user, provider="scoutid", uid="1234567"
        )
        _transfer_social_auths(self.user, other)
        latest = self._entries(social).first()
        self.assertEqual(
            {"user": [str(self.user.pk), str(other.pk)]}, latest.changes_dict
        )
